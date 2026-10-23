from __future__ import annotations

import argparse
import json
import hashlib
import os
import sys
import time
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "AIOS_RESUME_STATE.v1"
INPUT_SCHEMA = "AIOS_WAKE_CONTINUE.v1"
DEFAULT_OUTPUT_DIR = Path("Reports/aios_resume")
LATEST_FILENAME = "AIOS_RESUME_STATE_latest.json"

SENSITIVE_KEYS = {
    "api_key",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "credentials",
    "credential",
    "broker_credentials",
}


def safety_flags() -> dict[str, bool]:
    return {
        "queue_mutation": False,
        "approval_mutation": False,
        "worker_dispatch": False,
        "runtime_launch": False,
        "scheduler": False,
        "daemon": False,
        "broker": False,
        "credentials": False,
        "live_trading": False,
        "real_orders": False,
        "real_webhooks": False,
        "git_add": False,
        "git_commit": False,
        "git_push": False,
        "merge": False,
    }


def _sanitize(
    value: Any,
    *,
    typed_metadata: bool = False,
    path: tuple[str, ...] = (),
) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if key_lower in {"stdout", "stderr"}:
                continue
            # Only this known metadata name collides with a sensitive payload key.
            if (
                typed_metadata
                and path in {("safety",), ("approval_required",)}
                and key_text == "credentials"
                and type(item) is bool
            ):
                sanitized[key_text] = item
                continue
            if key_lower in SENSITIVE_KEYS:
                sanitized[key_text] = "[redacted]"
                continue
            sanitized[key_text] = _sanitize(item, typed_metadata=typed_metadata, path=(*path, key_text))
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def summarize_validators(wake_report: dict[str, Any]) -> dict[str, Any]:
    validators = wake_report.get("validators_run", [])
    if not isinstance(validators, list):
        validators = []

    summarized = []
    for validator in validators:
        if not isinstance(validator, dict):
            continue
        summarized.append(
            {
                "name": validator.get("name", "validator"),
                "command": validator.get("command", ""),
                "returncode": validator.get("returncode"),
                "passed": bool(validator.get("passed", False)),
            }
        )

    passed_count = sum(1 for validator in summarized if validator["passed"])
    return {
        "count": len(summarized),
        "passed_count": passed_count,
        "failed_count": len(summarized) - passed_count,
        "validators": summarized,
    }


def resume_readiness(wake_report: dict[str, Any]) -> tuple[bool, str]:
    result = wake_report.get("result")
    handoff = wake_report.get("bounded_executor_handoff")
    handoff_status = handoff.get("handoff_status") if isinstance(handoff, dict) else None
    if result != "DONE_FOR_CURRENT_GOAL":
        return False, "result_not_done_for_current_goal"
    if handoff_status != "ready":
        return False, "bounded_executor_handoff_not_ready"
    return True, "ready_for_resume"


def build_resume_state(wake_report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(wake_report, dict):
        wake_report = {}

    goal_decision = wake_report.get("goal_decision")
    if not isinstance(goal_decision, dict):
        goal_decision = {}

    next_build_plan = wake_report.get("next_build_plan")
    if not isinstance(next_build_plan, dict):
        next_build_plan = {}

    bounded_handoff = wake_report.get("bounded_executor_handoff")
    if not isinstance(bounded_handoff, dict):
        bounded_handoff = {}

    resume_ready, resume_reason_code = resume_readiness(wake_report)

    return {
        "schema": SCHEMA,
        "input_schema": wake_report.get("schema", INPUT_SCHEMA),
        "goal": wake_report.get("goal", "unknown"),
        "result": wake_report.get("result", "unknown"),
        "selected_action": wake_report.get("selected_action"),
        "last_decision": {
            "decision": goal_decision.get("decision"),
            "reason_code": goal_decision.get("reason_code"),
            "decision_reasons": goal_decision.get("decision_reasons", []),
        },
        "next_build_plan": _sanitize(
            next_build_plan,
            typed_metadata=next_build_plan.get("schema") == "AIOS_NEXT_BUILD_PLAN.v1",
        ),
        "bounded_executor_handoff": _sanitize(
            bounded_handoff,
            typed_metadata=bounded_handoff.get("schema") == "AIOS_BOUNDED_EXECUTOR_HANDOFF.v1",
        ),
        "next_safe_action": wake_report.get("next_safe_action", "Inspect wake/continue output before resuming."),
        "approval_required": _sanitize(
            wake_report.get("approval_required", {}),
            typed_metadata=wake_report.get("schema") == INPUT_SCHEMA,
            path=("approval_required",),
        ),
        "safety": safety_flags(),
        "validators_summary": summarize_validators(wake_report),
        "resume_ready": resume_ready,
        "resume_reason_code": resume_reason_code,
    }


def _resolved_path(path: Path) -> Path:
    text = str(path.resolve())
    # Windows can add this filesystem prefix when a concurrently created path
    # changes from nonexistent to existing between the two containment reads.
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[8:]
    elif text.startswith("\\\\?\\"):
        text = text[4:]
    return Path(text)


def _resolve_output_dir(repo_root: Path, output_dir: Path | str | None = None) -> Path:
    allowed_root = _resolved_path(repo_root / DEFAULT_OUTPUT_DIR)
    target = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    target = target if target.is_absolute() else repo_root / target
    target = _resolved_path(target)
    try:
        target.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError("resume_state_dir_outside_allowed_root") from exc
    return target



def serialized_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=False, allow_nan=False) + "\n").encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def atomic_write(path: Path, payload: bytes) -> None:
    """Replace a projection only after its entire new version is durable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != payload:
            raise OSError("publication_short_write")
        os.replace(temporary, path)
        if path.read_bytes() != payload:
            raise OSError("publication_readback_mismatch")
    finally:
        # This process owns this one temporary file, never a caller's file.
        temporary.unlink(missing_ok=True)


@contextmanager
def publication_lock(target_dir: Path, *, create: bool = True):
    """An OS-held lock releases on process death; a leftover name owns no lease."""
    if create:
        target_dir.mkdir(parents=True, exist_ok=True)
    lock_path = target_dir / ".publication.lock"
    with lock_path.open("a+b" if create else "r+b", buffering=0) as stream:
        if stream.seek(0, 2) == 0:
            if not create:
                raise ValueError("checkpoint_publication_lock_incomplete")
            stream.write(b"\0")
        deadline = time.monotonic() + 5
        while True:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("resume_publication_lock_unavailable")
                time.sleep(0.01)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def immutable_write(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError("immutable_checkpoint_content_mismatch")
    if path.read_bytes() != payload:
        raise OSError("immutable_checkpoint_readback_mismatch")


def write_resume_state(
    repo_root: Path,
    resume_state: dict[str, Any],
    *,
    output_dir: Path | str | None = None,
    generated_at_utc: datetime | None = None,
    publish_latest: bool = True,
    _locked: bool = False,
) -> dict[str, Any]:
    target_dir = _resolve_output_dir(repo_root, output_dir)
    semantic = {key: value for key, value in resume_state.items() if key not in {"generated_at_utc", "resume_state_paths", "checkpoint_id"}}
    checkpoint_id = content_hash(semantic)
    now = generated_at_utc or datetime.now(timezone.utc)
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    latest_path = target_dir / LATEST_FILENAME
    with (nullcontext() if _locked else publication_lock(target_dir)):
        matches = list(target_dir.glob(f"AIOS_RESUME_STATE_*_{checkpoint_id}.json"))
        if matches:
            timestamped_path = matches[0]
            payload = timestamped_path.read_bytes()
            output_state = json.loads(payload)
            saved_semantic = {key: value for key, value in output_state.items() if key not in {"generated_at_utc", "resume_state_paths", "checkpoint_id"}}
            if content_hash(saved_semantic) != checkpoint_id or output_state.get("checkpoint_id") != checkpoint_id:
                raise ValueError("immutable_checkpoint_content_mismatch")
        else:
            timestamped_path = target_dir / f"AIOS_RESUME_STATE_{timestamp}_{checkpoint_id}.json"
            output_state = {
                **semantic,
                "checkpoint_id": checkpoint_id,
                "generated_at_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "resume_state_paths": {
                    "timestamped": timestamped_path.relative_to(repo_root).as_posix(),
                    "latest": latest_path.relative_to(repo_root).as_posix(),
                },
            }
            payload = serialized_bytes(output_state)
            immutable_write(timestamped_path, payload)
        if publish_latest:
            atomic_write(latest_path, payload)
        return output_state



SOURCE_FILES = (
    "aios_resume_state.py", "aios_wake_continue.py", "aios_control_plane_status.py",
    "aios_operator_relay.py", "aios_continuation_controller.py", "aios_forex_goal_decision.py",
    "aios_forex_post_risk_decision.py", "aios_next_build_plan.py", "aios_bounded_executor_handoff.py",
    "aios_cli_result_ingest.py", "aios_local_runner_bridge.py", "aios_bounded_executor_ready.py",
    "aios_mode_capability_registry.py", "aios_build_intent_router.py", "aios_sos_escalation_policy.py",
    "aios_codex_packet_builder.py", "aios_self_build_loop_readiness.py",
)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity() -> dict[str, str]:
    return {name: file_hash(Path(__file__).with_name(name)) for name in SOURCE_FILES}


def bounded_path(repo_root: Path, value: str | Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError("publication_path_invalid")
    root = _resolved_path(repo_root)
    path = Path(value)
    path = _resolved_path(path if path.is_absolute() else root / path)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("publication_projection_outside_repo_root") from exc
    return path


def require_object(value: Any, reason: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(reason)
    return value


def require_hash(value: Any, reason: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(reason)
    return value


def verify_execution_identity(repo_root: Path, identity: dict[str, Any], *, admitted_context=None, native_admission_reader=None) -> None:
    identity = require_object(identity, "checkpoint_execution_identity_invalid")
    if "identity_contract" in identity:
        if identity["identity_contract"] != "AIOS_NATIVE_EXECUTION_IDENTITY.v1":
            raise ValueError("checkpoint_identity_contract_unknown")
        return _verify_native_identity(repo_root, identity, admitted_context, native_admission_reader, live=True)
    if identity.get("repo_root") != str(_resolved_path(repo_root)):
        raise ValueError("checkpoint_repository_mismatch")
    if identity.get("source_hashes") != source_identity():
        raise ValueError("checkpoint_source_changed")
    if (not isinstance(identity.get("attempt_id"), str) or not identity["attempt_id"]
            or not isinstance(identity.get("goal"), str) or not isinstance(identity.get("selected_action"), str)
            or identity.get("task_id") != content_hash({"goal": identity["goal"], "action": identity["selected_action"]})):
        raise ValueError("checkpoint_attempt_identity_invalid")
    command = identity.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(item, str) or not item for item in command):
        raise ValueError("checkpoint_command_invalid")
    result = require_object(identity.get("successful_result"), "checkpoint_successful_result_invalid")
    if (result.get("passed") is not True or type(result.get("returncode")) is not int or result["returncode"] != 0
            or identity.get("successful_result_sha256") != content_hash(result)
            or result.get("command") != " ".join(command)):
        raise ValueError("checkpoint_successful_result_invalid")
    inputs = identity.get("input_hashes")
    if not isinstance(inputs, dict) or not inputs:
        raise ValueError("checkpoint_inputs_missing")
    for relative, expected in inputs.items():
        if not isinstance(relative, str) or not relative:
            raise ValueError("checkpoint_input_path_invalid")
        if expected is not None:
            require_hash(expected, "checkpoint_input_hash_invalid")
        path = bounded_path(repo_root, relative)
        actual = file_hash(path) if path.is_file() else None
        if actual != expected:
            raise ValueError("checkpoint_inputs_changed")


def requested_projections(repo_root: Path, requested: Any) -> list[dict[str, str]]:
    requested = require_object(requested, "checkpoint_requested_invalid")
    required = {"state_path", "write_resume", "resume_dir", "write_control", "control_dir", "emit_continuation_controller"}
    if set(requested) != required:
        raise ValueError("checkpoint_requested_fields_invalid")
    for key in ("write_resume", "write_control", "emit_continuation_controller"):
        if type(requested[key]) is not bool:
            raise ValueError("checkpoint_requested_flag_invalid")
    for key in ("state_path", "resume_dir", "control_dir"):
        if not isinstance(requested[key], str) or not requested[key]:
            raise ValueError("checkpoint_requested_path_invalid")
    resume_dir = _resolve_output_dir(repo_root, requested["resume_dir"])
    control_dir = bounded_path(repo_root, requested["control_dir"])
    control_dir.relative_to(_resolved_path(repo_root / "Reports/aios_control_plane"))
    generic = bounded_path(repo_root, requested["state_path"])
    # A projection cannot overwrite archive/acceptance evidence or another role.
    if generic == resume_dir or resume_dir in generic.parents:
        raise ValueError("checkpoint_projection_overlaps_owner")
    outputs = []
    if requested["write_control"]:
        outputs.append({"role": "control", "path": (control_dir / "AIOS_CONTROL_PLANE_STATUS_latest.json").relative_to(repo_root).as_posix()})
    outputs.append({"role": "generic", "path": generic.relative_to(repo_root).as_posix()})
    if len({item["path"] for item in outputs}) != len(outputs):
        raise ValueError("checkpoint_projection_role_collision")
    return outputs


def accepted_revision(target_dir: Path) -> str | None:
    latest = target_dir / LATEST_FILENAME
    return file_hash(latest) if latest.is_file() else None


def validate_frontier(repo_root: Path, target_dir: Path) -> None:
    latest = target_dir / LATEST_FILENAME
    if not latest.is_file():
        return
    try:
        data = latest.read_bytes()
        state = require_object(json.loads(data), "checkpoint_envelope_invalid")
        archive, payload = checkpoint_bytes(repo_root, state)
        if payload != data or archive.parent != target_dir:
            raise ValueError("checkpoint_frontier_invalid")
        require_object(state.get("publication"), "checkpoint_publication_unbound")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ValueError("checkpoint_frontier_invalid") from exc


def assert_predecessor(target_dir: Path, predecessor: Any, *, repo_root: Path) -> None:
    if predecessor is not None:
        require_hash(predecessor, "checkpoint_predecessor_invalid")
    if accepted_revision(target_dir) != predecessor:
        raise ValueError("checkpoint_stale_predecessor")
    validate_frontier(repo_root, target_dir)


def capture_successful_attempt(repo_root: Path, minimal: dict[str, Any], identity: dict[str, Any], requested: dict[str, Any], *, admitted_context=None, native_admission_reader=None) -> tuple[Path, dict[str, Any]]:
    """Immutable evidence only: no successor or acceptance pointer is published."""
    if isinstance(identity, dict) and "identity_contract" in identity:
        return _capture_native_attempt(repo_root, minimal, identity, requested, admitted_context, native_admission_reader)
    verify_execution_identity(repo_root, identity)
    required_outputs = requested_projections(repo_root, requested)
    target_dir = _resolve_output_dir(repo_root, requested["resume_dir"])
    with publication_lock(target_dir):
        record = {"record_type": "successful_attempt", "execution_identity": identity,
                  "finalization_input": minimal, "requested": requested,
                  "required_outputs": required_outputs, "predecessor_sha256": accepted_revision(target_dir)}
        path = target_dir / f"AIOS_RESUME_ATTEMPT_{content_hash(record)}.json"
        immutable_write(path, serialized_bytes(record))
        return path, record


def load_successful_attempt(repo_root: Path, path: Path, *, admitted_context=None, native_admission_reader=None) -> dict[str, Any]:
    if admitted_context is not None or native_admission_reader is not None:
        return _load_native_attempt(repo_root, path, admitted_context=admitted_context, native_admission_reader=native_admission_reader, live=True)
    path = bounded_path(repo_root, path)
    path.relative_to(_resolve_output_dir(repo_root))
    record = require_object(json.loads(path.read_bytes()), "checkpoint_attempt_envelope_invalid")
    if isinstance(record.get("execution_identity"), dict) and "identity_contract" in record["execution_identity"]:
        return _load_native_attempt(repo_root, path, admitted_context=admitted_context, native_admission_reader=native_admission_reader, live=True)
    if record.get("record_type") != "successful_attempt" or path.name != f"AIOS_RESUME_ATTEMPT_{content_hash(record)}.json":
        raise ValueError("checkpoint_attempt_content_mismatch")
    verify_execution_identity(repo_root, record.get("execution_identity"))
    minimal = require_object(record.get("finalization_input"), "checkpoint_finalization_input_invalid")
    identity = record["execution_identity"]
    if minimal.get("execution_identity") != identity or minimal.get("goal") != identity["goal"] or minimal.get("selected_action") != identity["selected_action"]:
        raise ValueError("checkpoint_report_identity_mismatch")
    expected = requested_projections(repo_root, record.get("requested"))
    if record.get("required_outputs") != expected:
        raise ValueError("checkpoint_requested_projection_mismatch")
    if record.get("predecessor_sha256") is not None:
        require_hash(record["predecessor_sha256"], "checkpoint_predecessor_invalid")
    if path.parent != _resolve_output_dir(repo_root, record["requested"]["resume_dir"]):
        raise ValueError("checkpoint_attempt_owner_mismatch")
    return record


def checkpoint_bytes(repo_root: Path, state: dict[str, Any]) -> tuple[Path, bytes]:
    state = require_object(state, "checkpoint_envelope_invalid")
    paths = require_object(state.get("resume_state_paths"), "checkpoint_paths_invalid")
    if set(paths) != {"timestamped", "latest"} or any(not isinstance(value, str) or not value for value in paths.values()):
        raise ValueError("checkpoint_paths_invalid")
    archive = bounded_path(repo_root, paths["timestamped"])
    archive.relative_to(_resolve_output_dir(repo_root))
    if bounded_path(repo_root, paths["latest"]) != archive.parent / LATEST_FILENAME:
        raise ValueError("checkpoint_latest_path_mismatch")
    payload = archive.read_bytes()
    saved = require_object(json.loads(payload), "checkpoint_archive_envelope_invalid")
    semantic = {key: value for key, value in saved.items() if key not in {"generated_at_utc", "resume_state_paths", "checkpoint_id"}}
    checkpoint_id = require_hash(saved.get("checkpoint_id"), "checkpoint_id_invalid")
    if content_hash(semantic) != checkpoint_id or saved != state or not archive.stem.endswith("_" + checkpoint_id):
        raise ValueError("checkpoint_content_mismatch")
    return archive, payload


def publication_record(repo_root: Path, state: dict[str, Any], *, admitted_context=None, native_admission_reader=None) -> dict[str, Any]:
    publication = require_object(state.get("publication"), "checkpoint_publication_unbound")
    attempt_path = publication.get("attempt_path")
    if not isinstance(attempt_path, str) or not attempt_path:
        raise ValueError("checkpoint_attempt_path_invalid")
    attempt = (load_successful_attempt(repo_root, bounded_path(repo_root, attempt_path))
               if admitted_context is None and native_admission_reader is None else
               load_successful_attempt(repo_root, bounded_path(repo_root, attempt_path), admitted_context=admitted_context, native_admission_reader=native_admission_reader))
    for key in ("execution_identity", "finalization_input", "requested", "required_outputs", "predecessor_sha256"):
        equal = (_native_cycle().strict_json_equal(publication.get(key), attempt[key])
                 if attempt["execution_identity"].get("identity_contract") else publication.get(key) == attempt[key])
        if not equal:
            raise ValueError("checkpoint_attempt_binding_mismatch")
    return publication


def verify_outputs(repo_root: Path, outputs: Any, publication: dict[str, Any], pending_archive: Path) -> list[dict[str, str]]:
    required = requested_projections(repo_root, publication["requested"])
    if publication.get("required_outputs") != required or not isinstance(outputs, list) or len(outputs) != len(required):
        raise ValueError("checkpoint_completion_outputs_mismatch")
    for output, expected in zip(outputs, required):
        require_object(output, "checkpoint_completion_output_invalid")
        if set(output) != {"role", "path", "sha256", "snapshot"} or any(not isinstance(v, str) or not v for v in output.values()):
            raise ValueError("checkpoint_completion_output_invalid")
        if output["role"] != expected["role"] or output["path"] != expected["path"]:
            raise ValueError("checkpoint_completion_outputs_mismatch")
        require_hash(output["sha256"], "checkpoint_projection_hash_invalid")
        snapshot = pending_archive.with_name(f"{pending_archive.stem}.projection-{output['role']}-{output['sha256']}.json")
        if output["snapshot"] != snapshot.relative_to(repo_root).as_posix():
            raise ValueError("checkpoint_projection_snapshot_mismatch")
        if file_hash(bounded_path(repo_root, output["path"])) != output["sha256"] or file_hash(snapshot) != output["sha256"]:
            raise ValueError("checkpoint_projection_mismatch")
    return outputs


def publish_resume_state(repo_root: Path, resume_state: dict[str, Any], write_projections, *, output_dir=None, _locked=False, admitted_context=None, native_admission_reader=None) -> dict[str, Any]:
    """Pending and accepted immutable history; latest is the sole acceptance head."""
    if _native_publication_requested(resume_state, admitted_context, native_admission_reader):
        target_dir = _native_publication_input(repo_root, resume_state, output_dir, admitted_context, native_admission_reader)
    else:
        target_dir = _resolve_output_dir(repo_root, output_dir)
    with (nullcontext() if _locked else publication_lock(target_dir)):
        publication = (publication_record(repo_root, resume_state) if admitted_context is None and native_admission_reader is None else
                       publication_record(repo_root, resume_state, admitted_context=admitted_context, native_admission_reader=native_admission_reader))
        if admitted_context is None and native_admission_reader is None:
            assert_predecessor(target_dir, publication["predecessor_sha256"], repo_root=repo_root)
        else:
            _native_assert_predecessor(repo_root, target_dir, publication["predecessor_sha256"])
        candidate = write_resume_state(repo_root, resume_state, output_dir=target_dir, publish_latest=False, _locked=True)
        archive, _ = checkpoint_bytes(repo_root, candidate)
        outputs = write_projections(candidate)
        if admitted_context is None and native_admission_reader is None:
            verify_execution_identity(repo_root, publication["execution_identity"])
        else:
            verify_execution_identity(repo_root, publication["execution_identity"], admitted_context=admitted_context, native_admission_reader=native_admission_reader)
        required = requested_projections(repo_root, publication["requested"])
        if not isinstance(outputs, list) or len(outputs) != len(required):
            raise ValueError("publication_projection_set_mismatch")
        bound_outputs = []
        for output, expected in zip(outputs, required):
            output = require_object(output, "publication_projection_invalid")
            path = bounded_path(repo_root, output.get("path", ""))
            if output.get("role") != expected["role"] or path.relative_to(repo_root).as_posix() != expected["path"]:
                raise ValueError("publication_projection_set_mismatch")
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != output.get("sha256"):
                raise ValueError("publication_projection_changed")
            snapshot = archive.with_name(f"{archive.stem}.projection-{expected['role']}-{digest}.json")
            immutable_write(snapshot, data)
            bound_outputs.append({**expected, "sha256": digest, "snapshot": snapshot.relative_to(repo_root).as_posix()})
        # Raw expected hashes are now immutable candidate truth, independent of
        # the mutable completion receipt and its snapshot copies. Generic state
        # records the pending checkpoint it projected, avoiding a hash cycle.
        accepted_input = {key: value for key, value in candidate.items() if key not in {"generated_at_utc", "resume_state_paths", "checkpoint_id"}}
        accepted_input["publication"] = {**publication, "pending_checkpoint": candidate["resume_state_paths"]["timestamped"], "accepted_outputs": bound_outputs}
        accepted = write_resume_state(repo_root, accepted_input, output_dir=target_dir, publish_latest=False, _locked=True)
        accepted_archive, payload = checkpoint_bytes(repo_root, accepted)
        completion = {"checkpoint_id": accepted["checkpoint_id"], "archive_sha256": hashlib.sha256(payload).hexdigest(),
                      "execution_identity": publication["execution_identity"], "outputs": bound_outputs}
        immutable_write(accepted_archive.with_name(f"{accepted_archive.stem}.completion.json"), serialized_bytes(completion))
        verify_outputs(repo_root, bound_outputs, publication, archive)
        atomic_write(target_dir / LATEST_FILENAME, payload)
        return accepted


def load_resume_state(repo_root: Path, *, output_dir=None, expected_state: dict[str, Any] | None = None, _locked=False) -> dict[str, Any]:
    target_dir = _resolve_output_dir(repo_root, output_dir)
    with (nullcontext() if _locked else publication_lock(target_dir, create=False)):
        latest_bytes = (target_dir / LATEST_FILENAME).read_bytes()
        state = require_object(json.loads(latest_bytes), "checkpoint_envelope_invalid")
        archive, payload = checkpoint_bytes(repo_root, state)
        if archive.parent != target_dir or payload != latest_bytes or (expected_state is not None and expected_state != state):
            raise ValueError("checkpoint_not_current_accepted_publication")
        publication = publication_record(repo_root, state)
        pending = publication.get("pending_checkpoint")
        if not isinstance(pending, str) or not pending:
            raise ValueError("checkpoint_pending_reference_invalid")
        pending_archive = bounded_path(repo_root, pending)
        pending_state = require_object(json.loads(pending_archive.read_bytes()), "checkpoint_pending_envelope_invalid")
        verified_pending, _ = checkpoint_bytes(repo_root, pending_state)
        expected_pending = {key: value for key, value in publication.items() if key not in {"pending_checkpoint", "accepted_outputs"}}
        if (verified_pending != pending_archive or pending_archive.parent != target_dir
                or pending_state.get("publication") != expected_pending
                or {k: v for k, v in state.items() if k not in {"publication", "generated_at_utc", "resume_state_paths", "checkpoint_id"}}
                != {k: v for k, v in pending_state.items() if k not in {"publication", "generated_at_utc", "resume_state_paths", "checkpoint_id"}}):
            raise ValueError("checkpoint_pending_binding_mismatch")
        expected_outputs = verify_outputs(repo_root, publication.get("accepted_outputs"), publication, pending_archive)
        completion = require_object(json.loads(archive.with_name(f"{archive.stem}.completion.json").read_bytes()), "checkpoint_completion_envelope_invalid")
        if (set(completion) != {"checkpoint_id", "archive_sha256", "execution_identity", "outputs"}
                or completion["checkpoint_id"] != state["checkpoint_id"]
                or completion["archive_sha256"] != hashlib.sha256(payload).hexdigest()
                or completion["execution_identity"] != publication["execution_identity"]
                or completion["outputs"] != expected_outputs):
            raise ValueError("checkpoint_completion_mismatch")
        return state


def _native_cycle():
    from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1
    return aios_self_consuming_codex_cycle_v1


def _verify_native_identity(repo_root, identity, admitted_context, native_admission_reader, *, live):
    cycle = _native_cycle()
    if admitted_context is None or not callable(native_admission_reader):
        raise ValueError("native_admission_reader_required")
    if type(identity) is not dict:
        raise ValueError("native_execution_identity_invalid")
    expected = cycle.native_execution_identity(repo_root, admitted_context, identity.get("successful_result"),
        native_admission_reader=native_admission_reader, live=live)
    if not cycle.strict_json_equal(identity, expected):
        raise ValueError("native_execution_identity_mismatch")


def _capture_native_attempt(repo_root, minimal, identity, requested, context, reader):
    cycle = _native_cycle()
    _verify_native_identity(repo_root, identity, context, reader, live=True)
    data = cycle._native_admitted(context, reader)
    if not cycle.strict_json_equal(requested, data["requested"]):
        raise ValueError("native_requested_admission_mismatch")
    expected_minimal = {"schema": "AIOS_NATIVE_FINALIZATION.v1", "execution_identity": identity,
                        "requirement_request": identity["requirement_request"]}
    if not cycle.strict_json_equal(minimal, expected_minimal):
        raise ValueError("native_finalization_input_mismatch")
    target = _native_selected_owner(repo_root, context, reader)
    record = {"record_type": "successful_attempt", "execution_identity": identity, "finalization_input": minimal,
        "requested": requested, "required_outputs": requested_projections(repo_root, requested),
        "predecessor_sha256": _native_revision(repo_root, target)}
    path = target / ("AIOS_RESUME_ATTEMPT_" + content_hash(record) + ".json")
    _validate_native_attempt_record(repo_root, record, path, admitted_context=context,
        native_admission_reader=reader, live=True)
    try:
        with publication_lock(target):
            _native_assert_predecessor(repo_root, target, record["predecessor_sha256"])
            immutable_write(path, serialized_bytes(record))
    except Exception as exc:
        exc.native_prepared_attempt = {**record, "attempt_path": path.relative_to(repo_root).as_posix()}
        raise
    return path, record


def _native_state_semantic(attempt):
    return {"schema": "AIOS_NATIVE_PUBLICATION.v1", "result": "COMPLETE",
        "requirement_request": attempt["execution_identity"]["requirement_request"],
        "execution_identity": attempt["execution_identity"], "resume_ready": True, "safety": safety_flags()}


def _native_context_for(identity, reader):
    if not callable(reader):
        raise ValueError("native_admission_reader_required")
    from automation.orchestration.aios_abcd_autonomy_runner import RequirementReadRequest
    values = require_object(identity.get("requirement_request"), "native_requirement_request_invalid")
    if set(values) != {"task_id", "packet_id", "request_sha256", "claim_sha256", "acquired_at"}:
        raise ValueError("native_requirement_request_invalid")
    request = RequirementReadRequest(**values)
    _native_cycle()._native_request_dict(request)
    context = reader(request)
    if type(context) is not _native_cycle().NativeRequirementContext:
        raise ValueError("native_admission_context_missing")
    return context


def _native_selected_owner(repo_root, admitted_context, reader):
    cycle = _native_cycle()
    data = cycle._native_admitted(admitted_context, reader)
    requested = data.get("requested")
    requested_projections(repo_root, requested)
    if (requested["write_resume"] is not True or requested["write_control"] is not False
            or requested["emit_continuation_controller"] is not False):
        raise ValueError("native_initial_projection_profile_invalid")
    root = cycle.bound_path(str(repo_root))
    target = cycle._native_nonprivate_path(str(root / requested["resume_dir"]), anchor=root)
    if target != _resolve_output_dir(root, requested["resume_dir"]):
        raise ValueError("native_selected_owner_mismatch")
    return target


def _native_owner_path(repo_root, value, target, kind):
    import re
    cycle = _native_cycle()
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError("native_owner_path_invalid")
    raw = Path(value)
    raw = raw if raw.is_absolute() else repo_root / raw
    path = cycle._native_nonprivate_path(str(raw), anchor=cycle.bound_path(str(repo_root)))
    patterns = {
        "attempt": r"AIOS_RESUME_ATTEMPT_[0-9a-f]{64}\.json",
        "failure": r"AIOS_RESUME_FAILURE_[0-9a-f]{64}\.json",
        "archive": r"AIOS_RESUME_STATE_[0-9]{8}_[0-9]{6}Z_[0-9a-f]{64}\.json",
        "completion": r"AIOS_RESUME_STATE_[0-9]{8}_[0-9]{6}Z_[0-9a-f]{64}\.completion\.json",
        "snapshot": r"AIOS_RESUME_STATE_[0-9]{8}_[0-9]{6}Z_[0-9a-f]{64}\.projection-generic-[0-9a-f]{64}\.json",
        "latest": r"AIOS_RESUME_STATE_latest\.json",
    }
    if path.parent != target or kind not in patterns or re.fullmatch(patterns[kind], path.name) is None:
        raise ValueError("native_selected_owner_or_filename_mismatch")
    return path


def _native_revision(repo_root, target):
    path = _native_owner_path(repo_root, target / LATEST_FILENAME, target, "latest")
    if not path.exists():
        return None
    return hashlib.sha256(_native_cycle()._native_file(path)).hexdigest()


def _native_assert_predecessor(repo_root, target, predecessor):
    if predecessor is not None:
        require_hash(predecessor, "native_predecessor_invalid")
    if _native_revision(repo_root, target) != predecessor:
        raise ValueError("checkpoint_stale_predecessor")
    latest = _native_owner_path(repo_root, target / LATEST_FILENAME, target, "latest")
    if latest.exists():
        cycle = _native_cycle()
        raw = cycle._native_file(latest)
        state = cycle._native_json(raw)
        _, payload = _native_checkpoint_bytes(repo_root, state, target)
        if payload != raw or type(state.get("publication")) is not dict:
            raise ValueError("native_frontier_invalid")


def _native_checkpoint_bytes(repo_root, state, target):
    cycle = _native_cycle()
    if type(state) is not dict:
        raise ValueError("native_checkpoint_envelope_invalid")
    paths = state.get("resume_state_paths")
    if (type(paths) is not dict or set(paths) != {"timestamped", "latest"}
            or any(type(value) is not str for value in paths.values())):
        raise ValueError("native_checkpoint_paths_invalid")
    archive = _native_owner_path(repo_root, paths["timestamped"], target, "archive")
    latest = _native_owner_path(repo_root, paths["latest"], target, "latest")
    if (paths["timestamped"] != archive.relative_to(repo_root).as_posix()
            or paths["latest"] != latest.relative_to(repo_root).as_posix()):
        raise ValueError("native_checkpoint_path_encoding_invalid")
    checkpoint_id = require_hash(state.get("checkpoint_id"), "native_checkpoint_id_invalid")
    cycle._native_utc_timestamp(state.get("generated_at_utc"))
    semantic = {key: value for key, value in state.items() if key not in {"generated_at_utc", "resume_state_paths", "checkpoint_id"}}
    if content_hash(semantic) != checkpoint_id or not archive.stem.endswith("_" + checkpoint_id):
        raise ValueError("native_checkpoint_content_mismatch")
    payload = cycle._native_file(archive)
    if not cycle.strict_json_equal(cycle._native_json(payload), state):
        raise ValueError("native_checkpoint_archive_mismatch")
    return archive, payload


def _validate_native_attempt_record(repo_root, record, path, *, admitted_context, native_admission_reader, live):
    cycle = _native_cycle()
    target = _native_selected_owner(repo_root, admitted_context, native_admission_reader)
    path = _native_owner_path(repo_root, path, target, "attempt")
    if type(record) is not dict or set(record) != {"record_type", "execution_identity", "finalization_input", "requested", "required_outputs", "predecessor_sha256"}:
        raise ValueError("native_attempt_fields_invalid")
    if record["record_type"] != "successful_attempt" or path.name != f"AIOS_RESUME_ATTEMPT_{content_hash(record)}.json":
        raise ValueError("native_attempt_content_mismatch")
    identity = record["execution_identity"]
    if type(identity) is not dict:
        raise ValueError("native_attempt_identity_invalid")
    _verify_native_identity(repo_root, identity, admitted_context, native_admission_reader, live=live)
    expected_minimal = {"schema": "AIOS_NATIVE_FINALIZATION.v1", "execution_identity": identity,
                        "requirement_request": identity["requirement_request"]}
    if not cycle.strict_json_equal(record["finalization_input"], expected_minimal):
        raise ValueError("native_finalization_input_mismatch")
    data = cycle._native_admitted(admitted_context, native_admission_reader)
    if not cycle.strict_json_equal(record["requested"], data["requested"]):
        raise ValueError("native_requested_admission_mismatch")
    if not cycle.strict_json_equal(record["required_outputs"], requested_projections(repo_root, data["requested"])):
        raise ValueError("native_attempt_owner_or_outputs_mismatch")
    if record["predecessor_sha256"] is not None:
        require_hash(record["predecessor_sha256"], "native_predecessor_invalid")
    return record


def _load_native_attempt(repo_root, path, *, admitted_context, native_admission_reader, live):
    cycle = _native_cycle()
    target = _native_selected_owner(repo_root, admitted_context, native_admission_reader)
    path = _native_owner_path(repo_root, path, target, "attempt")
    record = cycle._native_json(cycle._native_file(path))
    return _validate_native_attempt_record(repo_root, record, path, admitted_context=admitted_context,
        native_admission_reader=native_admission_reader, live=live)


def _native_generic_projection(attempt, pending):
    return {"schema": "AIOS_NATIVE_FINALIZATION.v1", "result": "PENDING_COMMIT",
        "execution_identity": attempt["execution_identity"], "resume_state": pending,
        "finalization": {"status": "pending", "candidate_path": pending["publication"]["attempt_path"]}}


def _verify_archived_native_state(repo_root, state, target_dir, reader):
    cycle = _native_cycle()
    archive, payload = _native_checkpoint_bytes(repo_root, state, target_dir)
    if archive.parent != target_dir:
        raise ValueError("native_archive_owner_mismatch")
    publication = require_object(state.get("publication"), "native_publication_missing")
    identity = require_object(publication.get("execution_identity"), "native_identity_missing")
    if identity.get("identity_contract") != cycle.NATIVE_IDENTITY:
        raise ValueError("native_lineage_unsupported_identity")
    context = _native_context_for(identity, reader)
    attempt_path = bounded_path(repo_root, publication.get("attempt_path", ""))
    attempt = _load_native_attempt(repo_root, attempt_path, admitted_context=context, native_admission_reader=reader, live=False)
    expected_keys = {*attempt, "attempt_path", "pending_checkpoint", "accepted_outputs"} - {"record_type"}
    # Existing publication carries record_type too, as returned by capture.
    expected_keys.add("record_type")
    if set(publication) != expected_keys:
        raise ValueError("native_publication_fields_invalid")
    for key, value in attempt.items():
        if not cycle.strict_json_equal(publication.get(key), value):
            raise ValueError("native_publication_attempt_mismatch")
    semantic = {key: value for key, value in state.items() if key not in {"generated_at_utc", "resume_state_paths", "checkpoint_id"}}
    if not cycle.strict_json_equal(semantic, {**_native_state_semantic(attempt), "publication": publication}):
        raise ValueError("native_state_envelope_mismatch")
    if not cycle.strict_json_equal(publication["execution_identity"], state.get("execution_identity")):
        raise ValueError("native_state_identity_mismatch")
    pending_path = _native_owner_path(repo_root, publication.get("pending_checkpoint", ""), target_dir, "archive")
    pending = require_object(cycle._native_json(cycle._native_file(pending_path)), "native_pending_invalid")
    verified_pending, _ = _native_checkpoint_bytes(repo_root, pending, target_dir)
    if verified_pending != pending_path or pending_path.parent != target_dir:
        raise ValueError("native_pending_owner_mismatch")
    expected_pending = {key: value for key, value in publication.items() if key not in {"pending_checkpoint", "accepted_outputs"}}
    excluded = {"publication", "generated_at_utc", "resume_state_paths", "checkpoint_id"}
    if (not cycle.strict_json_equal(pending.get("publication"), expected_pending)
            or not cycle.strict_json_equal({k:v for k,v in pending.items() if k not in excluded}, {k:v for k,v in state.items() if k not in excluded})):
        raise ValueError("native_pending_binding_mismatch")
    outputs = publication.get("accepted_outputs")
    required = requested_projections(repo_root, publication["requested"])
    if type(outputs) is not list or len(outputs) != len(required):
        raise ValueError("native_archive_output_set_mismatch")
    for output, expected in zip(outputs, required, strict=True):
        if type(output) is not dict or set(output) != {"role", "path", "sha256", "snapshot"}:
            raise ValueError("native_archive_output_invalid")
        digest = require_hash(output.get("sha256"), "native_archive_output_hash_invalid")
        snapshot = pending_path.with_name(f"{pending_path.stem}.projection-{expected['role']}-{digest}.json")
        if (output.get("role") != expected["role"] or output.get("path") != expected["path"]
                or output.get("snapshot") != snapshot.relative_to(repo_root).as_posix()):
            raise ValueError("native_archive_projection_mismatch")
        snapshot = _native_owner_path(repo_root, snapshot, target_dir, "snapshot")
        expected_projection = serialized_bytes(_native_generic_projection(attempt, pending))
        if (expected["role"] != "generic" or hashlib.sha256(expected_projection).hexdigest() != digest
                or cycle._native_file(snapshot) != expected_projection):
            raise ValueError("native_archive_projection_semantic_mismatch")
    completion_path = _native_owner_path(repo_root, archive.with_name(archive.stem + ".completion.json"), target_dir, "completion")
    completion = require_object(cycle._native_json(cycle._native_file(completion_path)), "native_completion_invalid")
    expected_completion = {"checkpoint_id": state["checkpoint_id"], "archive_sha256": hashlib.sha256(payload).hexdigest(),
        "execution_identity": identity, "outputs": outputs}
    if not cycle.strict_json_equal(completion, expected_completion):
        raise ValueError("native_completion_mismatch")
    return context, publication


def _existing_native_attempt(repo_root, *, admitted_context, native_admission_reader):
    cycle = _native_cycle()
    data = cycle._verify_native_context(repo_root, admitted_context, native_admission_reader, live=False)
    target = _native_selected_owner(repo_root, admitted_context, native_admission_reader)
    found = []
    if target.exists():
        for path in target.glob("AIOS_RESUME_ATTEMPT_*.json"):
            path = _native_owner_path(repo_root, path, target, "attempt")
            record = require_object(cycle._native_json(cycle._native_file(path)), "native_attempt_envelope_invalid")
            identity = record.get("execution_identity")
            if type(identity) is not dict or identity.get("identity_contract") != cycle.NATIVE_IDENTITY:
                continue
            if cycle.strict_json_equal(identity.get("requirement_request"), cycle._native_request_dict(admitted_context.request)):
                _load_native_attempt(repo_root, path, admitted_context=admitted_context, native_admission_reader=native_admission_reader, live=False)
                found.append(path)
    if len(found) > 1:
        raise ValueError("native_attempt_conflict")
    if found:
        return found[0]
    return None


def find_native_attempt(repo_root, *, admitted_context, native_admission_reader):
    path = _existing_native_attempt(repo_root, admitted_context=admitted_context, native_admission_reader=native_admission_reader)
    if path is not None:
        return path
    data = _native_cycle()._native_admitted(admitted_context, native_admission_reader)
    if Path(data["descriptor"]["receipt_path"]).exists():
        raise ValueError("native_validator_existing_receipt_without_complete_attempt_no_replay")
    return None


def load_native_requirement(repo_root, *, output_dir, expected_request, admitted_context, native_admission_reader):
    cycle = _native_cycle()
    data = cycle._verify_native_context(repo_root, admitted_context, native_admission_reader, live=False)
    if not cycle.strict_json_equal(cycle._native_request_dict(expected_request), cycle._native_request_dict(admitted_context.request)):
        raise ValueError("native_expected_request_mismatch")
    target = _native_selected_owner(repo_root, admitted_context, native_admission_reader)
    selected = cycle._native_nonprivate_path(str(repo_root / output_dir), anchor=cycle.bound_path(str(repo_root)))
    if selected != target:
        raise ValueError("native_selected_owner_mismatch")
    if target != _resolve_output_dir(repo_root, data["requested"]["resume_dir"]):
        raise ValueError("native_selected_owner_mismatch")
    if not target.exists():
        find_native_attempt(repo_root, admitted_context=admitted_context, native_admission_reader=native_admission_reader)
        return None
    with publication_lock(target, create=False):
        latest = _native_owner_path(repo_root, target / LATEST_FILENAME, target, "latest")
        if not latest.exists():
            find_native_attempt(repo_root, admitted_context=admitted_context, native_admission_reader=native_admission_reader)
            return None
        raw = cycle._native_file(latest)
        state = require_object(cycle._native_json(raw), "native_latest_invalid")
        seen = set()
        selected_state = None
        while True:
            archive, payload = _native_checkpoint_bytes(repo_root, state, target)
            digest = hashlib.sha256(payload).hexdigest()
            if digest in seen or archive.parent != target or not seen and payload != raw:
                raise ValueError("native_lineage_cycle_or_head_mismatch")
            seen.add(digest)
            context, publication = _verify_archived_native_state(repo_root, state, target, native_admission_reader)
            if cycle.strict_json_equal(cycle._native_request_dict(context.request), cycle._native_request_dict(expected_request)):
                if context.context_json != admitted_context.context_json:
                    raise ValueError("native_lineage_context_conflict")
                if selected_state is not None:
                    raise ValueError("native_lineage_duplicate_requirement")
                selected_state = state
            predecessor = publication["predecessor_sha256"]
            if predecessor is None:
                break
            require_hash(predecessor, "native_predecessor_invalid")
            matches = []
            for path in target.glob("AIOS_RESUME_STATE_*.json"):
                if "." in path.stem or path.name == LATEST_FILENAME:
                    continue
                path = _native_owner_path(repo_root, path, target, "archive")
                candidate_raw = cycle._native_file(path)
                if hashlib.sha256(candidate_raw).hexdigest() == predecessor:
                    candidate = require_object(cycle._native_json(candidate_raw), "native_predecessor_envelope_invalid")
                    selected, _ = _native_checkpoint_bytes(repo_root, candidate, target)
                    if selected != path:
                        raise ValueError("native_predecessor_filename_mismatch")
                    matches.append(candidate)
            if len(matches) != 1:
                raise ValueError("native_predecessor_missing_or_ambiguous")
            state = matches[0]
        if selected_state is not None:
            return selected_state
        pending = find_native_attempt(repo_root, admitted_context=admitted_context, native_admission_reader=native_admission_reader)
        if pending is not None:
            record = _load_native_attempt(repo_root, pending, admitted_context=admitted_context, native_admission_reader=native_admission_reader, live=False)
            if record["predecessor_sha256"] != _native_revision(repo_root, target):
                raise ValueError("native_pending_stale_predecessor")
        return None


def _native_pending_attempt(repo_root, pending, target, context, reader, expected_identity):
    cycle = _native_cycle()
    _native_checkpoint_bytes(repo_root, pending, target)
    publication = pending.get("publication")
    if type(publication) is not dict or type(publication.get("attempt_path")) is not str:
        raise ValueError("native_pending_publication_invalid")
    path = _native_owner_path(repo_root, publication["attempt_path"], target, "attempt")
    attempt = _load_native_attempt(repo_root, path, admitted_context=context, native_admission_reader=reader, live=False)
    expected_publication = {**attempt, "attempt_path": path.relative_to(repo_root).as_posix()}
    semantic = {key: value for key, value in pending.items() if key not in {"generated_at_utc", "resume_state_paths", "checkpoint_id"}}
    if (not cycle.strict_json_equal(attempt["execution_identity"], expected_identity)
            or not cycle.strict_json_equal(publication, expected_publication)
            or not cycle.strict_json_equal(semantic, {**_native_state_semantic(attempt), "publication": expected_publication})):
        raise ValueError("native_pending_projection_binding_mismatch")
    return attempt


def _native_publication_requested(state, context, reader):
    if context is not None or reader is not None:
        return True
    if type(state) is not dict:
        return False
    publication = state.get("publication")
    candidates = [state.get("execution_identity")]
    if type(publication) is dict:
        candidates.append(publication.get("execution_identity"))
    return (state.get("schema") == "AIOS_NATIVE_PUBLICATION.v1"
        or any(type(value) is dict and "identity_contract" in value for value in candidates))


def _native_publication_input(repo_root, state, output_dir, context, reader):
    cycle = _native_cycle()
    target = _native_selected_owner(repo_root, context, reader)
    raw_target = repo_root / output_dir if output_dir is not None else repo_root / DEFAULT_OUTPUT_DIR
    selected = cycle._native_nonprivate_path(str(raw_target), anchor=cycle.bound_path(str(repo_root)))
    if selected != target:
        raise ValueError("native_selected_owner_mismatch")
    cycle._verify_native_context(repo_root, context, reader, live=True)
    if type(state) is not dict:
        raise ValueError("native_publication_input_invalid")
    publication = publication_record(repo_root, state, admitted_context=context, native_admission_reader=reader)
    expected_fields = {"record_type", "execution_identity", "finalization_input", "requested", "required_outputs", "predecessor_sha256", "attempt_path"}
    if (set(publication) != expected_fields
            or not cycle.strict_json_equal(state, {**_native_state_semantic(publication), "publication": publication})):
        raise ValueError("native_publication_input_invalid")
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build one sanitized AIOS resume-state preview.")
    parser.add_argument("--repo-root", default=None, help="Optional repository root.")
    parser.add_argument("--write", action="store_true", help="Write resume state under Reports/aios_resume.")
    parser.add_argument("--output-dir", default=None, help="Optional output dir under Reports/aios_resume.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    resume_state = build_resume_state({"schema": INPUT_SCHEMA, "goal": "forex-paper-bot", "result": "preview_only"})
    if args.write:
        print("preview_write_refused: use the verified wake/continue publication route", file=sys.stderr)
        return 2
    print(json.dumps(resume_state, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
