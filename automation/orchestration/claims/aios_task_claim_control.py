"""Collision-safe, on-demand task claim control for AIOS orchestration.

This module owns claim metadata only.  It does not start workers, services,
containers, schedulers, deployments, or cleanup commands.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import tempfile
import uuid
import shlex
import sys
import threading
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Mapping, Sequence


SCHEMA_VERSION = "AIOS_ACTIVE_TASK_CLAIM.v1"
ACTIVE_STATES = frozenset({"CLAIMING", "ACTIVE", "VERIFYING", "INTEGRATING", "RELEASING", "BLOCKED"})
COLLISION_STATES = frozenset({"CLAIMING", "ACTIVE", "VERIFYING", "INTEGRATING", "RELEASING", "BLOCKED"})
TRANSITIONS = {
    "CLAIMING": {"ACTIVE", "BLOCKED"},
    "ACTIVE": {"VERIFYING", "BLOCKED"},
    "VERIFYING": {"ACTIVE", "INTEGRATING", "BLOCKED"},
    "INTEGRATING": {"ACTIVE", "RELEASING", "BLOCKED"},
    "RELEASING": {"BLOCKED", "COMPLETE_RECEIPT"},
}
REQUIRED_FIELDS = (
    "schema_version", "task_id", "packet_id", "repository", "supervisor", "worker",
    "worktree", "branch", "base_branch", "base_sha", "claimed_paths", "ports",
    "processes_or_services", "containers", "cache_dirs", "temp_dirs", "log_dirs",
    "env_files", "databases_or_schemas", "deployment_targets", "pull_request", "state",
    "acquired_at", "heartbeat_at", "expires_at", "cleanup_policy", "receipt_path",
)
RESOURCE_FIELDS = {
    "ports": "port", "processes_or_services": "process_or_service", "containers": "container",
    "databases_or_schemas": "database_or_schema", "deployment_targets": "deployment_target",
    "pull_request": "pull_request",
}
PATH_FIELDS = {
    "claimed_paths": "claimed_path", "cache_dirs": "cache_dir", "temp_dirs": "temp_dir",
    "log_dirs": "log_dir", "env_files": "env_file",
}


class ClaimError(RuntimeError):
    """Fail-closed task claim error."""


class ClaimCollision(ClaimError):
    """A task claim overlaps an active owner."""


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ClaimError("timestamps must include a timezone")
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise ClaimError("invalid claim timestamp") from exc


def _norm_name(value: Any) -> str:
    text = str(value).strip().replace("\\", "/").casefold()
    if not text or any(part == ".." for part in PurePosixPath(text).parts):
        raise ClaimError(f"invalid runtime resource name: {value!r}")
    return re.sub(r"/+", "/", text)


def _norm_branch(value: Any) -> str:
    branch = _norm_name(value)
    for prefix in ("refs/heads/", "refs/remotes/origin/", "origin/"):
        if branch.startswith(prefix):
            branch = branch[len(prefix):]
            break
    if branch.startswith("-") or ".." in branch or branch.endswith("/"):
        raise ClaimError(f"invalid branch: {value!r}")
    return branch


def _norm_port(value: Any) -> int:
    if isinstance(value, bool):
        raise ClaimError("invalid Boolean port")
    if not isinstance(value, (int, float, str)):
        raise ClaimError(f"invalid port: {value!r}")
    try:
        port = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ClaimError(f"invalid port: {value!r}") from exc
    # Integral JSON numbers and integer strings retain their existing meaning;
    # a fractional resource must never alias the holder's integer port.
    if isinstance(value, float) and value != port:
        raise ClaimError(f"invalid fractional port: {value!r}")
    if not 1 <= port <= 65535:
        raise ClaimError(f"invalid port: {value!r}")
    return port


def _norm_path(value: Any, worktree: Path) -> str:
    raw = str(value).strip().replace("\\", "/")
    if not raw or any(part == ".." for part in PurePosixPath(raw).parts):
        raise ClaimError(f"path traversal rejected: {value!r}")
    root = worktree.resolve(strict=False)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ClaimError(f"path escapes worktree: {value!r}") from exc
    return resolved.as_posix().casefold()


def _overlap(left: str, right: str) -> bool:
    left_path, right_path = PurePosixPath(left), PurePosixPath(right)
    return left_path == right_path or left_path in right_path.parents or right_path in left_path.parents


def normalize_claim(claim: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(claim, Mapping):
        raise ClaimError("claim must be an object")
    missing = [field for field in REQUIRED_FIELDS if field not in claim]
    if missing:
        raise ClaimError("missing claim fields: " + ", ".join(missing))
    result = dict(claim)
    text_fields = set(REQUIRED_FIELDS) - set(PATH_FIELDS) - set(RESOURCE_FIELDS)
    for field in text_fields:
        if not isinstance(result[field], str) or not result[field].strip():
            raise ClaimError(f"invalid claim identity field: {field}")
    if not isinstance(result["pull_request"], str):
        raise ClaimError("invalid claim identity field: pull_request")
    for field in set(PATH_FIELDS) | (set(RESOURCE_FIELDS) - {"pull_request"}):
        if not isinstance(result[field], list):
            raise ClaimError(f"invalid claim resource list: {field}")
        if field != "ports" and any(not isinstance(item, str) or not item.strip() for item in result[field]):
            raise ClaimError(f"invalid claim resource identity: {field}")
    if "attempt_id" in result and (not isinstance(result["attempt_id"], str) or not result["attempt_id"].strip()):
        raise ClaimError("invalid claim attempt_id")
    if "attempt" in result and (type(result["attempt"]) is not int or result["attempt"] < 0):
        raise ClaimError("invalid claim attempt")
    if result["schema_version"] != SCHEMA_VERSION:
        raise ClaimError("unsupported claim schema")
    if result["state"] not in ACTIVE_STATES:
        raise ClaimError("unsupported active claim state")
    worktree = Path(str(result["worktree"])).resolve(strict=False)
    if not worktree.is_dir():
        raise ClaimError("worktree does not exist")
    result["worktree"] = worktree.as_posix().casefold()
    # Receipts may use an existing central namespace outside a task worktree.
    # Bind its exact canonical destination; this comparison grants no new path.
    receipt = Path(result["receipt_path"])
    result["receipt_path"] = (receipt if receipt.is_absolute() else worktree / receipt).resolve(strict=False).as_posix().casefold()
    result["branch"] = _norm_branch(result["branch"])
    result["base_branch"] = _norm_branch(result["base_branch"])
    for field in PATH_FIELDS:
        result[field] = sorted({_norm_path(item, worktree) for item in result[field]})
    result["ports"] = sorted({_norm_port(item) for item in result["ports"]})
    for field in ("processes_or_services", "containers", "databases_or_schemas", "deployment_targets"):
        result[field] = sorted({_norm_name(item) for item in result[field]})
    result["pull_request"] = _norm_name(result["pull_request"]) if result["pull_request"] else ""
    for field in ("acquired_at", "heartbeat_at", "expires_at"):
        result[field] = _utc(result[field]).isoformat()
    if _utc(str(result["expires_at"])) <= _utc(str(result["acquired_at"])):
        raise ClaimError("claim expiry must follow acquisition")
    _claim_contract(result)
    if "release_intent" in result:
        _validate_release_intent(result)
    return result


def _claim_contract(claim: Mapping[str, Any]) -> str:
    # acquired_at anchors the existing attempt; state transitions do not change
    # its owner, lease, scope, resources, or explicit request metadata.
    contract = {key: value for key, value in claim.items() if key not in {"state", "released_at", "release_intent"}}
    try:
        encoded = json.dumps(contract, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClaimError("invalid claim identity metadata") from exc
    return hashlib.sha256(encoded).hexdigest()


def _select_claim(board: Mapping[str, Any], task_id: str, expected_claim: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    matches = [item for item in board["claims"] if item["task_id"] == task_id]
    if len(matches) > 1:
        raise ClaimError("duplicate active task identity")
    selected = matches[0] if matches else None
    if selected is not None and expected_claim is not None:
        expected = normalize_claim(expected_claim)
        if expected["task_id"] != task_id or _claim_contract(normalize_claim(selected)) != _claim_contract(expected):
            raise ClaimError("active claim identity does not match the expected attempt")
    return selected


def collisions(candidate: Mapping[str, Any], active: Sequence[Mapping[str, Any]], *, now: datetime | None = None) -> list[str]:
    current = now or datetime.now(timezone.utc)
    candidate = normalize_claim(candidate)
    found: list[str] = []
    for raw in active:
        owner = normalize_claim(raw)
        if _utc(owner["expires_at"]) <= current:
            found.append(f"stale_claim:{owner['task_id']}")
            continue
        if owner["task_id"] == candidate["task_id"]:
            if _claim_contract(owner) != _claim_contract(candidate):
                found.append(f"same_task_identity:{owner['task_id']}")
            continue
        if owner["state"] not in COLLISION_STATES:
            continue
        if owner["worktree"] == candidate["worktree"]:
            found.append(f"worktree_path:{owner['task_id']}")
        if owner["branch"] == candidate["branch"]:
            found.append(f"branch:{owner['task_id']}")
        for field, label in PATH_FIELDS.items():
            if any(_overlap(a, b) for a in owner[field] for b in candidate[field]):
                found.append(f"{label}:{owner['task_id']}")
        for field, label in RESOURCE_FIELDS.items():
            left = {owner[field]} if field == "pull_request" and owner[field] else set(owner[field]) if field != "pull_request" else set()
            right = {candidate[field]} if field == "pull_request" and candidate[field] else set(candidate[field]) if field != "pull_request" else set()
            if left & right:
                found.append(f"{label}:{owner['task_id']}")
        if candidate["state"] == "INTEGRATING" and owner["state"] == "INTEGRATING" and owner["repository"].casefold() == candidate["repository"].casefold():
            found.append(f"repository_integration:{owner['task_id']}")
    return sorted(set(found))


LOCK_SCHEMA = "AIOS_TASK_CLAIM_BOARD_LOCK.v2"
LEGACY_LOCK_SCHEMA = "AIOS_TASK_CLAIM_BOARD_LOCK.v1"
RELEASE_SCHEMA = "AIOS_TASK_CLAIM_RELEASE.v1"
LOCK_BYTE = 65536  # separate from readable bounded ownership metadata
_PROCESS_LOCK_GUARD = threading.Lock()
_PROCESS_LOCKS: set[str] = set()


def _reset_process_locks() -> None:
    # A child opens its own descriptors when acquiring a new lock. It must
    # not inherit the parent's Python guard mutex or local ownership table.
    global _PROCESS_LOCK_GUARD, _PROCESS_LOCKS
    _PROCESS_LOCK_GUARD = threading.Lock()
    _PROCESS_LOCKS = set()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_process_locks)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _region_lock(descriptor: int, *, unlock: bool = False) -> None:
    os.lseek(descriptor, LOCK_BYTE, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.lockf(descriptor, fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB, 1, LOCK_BYTE)


def _claim_file_lock(descriptor: int, *, unlock: bool = False) -> None:
    if os.name == "nt":
        _region_lock(descriptor, unlock=unlock)
    else:
        import fcntl
        # Unlike process-owned lockf, flock survives metadata reads through
        # other descriptors. Only versioned claim locks use this protocol;
        # the master controller's separate lease retains _region_lock.
        fcntl.flock(descriptor, fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB)


def _write_lock_record(descriptor: int, record: Mapping[str, Any]) -> None:
    payload = _json_bytes(record)
    if len(payload) >= LOCK_BYTE:
        raise ClaimError("claim lock ownership record is too large")
    os.lseek(descriptor, 0, os.SEEK_SET)
    offset = 0
    while offset < len(payload):
        count = os.write(descriptor, payload[offset:])
        if count <= 0:
            raise OSError("short claim lock ownership write")
        offset += count
    os.ftruncate(descriptor, len(payload))
    os.fsync(descriptor)


@contextmanager
def _exclusive_lock(board_path: Path) -> Iterator[None]:
    # lockf is process-owned: another thread or nested descriptor can acquire
    # it, and closing that descriptor can release the original owner's lock.
    # Refuse local contenders before opening any descriptor for this path.
    identity = os.path.normcase(str(board_path.with_suffix(board_path.suffix + ".lock").resolve()))
    owner_pid = os.getpid()
    with _PROCESS_LOCK_GUARD:
        if identity in _PROCESS_LOCKS:
            raise ClaimError("claim board is locked by an in-process owner")
        _PROCESS_LOCKS.add(identity)
    try:
        with _exclusive_file_lock(board_path):
            yield
    finally:
        if os.getpid() == owner_pid:
            with _PROCESS_LOCK_GUARD:
                _PROCESS_LOCKS.remove(identity)


@contextmanager
def _exclusive_file_lock(board_path: Path) -> Iterator[None]:
    owner_pid = os.getpid()
    lock = board_path.with_suffix(board_path.suffix + ".lock")
    board_path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0), 0o600)
        created = True
    except FileExistsError:
        descriptor = os.open(lock, os.O_RDWR | getattr(os, "O_BINARY", 0))
    acquired = False
    legacy_acquired = False
    metadata_owned = False
    body_error = None
    try:
        try:
            _claim_file_lock(descriptor)
            acquired = True
        except OSError as exc:
            raise ClaimError("claim board is locked by an OS-held owner") from exc
        board_identity = board_path.resolve(strict=False).as_posix().casefold()
        if not created:
            if os.fstat(descriptor).st_size >= LOCK_BYTE:
                raise ClaimError("oversized claim lock metadata; preserve for owner review")
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                previous_bytes = os.read(descriptor, LOCK_BYTE)
                previous = json.loads(previous_bytes)
            except (ValueError, UnicodeError) as exc:
                raise ClaimError("unknown legacy claim lock; preserve for owner review") from exc
            required = {"schema", "board_path", "owner_pid", "owner_token", "acquired_at", "state"}
            if (not isinstance(previous, dict) or set(previous) != required
                    or previous["schema"] not in (LOCK_SCHEMA, LEGACY_LOCK_SCHEMA) or previous["board_path"] != board_identity
                    or type(previous["owner_pid"]) is not int or previous["owner_pid"] <= 0
                    or not isinstance(previous["owner_token"], str)
                    or re.fullmatch(r"[0-9a-f]{32}", previous["owner_token"]) is None
                    or not isinstance(previous["state"], str)
                    or previous["state"] not in {"HELD", "RELEASED"}):
                raise ClaimError("unbound claim lock ownership; preserve for owner review")
            _utc(previous["acquired_at"])
            if previous["schema"] == LEGACY_LOCK_SCHEMA:
                if os.name != "nt":
                    try:
                        # A legacy lockf owner may still be acquiring while
                        # its metadata says RELEASED. Hold both protocols
                        # until v2 is saved; old readers then refuse v2.
                        _region_lock(descriptor)
                        legacy_acquired = True
                    except OSError as error:
                        raise ClaimError("legacy claim lock is held; preserve for owner review") from error
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    if os.read(descriptor, LOCK_BYTE) != previous_bytes:
                        raise ClaimError("legacy claim lock metadata changed; preserve for owner review")
                if previous["state"] != "RELEASED":
                    raise ClaimError("legacy HELD claim lock; preserve for owner review")
            # The matching OS protocol proves no holder remains. Neither PID
            # nor elapsed time is used as inactivity proof.
        record = {"schema": LOCK_SCHEMA, "board_path": board_identity,
                  "owner_pid": os.getpid(), "owner_token": uuid.uuid4().hex,
                  "acquired_at": datetime.now(timezone.utc).isoformat(), "state": "HELD"}
        _write_lock_record(descriptor, record)
        if legacy_acquired:
            _region_lock(descriptor, unlock=True)
            legacy_acquired = False
        metadata_owned = True
        try:
            yield
        except BaseException as error:
            body_error = error
            raise
        finally:
            if metadata_owned and os.getpid() == owner_pid:
                try:
                    _write_lock_record(descriptor, {**record, "state": "RELEASED"})
                except OSError as error:
                    if body_error is not None:
                        body_error.add_note("Claim lock release metadata also failed: " + type(error).__name__)
                    else:
                        raise ClaimError("claim lock release metadata could not be saved") from error
    finally:
        try:
            if acquired and os.getpid() == owner_pid:
                _claim_file_lock(descriptor, unlock=True)
        finally:
            os.close(descriptor)


def _cleanup_plan(claim: Mapping[str, Any], requested: Mapping[str, Sequence[Any]]) -> list[dict[str, Any]]:
    if not isinstance(requested, Mapping):
        raise ClaimError("cleanup resources must be an object")
    plan = []
    for field, values in requested.items():
        if field not in PATH_FIELDS and field not in RESOURCE_FIELDS:
            raise ClaimError(f"unknown cleanup resource: {field}")
        if not isinstance(values, (list, tuple)):
            raise ClaimError("cleanup resource values must be a sequence")
        owned = {claim[field]} if field == "pull_request" and claim[field] else set() if field == "pull_request" else set(claim[field])
        normalized = []
        for value in values:
            if field == "ports":
                item = _norm_port(value)
            else:
                if not isinstance(value, str) or not value.strip():
                    raise ClaimError("invalid cleanup resource identity")
                item = _norm_path(value, Path(claim["worktree"])) if field in PATH_FIELDS else _norm_name(value)
            if item not in owned:
                raise ClaimError("cleanup requested for resource not owned by task")
            if item not in normalized:
                normalized.append(item)
        plan.extend({"field": field, "value": item} for item in sorted(normalized))
    return sorted(plan, key=lambda item: (item["field"], str(item["value"])))


def _validate_release_intent(claim: Mapping[str, Any]) -> dict[str, Any]:
    intent = claim.get("release_intent")
    required = {"schema", "claim_sha256", "started_at", "receipt_path", "cleanup_mode", "resources"}
    if (claim.get("state") != "RELEASING" or not isinstance(intent, dict) or set(intent) != required
            or intent["schema"] != RELEASE_SCHEMA or intent["claim_sha256"] != _claim_contract(claim)
            or intent["receipt_path"] != claim["receipt_path"]
            or not isinstance(intent["cleanup_mode"], str)
            or intent["cleanup_mode"] not in {"once", "idempotent", "reconcile"}
            or not isinstance(intent["resources"], list)):
        raise ClaimError("release intent is not bound to the exact owned claim")
    _utc(intent["started_at"])
    request: dict[str, list[Any]] = {}
    seen = set()
    for item in intent["resources"]:
        if (not isinstance(item, dict) or not {"field", "value", "status"} <= set(item)
                or set(item) - {"field", "value", "status", "error_type"}
                or not isinstance(item["field"], str)
                or not isinstance(item["status"], str)
                or item["status"] not in {"NOT_STARTED", "IN_PROGRESS", "COMPLETE", "UNKNOWN"}
                or ("error_type" in item and not isinstance(item["error_type"], str))):
            raise ClaimError("release cleanup progress has invalid shape")
        key = (item["field"], str(item["value"]))
        if key in seen:
            raise ClaimError("duplicate release cleanup resource")
        seen.add(key)
        request.setdefault(item["field"], []).append(item["value"])
    plan = _cleanup_plan(claim, request)
    if plan != [{"field": item["field"], "value": item["value"]} for item in intent["resources"]]:
        raise ClaimError("release cleanup resource identity changed")
    return intent


def _validate_terminal_references(board: Mapping[str, Any], active_ids: set[str]) -> None:
    references = board.get("completed_receipts", [])
    if not isinstance(references, list):
        raise ClaimError("terminal receipt references have invalid shape")
    seen = set(active_ids)
    for reference in references:
        if (not isinstance(reference, dict)
                or set(reference) != {"task_id", "claim_sha256", "receipt_path", "receipt_sha256"}
                or not isinstance(reference["task_id"], str) or not reference["task_id"]
                or not isinstance(reference["receipt_path"], str) or not Path(reference["receipt_path"]).is_absolute()
                or any(not isinstance(reference[key], str) or re.fullmatch(r"[0-9a-f]{64}", reference[key]) is None
                       for key in ("claim_sha256", "receipt_sha256"))):
            raise ClaimError("terminal receipt reference is invalid")
        if reference["task_id"] in seen:
            raise ClaimError("duplicate active or terminal task identity")
        seen.add(reference["task_id"])


def _read_board(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "claims": []}
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaimError("active claim board is unreadable") from exc
    if not isinstance(board, dict) or board.get("schema_version") != SCHEMA_VERSION or not isinstance(board.get("claims"), list):
        raise ClaimError("active claim board has invalid shape")
    seen: set[str] = set()
    for item in board["claims"]:
        normalized = normalize_claim(item)
        if normalized["task_id"] in seen:
            raise ClaimError("duplicate active task identity")
        seen.add(normalized["task_id"])
    _validate_terminal_references(board, seen)
    _validate_execution_intents(board)
    if any(item["board_path"] != path.resolve().as_posix().casefold()
           for item in board.get("execution_intents", [])):
        raise ClaimError("execution intent belongs to another board")
    return board


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


EXECUTION_SCHEMA = "AIOS_CLAIM_EXECUTION_INTENT.v1"
_EXECUTION_HASH_FIELDS = (
    "nonce_sha256", "claim_sha256", "invocation_sha256", "approval_sha256",
)
_EXECUTION_SOURCE_PATHS = (
    "automation/orchestration/aios_self_build_one_action_local_apply_executor.py",
    "automation/orchestration/claims/aios_task_claim_control.py",
    "automation/validators/aios_approval_authority_integrity_validator.py",
    "automation/validators/aios_approval_contract_v2.py",
)


def _execution_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _validate_execution_intents(board: Mapping[str, Any]) -> None:
    if "execution_intents" not in board:
        return
    intents = board["execution_intents"]
    if not isinstance(intents, list):
        raise ClaimError("execution intents must be a list")
    nonces, attempts = set(), set()
    fields = {"schema", "state", "consumed_at", "board_path", *_EXECUTION_HASH_FIELDS}
    for item in intents:
        if (not isinstance(item, dict) or set(item) != fields
                or item["schema"] != EXECUTION_SCHEMA or item["state"] != "CONSUMED"
                or not isinstance(item["board_path"], str) or not Path(item["board_path"]).is_absolute()
                or any(not isinstance(item[key], str) or re.fullmatch(r"[0-9a-f]{64}", item[key]) is None
                       for key in _EXECUTION_HASH_FIELDS)):
            raise ClaimError("execution intent is malformed or partial")
        _utc(item["consumed_at"])
        if item["nonce_sha256"] in nonces or item["claim_sha256"] in attempts:
            raise ClaimError("duplicate consumed execution identity")
        nonces.add(item["nonce_sha256"])
        attempts.add(item["claim_sha256"])


def _execution_head(root: Path, claim: Mapping[str, Any]) -> str:
    git = root / ".git"
    if git.is_file():
        text = git.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir: "):
            raise ClaimError("execution worktree identity is invalid")
        directory = Path(text[8:])
        git = directory if directory.is_absolute() else root / directory
    head = (git / "HEAD").read_text(encoding="utf-8").strip()
    expected = "refs/heads/" + claim["branch"]
    if head != "ref: " + expected:
        raise ClaimError("execution branch drift")
    common = git
    if (git / "commondir").is_file():
        common = (git / (git / "commondir").read_text(encoding="utf-8").strip()).resolve()
    reference = common / expected
    if reference.is_file():
        sha = reference.read_text(encoding="utf-8").strip()
    else:
        records = (common / "packed-refs").read_text(encoding="utf-8").splitlines()
        matches = [line.split()[0] for line in records if line.endswith(" " + expected)]
        if len(matches) != 1:
            raise ClaimError("execution HEAD is unavailable")
        sha = matches[0]
    if sha != claim["base_sha"]:
        raise ClaimError("execution HEAD differs from exact claim base")
    return sha


def _dispatch_lock_target(board_path: Path, claim: Mapping[str, Any]) -> Path:
    """A lock namespace derived only from the signed board and exact claim."""
    return board_path.with_name(board_path.name + ".dispatch-" + _claim_contract(normalize_claim(claim)))


def _dispatch_lock_file(board_path: Path, claim: Mapping[str, Any]) -> Path:
    target = _dispatch_lock_target(board_path, claim)
    return target.with_suffix(target.suffix + ".lock")


@contextmanager
def _claim_dispatch_lease(board_path: Path, claim: Mapping[str, Any], *, initialize: bool = False):
    target = _dispatch_lock_target(board_path, claim)
    marker = _dispatch_lock_file(board_path, claim)
    if not initialize and not marker.is_file():
        raise ClaimError("claim dispatch lease is missing; preserve consumed attempt")
    with ExitStack() as held:
        try:
            held.enter_context(_exclusive_lock(target))
        except (ClaimError, OSError) as error:
            raise ClaimError("claim dispatch is pending or its lease is invalid") from error
        owned = marker.read_bytes()
        def verify():
            if not marker.is_file() or marker.read_bytes() != owned:
                raise ClaimError("claim dispatch lease ownership changed")
        verify()
        yield verify


@contextmanager
def _lifecycle_dispatch_guard(board_path: Path, board: Mapping[str, Any], claim: Mapping[str, Any]):
    # Legacy claims without execution intents retain their original lifecycle
    # and create no dispatch metadata.
    digest = _claim_contract(normalize_claim(claim))
    if any(item["claim_sha256"] == digest for item in board.get("execution_intents", [])):
        with _claim_dispatch_lease(board_path, claim) as verify:
            verify()
            yield
    else:
        yield


def make_canonical_authority_reader(gate_path: Path | str | None = None) -> Callable[[], Mapping[str, Any]]:
    """Load original production permission material afresh; never grant permission.

    Construction has no effects. Only the returned host callback reads the
    canonical checker's existing records and runtime key channel. The existing
    execute-once verifier still owns signatures, freshness and consumption.
    """
    def read() -> Mapping[str, Any]:
        try:
            from automation.validators import aios_approval_authority_integrity_validator as canonical

            root = canonical.canonical_production_repo_root()
            expected = root / "automation/orchestration/approval_inbox/APPLY_APPROVAL_GATE_001.json"
            selected = expected if gate_path is None else Path(gate_path)
            if not selected.is_absolute():
                selected = root / selected
            if selected.resolve() != expected:
                raise ValueError("noncanonical selected approval record")
            gate = canonical.load_json(expected)
            authority = canonical.load_json(root / canonical.DEFAULT_APPROVAL_INBOX_PATH)
            trust = canonical.load_json(root / canonical.DEFAULT_TRUST_METADATA_PATH)
            key = os.environ.get("AIOS_HUMAN_APPROVAL_HMAC_KEY")
            if any(type(value) is not dict for value in (gate, authority, trust)) or type(key) is not str or not key:
                raise ValueError("incomplete production permission material")
            return {"gate": gate, "authority": authority, "hmac_key": key,
                    "trust_metadata": trust,
                    "approval_roots": (root / canonical.DEFAULT_APPROVAL_ROOT,
                                       root / canonical.DEFAULT_APPROVAL_ARCHIVE),
                    "current_gate_path": expected}
        except Exception:
            # Original material and runtime keys must never enter error text.
            raise ClaimError("production authority material unavailable") from None
    return read


@dataclass(frozen=True)
class ExecutionAdmission:
    """Internal host connection; display projections cannot create admission.

    The reader supplies raw signed material to the canonical verifier, never a
    decision. The default reader is lazy; construction reads no files or keys.
    """
    controller: "TaskClaimController"
    expected_claim: Mapping[str, Any]
    authority_reader: Callable[[], Mapping[str, Any]] = field(default_factory=make_canonical_authority_reader)
    allow_test_trust: bool = False

    def execute(self, invocation: Mapping[str, Any], action: Callable[[], Any]) -> Any:
        return self.controller.execute_once(
            expected_claim=self.expected_claim, invocation=invocation,
            authority_reader=self.authority_reader, action=action,
            allow_test_trust=self.allow_test_trust,
        )


@dataclass(frozen=True)
class TaskClaimController:
    board_path: Path

    def execution_identity(self, expected_claim: Mapping[str, Any], invocation: Mapping[str, Any]) -> dict[str, Any]:
        """Measure the exact local invocation; this method grants no permission."""
        claim = normalize_claim(expected_claim)
        value = json.loads(json.dumps(dict(invocation), allow_nan=False))
        required = {"packet_id", "goal_id", "requested_action", "command", "working_directory",
                    "allowed_paths", "blocked_paths", "validator_chain", "resource_limits",
                    "output_roots", "stop_point"}
        if set(value) != required:
            raise ClaimError("execution invocation fields are incomplete")
        if any(not isinstance(value[name], str) or not value[name].strip()
               for name in ("packet_id", "goal_id", "requested_action", "command", "working_directory", "stop_point")):
            raise ClaimError("execution invocation identity is incomplete")
        root = Path(claim["worktree"])
        if (not Path(value["working_directory"]).is_absolute()
                or Path(value["working_directory"]).resolve().as_posix().casefold() != claim["worktree"]
                or value["packet_id"] != claim["packet_id"]):
            raise ClaimError("execution packet or worktree mismatch")
        for field in ("allowed_paths", "blocked_paths", "validator_chain"):
            values = value[field]
            if (not isinstance(values, list) or not values
                    or any(not isinstance(item, str) or not item.strip() for item in values)
                    or len(values) != len(set(values))):
                raise ClaimError("execution scope is invalid")
        allowed = [_norm_path(path, root) for path in value["allowed_paths"]]
        blocked = [_norm_path(path, root) for path in value["blocked_paths"]]
        if (any(not any(path == owned or PurePosixPath(owned) in PurePosixPath(path).parents
                        for owned in claim["claimed_paths"]) for path in allowed)
                or any(_overlap(path, denied) for path in allowed for denied in blocked)):
            raise ClaimError("execution scope differs from owned claim")
        limits = value["resource_limits"]
        if (not isinstance(limits, dict) or set(limits) != {"max_repairs", "max_files_changed"}
                or any(type(limits[key]) is not int for key in limits)
                or not 0 <= limits["max_repairs"] <= 1 or not 1 <= limits["max_files_changed"] <= 5):
            raise ClaimError("execution resource limits invalid")
        journal = self.board_path.resolve().as_posix().casefold()
        dispatch_lease = _dispatch_lock_file(self.board_path, claim).resolve().as_posix().casefold()
        if (not isinstance(value["output_roots"], dict) or len(value["output_roots"]) < 3
                or value["output_roots"].get("execution_journal") != journal
                or value["output_roots"].get("execution_dispatch_lease") != dispatch_lease
                or any(not isinstance(item, str) or not any(
                    (output := _norm_path(item, root)) == scope or PurePosixPath(scope) in PurePosixPath(output).parents
                    for scope in allowed) for name, item in value["output_roots"].items()
                       if name not in {"execution_journal", "execution_dispatch_lease"})):
            raise ClaimError("execution output scope is unowned")
        argv = shlex.split(value["command"], posix=True)
        if (len(argv) < 2 or argv[0] != sys.executable.replace("\\", "/")
                or not argv[1].endswith(".py") or Path(argv[1]).is_absolute()
                or any(character in value["command"] for character in ("\n", "\r", "&", "|", ";", ">", "<", chr(96)))):
            raise ClaimError("execution command identity unsupported")
        entry = _norm_path(argv[1], root)
        sources = {}
        for name in (*_EXECUTION_SOURCE_PATHS, argv[1]):
            path = Path(_norm_path(name, root))
            sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        from automation.validators import aios_approval_authority_integrity_validator as canonical

        installed = {
            _EXECUTION_SOURCE_PATHS[1]: __file__,
            _EXECUTION_SOURCE_PATHS[2]: canonical.__file__,
            _EXECUTION_SOURCE_PATHS[3]: canonical.approval_contract_v2.__file__,
        }
        executor = sys.modules.get("automation.orchestration.aios_self_build_one_action_local_apply_executor")
        if executor is not None:
            installed[_EXECUTION_SOURCE_PATHS[0]] = executor.__file__
        if any(hashlib.sha256(Path(origin).read_bytes()).hexdigest() != sources[name]
               for name, origin in installed.items()):
            raise ClaimError("execution installed source differs from signed worktree source")
        value.update(
            working_directory=claim["worktree"], allowed_paths=sorted(allowed), blocked_paths=sorted(blocked),
            claim_sha256=_claim_contract(claim), board_path=self.board_path.resolve().as_posix().casefold(),
            dispatch_lease_path=dispatch_lease,
            worker=claim["worker"], lane=claim["supervisor"], worktree=claim["worktree"],
            branch=claim["branch"], head_sha=_execution_head(root, claim), source_hashes=sources,
            runtime={"executable": str(Path(sys.executable).resolve()), "version": list(sys.version_info[:3]),
                     "executable_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()},
            command_source_sha256=hashlib.sha256(Path(entry).read_bytes()).hexdigest(),
        )
        return value

    def _verify_execution(self, board, expected_claim, invocation, material, allow_test_trust):
        from automation.validators import aios_approval_authority_integrity_validator as canonical

        if type(allow_test_trust) is not bool or not isinstance(material, Mapping):
            raise ClaimError("execution authority material missing")
        claim = _select_claim(board, expected_claim["task_id"], expected_claim)
        if claim is None or claim["state"] not in {"ACTIVE", "VERIFYING", "INTEGRATING"}:
            raise ClaimError("execution claim is not active")
        identity = self.execution_identity(claim, invocation)
        if collisions(normalize_claim(claim), board["claims"]):
            raise ClaimError("execution ownership collision")
        gate, authority = material.get("gate"), material.get("authority")
        if not isinstance(gate, dict) or not isinstance(authority, dict) or gate.get("schema") != canonical.V2_PAYLOAD_SCHEMA:
            raise ClaimError("execution requires canonical v2 raw authority")
        expected = {name: identity[name] for name in (
            "packet_id", "goal_id", "requested_action", "allowed_paths", "blocked_paths",
            "validator_chain", "resource_limits", "output_roots", "stop_point", "source_hashes",
            "worker", "lane", "worktree",
        )}
        expected.update(execution_contract_sha256=_execution_digest(identity),
                        package_sha256=identity["command_source_sha256"],
                        authority_bundle_sha256=_execution_digest(authority))
        if any(gate.get(name) != value for name, value in expected.items()):
            raise ClaimError("signed execution binding mismatch")
        if (not isinstance(gate.get("capabilities"), dict)
                or any(value is not False for value in gate["capabilities"].values())
                or gate.get("resume_policy") != {"allow_resume": False}
                or any(authority.get(name) != gate.get(name) for name in (
                    "approval_gate_id", "packet_id", "requested_action", "requested_mode",
                    "allowed_paths", "blocked_paths"))):
            raise ClaimError("execution authority alignment mismatch")
        # File reads and potentially slow material reads precede the final clock
        # sample. The installed verifier makes the actual decision.
        now = datetime.now(timezone.utc)
        if _utc(claim["expires_at"]) <= now:
            raise ClaimError("execution claim expired")
        result = canonical.validate_authority_bundle(
            gate, authority, hmac_key=material.get("hmac_key"),
            trust_metadata=material.get("trust_metadata"), now=now,
            approval_roots=material.get("approval_roots", ()),
            current_gate_path=material.get("current_gate_path"),
            allow_test_trust=allow_test_trust,
        )
        if result.status != "PASS" or not result.hardened_approval_verified:
            raise ClaimError("canonical execution authority blocked: " + ", ".join(result.failed_checks))
        # History scans in the canonical validator can be slow. Re-measure after
        # them and let canonical v2 check time again after the last source read.
        if self.execution_identity(claim, invocation) != identity:
            raise ClaimError("execution source or runtime changed during verification")
        now = datetime.now(timezone.utc)
        final = canonical.approval_contract_v2.verify(gate, material.get("hmac_key"), now=now)
        if _utc(claim["expires_at"]) <= now or not final.passed:
            raise ClaimError("execution final freshness check blocked")
        return {
            "schema": EXECUTION_SCHEMA, "state": "CONSUMED", "consumed_at": now.isoformat(),
            "board_path": identity["board_path"], "claim_sha256": identity["claim_sha256"],
            "invocation_sha256": _execution_digest(identity),
            "approval_sha256": canonical.approval_contract_v2.payload_sha256(gate),
            "nonce_sha256": hashlib.sha256(gate["approval_nonce"].encode("utf-8")).hexdigest(),
        }

    def execute_once(self, *, expected_claim: Mapping[str, Any], invocation: Mapping[str, Any],
                     authority_reader: Callable[[], Mapping[str, Any]], action: Callable[[], Any],
                     allow_test_trust: bool = False) -> Any:
        """Consume one attempt durably, then dispatch once without holding the board lock.

        No completion or retry permission is inferred from an action's result.
        Every saved intent stays consumed, including final-check failures.
        """
        if not callable(authority_reader) or not callable(action):
            raise ClaimError("execution host connection missing")
        expected_claim = normalize_claim(expected_claim)
        invocation = json.loads(json.dumps(dict(invocation), allow_nan=False))
        material = authority_reader()
        with _exclusive_lock(self.board_path):
            board = _read_board(self.board_path)
            intent = self._verify_execution(board, expected_claim, invocation, material, allow_test_trust)
            if any(item["nonce_sha256"] == intent["nonce_sha256"]
                   or item["claim_sha256"] == intent["claim_sha256"]
                   for item in board.get("execution_intents", [])):
                raise ClaimError("execution attempt already consumed")
            with _claim_dispatch_lease(self.board_path, expected_claim, initialize=True) as verify_lease:
                verify_lease()
                board.setdefault("execution_intents", []).append(intent)
                _atomic_write(self.board_path, board)
                if _read_board(self.board_path) != board:
                    raise ClaimError("consumed execution intent readback failed")
        # The provider may be slow. It is deliberately outside both locks.
        fresh_material = authority_reader()
        with ExitStack() as dispatch:
            with _exclusive_lock(self.board_path):
                current = _read_board(self.board_path)
                if current.get("execution_intents", []).count(intent) != 1:
                    raise ClaimError("consumed execution intent lost")
                # Linearization: while holding the board lock, retain this
                # exact claim's OS lease through the pending call and result.
                # Lifecycle writers use the same nonblocking lease.
                verify_lease = dispatch.enter_context(_claim_dispatch_lease(self.board_path, expected_claim))
                fresh = self._verify_execution(current, expected_claim, invocation, fresh_material, allow_test_trust)
                if any(fresh[key] != intent[key] for key in (*_EXECUTION_HASH_FIELDS, "board_path")):
                    raise ClaimError("execution authority changed after consumption")
                verify_lease()
            verify_lease()
            return action()



    def acquire(self, raw_claim: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(raw_claim, Mapping):
            raise ClaimError("claim must be an object")
        if "release_intent" in raw_claim:
            raise ClaimError("caller-supplied release progress is not acquisition authority")
        claim = normalize_claim(raw_claim)
        claim["state"] = "CLAIMING"
        if _utc(claim["expires_at"]) <= datetime.now(timezone.utc):
            raise ClaimError("claim attempt is expired")
        with _exclusive_lock(self.board_path):
            board = _read_board(self.board_path)
            conflicts = collisions(claim, board["claims"])
            if conflicts:
                raise ClaimCollision("claim blocked: " + ", ".join(conflicts))
            existing = _select_claim(board, claim["task_id"], claim)
            if existing is not None:
                return normalize_claim(existing)
            if Path(claim["receipt_path"]).exists() or self._receipt_for_task(claim["task_id"], board=board):
                raise ClaimError("task already has terminal evidence; reconcile completion")
            claim["state"] = "ACTIVE"
            board["claims"].append(claim)
            _atomic_write(self.board_path, board)
        return claim

    def transition(self, task_id: str, state: str, *, base_drift: bool = False, expected_claim: Mapping[str, Any] | None = None) -> dict[str, Any]:
        with _exclusive_lock(self.board_path):
            board = _read_board(self.board_path)
            claim = _select_claim(board, task_id, expected_claim)
            if claim is None:
                raise ClaimError("active task claim not found")
            with _lifecycle_dispatch_guard(self.board_path, board, claim):
                target = "ACTIVE" if base_drift and claim["state"] in {"VERIFYING", "INTEGRATING"} else state
                if target not in TRANSITIONS.get(claim["state"], set()):
                    raise ClaimError(f"invalid transition: {claim['state']} -> {target}")
                candidate = normalize_claim({**claim, "state": target})
                conflicts = collisions(candidate, board["claims"])
                if conflicts:
                    raise ClaimCollision("transition blocked: " + ", ".join(conflicts))
                claim.update(candidate)
                _atomic_write(self.board_path, board)
                return dict(claim)

    def guard(self, task_id: str, *, repository: str, worktree: Path, branch: str, head_is_descendant: bool, changed_paths: Sequence[str], expected_claim: Mapping[str, Any] | None = None) -> dict[str, Any]:
        board = _read_board(self.board_path)
        selected = _select_claim(board, task_id, expected_claim)
        claim = normalize_claim(selected) if selected is not None else None
        if claim is None or claim["state"] not in {"ACTIVE", "VERIFYING", "INTEGRATING"}:
            raise ClaimError("task has no executable active claim")
        if claim["repository"].casefold() != repository.casefold():
            raise ClaimError("wrong repository")
        if claim["worktree"] != worktree.resolve(strict=False).as_posix().casefold():
            raise ClaimError("wrong worktree")
        if claim["branch"] != _norm_branch(branch):
            raise ClaimError("wrong branch")
        if not head_is_descendant:
            raise ClaimError("unacceptable HEAD ancestry")
        normalized_changes = [_norm_path(path, worktree) for path in changed_paths]
        if any(not any(_overlap(path, allowed) for allowed in claim["claimed_paths"]) for path in normalized_changes):
            raise ClaimError("write outside claimed paths")
        conflicts = collisions(claim, board["claims"])
        if conflicts:
            raise ClaimCollision("execution blocked: " + ", ".join(conflicts))
        return claim

    def release(self, task_id: str, *, owned_resources: Mapping[str, Sequence[Any]] | None = None,
                cleanup: Callable[[str, Any], None] | None = None,
                expected_claim: Mapping[str, Any] | None = None,
                cleanup_idempotent: bool = False,
                reconcile_cleanup: Callable[[str, Any], str] | None = None) -> Path:
        with _exclusive_lock(self.board_path):
            board = _read_board(self.board_path)
            claim = _select_claim(board, task_id, expected_claim)
            if claim is None:
                receipt = self._receipt_for_task(task_id, expected_claim=expected_claim, board=board)
                if receipt:
                    return receipt
                raise ClaimError("active task claim not found")
            with _lifecycle_dispatch_guard(self.board_path, board, claim):
                return self._finish_release(board, claim, owned_resources, cleanup,
                                            cleanup_idempotent, reconcile_cleanup)

    def reconcile_release(self, task_id: str, *, expected_claim: Mapping[str, Any],
                          owned_resources: Mapping[str, Sequence[Any]] | None = None,
                          cleanup: Callable[[str, Any], None] | None = None,
                          cleanup_idempotent: bool = False,
                          reconcile_cleanup: Callable[[str, Any], str] | None = None) -> Path | None:
        """Reconcile saved release only; never infer requirement acceptance."""
        with _exclusive_lock(self.board_path):
            board = _read_board(self.board_path)
            claim = _select_claim(board, task_id, expected_claim)
            if claim is None:
                return self._receipt_for_task(task_id, expected_claim=expected_claim, board=board)
            with _lifecycle_dispatch_guard(self.board_path, board, claim):
                if claim["state"] != "RELEASING":
                    return None
                if "release_intent" not in claim:
                    raise ClaimError("release intent missing; preserve for reconciliation")
                return self._finish_release(board, claim, owned_resources, cleanup,
                                            cleanup_idempotent, reconcile_cleanup)

    def _finish_release(self, board: dict[str, Any], claim: dict[str, Any],
                        owned_resources, cleanup, cleanup_idempotent, reconcile_cleanup) -> Path:
        if claim["state"] != "RELEASING":
            raise ClaimError("task must be RELEASING before cleanup")
        if type(cleanup_idempotent) is not bool:
            raise ClaimError("cleanup idempotency must be explicit Boolean")
        if cleanup is not None and not callable(cleanup):
            raise ClaimError("cleanup callback is invalid")
        if reconcile_cleanup is not None and not callable(reconcile_cleanup):
            raise ClaimError("cleanup reconciliation callback is invalid")
        normalized = normalize_claim(claim)
        mode = "idempotent" if cleanup_idempotent else "reconcile" if reconcile_cleanup else "once"
        try:
            if "release_intent" in claim:
                intent = _validate_release_intent(normalized)
                if owned_resources is not None:
                    requested = _cleanup_plan(normalized, owned_resources)
                    saved = [{"field": item["field"], "value": item["value"]} for item in intent["resources"]]
                    if requested != saved:
                        raise ClaimError("release cleanup request identity changed")
                if (cleanup is not None or cleanup_idempotent or reconcile_cleanup is not None) and intent["cleanup_mode"] != mode:
                    raise ClaimError("release cleanup policy changed")
                # Work on the actual board record after validating its binding.
                intent = claim["release_intent"]
            else:
                if Path(normalized["receipt_path"]).exists():
                    raise ClaimError("unbound terminal receipt exists; preserve before cleanup")
                plan = _cleanup_plan(normalized, owned_resources if owned_resources is not None else {})
                if plan and cleanup is None:
                    raise ClaimError("owned cleanup requires an explicit callback")
                intent = {"schema": RELEASE_SCHEMA, "claim_sha256": _claim_contract(normalized),
                          "started_at": datetime.now(timezone.utc).isoformat(),
                          "receipt_path": normalized["receipt_path"], "cleanup_mode": mode,
                          "resources": [{**item, "status": "NOT_STARTED"} for item in plan]}
                claim["release_intent"] = intent
                _atomic_write(self.board_path, board)
            existing_receipt = Path(intent["receipt_path"])
            if existing_receipt.exists():
                expected_payload = {key: value for key, value in claim.items() if key != "release_intent"}
                expected_payload.update(state="COMPLETE_RECEIPT", released_at=intent["started_at"])
                if existing_receipt.read_bytes() != _json_bytes(expected_payload):
                    raise ClaimError("immutable terminal receipt conflicts or is partial")
                if any(item["status"] != "COMPLETE" for item in intent["resources"]):
                    raise ClaimError("terminal receipt precedes confirmed cleanup progress")
            for item in intent["resources"]:
                if item["status"] == "COMPLETE":
                    continue
                if item["status"] in {"IN_PROGRESS", "UNKNOWN"}:
                    if intent["cleanup_mode"] == "once":
                        raise ClaimError("owned cleanup outcome is unknown; unsafe repetition blocked")
                    if intent["cleanup_mode"] == "reconcile":
                        if reconcile_cleanup is None:
                            raise ClaimError("owned cleanup requires explicit reconciliation")
                        try:
                            outcome = reconcile_cleanup(item["field"], item["value"])
                        except Exception as error:
                            raise ClaimError("owned cleanup reconciliation failed") from error
                        if not isinstance(outcome, str) or outcome not in {"COMPLETE", "NOT_DONE", "UNKNOWN"}:
                            raise ClaimError("owned cleanup reconciliation result is invalid")
                        if outcome == "UNKNOWN":
                            raise ClaimError("owned cleanup outcome remains unknown")
                        if outcome == "COMPLETE":
                            item["status"] = "COMPLETE"
                            item.pop("error_type", None)
                            _atomic_write(self.board_path, board)
                            continue
                    elif not cleanup_idempotent:
                        raise ClaimError("idempotent cleanup contract must be explicitly retained")
                if cleanup is None:
                    raise ClaimError("owned cleanup callback is missing")
                item["status"] = "IN_PROGRESS"
                item.pop("error_type", None)
                _atomic_write(self.board_path, board)
                try:
                    cleanup(item["field"], item["value"])
                except Exception as error:
                    item["status"] = "UNKNOWN"
                    item["error_type"] = type(error).__name__
                    try:
                        _atomic_write(self.board_path, board)
                    except OSError as persistence_error:
                        error.add_note("Cleanup progress persistence also failed: " + type(persistence_error).__name__)
                    raise ClaimError("owned cleanup outcome is unknown") from error
                item["status"] = "COMPLETE"
                _atomic_write(self.board_path, board)
            payload = {key: value for key, value in claim.items() if key != "release_intent"}
            payload.update(state="COMPLETE_RECEIPT", released_at=intent["started_at"])
            encoded = _json_bytes(payload)
            receipt = Path(intent["receipt_path"])
            receipt.parent.mkdir(parents=True, exist_ok=True)
            if receipt.exists():
                if receipt.read_bytes() != encoded:
                    raise ClaimError("immutable terminal receipt conflicts or is partial")
            else:
                descriptor = os.open(receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o444)
                with os.fdopen(descriptor, "wb") as stream:
                    if stream.write(encoded) != len(encoded):
                        raise OSError("short immutable terminal receipt write")
                    stream.flush()
                    os.fsync(stream.fileno())
                if receipt.read_bytes() != encoded:
                    raise ClaimError("immutable terminal receipt readback failed")
            reference = {"task_id": claim["task_id"], "claim_sha256": intent["claim_sha256"],
                         "receipt_path": receipt.resolve(strict=False).as_posix().casefold(),
                         "receipt_sha256": hashlib.sha256(encoded).hexdigest()}
            board.setdefault("completed_receipts", []).append(reference)
            board["claims"] = [item for item in board["claims"] if item is not claim]
            _atomic_write(self.board_path, board)
            return receipt
        except OSError as error:
            raise ClaimError("release persistence interrupted; reconcile saved intent without task replay") from error

    def _receipt_for_task(self, task_id: str, *, expected_claim: Mapping[str, Any] | None = None,
                          board: Mapping[str, Any] | None = None) -> Path | None:
        board = _read_board(self.board_path) if board is None else board
        references = [item for item in board.get("completed_receipts", []) if item["task_id"] == task_id]
        parent = self.board_path.parent / "receipts"
        paths = [Path(item["receipt_path"]) for item in references]
        if not references:
            paths = list(parent.glob("*.json")) if parent.exists() else []
        matches: list[Path] = []
        for receipt in paths:
            reference = references[0] if references else None
            if reference and expected_claim is not None:
                expected = normalize_claim(expected_claim)
                if (reference["claim_sha256"] != _claim_contract(expected)
                        or reference["receipt_path"] != expected["receipt_path"]):
                    raise ClaimError("terminal claim reference does not match the expected identity")
            try:
                encoded = receipt.read_bytes()
                payload = json.loads(encoded)
            except (OSError, ValueError, UnicodeError) as exc:
                raise ClaimError("terminal claim evidence is unreadable") from exc
            if not isinstance(payload, dict):
                raise ClaimError("terminal claim evidence has invalid shape")
            if payload.get("task_id") != task_id:
                if reference:
                    raise ClaimError("terminal task reference identity changed")
                continue
            if payload.get("state") != "COMPLETE_RECEIPT" or not isinstance(payload.get("released_at"), str):
                raise ClaimError("terminal claim identity is invalid")
            _utc(payload["released_at"])
            normalized = normalize_claim({**payload, "state": "ACTIVE"})
            if normalized["receipt_path"] != receipt.resolve(strict=False).as_posix().casefold():
                raise ClaimError("terminal claim receipt path identity changed")
            if reference and (reference["claim_sha256"] != _claim_contract(normalized)
                              or reference["receipt_sha256"] != hashlib.sha256(encoded).hexdigest()):
                raise ClaimError("terminal claim reference content changed")
            if expected_claim is not None and _claim_contract(normalized) != _claim_contract(normalize_claim(expected_claim)):
                raise ClaimError("terminal claim identity does not match the expected attempt")
            matches.append(receipt)
        if len(matches) > 1:
            raise ClaimError("duplicate terminal task identity")
        return matches[0] if matches else None


def verify_exact_allowlist(changed_paths: Sequence[str], allowed_paths: Sequence[str]) -> None:
    allowed = [PurePosixPath(path.replace("\\", "/")) for path in allowed_paths]
    for changed in changed_paths:
        path = PurePosixPath(changed.replace("\\", "/"))
        if not any(path == root or root in path.parents for root in allowed):
            raise ClaimError(f"unexpected changed path: {changed}")
