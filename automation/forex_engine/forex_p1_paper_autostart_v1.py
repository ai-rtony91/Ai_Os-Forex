"""Fail-closed launcher for one unattended Supertrend PAPER campaign run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

VERSION = "forex_p1_paper_autostart_v1"
TARGET_TRADES = 30
PAPER_OUTPUT_ROOT_RELATIVE_PATH = Path(
    ".aios/runtime/forex_p1_supertrend_paper_sessions"
)
STATE_RELATIVE_PATH = (
    PAPER_OUTPUT_ROOT_RELATIVE_PATH
    / "AIOS_FOREX_SUPERTREND_30_TRADE_CAMPAIGN_STATE.json"
)
LEGACY_STATE_RELATIVE_PATH = Path(
    "Reports/forex_delivery/AIOS_FOREX_SUPERTREND_30_TRADE_CAMPAIGN_STATE.json"
)
RUNNER_RELATIVE_PATH = Path(
    "scripts/forex_delivery/run_forex_p1_supervised_paper_campaign_v1.py"
)
RUNTIME_DIR_RELATIVE_PATH = Path(".aios/runtime/forex_p1_paper_autostart_v1")
STOP_FILES = (
    Path(".aios/runtime/forex/kill_switch.active"),
    Path(".aios/runtime/forex/risk_halt.active"),
    Path(".aios/runtime/forex/cancel_campaign.active"),
)
RUNTIME_LOCK_VERSION = "1"
OUTER_LOCK_SCHEMA = "AIOS_FOREX_P1_PAPER_AUTOSTART_LOCK.v1"
OUTER_LOCK_CAMPAIGN_IDENTITY = "FOREX_P1_SUPERTREND_PAPER_AUTOSTART_V1"
OUTER_LOCK_TTL_SECONDS = 26 * 60 * 60
LOCK_POWERSHELL_TIMEOUT_SECONDS = 5
LOCK_RECOVERY_RECEIPT_SCHEMA = "AIOS_FOREX_RUNTIME_LOCK_RECOVERY.v1"
LOCK_METADATA_FIELDS = frozenset(
    {
        "schema", "version", "status", "lock_id", "pid",
        "process_start_identity", "host_identity", "boot_identity",
        "acquired_at_utc", "heartbeat_at_utc", "expires_at_utc",
        "campaign_identity", "source_fingerprint",
    }
)
LEGACY_LOCK_METADATA_FIELDS = frozenset(
    {"schema", "status", "owner", "pid", "heartbeat_at_utc"}
)
LOCK_RECOVERY_RECEIPT_FIELDS = frozenset(
    {
        "schema", "version", "observed_at_utc", "status",
        "prior_metadata_sha256", "new_lock_id", "campaign_identity",
        "prior_lock_id", "prior_pid", "prior_campaign_identity",
        "prior_source_fingerprint", "current_source_fingerprint",
        "owner_state", "recovery_reason",
    }
)
_BOOT_IDENTITY_CACHE: str | None = None


@dataclass(frozen=True)
class PreflightResult:
    status: str
    reason: str
    accepted_trades: int
    target_trades: int = TARGET_TRADES
    paper_only: bool = True
    live_execution_allowed: bool = False


class LockOwnerState(str, Enum):
    ACTIVE = "ACTIVE"
    DEAD = "DEAD"
    UNKNOWN = "UNKNOWN"


class _AutostartLockReplaced(RuntimeError):
    """Raised when cleanup discovers a different valid lock owner."""

    def __init__(self, replacement_owner: RuntimeLockOwnership) -> None:
        super().__init__("AUTOSTART_LOCK_REPLACED")
        self.replacement_owner = replacement_owner


class _AutostartLockReplacementUnverifiable(RuntimeError):
    """Raised when replacement metadata cannot prove an owner identity."""

    def __init__(self) -> None:
        super().__init__("AUTOSTART_LOCK_REPLACEMENT_UNVERIFIABLE")


@dataclass(frozen=True)
class RuntimeLockOwnership:
    schema: str
    lock_id: str
    pid: int
    process_start_identity: str
    host_identity: str
    boot_identity: str
    campaign_identity: str
    source_fingerprint: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_lock_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("RUNTIME_LOCK_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("RUNTIME_LOCK_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError("RUNTIME_LOCK_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def _validate_ttl(ttl_seconds: int) -> int:
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds < 1:
        raise ValueError("RUNTIME_LOCK_TTL_INVALID")
    return ttl_seconds


def _windows_process_start_identity(pid: int) -> str:
    script = (
        "$ErrorActionPreference='Stop';"
        "try {" f"$p=Get-Process -Id {pid} -ErrorAction Stop;" "} catch {"
        "if ($_.FullyQualifiedErrorId -like 'NoProcessFoundForGivenId*') {"
        "'{\"status\":\"MISSING\"}'; exit 3};"
        "'{\"status\":\"UNKNOWN\"}'; exit 4};"
        "try {$start=$p.StartTime.ToUniversalTime().ToString('o');"
        "[pscustomobject]@{status='FOUND';start=$start}|ConvertTo-Json -Compress;exit 0"
        "} catch {'{\"status\":\"UNKNOWN\"}'; exit 4}"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            capture_output=True, check=False, text=True,
            timeout=LOCK_POWERSHELL_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        raise RuntimeError("RUNTIME_LOCK_PROCESS_LIVENESS_UNKNOWN") from None
    try:
        payload = json.loads(result.stdout.strip())
    except (json.JSONDecodeError, AttributeError):
        raise RuntimeError("RUNTIME_LOCK_PROCESS_LIVENESS_UNKNOWN") from None
    if result.returncode == 3 and isinstance(payload, Mapping) and payload.get("status") == "MISSING":
        raise ProcessLookupError(pid)
    if result.returncode == 0 and isinstance(payload, Mapping) and payload.get("status") == "FOUND":
        start = payload.get("start")
        if not isinstance(start, str) or not start.strip():
            raise RuntimeError("RUNTIME_LOCK_PROCESS_LIVENESS_UNKNOWN")
        try:
            return _stamp(_parse_lock_utc(start))
        except ValueError:
            raise RuntimeError("RUNTIME_LOCK_PROCESS_LIVENESS_UNKNOWN") from None
    raise RuntimeError("RUNTIME_LOCK_PROCESS_LIVENESS_UNKNOWN")


def _process_start_identity(pid: int) -> str:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        raise ValueError("RUNTIME_LOCK_PID_INVALID")
    if os.name == "nt":
        return _windows_process_start_identity(pid)
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProcessLookupError(pid) from exc
    closing_parenthesis = stat_text.rfind(")")
    if closing_parenthesis < 2:
        raise RuntimeError("RUNTIME_LOCK_PROCESS_LIVENESS_UNKNOWN")
    tail = stat_text[closing_parenthesis + 1:].strip().split()
    if len(tail) <= 19:
        raise RuntimeError("RUNTIME_LOCK_PROCESS_LIVENESS_UNKNOWN")
    return tail[19]


def _host_identity() -> str:
    value = platform.node().strip().lower()
    if not value:
        raise RuntimeError("RUNTIME_LOCK_HOST_IDENTITY_UNAVAILABLE")
    return value


def _boot_identity() -> str:
    global _BOOT_IDENTITY_CACHE
    if _BOOT_IDENTITY_CACHE is not None:
        return _BOOT_IDENTITY_CACHE
    if os.name == "nt":
        script = (
            "$ErrorActionPreference='Stop';"
            "try {"
            "$boot=(Get-CimInstance Win32_OperatingSystem -ErrorAction Stop)."
            "LastBootUpTime.ToUniversalTime();"
            "$boot.ToString('o')"
            "} catch {"
            "try {$uptime=[int64]([Environment]::TickCount64)} catch {"
            "$uptime=[int64]([uint32]([Environment]::TickCount))};"
            "[DateTime]::UtcNow.Subtract([TimeSpan]::FromMilliseconds($uptime)).ToString('o')"
            "}"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", script],
                capture_output=True, check=False, text=True,
                timeout=LOCK_POWERSHELL_TIMEOUT_SECONDS,
            )
        except (subprocess.TimeoutExpired, OSError):
            raise RuntimeError("RUNTIME_LOCK_BOOT_IDENTITY_UNAVAILABLE") from None
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("RUNTIME_LOCK_BOOT_IDENTITY_UNAVAILABLE")
        try:
            _BOOT_IDENTITY_CACHE = _stamp(_parse_lock_utc(result.stdout.strip()))
            return _BOOT_IDENTITY_CACHE
        except ValueError:
            raise RuntimeError("RUNTIME_LOCK_BOOT_IDENTITY_UNAVAILABLE") from None
    for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
        if line.startswith("btime "):
            _BOOT_IDENTITY_CACHE = line.split(maxsplit=1)[1]
            return _BOOT_IDENTITY_CACHE
    raise RuntimeError("RUNTIME_LOCK_BOOT_IDENTITY_UNAVAILABLE")


def source_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_fingerprint(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("RUNTIME_LOCK_SOURCE_FINGERPRINT_INVALID")
    return value


def _validate_runtime_lock_metadata(
    payload: Any, *, schema: str, campaign_identity: str,
    source_fingerprint_value: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != LOCK_METADATA_FIELDS:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    if payload.get("schema") != schema or payload.get("version") != RUNTIME_LOCK_VERSION or payload.get("status") != "ACTIVE":
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    try:
        uuid.UUID(str(payload.get("lock_id")))
    except (ValueError, AttributeError) as exc:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID") from exc
    pid = payload.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    for field in ("process_start_identity", "host_identity", "boot_identity"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    if payload.get("campaign_identity") != campaign_identity or payload.get("source_fingerprint") != source_fingerprint_value:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    _validate_fingerprint(payload.get("source_fingerprint"))
    acquired = _parse_lock_utc(payload.get("acquired_at_utc"))
    heartbeat = _parse_lock_utc(payload.get("heartbeat_at_utc"))
    expiration = _parse_lock_utc(payload.get("expires_at_utc"))
    if heartbeat < acquired or expiration <= heartbeat:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    return dict(payload)


def _validate_runtime_lock_metadata_for_recovery(
    payload: Any, *, schema: str, campaign_identity: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != LOCK_METADATA_FIELDS:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    if payload.get("schema") != schema or payload.get("version") != RUNTIME_LOCK_VERSION or payload.get("status") != "ACTIVE":
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    try:
        uuid.UUID(str(payload.get("lock_id")))
    except (ValueError, AttributeError) as exc:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID") from exc
    pid = payload.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    for field in ("process_start_identity", "host_identity", "boot_identity"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    _validate_fingerprint(payload.get("source_fingerprint"))
    if payload.get("campaign_identity") != campaign_identity:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    acquired = _parse_lock_utc(payload.get("acquired_at_utc"))
    heartbeat = _parse_lock_utc(payload.get("heartbeat_at_utc"))
    expiration = _parse_lock_utc(payload.get("expires_at_utc"))
    if heartbeat < acquired or expiration <= heartbeat:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    return dict(payload)


def _validate_legacy_runtime_lock_metadata(
    payload: Any, *, schema: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != LEGACY_LOCK_METADATA_FIELDS:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    if payload.get("schema") != schema or payload.get("status") != "ACTIVE":
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    owner = payload.get("owner")
    if not isinstance(owner, str) or not owner.strip() or len(owner) > 256:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    pid = payload.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID")
    _parse_lock_utc(payload.get("heartbeat_at_utc"))
    return dict(payload)


def _render_lock_json(payload: Mapping[str, Any]) -> bytes:
    rendered = json.dumps(dict(payload), sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n"
    json.loads(rendered)
    return rendered.encode("utf-8")


def _mutex_name(path: Path) -> str:
    identity = str(path.resolve(strict=False)).lower().encode("utf-8")
    return "Global\\AIOS_FOREX_RUNTIME_LOCK_" + hashlib.sha256(identity).hexdigest()


def _windows_mutex_api():
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


@contextmanager
def _transition_serialization(path: Path) -> Iterator[None]:
    if os.name == "nt":
        import ctypes
        kernel32 = _windows_mutex_api()
        handle = kernel32.CreateMutexW(None, False, _mutex_name(path))
        if not handle:
            error_code = ctypes.get_last_error()
            if error_code == 5:
                raise PermissionError("RUNTIME_LOCK_GLOBAL_MUTEX_ACCESS_DENIED")
            raise OSError(error_code, "RUNTIME_LOCK_GLOBAL_MUTEX_CREATION_FAILED")
        wait_result = kernel32.WaitForSingleObject(handle, 30_000)
        if wait_result not in (0x00000000, 0x00000080):
            kernel32.CloseHandle(handle)
            if wait_result == 0x00000102:
                raise TimeoutError("RUNTIME_LOCK_TRANSITION_TIMEOUT")
            raise OSError("RUNTIME_LOCK_TRANSITION_WAIT_FAILED")
        try:
            yield
        finally:
            try:
                kernel32.ReleaseMutex(handle)
            finally:
                kernel32.CloseHandle(handle)
        return
    import fcntl
    guard_path = path.with_name(f"{path.name}.transition.guard")
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    with guard_path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _exclusive_create_lock(path: Path, payload: Mapping[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _render_lock_json(payload)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return True


def _atomic_replace_lock(path: Path, payload: Mapping[str, Any]) -> None:
    rendered = _render_lock_json(payload)
    temporary_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary_path.open("xb") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_runtime_lock_capture(
    path: Path, *, schema: str, campaign_identity: str,
    source_fingerprint_value: str,
) -> tuple[bytes, dict[str, Any]] | None:
    try:
        captured = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        payload = json.loads(captured.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("RUNTIME_LOCK_METADATA_INVALID") from exc
    try:
        validated = _validate_runtime_lock_metadata(
            payload, schema=schema, campaign_identity=campaign_identity,
            source_fingerprint_value=source_fingerprint_value,
        )
        return captured, validated
    except ValueError as current_error:
        try:
            legacy = _validate_legacy_runtime_lock_metadata(payload, schema=schema)
        except ValueError:
            raise current_error
        return captured, legacy


def read_runtime_lock(
    path: Path, *, schema: str, campaign_identity: str,
    source_fingerprint_value: str,
) -> dict[str, Any] | None:
    captured = _read_runtime_lock_capture(
        path, schema=schema, campaign_identity=campaign_identity,
        source_fingerprint_value=source_fingerprint_value,
    )
    return None if captured is None else captured[1]


def classify_lock_owner(
    payload: Mapping[str, Any], *, current_host_identity: str,
    current_boot_identity: str, process_start_reader: Callable[[int], str],
) -> LockOwnerState:
    if payload["host_identity"] != current_host_identity:
        return LockOwnerState.UNKNOWN
    if payload["boot_identity"] != current_boot_identity:
        return LockOwnerState.DEAD
    try:
        observed_start = process_start_reader(int(payload["pid"]))
    except ProcessLookupError:
        return LockOwnerState.DEAD
    except (PermissionError, subprocess.TimeoutExpired, OSError, RuntimeError, ValueError):
        return LockOwnerState.UNKNOWN
    return LockOwnerState.ACTIVE if observed_start == payload["process_start_identity"] else LockOwnerState.DEAD


def _lock_metadata(
    owner: RuntimeLockOwnership, *, acquired_at: datetime,
    heartbeat_at: datetime, expires_at: datetime,
) -> dict[str, Any]:
    return {
        "schema": owner.schema, "version": RUNTIME_LOCK_VERSION,
        "status": "ACTIVE", "lock_id": owner.lock_id, "pid": owner.pid,
        "process_start_identity": owner.process_start_identity,
        "host_identity": owner.host_identity, "boot_identity": owner.boot_identity,
        "acquired_at_utc": _stamp(acquired_at),
        "heartbeat_at_utc": _stamp(heartbeat_at),
        "expires_at_utc": _stamp(expires_at),
        "campaign_identity": owner.campaign_identity,
        "source_fingerprint": owner.source_fingerprint,
    }


def _exact_owner_matches(payload: Mapping[str, Any], owner: RuntimeLockOwnership) -> bool:
    return (
        payload.get("schema") == owner.schema and payload.get("lock_id") == owner.lock_id
        and payload.get("pid") == owner.pid
        and payload.get("process_start_identity") == owner.process_start_identity
        and payload.get("host_identity") == owner.host_identity
        and payload.get("boot_identity") == owner.boot_identity
        and payload.get("campaign_identity") == owner.campaign_identity
        and payload.get("source_fingerprint") == owner.source_fingerprint
    )


def _release_exact_owner_locked(path: Path, owner: RuntimeLockOwnership) -> bool:
    captured = _read_runtime_lock_capture(
        path, schema=owner.schema, campaign_identity=owner.campaign_identity,
        source_fingerprint_value=owner.source_fingerprint,
    )
    if captured is None or not _exact_owner_matches(captured[1], owner):
        return False
    path.unlink()
    return True


def _runtime_lock_owner(payload: Mapping[str, Any]) -> RuntimeLockOwnership | None:
    fields = (
        "schema", "lock_id", "pid", "process_start_identity",
        "host_identity", "boot_identity", "campaign_identity",
        "source_fingerprint",
    )
    if any(field not in payload for field in fields):
        return None
    values = {field: payload.get(field) for field in fields}
    if (
        not all(isinstance(values[field], str) and values[field].strip() for field in fields if field != "pid")
        or isinstance(values["pid"], bool)
        or not isinstance(values["pid"], int)
        or values["pid"] < 1
    ):
        return None
    return RuntimeLockOwnership(
        schema=values["schema"],
        lock_id=values["lock_id"],
        pid=values["pid"],
        process_start_identity=values["process_start_identity"],
        host_identity=values["host_identity"],
        boot_identity=values["boot_identity"],
        campaign_identity=values["campaign_identity"],
        source_fingerprint=values["source_fingerprint"],
    )


def _classify_legacy_lock_owner(
    payload: Mapping[str, Any], *, now: datetime, ttl_seconds: int,
    process_start_reader: Callable[[int], str],
) -> LockOwnerState:
    try:
        process_start_reader(int(payload["pid"]))
    except ProcessLookupError:
        return LockOwnerState.DEAD
    except (PermissionError, subprocess.TimeoutExpired, OSError, RuntimeError, ValueError):
        heartbeat = _parse_lock_utc(payload["heartbeat_at_utc"])
        return (
            LockOwnerState.UNKNOWN
            if now <= heartbeat + timedelta(seconds=ttl_seconds)
            else LockOwnerState.DEAD
        )
    return LockOwnerState.ACTIVE


def _append_lock_recovery_receipt(
    lock_path: Path, *, prior_metadata: bytes,
    owner: RuntimeLockOwnership, observed_at: datetime,
    prior_lock_id: str | None = None, prior_pid: int | None = None,
    prior_campaign_identity: str | None = None,
    prior_source_fingerprint: str | None = None,
    owner_state: str = "DEAD",
    recovery_reason: str = "DEAD_OWNER_SOURCE_FINGERPRINT_MISMATCH",
) -> None:
    receipt = {
        "schema": LOCK_RECOVERY_RECEIPT_SCHEMA, "version": RUNTIME_LOCK_VERSION,
        "observed_at_utc": _stamp(observed_at), "status": "STALE_LOCK_RECOVERED",
        "prior_metadata_sha256": hashlib.sha256(prior_metadata).hexdigest(),
        "new_lock_id": owner.lock_id, "campaign_identity": owner.campaign_identity,
        "prior_lock_id": prior_lock_id, "prior_pid": prior_pid,
        "prior_campaign_identity": prior_campaign_identity,
        "prior_source_fingerprint": prior_source_fingerprint,
        "current_source_fingerprint": owner.source_fingerprint,
        "owner_state": owner_state, "recovery_reason": recovery_reason,
    }
    if set(receipt) != LOCK_RECOVERY_RECEIPT_FIELDS:
        raise ValueError("RUNTIME_LOCK_RECEIPT_FIELD_VIOLATION")
    receipt_path = lock_path.with_name(f"{lock_path.name}.recovery.jsonl")
    try:
        previous_bytes = receipt_path.read_bytes()
    except FileNotFoundError:
        previous_bytes = b""
    except OSError:
        raise RuntimeError("RUNTIME_LOCK_RECOVERY_RECEIPT_PERSISTENCE_FAILED") from None
    if previous_bytes and not previous_bytes.endswith(b"\n"):
        raise RuntimeError("RUNTIME_LOCK_RECOVERY_RECEIPT_HISTORY_INVALID")
    receipt_line = (json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = receipt_path.parent / f".{receipt_path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary_path.open("xb") as stream:
            stream.write(previous_bytes + receipt_line)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, receipt_path)
    except OSError:
        raise RuntimeError("RUNTIME_LOCK_RECOVERY_RECEIPT_PERSISTENCE_FAILED") from None
    finally:
        temporary_path.unlink(missing_ok=True)


def acquire_runtime_lock(
    path: Path, *, schema: str, campaign_identity: str,
    source_fingerprint_value: str, ttl_seconds: int,
    now: datetime | None = None, pid: int | None = None,
    process_start_identity: str | None = None,
    host_identity: str | None = None, boot_identity: str | None = None,
    process_start_reader: Callable[[int], str] | None = None,
) -> RuntimeLockOwnership | None:
    ttl = _validate_ttl(ttl_seconds)
    fingerprint = _validate_fingerprint(source_fingerprint_value)
    acquired_at = (now or _utc_now()).astimezone(timezone.utc)
    selected_pid = os.getpid() if pid is None else pid
    selected_start = _process_start_identity(selected_pid) if process_start_identity is None else process_start_identity
    selected_host = _host_identity() if host_identity is None else host_identity
    selected_boot = _boot_identity() if boot_identity is None else boot_identity
    reader = _process_start_identity if process_start_reader is None else process_start_reader
    owner = RuntimeLockOwnership(
        schema=schema, lock_id=str(uuid.uuid4()), pid=selected_pid,
        process_start_identity=selected_start, host_identity=selected_host,
        boot_identity=selected_boot, campaign_identity=campaign_identity,
        source_fingerprint=fingerprint,
    )
    metadata = _lock_metadata(
        owner, acquired_at=acquired_at, heartbeat_at=acquired_at,
        expires_at=acquired_at + timedelta(seconds=ttl),
    )
    _validate_runtime_lock_metadata(
        metadata, schema=schema, campaign_identity=campaign_identity,
        source_fingerprint_value=fingerprint,
    )
    with _transition_serialization(path):
        if _exclusive_create_lock(path, metadata):
            return owner
        try:
            captured = _read_runtime_lock_capture(
                path, schema=schema, campaign_identity=campaign_identity,
                source_fingerprint_value=fingerprint,
            )
        except ValueError as current_error:
            try:
                prior_bytes = path.read_bytes()
                recovery_candidate = _validate_runtime_lock_metadata_for_recovery(
                    json.loads(prior_bytes.decode("utf-8")),
                    schema=schema,
                    campaign_identity=campaign_identity,
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                raise current_error
            if recovery_candidate["source_fingerprint"] == fingerprint:
                raise current_error
            owner_state = classify_lock_owner(
                recovery_candidate, current_host_identity=selected_host,
                current_boot_identity=selected_boot, process_start_reader=reader,
            )
            if owner_state is not LockOwnerState.DEAD:
                raise current_error
            _atomic_replace_lock(path, metadata)
            try:
                _append_lock_recovery_receipt(
                    path,
                    prior_metadata=prior_bytes,
                    owner=owner,
                    observed_at=acquired_at,
                    prior_lock_id=str(recovery_candidate["lock_id"]),
                    prior_pid=int(recovery_candidate["pid"]),
                    prior_campaign_identity=str(recovery_candidate["campaign_identity"]),
                    prior_source_fingerprint=str(recovery_candidate["source_fingerprint"]),
                    owner_state=owner_state.value,
                    recovery_reason="DEAD_OWNER_SOURCE_FINGERPRINT_MISMATCH",
                )
            except RuntimeError:
                if not _release_exact_owner_locked(path, owner):
                    raise RuntimeError("RUNTIME_LOCK_RECEIPT_FAILED_AND_CLEANUP_FAILED") from None
                raise RuntimeError("RUNTIME_LOCK_RECOVERY_RECEIPT_PERSISTENCE_FAILED") from None
            return owner
        if captured is None:
            return owner if _exclusive_create_lock(path, metadata) else None
        prior_bytes, existing = captured
        if set(existing) == LEGACY_LOCK_METADATA_FIELDS:
            owner_state = _classify_legacy_lock_owner(
                existing, now=acquired_at, ttl_seconds=ttl,
                process_start_reader=reader,
            )
            expiration = _parse_lock_utc(existing["heartbeat_at_utc"]) + timedelta(seconds=ttl)
        else:
            owner_state = classify_lock_owner(
                existing, current_host_identity=selected_host,
                current_boot_identity=selected_boot, process_start_reader=reader,
            )
            expiration = _parse_lock_utc(existing["expires_at_utc"])
        if owner_state is LockOwnerState.ACTIVE:
            return None
        if owner_state is LockOwnerState.UNKNOWN and acquired_at <= expiration:
            return None
        _atomic_replace_lock(path, metadata)
        try:
            _append_lock_recovery_receipt(
                path, prior_metadata=prior_bytes, owner=owner,
                observed_at=acquired_at,
                prior_lock_id=str(existing.get("lock_id")),
                prior_pid=int(existing["pid"]),
                prior_campaign_identity=str(existing.get("campaign_identity", campaign_identity)),
                prior_source_fingerprint=str(existing.get("source_fingerprint", fingerprint)),
                owner_state=owner_state.value,
                recovery_reason="STALE_OWNER_RECOVERY",
            )
        except RuntimeError:
            if not _release_exact_owner_locked(path, owner):
                raise RuntimeError("RUNTIME_LOCK_RECEIPT_FAILED_AND_CLEANUP_FAILED") from None
            raise RuntimeError("RUNTIME_LOCK_RECOVERY_RECEIPT_PERSISTENCE_FAILED") from None
        return owner


def release_runtime_lock(path: Path, owner: RuntimeLockOwnership) -> bool:
    with _transition_serialization(path):
        return _release_exact_owner_locked(path, owner)


def refresh_runtime_lock(
    path: Path, owner: RuntimeLockOwnership, *, ttl_seconds: int,
    now: datetime | None = None,
) -> bool:
    ttl = _validate_ttl(ttl_seconds)
    refreshed_at = (now or _utc_now()).astimezone(timezone.utc)
    with _transition_serialization(path):
        captured = _read_runtime_lock_capture(
            path, schema=owner.schema, campaign_identity=owner.campaign_identity,
            source_fingerprint_value=owner.source_fingerprint,
        )
        if captured is None or not _exact_owner_matches(captured[1], owner):
            return False
        payload = captured[1]
        refreshed = _lock_metadata(
            owner, acquired_at=_parse_lock_utc(payload["acquired_at_utc"]),
            heartbeat_at=refreshed_at,
            expires_at=refreshed_at + timedelta(seconds=ttl),
        )
        _atomic_replace_lock(path, refreshed)
        return True


def _read_state(path: Path) -> Mapping[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("CAMPAIGN_STATE_INVALID")
    return payload


def _render_state(state: Mapping[str, object]) -> bytes:
    return (
        json.dumps(dict(state), indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _atomic_write_state(path: Path, state: Mapping[str, object]) -> None:
    rendered = _render_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        descriptor = os.open(
            temporary_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_create_state(path: Path, state: Mapping[str, object]) -> bool:
    """Publish a state only if the canonical destination is still absent."""
    rendered = _render_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        descriptor = os.open(
            temporary_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            return False
        return True
    finally:
        temporary_path.unlink(missing_ok=True)


def _accepted_trades(state: Mapping[str, object]) -> int:
    if "accepted_qualifying_trades" not in state:
        raise ValueError("CAMPAIGN_ACCEPTED_COUNT_MISSING")
    value = state["accepted_qualifying_trades"]
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > TARGET_TRADES
    ):
        raise ValueError("CAMPAIGN_ACCEPTED_COUNT_INVALID")
    return value


def _existing_state(path: Path) -> Mapping[str, object] | None:
    if not path.exists():
        return None
    state = _read_state(path)
    _accepted_trades(state)
    return state


def _validate_campaign_state(state: Mapping[str, object], accepted: int) -> None:
    generic_campaign_status = state.get("campaign_status")
    if generic_campaign_status is not None:
        allowed_campaign_statuses = {
            "ACTIVE", "BLOCKED", "CLOSED", "COMPLETE", "COMPLETED",
            "COLLECTING", "FAILED", "IDLE", "INACTIVE", "IN_PROGRESS",
            "NOT_STARTED", "READY", "READY_FOR_COLLECTION", "RUNNING",
            "STOPPED", "WAITING_FOR_NEXT_RUN",
        }
        if (
            not isinstance(generic_campaign_status, str)
            or generic_campaign_status not in allowed_campaign_statuses
        ):
            raise ValueError("CAMPAIGN_STATE_STATUS_INVALID")

    session_status = state.get("session_status")
    if session_status is not None and not isinstance(session_status, str):
        raise ValueError("CAMPAIGN_STATE_SESSION_STATUS_INVALID")
    unresolved_session = state.get("unresolved_session")
    if unresolved_session is not None and not isinstance(unresolved_session, bool):
        raise ValueError("CAMPAIGN_STATE_UNRESOLVED_SESSION_INVALID")

    if "qualifying_trades" in state:
        qualifying_trades = state["qualifying_trades"]
        if (
            isinstance(qualifying_trades, bool)
            or not isinstance(qualifying_trades, int)
            or qualifying_trades != accepted
        ):
            raise ValueError("CAMPAIGN_STATE_COUNT_CONTRADICTION")
    if "required_qualifying_trades" in state:
        required = state["required_qualifying_trades"]
        if (
            isinstance(required, bool)
            or not isinstance(required, int)
            or required != TARGET_TRADES
        ):
            raise ValueError("CAMPAIGN_STATE_TARGET_INVALID")

    active_position = state.get("active_position")
    if (
        active_position is not None
        and active_position != "NONE"
        and not isinstance(active_position, Mapping)
    ):
        raise ValueError("CAMPAIGN_STATE_POSITION_INVALID")

    specialized_campaign_status = state.get("thirty_trade_campaign_status")
    if specialized_campaign_status is not None:
        allowed_specialized_statuses = {
            "ACTIVE", "COMPLETE", "IN_PROGRESS", "RUNNING",
        }
        if (
            not isinstance(specialized_campaign_status, str)
            or specialized_campaign_status not in allowed_specialized_statuses
        ):
            raise ValueError("CAMPAIGN_STATE_SPECIALIZED_STATUS_INVALID")
        if specialized_campaign_status == "COMPLETE" and accepted < TARGET_TRADES:
            raise ValueError("CAMPAIGN_STATE_COMPLETE_INCOMPLETE")
        if specialized_campaign_status == "IN_PROGRESS" and accepted >= TARGET_TRADES:
            raise ValueError("CAMPAIGN_STATE_IN_PROGRESS_COMPLETE")

    if "active_position_status" in state:
        specialized_position_status = state["active_position_status"]
        if (
            not isinstance(specialized_position_status, str)
            or specialized_position_status not in {"ACTIVE", "NONE"}
        ):
            raise ValueError("CAMPAIGN_STATE_SPECIALIZED_POSITION_INVALID")

    runtime_launch_status = state.get("runtime_launch_status")
    if runtime_launch_status is not None:
        allowed_runtime_statuses = {
            "ACTIVE", "BLOCKED", "COMPLETE", "FAILED", "LAUNCHED",
            "NOT_LAUNCHED", "RUNNING", "STOPPED",
        }
        if (
            not isinstance(runtime_launch_status, str)
            or runtime_launch_status not in allowed_runtime_statuses
        ):
            raise ValueError("CAMPAIGN_STATE_RUNTIME_STATUS_INVALID")
        if runtime_launch_status == "COMPLETE" and accepted < TARGET_TRADES:
            raise ValueError("CAMPAIGN_STATE_RUNTIME_COMPLETE_INCOMPLETE")


def _state_block_reason(state: Mapping[str, object], accepted: int) -> str | None:
    _validate_campaign_state(state, accepted)
    campaign_status = state.get("campaign_status")
    if campaign_status in {"RUNNING", "ACTIVE", "IN_PROGRESS"}:
        return "CAMPAIGN_STATE_ACTIVE"
    active_position = state.get("active_position")
    specialized_position_status = state.get("active_position_status")
    if specialized_position_status == "NONE" and (
        active_position is not None and active_position != "NONE"
    ):
        return "CAMPAIGN_STATE_CONTRADICTION"
    if active_position is not None and active_position != "NONE":
        return "CAMPAIGN_STATE_UNRESOLVED_POSITION"
    if state.get("unresolved_session") is True or state.get("session_status") in {
        "ACTIVE", "RUNNING", "UNRESOLVED"
    }:
        return "CAMPAIGN_STATE_UNRESOLVED_SESSION"
    specialized_campaign_status = state.get("thirty_trade_campaign_status")
    if specialized_campaign_status in {"ACTIVE", "RUNNING"}:
        return "CAMPAIGN_STATE_ACTIVE"
    if specialized_position_status == "ACTIVE":
        return "CAMPAIGN_STATE_UNRESOLVED_POSITION"
    runtime_launch_status = state.get("runtime_launch_status")
    if runtime_launch_status in {"ACTIVE", "LAUNCHED", "RUNNING"}:
        return "CAMPAIGN_STATE_ACTIVE"
    if campaign_status == "COMPLETE" and accepted < TARGET_TRADES:
        return "CAMPAIGN_STATE_COMPLETE_INCOMPLETE"
    return None


def _reconcile_campaign_state(root: Path) -> Mapping[str, object] | None:
    canonical_path = root / STATE_RELATIVE_PATH
    legacy_path = root / LEGACY_STATE_RELATIVE_PATH
    with _transition_serialization(canonical_path):
        canonical = _existing_state(canonical_path)
        if canonical is not None:
            return canonical
        legacy = _existing_state(legacy_path)
        if legacy is not None:
            published = _existing_state(canonical_path)
            if published is not None:
                return published
            if not _atomic_create_state(canonical_path, legacy):
                published = _existing_state(canonical_path)
                if published is None:
                    raise ValueError("CAMPAIGN_STATE_CONFLICT")
                return published
            published = _existing_state(canonical_path)
            if published is None:
                raise ValueError("CAMPAIGN_STATE_CONFLICT")
            return published
        return None


def _state_gate(root: Path) -> PreflightResult:
    try:
        state = _reconcile_campaign_state(root)
        if state is None:
            return PreflightResult("READY", "PAPER_CAMPAIGN_READY", 0)
        accepted = _accepted_trades(state)
        state_block_reason = _state_block_reason(state, accepted)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return PreflightResult("BLOCKED", str(exc), 0)
    if state_block_reason is not None:
        return PreflightResult("BLOCKED", state_block_reason, accepted)
    if accepted >= TARGET_TRADES:
        return PreflightResult("NO_ACTION", "TARGET_ALREADY_REACHED", accepted)
    return PreflightResult("READY", "PAPER_CAMPAIGN_READY", accepted)


def _branch(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError("GIT_BRANCH_UNAVAILABLE")
    return result.stdout.strip()


def preflight(
    repo_root: Path,
    *,
    environment: Mapping[str, str] | None = None,
    branch_reader: Callable[[Path], str] = _branch,
) -> PreflightResult:
    """Verify that exactly one bounded Practice/PAPER run may start."""
    env = os.environ if environment is None else environment
    root = repo_root.resolve()
    runner = root / RUNNER_RELATIVE_PATH
    if not runner.is_file():
        return PreflightResult("BLOCKED", "CANONICAL_RUNNER_MISSING", 0)
    if branch_reader(root) != "main":
        return PreflightResult("BLOCKED", "MAIN_BRANCH_REQUIRED", 0)
    if not env.get("OANDA_API_TOKEN") or not env.get("OANDA_ACCOUNT_ID"):
        return PreflightResult("BLOCKED", "RUNTIME_CREDENTIALS_MISSING", 0)
    active_stop = next((str(path) for path in STOP_FILES if (root / path).exists()), None)
    if active_stop:
        return PreflightResult("BLOCKED", f"SAFETY_STOP_ACTIVE:{active_stop}", 0)
    return _state_gate(root)


def _write_jsonl(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True, allow_nan=False) + "\n")


def _acquire_lock(path: Path) -> RuntimeLockOwnership:
    owner = acquire_runtime_lock(
        path, schema=OUTER_LOCK_SCHEMA,
        campaign_identity=OUTER_LOCK_CAMPAIGN_IDENTITY,
        source_fingerprint_value=source_fingerprint(Path(__file__)),
        ttl_seconds=OUTER_LOCK_TTL_SECONDS,
    )
    if owner is None:
        raise RuntimeError("AUTOSTART_ALREADY_ACTIVE")
    return owner


def _release_lock(path: Path, owner: RuntimeLockOwnership) -> None:
    with _transition_serialization(path):
        captured = _read_runtime_lock_capture(
            path, schema=owner.schema, campaign_identity=owner.campaign_identity,
            source_fingerprint_value=owner.source_fingerprint,
        )
        if captured is None:
            raise FileNotFoundError(path)
        _, current = captured
        if _exact_owner_matches(current, owner):
            _release_exact_owner_locked(path, owner)
            return
        replacement_owner = _runtime_lock_owner(current)
        if replacement_owner is None:
            raise _AutostartLockReplacementUnverifiable()
        raise _AutostartLockReplaced(replacement_owner)


def launch(
    repo_root: Path,
    *,
    cycles: int = 288,
    reviewer: str = "Human Owner Anthony",
    preflight_only: bool = False,
    environment: Mapping[str, str] | None = None,
    branch_reader: Callable[[Path], str] = _branch,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    if cycles < 1 or cycles > 288:
        raise ValueError("CYCLES_OUT_OF_RANGE")
    root = repo_root.resolve()
    runtime_dir = root / RUNTIME_DIR_RELATIVE_PATH
    log_path = runtime_dir / "events.jsonl"
    result = preflight(
        root,
        environment=environment,
        branch_reader=branch_reader,
    )
    event = {
        "schema": "AIOS_FOREX_P1_PAPER_AUTOSTART_EVENT.v1",
        "version": VERSION,
        "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **asdict(result),
    }
    _write_jsonl(log_path, event)
    print(json.dumps(event, sort_keys=True))
    if result.status == "NO_ACTION":
        return 0
    if result.status != "READY":
        return 2
    if preflight_only:
        return 0

    lock_path = runtime_dir / "launch.lock"
    lock_owner = _acquire_lock(lock_path)
    primary_exception: BaseException | None = None
    try:
        launch_state = _state_gate(root)
        if launch_state.status != "READY":
            _write_jsonl(
                log_path,
                {
                    "schema": "AIOS_FOREX_P1_PAPER_AUTOSTART_EVENT.v1",
                    "version": VERSION,
                    "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "status": "LAUNCH_RECHECK_" + launch_state.status,
                    "reason": launch_state.reason,
                    "accepted_trades": launch_state.accepted_trades,
                    "paper_only": True,
                    "live_execution_allowed": False,
                },
            )
            return 0 if launch_state.status == "NO_ACTION" else 2
        command: Sequence[str] = (
            sys.executable,
            str(root / RUNNER_RELATIVE_PATH),
            "--owner-local-runtime",
            "--signal-source",
            "supertrend",
            "--supertrend-paper-demo-only",
            "--output-root",
            str(root / PAPER_OUTPUT_ROOT_RELATIVE_PATH),
            "--cycles",
            str(cycles),
            "--reviewer",
            reviewer,
        )
        completed = run(
            command,
            cwd=root,
            env=dict(os.environ if environment is None else environment),
            check=False,
            text=True,
        )
        _write_jsonl(
            log_path,
            {
                "schema": "AIOS_FOREX_P1_PAPER_AUTOSTART_EVENT.v1",
                "version": VERSION,
                "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "status": "RUN_COMPLETE" if completed.returncode == 0 else "RUN_STOPPED",
                "return_code": completed.returncode,
                "paper_only": True,
                "live_execution_allowed": False,
            },
        )
        return completed.returncode
    except BaseException as exc:
        primary_exception = exc
        raise
    finally:
        try:
            _release_lock(lock_path, lock_owner)
        except _AutostartLockReplaced:
            if primary_exception is None:
                raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo-root", type=Path, required=True)
    result.add_argument("--cycles", type=int, default=288)
    result.add_argument("--reviewer", default="Human Owner Anthony")
    result.add_argument("--preflight-only", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return launch(
            args.repo_root,
            cycles=args.cycles,
            reviewer=args.reviewer,
            preflight_only=args.preflight_only,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
