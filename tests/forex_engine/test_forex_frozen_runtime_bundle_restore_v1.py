from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from automation.forex_engine import forex_frozen_runtime_bundle_restore_v1 as restore_module
from automation.forex_engine.forex_frozen_runtime_bundle_restore_v1 import restore_bundle


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/forex_delivery/restore_forex_frozen_runtime_bundle_v1.py"


def test_restore_bundle_copies_only_exact_hash_matches(tmp_path: Path) -> None:
    source = tmp_path / "backup"
    target = tmp_path / "target"
    source.mkdir()
    expected = {
        "AIOS_FOREX_PHASE1_RECEIPT.json": "f60c0a47613a06b34b0df267113d5d08872fef3a5415e362a6252a838ba3f076",
    }
    (source / "AIOS_FOREX_PHASE1_RECEIPT.json").write_bytes(b"authoritative\n")

    result = restore_bundle([source], target, expected_hashes=expected, copy=True)

    assert result["status"] == "RESTORED_VERIFIED_BUNDLE"
    assert result["counts"] == {"expected": 1, "matched": 1, "copied": 1, "missing": 0}
    assert (target / "AIOS_FOREX_PHASE1_RECEIPT.json").read_bytes() == b"authoritative\n"


def test_restore_bundle_does_not_copy_wrong_hash(tmp_path: Path) -> None:
    source = tmp_path / "backup"
    target = tmp_path / "target"
    source.mkdir()
    expected = {
        "AIOS_FOREX_PHASE1_RECEIPT.json": "20d099f8ee0e7318fbd18b7b935ab2e2f40ed50a6fb83051790f2be8acf486a5",
    }
    (source / "AIOS_FOREX_PHASE1_RECEIPT.json").write_text("wrong\n", encoding="utf-8")

    result = restore_bundle([source], target, expected_hashes=expected, copy=True)

    assert result["status"] == "BLOCKED_SOURCE_FILES_NOT_FOUND"
    assert result["counts"] == {"expected": 1, "matched": 0, "copied": 0, "missing": 1}
    assert not (target / "AIOS_FOREX_PHASE1_RECEIPT.json").exists()


def test_dry_run_finds_match_without_copying(tmp_path: Path) -> None:
    source = tmp_path / "backup"
    target = tmp_path / "target"
    source.mkdir()
    (source / "AIOS_FOREX_PHASE1_RECEIPT.json").write_bytes(b"authoritative\n")

    receipt = restore_bundle(
        [source], target,
        expected_hashes={"AIOS_FOREX_PHASE1_RECEIPT.json": "f60c0a47613a06b34b0df267113d5d08872fef3a5415e362a6252a838ba3f076"},
    )

    assert receipt["status"] == "DRY_RUN_MATCHES_FOUND_COPY_NOT_REQUESTED"
    assert receipt["counts"]["matched"] == 1
    assert not (target / "AIOS_FOREX_PHASE1_RECEIPT.json").exists()


def test_already_verified_target_needs_no_archive_or_copy(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    frozen_file = target / "AIOS_FOREX_PHASE1_RECEIPT.json"
    frozen_file.write_bytes(b"authoritative\n")
    original_mtime = frozen_file.stat().st_mtime_ns

    result = restore_bundle(
        [], target,
        expected_hashes={"AIOS_FOREX_PHASE1_RECEIPT.json": "f60c0a47613a06b34b0df267113d5d08872fef3a5415e362a6252a838ba3f076"},
        copy=True,
    )

    assert result["status"] == "ALREADY_VERIFIED_BUNDLE"
    assert result["counts"]["copied"] == 0
    assert frozen_file.read_bytes() == b"authoritative\n"
    assert frozen_file.stat().st_mtime_ns == original_mtime


def test_mismatched_target_blocks_without_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "backup"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    name = "AIOS_FOREX_PHASE1_RECEIPT.json"
    (source / name).write_bytes(b"authoritative\n")
    (target / name).write_bytes(b"different\n")

    result = restore_bundle(
        [source], target,
        expected_hashes={name: "f60c0a47613a06b34b0df267113d5d08872fef3a5415e362a6252a838ba3f076"},
        copy=True,
    )

    assert result["status"] == "BLOCKED_TARGET_HASH_MISMATCH"
    assert result["counts"]["copied"] == 0
    assert result["next_safe_action"] == "inspect_mismatched_target_without_overwrite"
    assert (target / name).read_bytes() == b"different\n"


def test_atomic_publish_failure_reports_block_without_partial_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "backup"
    target = tmp_path / "target"
    source.mkdir()
    name = "AIOS_FOREX_PHASE1_RECEIPT.json"
    (source / name).write_bytes(b"authoritative\n")

    def no_hard_links(*args: object) -> None:
        raise OSError("hard links unavailable")

    monkeypatch.setattr(restore_module.os, "link", no_hard_links)
    result = restore_bundle(
        [source], target,
        expected_hashes={name: "f60c0a47613a06b34b0df267113d5d08872fef3a5415e362a6252a838ba3f076"},
        copy=True,
    )

    assert result["status"] == "BLOCKED_ATOMIC_PUBLISH_UNAVAILABLE"
    assert result["counts"]["copied"] == 0
    assert not (target / name).exists()


def test_archive_search_accepts_uppercase_digest(tmp_path: Path) -> None:
    source = tmp_path / "backup"
    target = tmp_path / "target"
    source.mkdir()
    name = "AIOS_FOREX_PHASE1_RECEIPT.json"
    (source / name).write_bytes(b"authoritative\n")

    result = restore_bundle(
        [source], target,
        expected_hashes={name: "F60C0A47613A06B34B0DF267113D5D08872FEF3A5415E362A6252A838BA3F076"},
    )

    assert result["status"] == "DRY_RUN_MATCHES_FOUND_COPY_NOT_REQUESTED"
    assert result["counts"]["matched"] == 1


def test_changed_source_never_leaves_partial_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "backup"
    target = tmp_path / "target"
    source.mkdir()
    name = "AIOS_FOREX_PHASE1_RECEIPT.json"
    source_file = source / name
    source_file.write_bytes(b"authoritative\n")
    find_matches = restore_module._find_matches

    def change_after_discovery(roots: list[Path], hashes: dict[str, str]) -> dict[str, dict[str, object]]:
        matches = find_matches(roots, hashes)
        source_file.write_bytes(b"changed\n")
        return matches

    monkeypatch.setattr(restore_module, "_find_matches", change_after_discovery)

    with pytest.raises(RuntimeError, match="source hash mismatch"):
        restore_bundle(
            [source], target,
            expected_hashes={name: "f60c0a47613a06b34b0df267113d5d08872fef3a5415e362a6252a838ba3f076"},
            copy=True,
        )

    assert not (target / name).exists()


def test_rejects_traversal_in_expected_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="plain filename"):
        restore_bundle(
            [tmp_path], tmp_path / "target",
            expected_hashes={"../escaped.json": "f60c0a47613a06b34b0df267113d5d08872fef3a5415e362a6252a838ba3f076"},
            copy=True,
        )
    assert not (tmp_path / "escaped.json").exists()


def test_cli_rejects_hash_override_even_if_well_formed(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--search-root", str(tmp_path),
            "--target-root", str(tmp_path / "target"),
            "--state-path", str(tmp_path / "state.json"),
            "--expected", "AIOS_FOREX_PHASE1_RECEIPT.json=f60c0a47613a06b34b0df267113d5d08872fef3a5415e362a6252a838ba3f076",
            "--copy",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert not (tmp_path / "state.json").exists()


def test_rejects_invalid_expected_hash(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="64 hexadecimal"):
        restore_bundle([tmp_path], expected_hashes={"AIOS_FOREX_PHASE1_RECEIPT.json": "z" * 64})


def test_cli_can_check_empty_target_without_search_root(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--target-root", str(tmp_path / "target"),
            "--state-path", str(tmp_path / "state.json"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "BLOCKED_SOURCE_FILES_NOT_FOUND"


def test_cli_refuses_state_path_inside_target_bundle(tmp_path: Path) -> None:
    source = tmp_path / "backup"
    target = tmp_path / "target"
    source.mkdir()
    name = "AIOS_FOREX_PHASE1_RECEIPT.json"
    (source / name).write_bytes(b"authoritative\n")

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--search-root", str(source),
            "--target-root", str(target),
            "--state-path", str(target / name),
            "--copy",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert not (target / name).exists()


def test_cli_does_not_follow_preexisting_state_temp_symlink(tmp_path: Path) -> None:
    source = tmp_path / "backup"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    name = "AIOS_FOREX_PHASE1_RECEIPT.json"
    (source / name).write_bytes(b"authoritative\n")
    frozen_file = target / name
    frozen_file.write_bytes(b"authoritative\n")
    try:
        (tmp_path / ".state.json.tmp").symlink_to(frozen_file)
    except OSError:
        pytest.skip("file symlinks unavailable")

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--search-root", str(source),
            "--target-root", str(target),
            "--state-path", str(tmp_path / "state.json"),
            "--copy",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert (tmp_path / "state.json").is_file()
    assert frozen_file.read_bytes() == b"authoritative\n"


def test_target_symlink_blocks_copy_even_when_hash_matches(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"authoritative\n")
    name = "AIOS_FOREX_PHASE1_RECEIPT.json"
    try:
        (target / name).symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks unavailable")

    result = restore_bundle(
        [], target,
        expected_hashes={name: "f60c0a47613a06b34b0df267113d5d08872fef3a5415e362a6252a838ba3f076"},
        copy=True,
    )

    assert result["status"] == "BLOCKED_TARGET_HASH_MISMATCH"
    assert outside.read_bytes() == b"authoritative\n"


def test_cli_custom_target_cannot_write_state_inside_default_frozen_root(tmp_path: Path) -> None:
    default_root = tmp_path / ".aios/runtime/forex_frozen_21_series_edge_research_v1"
    default_root.mkdir(parents=True)
    frozen_file = default_root / "audit.json"
    frozen_file.write_bytes(b"existing evidence\n")

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--target-root", str(tmp_path / "alternate"),
            "--state-path", str(frozen_file),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert frozen_file.read_bytes() == b"existing evidence\n"
