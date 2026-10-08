"""Collision-safe, on-demand task claim control for AIOS orchestration.

This module owns claim metadata only.  It does not start workers, services,
containers, schedulers, deployments, or cleanup commands.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
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
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ClaimError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


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
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ClaimError(f"invalid port: {value!r}") from exc
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
    missing = [field for field in REQUIRED_FIELDS if field not in claim]
    if missing:
        raise ClaimError("missing claim fields: " + ", ".join(missing))
    result = dict(claim)
    if result["schema_version"] != SCHEMA_VERSION:
        raise ClaimError("unsupported claim schema")
    if result["state"] not in ACTIVE_STATES:
        raise ClaimError("unsupported active claim state")
    worktree = Path(str(result["worktree"])).resolve(strict=False)
    if not worktree.exists():
        raise ClaimError("worktree does not exist")
    result["worktree"] = worktree.as_posix().casefold()
    result["branch"] = _norm_branch(result["branch"])
    result["base_branch"] = _norm_branch(result["base_branch"])
    for field in PATH_FIELDS:
        result[field] = sorted({_norm_path(item, worktree) for item in result[field]})
    result["ports"] = sorted({_norm_port(item) for item in result["ports"]})
    for field in ("processes_or_services", "containers", "databases_or_schemas", "deployment_targets"):
        result[field] = sorted({_norm_name(item) for item in result[field]})
    result["pull_request"] = _norm_name(result["pull_request"]) if result["pull_request"] else ""
    for field in ("acquired_at", "heartbeat_at", "expires_at"):
        _utc(str(result[field]))
    if _utc(str(result["expires_at"])) <= _utc(str(result["acquired_at"])):
        raise ClaimError("claim expiry must follow acquisition")
    return result


def collisions(candidate: Mapping[str, Any], active: Sequence[Mapping[str, Any]], *, now: datetime | None = None) -> list[str]:
    current = now or datetime.now(timezone.utc)
    found: list[str] = []
    for raw in active:
        owner = normalize_claim(raw)
        if owner["task_id"] == candidate["task_id"]:
            continue
        if owner["state"] not in COLLISION_STATES:
            continue
        if _utc(owner["expires_at"]) <= current:
            found.append(f"stale_claim:{owner['task_id']}")
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


@contextmanager
def _exclusive_lock(board_path: Path) -> Iterator[None]:
    lock = board_path.with_suffix(board_path.suffix + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ClaimError(f"claim board is locked: {lock}") from exc
    os.close(descriptor)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _read_board(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "claims": []}
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaimError("active claim board is unreadable") from exc
    if not isinstance(board.get("claims"), list):
        raise ClaimError("active claim board has invalid shape")
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


@dataclass(frozen=True)
class TaskClaimController:
    board_path: Path

    def acquire(self, raw_claim: Mapping[str, Any]) -> dict[str, Any]:
        claim = normalize_claim({**raw_claim, "state": "CLAIMING"})
        with _exclusive_lock(self.board_path):
            board = _read_board(self.board_path)
            conflicts = collisions(claim, board["claims"])
            if conflicts:
                raise ClaimCollision("claim blocked: " + ", ".join(conflicts))
            claim["state"] = "ACTIVE"
            board["claims"].append(claim)
            _atomic_write(self.board_path, board)
        return claim

    def transition(self, task_id: str, state: str, *, base_drift: bool = False) -> dict[str, Any]:
        with _exclusive_lock(self.board_path):
            board = _read_board(self.board_path)
            claim = next((item for item in board["claims"] if item["task_id"] == task_id), None)
            if claim is None:
                raise ClaimError("active task claim not found")
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

    def guard(self, task_id: str, *, repository: str, worktree: Path, branch: str, head_is_descendant: bool, changed_paths: Sequence[str]) -> dict[str, Any]:
        board = _read_board(self.board_path)
        claim = next((normalize_claim(item) for item in board["claims"] if item["task_id"] == task_id), None)
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

    def release(self, task_id: str, *, owned_resources: Mapping[str, Sequence[str]] | None = None, cleanup: Callable[[str, str], None] | None = None) -> Path:
        with _exclusive_lock(self.board_path):
            board = _read_board(self.board_path)
            claim = next((item for item in board["claims"] if item["task_id"] == task_id), None)
            if claim is None:
                receipt = self._receipt_for_task(task_id)
                if receipt:
                    return receipt
                raise ClaimError("active task claim not found")
            if claim["state"] != "RELEASING":
                raise ClaimError("task must be RELEASING before cleanup")
            normalized = normalize_claim(claim)
            for field, values in (owned_resources or {}).items():
                if field not in PATH_FIELDS and field not in RESOURCE_FIELDS:
                    raise ClaimError(f"unknown cleanup resource: {field}")
                owned = normalized[field]
                requested = [_norm_path(v, Path(normalized["worktree"])) for v in values] if field in PATH_FIELDS else [_norm_name(v) for v in values]
                if any(value not in owned for value in requested):
                    raise ClaimError("cleanup requested for resource not owned by task")
                if cleanup:
                    for value in requested:
                        cleanup(field, value)
            receipt = Path(claim["receipt_path"])
            receipt.parent.mkdir(parents=True, exist_ok=True)
            payload = {**claim, "state": "COMPLETE_RECEIPT", "released_at": datetime.now(timezone.utc).isoformat()}
            try:
                descriptor = os.open(receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o444)
            except FileExistsError as exc:
                raise ClaimError("immutable receipt already exists with active claim") from exc
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
            board["claims"] = [item for item in board["claims"] if item["task_id"] != task_id]
            _atomic_write(self.board_path, board)
            return receipt

    def _receipt_for_task(self, task_id: str) -> Path | None:
        parent = self.board_path.parent / "receipts"
        for receipt in parent.glob("*.json") if parent.exists() else ():
            try:
                if json.loads(receipt.read_text(encoding="utf-8")).get("task_id") == task_id:
                    return receipt
            except (OSError, json.JSONDecodeError):
                continue
        return None


def verify_exact_allowlist(changed_paths: Sequence[str], allowed_paths: Sequence[str]) -> None:
    allowed = [PurePosixPath(path.replace("\\", "/")) for path in allowed_paths]
    for changed in changed_paths:
        path = PurePosixPath(changed.replace("\\", "/"))
        if not any(path == root or root in path.parents for root in allowed):
            raise ClaimError(f"unexpected changed path: {changed}")
