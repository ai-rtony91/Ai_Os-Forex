"""Find and restore frozen Phase 1 runtime inputs from local archives.

The restore is hash-gated. Files are copied only when their SHA-256 exactly
matches the frozen contract. The tool never reconstructs runtime evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from automation.forex_engine.forex_frozen_21_series_phase1_postmortem_v1 import INPUT_HASHES
from automation.forex_engine.forex_frozen_runtime_restore_verifier_v1 import (
    DEFAULT_INPUT_ROOT,
    atomic_json,
    output_overlaps_frozen_inputs,
    validate_expected_hashes,
)


SCHEMA = "AIOS_FOREX_FROZEN_RUNTIME_BUNDLE_RESTORE.v1"
DEFAULT_STATE_PATH = Path("Reports/forex_delivery/AIOS_FOREX_FROZEN_RUNTIME_BUNDLE_RESTORE_V1_STATE.json")


class AtomicPublishUnavailable(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_files(root: Path, name: str) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root] if root.name == name else []
    return [path for path in root.rglob(name) if path.is_file()]


def _linked_target_root(root: Path) -> bool:
    absolute = root.absolute()
    try:
        if absolute.resolve(strict=False) != absolute:
            return True
    except (OSError, RuntimeError):
        return True
    return any(
        part.is_symlink() or getattr(part, "is_junction", lambda: False)()
        for part in (absolute, *absolute.parents)
    )


def _copy_verified_new_file(source: Path, destination: Path, expected_sha256: str) -> None:
    temporary: Path | None = None
    digest = hashlib.sha256()
    try:
        with source.open("rb") as stream, tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest().lower() != expected_sha256.lower():
            raise RuntimeError(f"source hash mismatch during copy: {source.name}")
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise RuntimeError(f"destination appeared during copy: {destination.name}") from exc
        except (OSError, NotImplementedError) as exc:
            raise AtomicPublishUnavailable(str(exc)) from exc
        if sha256_file(destination).lower() != expected_sha256.lower():
            raise RuntimeError(f"destination hash mismatch after copy: {destination.name}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _find_matches(search_roots: Sequence[Path], expected_hashes: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    matches: dict[str, dict[str, Any]] = {}
    for name, expected_sha256 in sorted(expected_hashes.items()):
        rejected: list[dict[str, str]] = []
        for root in search_roots:
            for candidate in _candidate_files(Path(root), name):
                actual_sha256 = sha256_file(candidate)
                if actual_sha256.lower() == expected_sha256.lower():
                    matches[name] = {
                        "source_path": candidate.as_posix(),
                        "sha256": actual_sha256,
                        "bytes": candidate.stat().st_size,
                    }
                    break
                rejected.append({"path": candidate.as_posix(), "actual_sha256": actual_sha256})
            if name in matches:
                break
        if name not in matches:
            matches[name] = {"missing": True, "expected_sha256": expected_sha256, "rejected_candidates": rejected[:10]}
    return matches


def restore_bundle(
    search_roots: Sequence[Path],
    target_root: Path = DEFAULT_INPUT_ROOT,
    *,
    expected_hashes: Mapping[str, str] = INPUT_HASHES,
    copy: bool = False,
) -> dict[str, Any]:
    validate_expected_hashes(expected_hashes)
    target_root = Path(target_root)
    search_roots = [Path(root) for root in search_roots]
    linked_root = _linked_target_root(target_root)
    matches: dict[str, dict[str, Any]] = {}
    target_mismatched: list[str] = []
    needed: dict[str, str] = {}
    if not linked_root:
        for name, expected_sha256 in sorted(expected_hashes.items()):
            destination = target_root / name
            if destination.is_symlink():
                target_mismatched.append(name)
                matches[name] = {"target_path": destination.as_posix(), "blocked_symlink": True}
            elif destination.exists():
                if not destination.is_file():
                    target_mismatched.append(name)
                    matches[name] = {"target_path": destination.as_posix(), "blocked_non_file": True}
                else:
                    actual_sha256 = sha256_file(destination)
                    if actual_sha256.lower() != expected_sha256.lower():
                        target_mismatched.append(name)
                        matches[name] = {"target_path": destination.as_posix(), "actual_sha256": actual_sha256, "expected_sha256": expected_sha256}
                    else:
                        matches[name] = {"target_path": destination.as_posix(), "sha256": actual_sha256, "bytes": destination.stat().st_size, "already_present": True}
            else:
                needed[name] = expected_sha256

        matches.update(_find_matches(search_roots, needed))
    missing = [name for name, match in matches.items() if match.get("missing")]
    copied: list[str] = []
    publication_error: str | None = None

    if copy and not linked_root and not missing and not target_mismatched:
        if _linked_target_root(target_root):
            linked_root = True
        else:
            target_root.mkdir(parents=True, exist_ok=True)
            for name in needed:
                if _linked_target_root(target_root):
                    linked_root = True
                    break
                match = matches[name]
                destination = target_root / name
                try:
                    _copy_verified_new_file(Path(match["source_path"]), destination, expected_hashes[name])
                except AtomicPublishUnavailable as exc:
                    publication_error = str(exc)
                    break
                copied.append(name)

    if linked_root:
        status = "BLOCKED_TARGET_ROOT_LINK"
    elif target_mismatched:
        status = "BLOCKED_TARGET_HASH_MISMATCH"
    elif missing:
        status = "BLOCKED_SOURCE_FILES_NOT_FOUND"
    elif publication_error is not None:
        status = "BLOCKED_ATOMIC_PUBLISH_UNAVAILABLE"
    elif not needed:
        status = "ALREADY_VERIFIED_BUNDLE"
    elif copy:
        status = "RESTORED_VERIFIED_BUNDLE"
    else:
        status = "DRY_RUN_MATCHES_FOUND_COPY_NOT_REQUESTED"

    return {
        "schema": SCHEMA,
        "status": status,
        "search_roots": [root.as_posix() for root in search_roots],
        "target_root": target_root.as_posix(),
        "copy_requested": copy,
        "counts": {
            "expected": len(expected_hashes),
            "matched": 0 if linked_root else len(expected_hashes) - len(missing) - len(target_mismatched),
            "copied": len(copied),
            "missing": len(missing),
        },
        "missing": missing,
        "target_mismatched": target_mismatched,
        "blocked_target_root_link": linked_root,
        "publication_error": publication_error,
        "files": matches,
        "copied": copied,
        "next_safe_action": (
            "select_target_root_without_links" if linked_root else
            "run_restore_verifier" if status in {"RESTORED_VERIFIED_BUNDLE", "ALREADY_VERIFIED_BUNDLE"} else
            "inspect_mismatched_target_without_overwrite" if target_mismatched else
            "use_local_filesystem_supporting_atomic_publish" if publication_error is not None else
            "locate_authoritative_archive_or_rerun_with_copy"
        ),
        "safety": {
            "requires_exact_hash_match": True,
            "reconstructs_evidence": False,
            "uses_broker": False,
            "uses_credentials": False,
            "uses_network": False,
            "places_orders": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--search-root", type=Path, action="append", default=[])
    parser.add_argument("--target-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--copy", action="store_true")
    args = parser.parse_args(argv)

    if output_overlaps_frozen_inputs(args.state_path, args.target_root):
        parser.error("state path must be outside frozen input roots")
    if args.state_path.resolve().name.casefold() in {name.casefold() for name in INPUT_HASHES}:
        parser.error("state path must not alias a frozen source file")
    receipt = restore_bundle(args.search_root, args.target_root, copy=args.copy)
    atomic_json(args.state_path, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] in {"RESTORED_VERIFIED_BUNDLE", "ALREADY_VERIFIED_BUNDLE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
