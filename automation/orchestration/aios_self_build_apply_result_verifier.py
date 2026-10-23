from __future__ import annotations

import argparse
import json
import hashlib
import re
import stat
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


SCHEMA = "AIOS_SELF_BUILD_APPLY_RESULT_VERIFIER.v1"
SANDBOX_1312_MARKER = "createprocessasuserw failed: 1312"


def _base_safety() -> dict[str, bool]:
    return {
        "verifier_only": True,
        "commands_executed": False,
        "files_written": False,
        "reports_written": False,
        "network_access": False,
        "codex_launch": False,
        "chatgpt_api_call": False,
        "broker": False,
        "live_trading": False,
        "credentials": False,
        "real_orders": False,
        "real_webhooks": False,
        "scheduler": False,
        "daemon": False,
        "worker_dispatch": False,
        "queue_mutation": False,
        "approval_mutation": False,
        "git_add": False,
        "git_commit": False,
        "git_push": False,
        "merge": False,
        "destructive_action": False,
        "background_runtime": False,
        "sandbox_1312_blocker": False,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bounded_path(path_text: str) -> bool:
    parsed = PurePosixPath(path_text)
    return bool(path_text) and "\\" not in path_text and not parsed.is_absolute() and ".." not in parsed.parts


def _normalize_paths(paths: Any) -> list[str]:
    return [str(path) for path in _as_list(paths) if _bounded_path(str(path))]


def _payload_text(*payloads: Any) -> str:
    return " ".join(json.dumps(payload, sort_keys=True).lower() for payload in payloads if payload is not None)


def _status_paths(status: Any) -> list[str]:
    if isinstance(status, dict):
        for key in ("changed_files", "files_changed", "files", "paths"):
            value = status.get(key)
            if isinstance(value, list):
                return _normalize_paths(value)
        status = status.get("status_text", status.get("stdout", ""))
    if isinstance(status, list):
        return _normalize_paths(status)
    output: list[str] = []
    for raw_line in str(status or "").splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("##"):
            continue
        path_text = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1].strip()
        if _bounded_path(path_text):
            output.append(path_text)
    return sorted(set(output))


PRESERVATION_ASSURANCE = "supplied_manifest_comparison_only"
PRESERVATION_CONTEXT_SCHEMA = "AIOS_APPLY_PRESERVATION_CONTEXT.v1"
PRESERVATION_MANIFEST_SCHEMA = "AIOS_WORKTREE_STATE_MANIFEST.v1"
PRESERVATION_MANIFEST_LIMIT = 16 * 1024 * 1024
PRESERVATION_ERRORS = {
    "private_refused", "reparse_refused", "nonregular_refused", "read_failed",
    "stat_failed", "identity_unavailable", "unstable", "budget_exceeded",
}


class _PreservationError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _preservation_require(condition: bool, reason: str) -> None:
    if not condition:
        raise _PreservationError(reason)


def _preservation_object(value: Any, fields: set[str], reason: str) -> dict[str, Any]:
    _preservation_require(type(value) is dict and all(type(key) is str for key in value) and set(value) == fields, reason)
    return value


def _preservation_text(value: Any) -> bool:
    return type(value) is str and bool(value) and "\0" not in value


def _preservation_hash(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _preservation_integer(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _preservation_canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def _preservation_same(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return all(type(key) is str for key in left) and all(type(key) is str for key in right) and set(left) == set(right) and all(_preservation_same(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_preservation_same(a, b) for a, b in zip(left, right))
    if type(left) in {str, int, bool, float, type(None)}:
        return _preservation_canonical(left) == _preservation_canonical(right)
    return False


def _preservation_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        _preservation_require(key not in output, "preservation_manifest_invalid")
        output[key] = value
    return output


def _preservation_nonfinite(_value: str) -> None:
    raise _PreservationError("preservation_manifest_invalid")


def _preservation_time(value: Any, reason: str) -> datetime:
    _preservation_require(type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value) is not None, reason)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except (ValueError, OverflowError) as error:
        raise _PreservationError(reason) from error
    _preservation_require(parsed.isoformat(timespec="microseconds").replace("+00:00", "Z") == value, reason)
    return parsed


def _preservation_path(value: Any) -> bytes:
    _preservation_require(_preservation_text(value), "preservation_manifest_invalid")
    raw = value.encode("utf-8", "surrogateescape")
    _preservation_require(not any(part in {b"", b".", b".."} for part in raw.split(b"/")), "preservation_manifest_invalid")
    return raw


def _preservation_children(value: Any) -> list[str]:
    _preservation_require(type(value) is list, "preservation_census_invalid")
    for child in value:
        raw = _preservation_path(child)
        _preservation_require(b"/" not in raw, "preservation_census_invalid")
    _preservation_require(value == sorted(set(value), key=_preservation_path), "preservation_census_invalid")
    return value


def _preservation_identity(value: Any, reason: str) -> None:
    record = _preservation_object(value, {"device", "inode"}, reason)
    _preservation_require(_preservation_integer(record["device"]) and _preservation_integer(record["inode"], 1), reason)


def _preservation_repository(value: Any) -> None:
    reason = "preservation_context_invalid"
    record = _preservation_object(value, {"resolved", "reason", "repo_root", "git_dir", "branch", "symbolic_ref", "detached", "commit"}, reason)
    _preservation_require(record["resolved"] is True and type(record["reason"]) is str and record["reason"] == "resolved", reason)
    _preservation_require(all(_preservation_text(record[key]) for key in ("repo_root", "git_dir", "branch", "commit")), reason)
    _preservation_require(type(record["detached"]) is bool, reason)
    _preservation_require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", record["commit"]) is not None, reason)
    for key in ("repo_root", "git_dir"):
        path = record[key]
        _preservation_require(PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute(), reason)
    if record["detached"]:
        _preservation_require(record["branch"] == "detached" and record["symbolic_ref"] is None, reason)
    else:
        _preservation_require(type(record["symbolic_ref"]) is str and record["symbolic_ref"] == "refs/heads/" + record["branch"], reason)


def _preservation_context(context: Any, queue: dict[str, Any], executor: dict[str, Any], allowed: Any, maximum: Any) -> dict[str, Any]:
    reason = "preservation_context_invalid"
    _preservation_require(type(queue) is dict and type(executor) is dict and all(type(key) is str for key in queue) and all(type(key) is str for key in executor), reason)
    record = _preservation_object(context, {"schema", "binding", "execution", "before_manifest_sha256", "after_manifest_sha256"}, reason)
    _preservation_require(type(record["schema"]) is str and record["schema"] == PRESERVATION_CONTEXT_SCHEMA, reason)
    _preservation_require(_preservation_hash(record["before_manifest_sha256"]) and _preservation_hash(record["after_manifest_sha256"]), reason)
    binding = _preservation_object(record["binding"], {"task", "repository_identity", "interval_ref", "allowed_paths", "max_files_changed", "implementation_manifest", "capture_contract"}, reason)
    task = _preservation_object(binding["task"], {"task_id", "packet_id", "action_id", "attempt_id"}, reason)
    _preservation_require(all(_preservation_text(item) for item in task.values()), reason)
    _preservation_require(_preservation_text(binding["interval_ref"]), reason)
    _preservation_repository(binding["repository_identity"])
    paths = binding["allowed_paths"]
    _preservation_require(type(paths) is list and bool(paths), reason)
    for path in paths:
        _preservation_path(path)
        _preservation_require(_bounded_path(path), reason)
    _preservation_require(len(paths) == len(set(paths)), reason)
    _preservation_require(_preservation_integer(binding["max_files_changed"], 1), reason)
    _preservation_require(type(allowed) is list and _preservation_same(allowed, paths), "preservation_identity_mismatch")
    _preservation_require(type(maximum) is int and maximum == binding["max_files_changed"], "preservation_identity_mismatch")
    implementation = binding["implementation_manifest"]
    _preservation_require(type(implementation) is dict and bool(implementation), reason)
    _preservation_require(all(_preservation_text(key) and _preservation_hash(value) for key, value in implementation.items()), reason)
    capture = _preservation_object(binding["capture_contract"], {"schema", "domain", "platform", "rules_sha256"}, reason)
    _preservation_require(type(capture["schema"]) is str and capture["schema"] == "AIOS_FULL_WORKTREE_STATE_CAPTURE.v1" and type(capture["domain"]) is str and capture["domain"] == "entire_worktree_subtree", reason)
    _preservation_require(type(capture["platform"]) is str and capture["platform"] in {"nt", "posix"} and _preservation_hash(capture["rules_sha256"]), reason)
    if capture["platform"] == "nt":
        _preservation_require(all(not PureWindowsPath(path).drive and ":" not in path for path in paths), reason)
    execution = _preservation_object(record["execution"], {"record_sha256", "started_at_utc", "ended_at_utc"}, reason)
    _preservation_require(_preservation_hash(execution["record_sha256"]), reason)
    start = _preservation_time(execution["started_at_utc"], reason)
    end = _preservation_time(execution["ended_at_utc"], reason)
    _preservation_require(start <= end, "preservation_interval_mismatch")
    for key in ("task_id", "packet_id", "attempt_id"):
        _preservation_require(_preservation_same(queue.get(key), task[key]) and _preservation_same(executor.get(key), task[key]), "preservation_identity_mismatch")
    _preservation_require(_preservation_same(queue.get("action_id"), task["action_id"]) and _preservation_same(executor.get("selected_action"), task["action_id"]), "preservation_identity_mismatch")
    for source in (queue, executor):
        _preservation_require(_preservation_same(source.get("allowed_paths"), paths), "preservation_identity_mismatch")
    _preservation_require(_preservation_same(executor.get("max_files_changed"), binding["max_files_changed"]), "preservation_identity_mismatch")
    _preservation_require(_preservation_same(executor.get("repository_identity"), binding["repository_identity"]), "preservation_identity_mismatch")
    _preservation_require(_preservation_same(executor.get("interval_ref"), binding["interval_ref"]), "preservation_interval_mismatch")
    for key, expected in (("execution_record_sha256", execution["record_sha256"]), ("execution_started_at_utc", execution["started_at_utc"]), ("execution_ended_at_utc", execution["ended_at_utc"])):
        _preservation_require(_preservation_same(executor.get(key), expected), "preservation_interval_mismatch")
    return record


def _preservation_node(record: Any, platform: str, root: bool = False, *, nonprivate: bool = False) -> None:
    reason = "preservation_manifest_invalid"
    _preservation_require(type(record) is dict, reason)
    kind = "directory" if root else record.get("kind")
    if kind == "private_boundary" and nonprivate and not root:
        _preservation_object(record, {"kind", "contents_observed", "identity", "file_attributes"}, reason)
        _preservation_require(record["contents_observed"] is False and platform == "nt", reason)
        _preservation_identity(record["identity"], reason)
        _preservation_require(_preservation_integer(record["file_attributes"]), reason)
        return
    if kind == "absent":
        _preservation_object(record, {"kind"}, reason)
        return
    if kind == "unobserved":
        _preservation_object(record, {"kind", "reason"}, reason)
        _preservation_require(type(record["reason"]) is str and record["reason"] in PRESERVATION_ERRORS, reason)
        return
    if root:
        fields = {"mode", "identity", "children"}
    elif kind == "directory":
        fields = {"kind", "mode", "identity", "children", "file_attributes"}
    elif kind == "file":
        fields = {"kind", "sha256", "size", "mode", "identity", "mtime_ns", "ctime_ns", "file_attributes"}
    else:
        raise _PreservationError(reason)
    _preservation_object(record, fields, reason)
    _preservation_require(_preservation_integer(record["mode"]), reason)
    _preservation_require(stat.S_ISDIR(record["mode"]) if kind == "directory" else stat.S_ISREG(record["mode"]), reason)
    _preservation_identity(record["identity"], reason)
    if not root:
        attributes = record["file_attributes"]
        if platform == "nt":
            _preservation_require(_preservation_integer(attributes) and not attributes & 0x400, reason)
            _preservation_require(bool(attributes & 0x10) == (kind == "directory"), reason)
        else:
            _preservation_require(attributes is None, reason)
    if kind == "directory":
        _preservation_children(record["children"])
    else:
        _preservation_require(_preservation_hash(record["sha256"]), reason)
        _preservation_require(all(_preservation_integer(record[key]) for key in ("size", "mtime_ns", "ctime_ns")), reason)


def _preservation_manifest(raw: Any, context: dict[str, Any], phase: str, *, nonprivate: bool = False) -> dict[str, Any]:
    reason = "preservation_manifest_invalid"
    _preservation_require(type(raw) is bytes and 0 < len(raw) <= PRESERVATION_MANIFEST_LIMIT, reason)
    _preservation_require(hashlib.sha256(raw).hexdigest() == context[phase + "_manifest_sha256"], "preservation_manifest_hash_mismatch")
    record = json.loads(raw.decode("ascii"), object_pairs_hook=_preservation_pairs, parse_constant=_preservation_nonfinite)
    _preservation_require(_preservation_canonical(record) == raw, reason)
    _preservation_object(record, {"schema", "binding_sha256", "phase", "captured_at_utc", "coverage", "root_state", "entries"}, reason)
    schema = "AIOS_NONPRIVATE_WORKTREE_STATE_MANIFEST.v1" if nonprivate else PRESERVATION_MANIFEST_SCHEMA
    _preservation_require(record["schema"] == schema and type(record["phase"]) is str and record["phase"] == phase, reason)
    expected = hashlib.sha256(_preservation_canonical(context["binding"])).hexdigest()
    _preservation_require(record["binding_sha256"] == expected, "preservation_binding_mismatch")
    stamp = _preservation_time(record["captured_at_utc"], reason)
    execution = context["execution"]
    bound = _preservation_time(execution["started_at_utc"] if phase == "before" else execution["ended_at_utc"], reason)
    _preservation_require(stamp <= bound if phase == "before" else stamp >= bound, "preservation_interval_mismatch")
    fields = {"enumeration_complete", "inspection_complete", "errors"}
    if nonprivate:
        fields = {"enumeration_complete", "nonprivate_inspection_complete", "private_contents_observed", "private_boundary_paths", "errors"}
    coverage = _preservation_object(record["coverage"], fields, reason)
    inspection_key = "nonprivate_inspection_complete" if nonprivate else "inspection_complete"
    _preservation_require(type(coverage["enumeration_complete"]) is bool and type(coverage[inspection_key]) is bool and type(coverage["errors"]) is list, reason)
    if nonprivate:
        _preservation_require(coverage["private_contents_observed"] is False, reason)
        paths = coverage["private_boundary_paths"]
        _preservation_require(type(paths) is list and all(type(path) is str for path in paths), reason)
        for path in paths:
            _preservation_path(path)
        _preservation_require(paths == sorted(set(paths)), reason)
    for error in coverage["errors"]:
        _preservation_object(error, {"path", "reason"}, reason)
        if error["path"] != ".":
            _preservation_path(error["path"])
        _preservation_require(type(error["reason"]) is str and error["reason"] in PRESERVATION_ERRORS, reason)
    platform = context["binding"]["capture_contract"]["platform"]
    _preservation_node(record["root_state"], platform, root=True)
    entries = record["entries"]
    _preservation_require(type(entries) is dict, reason)
    for path, node in entries.items():
        _preservation_path(path)
        _preservation_node(node, platform, nonprivate=nonprivate)
        if nonprivate:
            from automation.orchestration.aios_repo_state_evidence import _full_capture_private
            _preservation_require(_full_capture_private(path) == (node["kind"] == "private_boundary"), reason)
    if nonprivate:
        boundaries = sorted(path for path, node in entries.items() if node["kind"] == "private_boundary")
        _preservation_require(coverage["private_boundary_paths"] == boundaries, reason)
    present = {path: node for path, node in entries.items() if node["kind"] != "absent"}
    children_by_parent: dict[str | None, list[str]] = {}
    path_children: dict[str, dict[str, Any]] = {path: {} for path in present}
    root_children_index: dict[str, Any] = {}
    for path in present:
        parent, child = path.rsplit("/", 1) if "/" in path else (None, path)
        if parent is not None:
            _preservation_require(parent in present and present[parent]["kind"] == "directory", "preservation_census_invalid")
        children_by_parent.setdefault(parent, []).append(child)
        parent_children = root_children_index if parent is None else path_children[parent]
        parent_children[child] = (present[path]["kind"], path_children[path])
    for children in children_by_parent.values():
        children.sort(key=_preservation_path)
    _preservation_require(record["root_state"]["children"] == children_by_parent.get(None, []), "preservation_census_invalid")
    for path, node in present.items():
        if node["kind"] == "directory":
            _preservation_require(node["children"] == children_by_parent.get(path, []), "preservation_census_invalid")
    allowed = set(context["binding"]["allowed_paths"])
    for path in allowed:
        _preservation_require(path in entries, "preservation_census_invalid")
    for path, node in entries.items():
        if node["kind"] == "absent":
            _preservation_require(path in allowed, "preservation_census_invalid")
            parts = path.split("/")
            children_index = root_children_index
            for part in parts[:-1]:
                ancestor = children_index.get(part)
                if ancestor is None:
                    break
                kind, children_index = ancestor
                _preservation_require(kind == "directory", "preservation_census_invalid")
    if not coverage["enumeration_complete"] or not coverage[inspection_key] or coverage["errors"] or any(node["kind"] == "unobserved" for node in entries.values()):
        raise _PreservationError("preservation_coverage_incomplete")
    return record


def _preservation_result(context: Any, before: Any, after: Any, queue: dict[str, Any], executor: dict[str, Any], allowed: Any, maximum: Any) -> dict[str, Any]:
    output: dict[str, Any] = {
        "preservation_status": "missing", "preservation_comparison_passed": False,
        "preservation_assurance": PRESERVATION_ASSURANCE, "preservation_reasons": [],
        "before_manifest_sha256": hashlib.sha256(before).hexdigest() if type(before) is bytes and len(before) <= PRESERVATION_MANIFEST_LIMIT else None,
        "after_manifest_sha256": hashlib.sha256(after).hexdigest() if type(after) is bytes and len(after) <= PRESERVATION_MANIFEST_LIMIT else None,
        "before_entry_count": None, "after_entry_count": None, "changed_files": None,
        "changed_file_count": None, "unexpected_files": None,
        "preservation_root_changed": None,
        "file_count_ok": False, "allowed_paths_ok": False,
    }
    if context is None and before is None and after is None and executor.get("command_executed") is not True:
        output["preservation_status"] = "not_evaluated_pre_execution"
        return output
    if context is None or before is None or after is None:
        output["preservation_reasons"] = ["preservation_evidence_missing"]
        return output
    try:
        verified = _preservation_context(context, queue, executor, allowed, maximum)
        prior = _preservation_manifest(before, verified, "before")
        current = _preservation_manifest(after, verified, "after")
        changed = _changed_files(prior, current)
        root_changed = any(not _preservation_same(prior["root_state"][key], current["root_state"][key]) for key in ("mode", "identity"))
        if root_changed:
            changed = [".", *changed]
            output["preservation_reasons"] = ["preservation_root_changed"]
        allowed_set = set(verified["binding"]["allowed_paths"])
        unexpected = [path for path in changed if path not in allowed_set]
        output.update({
            "preservation_status": "compared", "changed_files": changed,
            "preservation_root_changed": root_changed,
            "changed_file_count": len(changed), "unexpected_files": unexpected,
            "before_entry_count": len(prior["entries"]), "after_entry_count": len(current["entries"]),
            "file_count_ok": len(changed) <= verified["binding"]["max_files_changed"],
            "allowed_paths_ok": not unexpected,
        })
        output["preservation_comparison_passed"] = not root_changed and not unexpected and output["file_count_ok"]
    except _PreservationError as error:
        output["preservation_status"] = "incomplete" if error.reason == "preservation_coverage_incomplete" else "invalid"
        output["preservation_reasons"] = [error.reason]
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        output["preservation_status"] = "invalid"
        output["preservation_reasons"] = ["preservation_manifest_invalid"]
    return output


def _preservation_json_input(value: Any, active: set[int] | None = None) -> None:
    if type(value) in {str, int, bool, type(None)}:
        return
    if type(value) is float:
        _preservation_canonical(value)
        return
    _preservation_require(type(value) in {dict, list}, "preservation_context_invalid")
    seen = set() if active is None else active
    identity = id(value)
    _preservation_require(identity not in seen, "preservation_context_invalid")
    seen.add(identity)
    try:
        if type(value) is dict:
            _preservation_require(all(type(key) is str for key in value), "preservation_context_invalid")
            for item in value.values():
                _preservation_json_input(item, seen)
        else:
            for item in value:
                _preservation_json_input(item, seen)
    finally:
        seen.remove(identity)


def _changed_files(before_manifest: dict[str, Any], after_manifest: dict[str, Any]) -> list[str]:
    before = before_manifest["entries"]
    after = after_manifest["entries"]
    changed: list[str] = []
    for path in sorted(set(before) | set(after), key=_preservation_path):
        prior = before.get(path, {"kind": "absent"})
        current = after.get(path, {"kind": "absent"})
        if prior["kind"] == current["kind"] == "directory":
            equal = all(_preservation_same(prior[key], current[key]) for key in ("mode", "identity", "file_attributes"))
        else:
            equal = _preservation_same(prior, current)
        if not equal:
            changed.append(path)
    return changed


def _validator_list(validator_results: Any) -> list[dict[str, Any]]:
    source = validator_results
    if isinstance(source, dict):
        for key in ("validators", "validator_results", "validators_run"):
            if isinstance(source.get(key), list):
                source = source[key]
                break
    output: list[dict[str, Any]] = []
    for index, validator in enumerate(_as_list(source)):
        if isinstance(validator, dict):
            name = str(validator.get("name", validator.get("command", f"validator_{index + 1}")))
            command = str(validator.get("command", name))
            passed = bool(validator.get("passed") is True or validator.get("returncode") == 0)
            returncode = validator.get("returncode")
        else:
            name = str(validator)
            command = name
            passed = False
            returncode = None
        output.append(
            {
                "name": name,
                "command": command,
                "passed": passed,
                "returncode": returncode,
            }
        )
    return output


def build_self_build_apply_result_verifier(
    selected_queue_item: dict[str, Any] | None = None,
    single_action_executor: dict[str, Any] | None = None,
    before_git_status: Any = None,
    after_git_status: Any = None,
    validator_results: Any = None,
    allowed_paths: list[str] | None = None,
    max_files_changed: int | None = None,
    *,
    preservation_context: dict[str, Any] | None = None,
    before_manifest: bytes | None = None,
    after_manifest: bytes | None = None,
) -> dict[str, Any]:
    command_executed = type(single_action_executor) is dict and all(type(key) is str for key in single_action_executor) and single_action_executor.get("command_executed") is True
    safety = _base_safety()
    try:
        for value in (selected_queue_item, single_action_executor, before_git_status, after_git_status, validator_results, allowed_paths, max_files_changed):
            _preservation_json_input(value)
        queue_item = _as_dict(selected_queue_item)
        executor = _as_dict(single_action_executor)
        selected_action = str(executor.get("selected_action", queue_item.get("action_id", "none")))
        preview = preservation_context is None and before_manifest is None and after_manifest is None and not command_executed
        allowed_raw = allowed_paths if allowed_paths is not None else queue_item.get("allowed_paths", []) if preview else None
        allowed = _normalize_paths(allowed_raw)
        maximum_raw = max_files_changed if max_files_changed is not None else executor.get("max_files_changed", len(allowed) or 1) if preview else None
        max_changed = maximum_raw if type(maximum_raw) is int and maximum_raw > 0 else None
        preservation = _preservation_result(preservation_context, before_manifest, after_manifest, queue_item, executor, allowed_paths, max_files_changed)
        validators = _validator_list(validator_results)
        if SANDBOX_1312_MARKER in _payload_text(selected_queue_item, single_action_executor, before_git_status, after_git_status, validator_results):
            safety["sandbox_1312_blocker"] = True
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        selected_action = "none"
        allowed = []
        max_changed = None
        validators = []
        preservation = _preservation_result(None, before_manifest, after_manifest, {}, {}, None, None)
        preservation.update({"preservation_status": "invalid", "preservation_reasons": ["preservation_context_invalid"]})
    changed_files = preservation["changed_files"]
    unexpected_files = preservation["unexpected_files"]
    validators_passed = sum(1 for validator in validators if validator["passed"] is True)
    validators_failed = sum(1 for validator in validators if validator["passed"] is not True)
    file_count_ok = preservation["file_count_ok"]
    allowed_paths_ok = preservation["allowed_paths_ok"]

    rejection_reasons: list[str] = []
    if not command_executed:
        rejection_reasons.append("command_not_executed")
    if safety["sandbox_1312_blocker"]:
        rejection_reasons.append("sandbox_1312_runner_blocker")
    rejection_reasons.extend(preservation["preservation_reasons"])
    if unexpected_files:
        rejection_reasons.append("unexpected_files_outside_allowed_paths")
    if preservation["preservation_status"] == "compared" and not file_count_ok:
        rejection_reasons.append("max_files_changed_exceeded")
    if not validators:
        rejection_reasons.append("validators_missing")
    elif validators_failed:
        rejection_reasons.append("validators_failed")

    if preservation["preservation_root_changed"] is True:
        verifier_status = "failed"
    elif not command_executed or safety["sandbox_1312_blocker"] or preservation["preservation_status"] != "compared":
        verifier_status = "blocked"
    elif not preservation["preservation_comparison_passed"] or not validators or validators_failed:
        verifier_status = "failed"
    else:
        verifier_status = "passed"

    result_safe_to_report = verifier_status in {"passed", "failed", "blocked"}
    result_safe_to_package = verifier_status == "passed"
    if verifier_status == "passed":
        next_safe_action = "Supplied preservation evidence compared. Actual capture provenance and packaging authority require separate qualification; staging, commit, push, and merge still require approval."
    elif preservation["preservation_root_changed"] is True:
        next_safe_action = "Stop and retain both original snapshots: the admitted worktree root state changed."
    elif safety["sandbox_1312_blocker"]:
        next_safe_action = "Treat sandbox 1312 as a local runner blocker, not a code failure."
    elif preservation["preservation_status"] in {"missing", "invalid", "incomplete"}:
        next_safe_action = "Stop packaging until complete task-bound before/after preservation evidence is available; retain both original snapshots and rejection evidence."
    elif verifier_status == "blocked":
        next_safe_action = "Stop until a bounded local APPLY has executed and produced validator and preservation evidence."
    else:
        next_safe_action = "Stop and report verifier failure before any package, stage, commit, push, or merge."

    return {
        "schema": SCHEMA,
        "verifier_status": verifier_status,
        "selected_action": selected_action,
        "changed_files": changed_files,
        "allowed_paths": allowed,
        "unexpected_files": unexpected_files,
        "validators": validators,
        "validators_passed": validators_passed,
        "validators_failed": validators_failed,
        "max_files_changed": max_changed,
        "file_count_ok": file_count_ok,
        "allowed_paths_ok": allowed_paths_ok,
        "result_safe_to_report": result_safe_to_report,
        "result_safe_to_package": result_safe_to_package,
        "rejection_reasons": rejection_reasons,
        "next_safe_action": next_safe_action,
        "safety": safety,
        **{key: value for key, value in preservation.items() if key not in {"changed_files", "unexpected_files", "file_count_ok", "allowed_paths_ok"}},
    }


verify_self_build_apply_result = build_self_build_apply_result_verifier
build_apply_result_verifier = build_self_build_apply_result_verifier


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify one AIOS self-build APPLY result without side effects.")
    parser.add_argument("--queue-item", default="{}")
    parser.add_argument("--single-action-executor", default="{}")
    parser.add_argument("--before-git-status", default="")
    parser.add_argument("--after-git-status", default="")
    parser.add_argument("--validator-results", default="[]")
    parser.add_argument("--allowed-paths", default="[]")
    parser.add_argument("--max-files-changed", type=int, default=None)
    parser.add_argument("--preservation-context", default=None)
    parser.add_argument("--before-manifest", default=None)
    parser.add_argument("--after-manifest", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        queue_item = json.loads(args.queue_item)
        executor = json.loads(args.single_action_executor)
        validators = json.loads(args.validator_results)
        allowed_paths = json.loads(args.allowed_paths)
    except json.JSONDecodeError:
        queue_item = {}
        executor = {}
        validators = []
        allowed_paths = []
    context = None
    if args.preservation_context is not None:
        try:
            context = json.loads(args.preservation_context, object_pairs_hook=_preservation_pairs, parse_constant=_preservation_nonfinite)
        except (ValueError, TypeError, RecursionError):
            context = {"invalid_cli_preservation_context": True}
        if context is None:
            context = {"invalid_cli_preservation_context": True}
    before = args.before_manifest.encode("utf-8", "surrogatepass") if args.before_manifest is not None else None
    after = args.after_manifest.encode("utf-8", "surrogatepass") if args.after_manifest is not None else None
    print(
        json.dumps(
            build_self_build_apply_result_verifier(
                queue_item,
                executor,
                args.before_git_status,
                args.after_git_status,
                validators,
                allowed_paths,
                args.max_files_changed,
                preservation_context=context,
                before_manifest=before,
                after_manifest=after,
            ),
            indent=2,
            sort_keys=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def compare_nonprivate_worktree_states(before: bytes, after: bytes, *, binding: dict[str, Any],
        execution_started_at_utc: str, execution_ended_at_utc: str) -> dict[str, Any]:
    """Compare observed contents only. Never establish full preservation or packaging safety."""
    from automation.orchestration.aios_repo_state_evidence import nonprivate_capture_contract, _full_capture_validate
    if type(binding) is not dict or binding.get("capture_contract") != nonprivate_capture_contract():
        raise ValueError("nonprivate_comparison_contract_required")
    _full_capture_validate(binding.get("repository_identity", {}).get("repo_root"), binding, "before",
                           (10000, 16777216, 67108864, 5))
    start = _preservation_time(execution_started_at_utc, "nonprivate_interval_invalid")
    end = _preservation_time(execution_ended_at_utc, "nonprivate_interval_invalid")
    _preservation_require(end >= start, "nonprivate_interval_invalid")
    context = {"binding": binding, "execution": {"started_at_utc": execution_started_at_utc,
        "ended_at_utc": execution_ended_at_utc}, "before_manifest_sha256": hashlib.sha256(before).hexdigest(),
        "after_manifest_sha256": hashlib.sha256(after).hexdigest()}
    prior = _preservation_manifest(before, context, "before", nonprivate=True)
    current = _preservation_manifest(after, context, "after", nonprivate=True)
    changed = _changed_files(prior, current)
    root_changed = any(not _preservation_same(prior["root_state"][key], current["root_state"][key]) for key in ("mode", "identity"))
    if root_changed:
        changed = [".", *changed]
    unexpected = [path for path in changed if path not in binding["allowed_paths"]]
    boundaries = sorted(set(prior["coverage"]["private_boundary_paths"]) | set(current["coverage"]["private_boundary_paths"]))
    return {"schema": "AIOS_NONPRIVATE_WORKTREE_COMPARISON.v1",
        "nonprivate_comparison_passed": not root_changed and not unexpected and len(changed) <= binding["max_files_changed"],
        "changed_files": changed, "unexpected_files": unexpected, "private_boundary_proof_required": boundaries,
        "private_contents_observed": False, "private_contents_unchanged": None,
        "preservation_comparison_passed": False, "result_safe_to_package": False,
        "assurance": "nonprivate_observation_only_private_contents_not_verified"}


WINDOWS_WORKER_ORIGINAL_ROLES = (
    'selected_entry_source', 'configuration_source', 'launch_and_environment_source',
    'process_result_original', 'process_result_independent_verification',
    'same_launch_policy_binding_source', 'backend_source', 'network_proxy_source',
    'qualification_acceptance_review', 'qualification_execution_seal',
)


class _WindowsOriginalError(ValueError):
    pass


def _ws_need(condition, code):
    if not condition:
        raise _WindowsOriginalError('windows_originals_' + code)


def _ws_object(value, fields):
    _ws_need(type(value) is dict and set(value) == set(fields), 'object_fields_invalid')
    return value


def _ws_json(value):
    from automation.orchestration.aios_repo_state_evidence import campaign_json
    return campaign_json(value).encode('ascii')


def _ws_decode(raw, limit):
    _ws_need(type(raw) is bytes and 0 < len(raw) <= limit, 'original_size_invalid')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_preservation_pairs,
                           parse_constant=_preservation_nonfinite)
        _ws_json(value)  # Reject float tokens and unsupported nested raw types.
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _WindowsOriginalError('windows_originals_json_invalid') from None
    return value


def _ws_text(value, limit=512):
    return type(value) is str and 0 < len(value) <= limit and '\0' not in value


def _ws_uint(value, upper, minimum=1):
    return type(value) is int and minimum <= value < upper


def _ws_path(value):
    _ws_need(_ws_text(value) and re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', value)
             and all(part not in {'.', '..'} for part in value.split('/')), 'relative_path_invalid')


def _ws_expectation(expected):
    _ws_object(expected, {'schema', 'attempt', 'candidate', 'session_id', 'policy_export_manifest_sha256',
        'policy_state_sha256', 'profile_reference_sha256', 'native_cwd', 'canonical_cwd_uri',
        'process_chain', 'interval', 'launch', 'backend', 'filesystem', 'network', 'checker_sha256',
        'reviewer', 'producer_manifest'})
    _ws_need(len(_ws_json(expected)) <= 1048576, 'expectation_size_invalid')
    _ws_need(expected['schema'] == 'AIOS_WINDOWS_WORKER_CHECK_EXPECTATION.v1', 'expectation_schema_invalid')
    attempt = _ws_object(expected['attempt'], {'task_id', 'packet_id', 'attempt_id',
                                              'request_sha256', 'claim_sha256', 'nonce_sha256'})
    for key in ('task_id', 'packet_id', 'attempt_id'):
        _ws_need(_ws_text(attempt[key], 256), 'attempt_invalid')
    for key in ('request_sha256', 'claim_sha256', 'nonce_sha256'):
        _ws_need(_preservation_hash(attempt[key]), 'attempt_hash_invalid')
    candidate = _ws_object(expected['candidate'], {'bytes', 'sha256'})
    _ws_need(_ws_uint(candidate['bytes'], 2**31) and _preservation_hash(candidate['sha256']), 'candidate_invalid')
    for key in ('policy_export_manifest_sha256', 'policy_state_sha256', 'profile_reference_sha256', 'checker_sha256'):
        _ws_need(_preservation_hash(expected[key]), 'expectation_hash_invalid')
    _ws_need(_ws_text(expected['session_id'], 256) and _ws_text(expected['reviewer'], 256), 'identity_invalid')
    cwd = expected['native_cwd']
    _ws_need(_ws_text(cwd) and PureWindowsPath(cwd).is_absolute() and not cwd.startswith(('\\\\', '//'))
             and '..' not in PureWindowsPath(cwd).parts, 'cwd_invalid')
    _ws_need(expected['canonical_cwd_uri'] == PureWindowsPath(cwd).as_uri(), 'cwd_uri_invalid')
    chain = expected['process_chain']
    _ws_need(type(chain) is list and 2 <= len(chain) <= 16, 'process_chain_invalid')
    seen = set()
    for index, row in enumerate(chain):
        _ws_object(row, {'pid', 'parent_pid', 'creation_filetime', 'parent_creation_filetime',
                         'image_sha256', 'image_bytes'})
        _ws_need(_ws_uint(row['pid'], 2**32) and _ws_uint(row['parent_pid'], 2**32)
                 and row['pid'] not in seen and row['pid'] != row['parent_pid'], 'process_pid_invalid')
        seen.add(row['pid'])
        _ws_need(_ws_uint(row['creation_filetime'], 2**64) and _ws_uint(row['parent_creation_filetime'], 2**64)
                 and row['parent_creation_filetime'] <= row['creation_filetime'], 'process_creation_invalid')
        _ws_need(_preservation_hash(row['image_sha256']) and _ws_uint(row['image_bytes'], 2**31), 'process_image_invalid')
        if index + 1 < len(chain):
            parent = chain[index + 1]
            _ws_need(type(parent) is dict and row['parent_pid'] == parent.get('pid')
                     and row['parent_creation_filetime'] == parent.get('creation_filetime'), 'process_parent_invalid')
    _ws_need(chain[-1]['image_sha256'] == candidate['sha256'] and chain[-1]['image_bytes'] == candidate['bytes'],
             'installed_image_mismatch')
    interval = _ws_object(expected['interval'], {'started_filetime', 'ended_filetime'})
    _ws_need(all(_ws_uint(value, 2**64) for value in interval.values())
             and chain[0]['creation_filetime'] <= interval['started_filetime'] <= interval['ended_filetime'],
             'interval_invalid')
    launch = _ws_object(expected['launch'], {'argv', 'environment_sha256', 'shell_image_sha256', 'shell_version',
                                           'requested_route', 'actual_route', 'stdin_bytes', 'stdin_sha256'})
    _ws_need(type(launch['argv']) is list and 1 <= len(launch['argv']) <= 128
             and all(_ws_text(arg, 32768) for arg in launch['argv'])
             and sum(len(arg) for arg in launch['argv']) <= 262144, 'argv_invalid')
    _ws_need(all(_preservation_hash(launch[key]) for key in ('environment_sha256', 'shell_image_sha256', 'stdin_sha256'))
             and launch['shell_image_sha256'] == chain[0]['image_sha256'], 'launch_hash_invalid')
    _ws_need(_ws_text(launch['shell_version'], 64) and re.fullmatch(r'\d+(?:\.\d+){1,3}', launch['shell_version'])
             and _ws_text(launch['requested_route'], 128) and launch['actual_route'] == launch['requested_route']
             and _ws_uint(launch['stdin_bytes'], 1048577, minimum=0), 'shell_route_invalid')
    backend = _ws_object(expected['backend'], {'kind', 'applied_policy_sha256', 'process_token_sha256'})
    _ws_need(backend['kind'] == 'windows_mxc' and all(_preservation_hash(backend[key])
             for key in ('applied_policy_sha256', 'process_token_sha256')), 'backend_invalid')
    producers = _ws_object(expected['producer_manifest'], WINDOWS_WORKER_ORIGINAL_ROLES)
    _ws_need(all(_preservation_hash(value) for value in producers.values()), 'producer_manifest_invalid')
    _ws_filesystem(expected['filesystem'])
    _ws_network(expected['network'])


def _ws_filesystem(value):
    from automation.orchestration.aios_repo_state_evidence import _full_capture_private
    _ws_object(value, {'private_boundaries', 'observations'})
    private = value['private_boundaries']
    _ws_need(type(private) is list and 1 <= len(private) <= 64 and all(type(path) is str for path in private)
             and private == sorted(set(private)) and len({path.casefold() for path in private}) == len(private),
             'private_boundaries_invalid')
    for path in private:
        _ws_path(path)
        _ws_need(_full_capture_private(path), 'private_boundary_invalid')
    rows = value['observations']
    _ws_need(type(rows) is list and len(rows) == 2 * len(private) + 2, 'filesystem_coverage_incomplete')
    observed = set()
    public = set()
    for row in rows:
        _ws_object(row, {'path', 'operation', 'result'})
        _ws_path(row['path'])
        _ws_need(row['operation'] in {'read', 'write'} and row['result'] in {'allowed', 'access_denied'},
                 'filesystem_operation_invalid')
        key = (row['path'], row['operation'], row['result'])
        _ws_need(key not in observed, 'filesystem_operation_duplicate')
        observed.add(key)
        if row['result'] == 'allowed':
            _ws_need(not _full_capture_private(row['path']), 'private_access_allowed')
            public.add(row['path'])
    wanted = {(path, operation, 'access_denied') for path in private for operation in ('read', 'write')}
    _ws_need(len(public) == 1 and observed == wanted | {(path, operation, 'allowed')
             for path in public for operation in ('read', 'write')}, 'filesystem_coverage_incomplete')


def _ws_network(value):
    _ws_object(value, {'mode', 'policy_sha256', 'proxy_sha256', 'observations'})
    _ws_need(value['mode'] == 'deny_by_default' and _preservation_hash(value['policy_sha256'])
             and _preservation_hash(value['proxy_sha256']), 'network_policy_invalid')
    rows = value['observations']
    _ws_need(type(rows) is list and len(rows) == 4, 'network_coverage_incomplete')
    wanted = {'direct_outbound': 'access_denied', 'proxy_bypass': 'access_denied',
              'unapproved_endpoint': 'access_denied', 'approved_endpoint': 'allowed'}
    seen = set()
    for row in rows:
        _ws_object(row, {'operation', 'target_sha256', 'result'})
        _ws_need(type(row['operation']) is str and row['operation'] in wanted and row['operation'] not in seen
                 and row['result'] == wanted[row['operation']] and _preservation_hash(row['target_sha256']),
                 'network_operation_invalid')
        seen.add(row['operation'])


def check_windows_worker_originals(binding_bytes, original_bytes_by_role, *, expected):
    """Check supplied originals without files, processes, probes or admission.

    This opt-in diagnostic uses the proposed 17-field binding shape; it does
    not adopt that proposal as authority. Matching records and finite probe
    results cannot authenticate their collector or prove complete enforcement.
    Neither CONSISTENT nor hashes may be used as a native admission decision.
    """
    result = {'schema': 'AIOS_WINDOWS_WORKER_ORIGINAL_CHECK.v1', 'check_status': 'BLOCKED',
        'reason_codes': [], 'checked_original_count': 0, 'origin_authenticated': False,
        'native_admission_granted': False, 'windows_qualification': False, 'execution_authority': False,
        'assurance': 'supplied_original_consistency_only_not_origin_or_complete_enforcement'}
    try:
        _ws_expectation(expected)
        binding = _ws_decode(binding_bytes, 131072)
        core = {'schema': 'AIOS_NATIVE_SELECTED_EXEC_POLICY_BINDING.v1', 'candidate': expected['candidate'],
            **{key: expected[key] for key in ('policy_export_manifest_sha256', 'policy_state_sha256',
                'profile_reference_sha256', 'canonical_cwd_uri', 'native_cwd')}}
        _ws_object(binding, set(core) | set(WINDOWS_WORKER_ORIGINAL_ROLES))
        _ws_need(_ws_json({key: binding[key] for key in core}) == _ws_json(core), 'binding_core_mismatch')
        _ws_object(original_bytes_by_role, WINDOWS_WORKER_ORIGINAL_ROLES)
        _ws_need(all(type(raw) is bytes and 0 < len(raw) <= 1048576 for raw in original_bytes_by_role.values())
                 and sum(map(len, original_bytes_by_role.values())) <= 8388608, 'original_size_invalid')
        records, hashes, paths = {}, {}, set()
        for role in WINDOWS_WORKER_ORIGINAL_ROLES:
            reference = _ws_object(binding[role], {'publication_root', 'relative_path', 'bytes', 'sha256'})
            _ws_need(reference['publication_root'] == 'EXISTING_APPROVED_EXECUTION_EVIDENCE', 'reference_root_invalid')
            _ws_path(reference['relative_path'])
            from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import source_relative
            source_relative(reference['relative_path'])  # Pure validation; never a filesystem lookup.
            path_key = reference['relative_path'].casefold()
            _ws_need(path_key not in paths, 'reference_path_duplicate')
            paths.add(path_key)
            raw = original_bytes_by_role[role]
            digest = hashlib.sha256(raw).hexdigest()
            _ws_need(_ws_uint(reference['bytes'], 1048577) and reference['bytes'] == len(raw)
                     and _preservation_hash(reference['sha256']) and reference['sha256'] == digest, 'reference_bytes_mismatch')
            record = _ws_object(_ws_decode(raw, 1048576), {'schema', 'role', 'attempt', 'session_id',
                'child_identity', 'interval', 'producer_sha256', 'payload'})
            _ws_need(record['schema'] == 'AIOS_WINDOWS_WORKER_OBSERVATION.v1' and record['role'] == role,
                     'observation_role_invalid')
            for key, wanted in (('attempt', expected['attempt']), ('session_id', expected['session_id']),
                    ('child_identity', expected['process_chain'][0]), ('interval', expected['interval']),
                    ('producer_sha256', expected['producer_manifest'][role])):
                _ws_need(_ws_json(record[key]) == _ws_json(wanted), 'observation_binding_mismatch')
            records[role], hashes[role] = record['payload'], digest
        payloads = {
            'selected_entry_source': {'candidate': expected['candidate'],
                'entry_sha256': expected['producer_manifest']['selected_entry_source']},
            'configuration_source': {key: expected[key] for key in ('policy_export_manifest_sha256',
                'policy_state_sha256', 'profile_reference_sha256')},
            'launch_and_environment_source': {**expected['launch'], 'native_cwd': expected['native_cwd'],
                'canonical_cwd_uri': expected['canonical_cwd_uri'], 'process_chain': expected['process_chain']},
            'same_launch_policy_binding_source': {'policy_state_sha256': expected['policy_state_sha256'],
                'profile_reference_sha256': expected['profile_reference_sha256'], 'process_chain': expected['process_chain'],
                'filesystem': expected['filesystem']},
            'backend_source': expected['backend'], 'network_proxy_source': expected['network'],
            'process_result_independent_verification': {'process_result_sha256': hashes['process_result_original'],
                'checker_sha256': expected['checker_sha256'], 'reviewer': expected['reviewer']},
            'qualification_acceptance_review': {'evidence_sha256': {role: hashes[role]
                for role in WINDOWS_WORKER_ORIGINAL_ROLES[:8]}, 'checker_sha256': expected['checker_sha256'],
                'reviewer': expected['reviewer']},
            'qualification_execution_seal': {'evidence_sha256': {role: hashes[role]
                for role in WINDOWS_WORKER_ORIGINAL_ROLES[:9]}, 'review_sha256': hashes['qualification_acceptance_review'],
                'binding_core_sha256': hashlib.sha256(_ws_json(core)).hexdigest(),
                'binding_references_sha256': hashlib.sha256(_ws_json({key: item for key, item in binding.items()
                    if key != 'qualification_execution_seal'})).hexdigest(),
                'checker_sha256': expected['checker_sha256']}}
        for role, wanted in payloads.items():
            _ws_need(_ws_json(records[role]) == _ws_json(wanted), 'payload_mismatch_' + role)
        process = _ws_object(records['process_result_original'], {'shape_valid', 'root_exit_confirmed',
            'tree_exit_confirmed', 'drains_completed', 'stdin_completed', 'stdin_writer_joined', 'timed_out',
            'startup_failed', 'process_error_present', 'exit_code', 'child_exit_code', 'stdin_error_code',
            'stdin_close_error_code', 'cleanup_error_code', 'cancellation_error_code', 'cleanup_state',
            'working_directory', 'stdin_bytes_written', 'root_process_id'})
        from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import verify_process_success
        _ws_need(type(process['root_process_id']) is int
                 and process['root_process_id'] == expected['process_chain'][0]['pid'], 'process_result_identity_mismatch')
        verify_process_success(process, cwd=expected['native_cwd'], input_bytes=expected['launch']['stdin_bytes'])
        result.update(check_status='CONSISTENT', checked_original_count=len(records), original_sha256=hashes)
    except _WindowsOriginalError as error:
        result['reason_codes'] = [str(error)]
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        result['reason_codes'] = ['windows_originals_invalid_or_incomplete']
    return result


def collect_windows_worker_originals(publication_root, binding_bytes, *, expected,
                                     root_identity, timeout_seconds=5):
    """Read exactly ten existing originals through retained native NTFS handles.

    The caller must already be permitted to read the exact evidence directory
    and supply its pinned device/inode. These arguments are not a permission
    grant. This opt-in API neither collects live process/policy observations nor
    authenticates their creator. It does not construct a native context or
    change the default launch refusal. Importing it acquires no native handles.
    """
    import math
    import time
    from automation.orchestration import aios_repo_state_evidence as native
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import source_relative

    result = {'schema': 'AIOS_WINDOWS_WORKER_ORIGINAL_COLLECTION.v1',
        'collection_status': 'BLOCKED', 'reason_codes': [], 'check': None,
        'binding_bytes': None, 'original_bytes_by_role': {},
        'origin_authenticated': False, 'native_admission_granted': False,
        'windows_qualification': False, 'execution_authority': False,
        'assurance': 'existing_record_collection_only_not_live_observation_or_origin'}
    reader = None
    complete = None
    try:
        _ws_expectation(expected)
        # Freeze the data before I/O; later caller mutations cannot change the
        # checked selection. Never serialize environment values or exceptions.
        expected = _ws_decode(_ws_json(expected), 1048576)
        _ws_object(root_identity, {'device', 'inode'})
        _ws_need(all(_ws_uint(value, 2**64) for value in root_identity.values()), 'collection_root_identity_invalid')
        root_identity = dict(root_identity)
        _ws_need(_ws_text(publication_root, 32768), 'collection_root_invalid')
        root = PureWindowsPath(publication_root)
        _ws_need(root.is_absolute() and re.fullmatch(r'[A-Za-z]:', root.drive)
                 and str(root) == publication_root and len(root.parts) > 1
                 and all(native._full_capture_name(part) for part in root.parts[1:]), 'collection_root_invalid')
        _ws_need(type(timeout_seconds) in {int, float} and math.isfinite(timeout_seconds)
                 and 0 < timeout_seconds <= 5, 'collection_deadline_invalid')
        binding = _ws_decode(binding_bytes, 131072)
        core = {'schema': 'AIOS_NATIVE_SELECTED_EXEC_POLICY_BINDING.v1', 'candidate': expected['candidate'],
            **{key: expected[key] for key in ('policy_export_manifest_sha256', 'policy_state_sha256',
                'profile_reference_sha256', 'canonical_cwd_uri', 'native_cwd')}}
        _ws_object(binding, set(core) | set(WINDOWS_WORKER_ORIGINAL_ROLES))
        _ws_need(_ws_json({key: binding[key] for key in core}) == _ws_json(core), 'binding_core_mismatch')
        paths, total = set(), 0
        for role in WINDOWS_WORKER_ORIGINAL_ROLES:
            ref = _ws_object(binding[role], {'publication_root', 'relative_path', 'bytes', 'sha256'})
            _ws_need(ref['publication_root'] == 'EXISTING_APPROVED_EXECUTION_EVIDENCE', 'reference_root_invalid')
            _ws_path(ref['relative_path'])
            _ws_need(native._full_capture_relative(ref['relative_path']), 'collection_reference_invalid')
            source_relative(ref['relative_path'])
            key = ref['relative_path'].casefold()
            _ws_need(key not in paths, 'reference_path_duplicate')
            paths.add(key)
            _ws_need(_ws_uint(ref['bytes'], 1048577) and _preservation_hash(ref['sha256']), 'reference_bytes_mismatch')
            total += ref['bytes']
        _ws_need(total <= 8388608, 'original_size_invalid')

        reader = native._FullWorktreeWindowsReader(time.monotonic() + timeout_seconds)
        root_handle, mapping = reader.open_root(root.drive, list(root.parts[1:]))
        _ws_need(reader.guards[root_handle]['identity'] == root_identity, 'collection_root_identity_mismatch')
        guards = dict(reader.guards)
        streams = {}
        for handle, facts in guards.items():
            _ws_need(facts['directory'] is True, 'collection_ancestor_invalid')
            streams[handle] = reader.streams(handle, True)
            _ws_need(streams[handle] == [], 'collection_stream_invalid')
        directories = {'': root_handle}
        identities = set()
        originals = {}
        for role in WINDOWS_WORKER_ORIGINAL_ROLES:
            ref = binding[role]
            parts = ref['relative_path'].split('/')
            parent, prefix = root_handle, ''
            for name in parts[:-1]:
                prefix = prefix + '/' + name if prefix else name
                if prefix not in directories:
                    handle = reader.open_relative(parent, name, 0x100080)
                    facts = reader.metadata(handle)
                    _ws_need(facts['directory'] is True and facts['identity']['device'] == root_identity['device'],
                             'collection_ancestor_invalid')
                    reader.guards[handle] = facts
                    guards[handle] = facts
                    streams[handle] = reader.streams(handle, True)
                    _ws_need(streams[handle] == [], 'collection_stream_invalid')
                    directories[prefix] = handle
                parent = directories[prefix]
            metadata = reader.open_relative(parent, parts[-1], 0x100080)
            facts = reader.metadata(metadata)
            _ws_need(facts['directory'] is False and facts['links'] == 1
                     and facts['identity']['device'] == root_identity['device']
                     and facts['size'] == ref['bytes'], 'collection_file_invalid')
            identity = (facts['identity']['device'], facts['identity']['inode'])
            _ws_need(identity not in identities, 'collection_file_alias')
            identities.add(identity)
            stream = reader.streams(metadata, False)
            _ws_need(len(stream) == 1 and stream[0][0] == '::$DATA' and stream[0][1] == ref['bytes'],
                     'collection_stream_invalid')
            reader.guards[metadata] = facts
            guards[metadata], streams[metadata] = facts, stream
            handle = reader.open_relative(parent, parts[-1], 0x100081)
            _ws_need(reader.metadata(handle) == facts and reader.streams(handle, False) == stream,
                     'collection_data_identity_mismatch')
            reader.guards[handle] = facts
            guards[handle], streams[handle] = facts, stream
            chunks, used = [], 0
            while used < ref['bytes']:
                _ws_need(reader.metadata(handle) == facts, 'collection_changed')
                count = min(65536, ref['bytes'] - used)
                chunk = reader.read(handle, count)
                _ws_need(type(chunk) is bytes and 0 < len(chunk) <= count, 'collection_read_invalid')
                chunks.append(chunk)
                used += len(chunk)
            _ws_need(reader.read(handle, 1) == b'', 'collection_extra_bytes')
            raw = b''.join(chunks)
            _ws_need(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'collection_hash_mismatch')
            originals[role] = raw
        for handle, facts in guards.items():
            _ws_need(reader.metadata(handle) == facts
                     and reader.streams(handle, facts['directory']) == streams[handle], 'collection_changed')
        _ws_need(reader.drive_mapping(root.drive) == mapping, 'collection_mapping_changed')
        checked = check_windows_worker_originals(binding_bytes, originals, expected=expected)
        _ws_need(checked['check_status'] == 'CONSISTENT', 'collection_originals_inconsistent')
        reader.tick()
        complete = {'collection_status': 'COLLECTED', 'check': checked,
                    'binding_bytes': binding_bytes, 'original_bytes_by_role': originals}
    except _WindowsOriginalError as error:
        result['reason_codes'] = [str(error)]
    except (native._FullCaptureFailure, native._FullWorktreeCaptureUnavailable, OSError,
            ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        result['reason_codes'] = ['windows_originals_collection_unavailable']
    finally:
        if reader is not None:
            try:
                reader.close_all()
            except Exception:
                complete = None
                result['reason_codes'] = ['windows_originals_collection_cleanup_unconfirmed']
    if complete is not None:
        result.update(complete)
    return result


# Windows worker recorder
"""Bounded native Windows worker observations, with no activation on import.

Prepare before the existing owner starts its selected child; collect afterwards.
The emitter must already exist. This does not cover an emitter created by launch.
It does not launch a worker, read process memory/environment, change protections,
issue permission, or turn recorder output into full worker qualification.
Call only inside the existing owner's separately authorized recording scope.
"""

import ctypes as C
import hashlib
import json
import math
import os
import re
import threading
import time
import uuid
from types import SimpleNamespace

MXC_PROVIDER = '7f10def4-a258-5fea-510e-2c3bb976687f'
_EVENT_FIELDS = {
    'MXC.PolicyHash': {'identity': 'id', 'policyHash': 'hash'},
    'MXC.SandboxNetworkPolicyApplied': {'identity': 'id', 'enforcementMode': 'mode',
        'defaultPolicy': 'policy', 'proxyPort': 'uint'},
    'MXC.ProcessExited': {'identity': 'id', 'processId': 'uint', 'exitCode': 'uint'},
    'MXC.SandboxTornDown': {'identity': 'id', 'status': 'status'},
}
_NATIVE_EVENT_FIELDS = {
    'MXC.PolicyHash': {'identity': 'mxc.identity', 'policyHash': 'mxc.policy_hash'},
    'MXC.SandboxNetworkPolicyApplied': {'identity': 'mxc.identity',
        'enforcementMode': 'mxc.enforcement_mode', 'defaultPolicy': 'mxc.default_policy',
        'proxyPort': 'mxc.proxy_port'},
    'MXC.ProcessExited': {'identity': 'mxc.identity', 'processId': 'mxc.process_id',
        'exitCode': 'mxc.exit_code'},
    'MXC.SandboxTornDown': {'identity': 'mxc.identity', 'status': 'mxc.status'},
}
_MISSING_ROLES = ['selected_entry_source', 'configuration_source',
    'launch_and_environment_source', 'process_result_original',
    'process_result_independent_verification', 'same_launch_policy_binding_source',
    'backend_source', 'network_proxy_source', 'qualification_acceptance_review',
    'qualification_execution_seal']


class RecorderUnavailable(ValueError):
    """Bounded public reason only; native exception text is never returned."""


def _need(ok, code):
    if not ok:
        raise RecorderUnavailable('windows_recorder_' + code)


def _uint(value, maximum=2**64, minimum=1):
    return type(value) is int and minimum <= value < maximum


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _identifier(value):
    return type(value) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', value) is not None


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def _request(value, *, min_chain=2):
    _need(type(value) is dict and set(value) == {'schema', 'attempt_id', 'session_id',
        'mxc_identity', 'policy_sha256', 'process_chain'}, 'request_invalid')
    _need(value['schema'] == 'AIOS_WINDOWS_WORKER_RECORDING_REQUEST.v1'
          and all(_identifier(value[key]) for key in ('attempt_id', 'session_id', 'mxc_identity'))
          and _hash(value['policy_sha256']), 'request_identity_invalid')
    chain = value['process_chain']
    _need(type(chain) is list and min_chain <= len(chain) <= 16, 'chain_invalid')
    seen = set()
    for index, row in enumerate(chain):
        _need(type(row) is dict and set(row) == {'pid', 'parent_pid', 'creation_filetime',
            'parent_creation_filetime', 'image_sha256', 'image_bytes'}, 'chain_invalid')
        _need(_uint(row['pid'], 2**32) and _uint(row['parent_pid'], 2**32)
              and row['pid'] != row['parent_pid'] and row['pid'] not in seen
              and _uint(row['creation_filetime']) and _uint(row['parent_creation_filetime'])
              and row['parent_creation_filetime'] <= row['creation_filetime']
              and _hash(row['image_sha256']) and _uint(row['image_bytes'], 2**31), 'chain_invalid')
        seen.add(row['pid'])
        if index + 1 < len(chain):
            parent = chain[index + 1]
            _need(type(parent) is dict and row['parent_pid'] == parent.get('pid')
                  and row['parent_creation_filetime'] == parent.get('creation_filetime'), 'parent_mismatch')
    _need(chain[-1]['parent_pid'] not in seen, 'parent_mismatch')
    return json.loads(_json(value))


def _checked_events(events, spec, started, ended, maximum):
    _need(type(events) is list and len(events) <= maximum, 'events_invalid')
    found = {}
    for row in events:
        _need(type(row) is dict and set(row) == {'provider', 'emitter_pid', 'timestamp_filetime',
                                               'name', 'fields'}, 'event_invalid')
        _need(row['provider'] == MXC_PROVIDER and type(row['emitter_pid']) is int
              and row['emitter_pid'] == spec['process_chain'][1]['pid']
              and _uint(row['timestamp_filetime'])
              and started <= row['timestamp_filetime'] <= ended, 'event_attribution_invalid')
        name, fields = row['name'], row['fields']
        _need(type(name) is str and name in _EVENT_FIELDS and name not in found, 'event_set_invalid')
        _need(type(fields) is dict and set(fields) == set(_EVENT_FIELDS[name]), 'event_fields_invalid')
        _need(fields['identity'] == spec['mxc_identity'], 'event_identity_mismatch')
        if name == 'MXC.PolicyHash':
            _need(fields['policyHash'] == 'sha256:' + spec['policy_sha256'], 'policy_mismatch')
        elif name == 'MXC.SandboxNetworkPolicyApplied':
            _need(fields['enforcementMode'] == 'capabilities' and fields['defaultPolicy'] == 'block'
                  and _uint(fields['proxyPort'], 65536, 0), 'network_posture_invalid')
        elif name == 'MXC.ProcessExited':
            _need(type(fields['processId']) is int and fields['processId'] == spec['process_chain'][0]['pid']
                  and type(fields['exitCode']) is int and fields['exitCode'] == 0, 'exit_mismatch')
        else:
            _need(fields['status'] == 'success', 'teardown_not_successful')
        found[name] = row
    _need(set(found) == set(_EVENT_FIELDS), 'required_events_missing')
    creation = spec['process_chain'][0]['creation_filetime']
    _need(started <= creation and found['MXC.PolicyHash']['timestamp_filetime'] <= creation
          <= found['MXC.ProcessExited']['timestamp_filetime']
          <= found['MXC.SandboxTornDown']['timestamp_filetime'], 'event_order_invalid')
    return [found[name] for name in _EVENT_FIELDS]


def _recording_result():
    return {'schema': 'AIOS_WINDOWS_WORKER_RECORDING_RESULT.v1', 'recording_status': 'BLOCKED',
        'reason_codes': [], 'recording_bytes': None, 'recording_sha256': None,
        'process_chain': [], 'observed_event_names': [], 'native_admission_granted': False,
        'windows_qualification': False, 'complete_worker_proof': False,
        'missing_original_roles': list(_MISSING_ROLES)}


class _PreparedWindowsRecording:
    """Short-lived recorder owned by a with-block, never a worker launcher.

    A deadline expiry refuses evidence. Synchronous Windows cleanup calls cannot
    be forcibly interrupted here, so this does not promise a hard return time.
    """

    def __init__(self, spec, timeout_seconds, max_events, deadline=None):
        _need(type(timeout_seconds) in (int, float) and math.isfinite(timeout_seconds)
              and 0 < timeout_seconds <= 51 and _uint(max_events, 4097), 'limits_invalid')
        self.spec = _request(spec, min_chain=1)
        _need(len(self.spec['process_chain']) < 16, 'chain_invalid')
        now = time.monotonic()
        _need(deadline is None or (type(deadline) in (int, float) and math.isfinite(deadline)
              and now < deadline <= now + timeout_seconds), 'deadline_invalid')
        self.deadline = now + timeout_seconds if deadline is None else deadline
        self.maximum = max_events
        self.source, self.started = None, None
        self.used, self.closed = False, False

    def remaining(self):
        value = self.deadline - time.monotonic()
        _need(value > 0, 'deadline_exceeded')
        return value

    def __enter__(self):
        _need(self.source is None and not self.closed, 'recording_already_opened')
        try:
            self.remaining()
            self.source = _NativeWindowsSource(self.spec, self.deadline, self.maximum)
            _need(self.source.snapshot() == self.spec['process_chain'], 'process_identity_changed')
            self.started = self.source.clock()
            self.source.start()
            self.remaining()
            return self
        except Exception:
            self.close()
            raise RecorderUnavailable('windows_recorder_prelaunch_unavailable') from None

    def close(self):
        if not self.closed:
            self.closed = True
            if self.source is not None:
                try:
                    self.source.close()
                except Exception:
                    raise RecorderUnavailable('windows_recorder_cleanup_unconfirmed') from None

    def __exit__(self, *ignored):
        self.close()


def prepare_windows_worker_recording(request, *, timeout_seconds=5, max_events=256, deadline=None):
    """Return a with-block recorder for an existing emitter and its ancestors.

    Enter before the owner's separately permitted launch. No launcher is called,
    and preparing or collecting observations never grants permission to launch.
    """
    return _PreparedWindowsRecording(request, timeout_seconds, max_events, deadline)


def record_windows_worker(request, *, prepared=None):
    """Collect a child of the recorded emitter chain; never start late recording."""
    result, pending = _recording_result(), None
    try:
        _need(type(prepared) is _PreparedWindowsRecording and not prepared.used
              and not prepared.closed and prepared.source is not None, 'prelaunch_recording_required')
        prepared.used = True
        spec = _request(request)
        emitter = {**spec, 'process_chain': spec['process_chain'][1:]}
        _need(emitter == prepared.spec, 'prelaunch_attempt_mismatch')
        source, started = prepared.source, prepared.started
        prepared.remaining()
        source.attach(spec)
        _need(source.snapshot() == spec['process_chain'], 'process_identity_changed')
        outcome = source.wait(prepared.remaining())
        _need(type(outcome) is dict and set(outcome) == {'root_exit_confirmed', 'exit_code'}
              and outcome['root_exit_confirmed'] is True and type(outcome['exit_code']) is int
              and outcome['exit_code'] == 0, 'process_outcome_unconfirmed')
        captured = source.stop(prepared.remaining())
        ended = source.clock()
        _need(_uint(started) and _uint(ended) and started <= ended, 'clock_invalid')
        _need(source.snapshot() == spec['process_chain'], 'process_identity_changed')
        _need(type(captured) is dict and set(captured) == {'events', 'events_lost', 'buffers_lost',
            'consumer_complete'} and captured['consumer_complete'] is True
            and type(captured['events_lost']) is int and captured['events_lost'] == 0
            and type(captured['buffers_lost']) is int and captured['buffers_lost'] == 0, 'event_stream_incomplete')
        events = _checked_events(captured['events'], spec, started, ended, prepared.maximum)
        prepared.remaining()
        pending = {'schema': 'AIOS_WINDOWS_NATIVE_OBSERVATIONS.v1',
            'request_sha256': hashlib.sha256(_json(spec)).hexdigest(),
            'attempt_id': spec['attempt_id'], 'session_id': spec['session_id'],
            'process_chain': spec['process_chain'], 'interval': {'started_filetime': started, 'ended_filetime': ended},
            'events': events, 'evidence_kind': 'native_identity_and_projected_etw_only',
            'complete_worker_proof': False, 'missing_original_roles': list(_MISSING_ROLES)}
    except RecorderUnavailable as error:
        result['reason_codes'] = [str(error)]
    except Exception:
        result['reason_codes'] = ['windows_recorder_native_unavailable']
    finally:
        if type(prepared) is _PreparedWindowsRecording:
            try:
                prepared.close()
            except Exception:
                pending = None
                result['reason_codes'] = ['windows_recorder_cleanup_unconfirmed']
    if pending is not None:
        if time.monotonic() >= prepared.deadline:
            result['reason_codes'] = ['windows_recorder_deadline_exceeded']
            return result
        raw = _json(pending)
        result.update(recording_status='RECORDED_REQUIRES_REVIEW', recording_bytes=raw,
            recording_sha256=hashlib.sha256(raw).hexdigest(), process_chain=pending['process_chain'],
            observed_event_names=[row['name'] for row in pending['events']])
    return result


def _windows_types():
    """Windows x64 ABI declarations only: never load a library here."""
    U16, U32, U64 = C.c_uint16, C.c_uint32, C.c_uint64

    class GUID(C.Structure):
        _fields_ = [('bytes', C.c_ubyte * 16)]

    class FILETIME(C.Structure):
        _fields_ = [('low', U32), ('high', U32)]

    class EVENT_DESCRIPTOR(C.Structure):
        _fields_ = [('Id', U16), ('Version', C.c_ubyte), ('Channel', C.c_ubyte),
            ('Level', C.c_ubyte), ('Opcode', C.c_ubyte), ('Task', U16), ('Keyword', U64)]

    class EVENT_HEADER(C.Structure):
        _fields_ = [('Size', U16), ('HeaderType', U16), ('Flags', U16), ('EventProperty', U16),
            ('ThreadId', U32), ('ProcessId', U32), ('TimeStamp', U64), ('ProviderId', GUID),
            ('EventDescriptor', EVENT_DESCRIPTOR), ('ProcessorTime', U64), ('ActivityId', GUID)]

    class EVENT_RECORD(C.Structure):
        _fields_ = [('EventHeader', EVENT_HEADER), ('BufferContext', U32), ('ExtendedDataCount', U16),
            ('UserDataLength', U16), ('ExtendedData', C.c_void_p), ('UserData', C.c_void_p),
            ('UserContext', C.c_void_p)]

    class WNODE_HEADER(C.Structure):
        _fields_ = [('BufferSize', U32), ('ProviderId', U32), ('HistoricalContext', U64),
            ('TimeStamp', U64), ('Guid', GUID), ('ClientContext', U32), ('Flags', U32)]

    class EVENT_TRACE_PROPERTIES(C.Structure):
        _fields_ = [('Wnode', WNODE_HEADER)] + [(name, U32) for name in (
            'BufferSize', 'MinimumBuffers', 'MaximumBuffers', 'MaximumFileSize', 'LogFileMode',
            'FlushTimer', 'EnableFlags', 'AgeLimit', 'NumberOfBuffers', 'FreeBuffers', 'EventsLost',
            'BuffersWritten', 'LogBuffersLost', 'RealTimeBuffersLost')] + [
            ('LoggerThreadId', C.c_void_p), ('LogFileNameOffset', U32), ('LoggerNameOffset', U32)]

    class TRACE_LOGFILE_HEADER(C.Structure):
        _fields_ = [(name, U32) for name in ('BufferSize', 'Version', 'ProviderVersion', 'NumberOfProcessors')]
        _fields_ += [('EndTime', U64)] + [(name, U32) for name in (
            'TimerResolution', 'MaximumFileSize', 'LogFileMode', 'BuffersWritten')]
        _fields_ += [('LogInstanceGuid', GUID), ('LoggerName', C.c_void_p), ('LogFileName', C.c_void_p),
            ('TimeZone', C.c_ubyte * 172), ('BootTime', U64), ('PerfFreq', U64), ('StartTime', U64),
            ('ReservedFlags', U32), ('BuffersLost', U32)]

    class EVENT_TRACE(C.Structure):
        _fields_ = [('Header', C.c_ubyte * 48), ('InstanceId', U32), ('ParentInstanceId', U32),
            ('ParentGuid', GUID), ('MofData', C.c_void_p), ('MofLength', U32), ('ClientContext', U32)]

    callback = getattr(C, 'WINFUNCTYPE', C.CFUNCTYPE)(None, C.POINTER(EVENT_RECORD))

    class EVENT_TRACE_LOGFILE(C.Structure):
        _fields_ = [('LogFileName', C.c_wchar_p), ('LoggerName', C.c_wchar_p), ('CurrentTime', U64),
            ('BuffersRead', U32), ('ProcessTraceMode', U32), ('CurrentEvent', EVENT_TRACE),
            ('LogfileHeader', TRACE_LOGFILE_HEADER), ('BufferCallback', C.c_void_p),
            ('BufferSize', U32), ('Filled', U32), ('EventsLost', U32), ('EventRecordCallback', callback),
            ('IsKernelTrace', U32), ('Context', C.c_void_p)]

    class TRACE_EVENT_INFO(C.Structure):
        _fields_ = [('ProviderGuid', GUID), ('EventGuid', GUID), ('EventDescriptor', EVENT_DESCRIPTOR)]
        _fields_ += [(name, U32) for name in ('DecodingSource', 'ProviderNameOffset', 'LevelNameOffset',
            'ChannelNameOffset', 'KeywordsNameOffset', 'TaskNameOffset', 'OpcodeNameOffset',
            'EventMessageOffset', 'ProviderMessageOffset', 'BinaryXMLOffset', 'BinaryXMLSize',
            'EventNameOffset', 'EventAttributesOffset', 'PropertyCount', 'TopLevelPropertyCount', 'Flags')]

    class PROPERTY_DATA_DESCRIPTOR(C.Structure):
        _fields_ = [('PropertyName', U64), ('ArrayIndex', U32), ('Reserved', U32)]

    class EVENT_PROPERTY_INFO(C.Structure):
        _fields_ = [('Flags', U32), ('NameOffset', U32), ('InType', U16), ('OutType', U16),
            ('MapNameOffset', U32), ('Count', U16), ('Length', U16), ('Reserved', U32)]

    class EVENT_FILTER_DESCRIPTOR(C.Structure):
        _fields_ = [('Ptr', U64), ('Size', U32), ('Type', U32)]

    class ENABLE_TRACE_PARAMETERS(C.Structure):
        _fields_ = [('Version', U32), ('EnableProperty', U32), ('ControlFlags', U32),
            ('SourceId', GUID), ('EnableFilterDesc', C.POINTER(EVENT_FILTER_DESCRIPTOR)),
            ('FilterDescCount', U32)]

    class PROCESS_BASIC_INFORMATION(C.Structure):
        _fields_ = [('Reserved1', C.c_void_p), ('PebBaseAddress', C.c_void_p),
            ('Reserved2', C.c_void_p * 2), ('UniqueProcessId', C.c_size_t),
            ('InheritedFromUniqueProcessId', C.c_size_t)]

    class FILE_INFORMATION(C.Structure):
        _fields_ = [('FileAttributes', U32), ('CreationTime', FILETIME), ('LastAccessTime', FILETIME),
            ('LastWriteTime', FILETIME), ('VolumeSerialNumber', U32), ('FileSizeHigh', U32),
            ('FileSizeLow', U32), ('NumberOfLinks', U32), ('FileIndexHigh', U32), ('FileIndexLow', U32)]

    return SimpleNamespace(**{name: value for name, value in locals().items()
        if isinstance(value, type) and issubclass(value, C.Structure)}, callback=callback)


def _api(dll, name, restype, *args):
    function = getattr(dll, name)
    function.restype, function.argtypes = restype, list(args)
    return function


def _utf16(raw, offset=0):
    _need(type(raw) is bytes and type(offset) is int and 0 <= offset < len(raw)
          and offset % 2 == 0, 'event_text_invalid')
    for end in range(offset, len(raw) - 1, 2):
        if raw[end:end + 2] == b'\0\0':
            value = raw[offset:end].decode('utf-16-le', errors='strict')
            _need(len(value) <= 256, 'event_text_invalid')
            return value
    raise RecorderUnavailable('windows_recorder_event_text_invalid')


def _decode_property(raw, in_type, kind):
    """Decode a TDH scalar according to its native schema, never by byte length alone."""
    _need(type(raw) is bytes and 0 < len(raw) <= 1024 and type(in_type) is int,
          'event_property_invalid')
    if kind == 'uint':
        sizes = {7: (4, True), 8: (4, False), 9: (8, True), 10: (8, False)}
        _need(in_type in sizes and len(raw) == sizes[in_type][0], 'event_integer_invalid')
        value = int.from_bytes(raw, 'little', signed=sizes[in_type][1])
        _need(value >= 0, 'event_integer_invalid')
        return value
    _need(in_type in (1, 2), 'event_string_type_invalid')
    try:
        value = raw.decode('utf-16-le' if in_type == 1 else 'ascii', errors='strict')
    except UnicodeError:
        raise RecorderUnavailable('windows_recorder_event_text_invalid') from None
    _need(value.endswith('\0') and '\0' not in value[:-1] and len(value) <= 257,
          'event_text_invalid')
    value = value[:-1]
    allowed = {'mode': {'capabilities'}, 'policy': {'block', 'allow'}, 'status': {'success', 'failure'}}
    if kind == 'id':
        _need(_identifier(value), 'event_identity_invalid')
    elif kind == 'hash':
        _need(value.startswith('sha256:') and _hash(value[7:]), 'event_hash_invalid')
    else:
        _need(kind in allowed and value in allowed[kind], 'event_enum_invalid')
    return value


def _property_types(raw, a, wanted):
    _need(type(raw) is bytes and C.sizeof(a.TRACE_EVENT_INFO) <= len(raw) <= 65536,
          'event_schema_invalid')
    info = a.TRACE_EVENT_INFO.from_buffer_copy(raw)
    _need(0 < info.TopLevelPropertyCount <= info.PropertyCount <= 256
          and C.sizeof(a.TRACE_EVENT_INFO) + info.PropertyCount * C.sizeof(a.EVENT_PROPERTY_INFO)
          <= len(raw), 'event_schema_invalid')
    result = {}
    for index in range(info.TopLevelPropertyCount):
        offset = C.sizeof(a.TRACE_EVENT_INFO) + index * C.sizeof(a.EVENT_PROPERTY_INFO)
        prop = a.EVENT_PROPERTY_INFO.from_buffer_copy(raw, offset)
        _need(prop.NameOffset >= C.sizeof(a.TRACE_EVENT_INFO)
              + info.PropertyCount * C.sizeof(a.EVENT_PROPERTY_INFO), 'event_schema_invalid')
        name = _utf16(raw, prop.NameOffset)
        if name in wanted:
            _need(name not in result and prop.Flags & ~0x30 == 0 and prop.Count == 1,
                  'event_scalar_schema_invalid')
            result[name] = prop.InType
    _need(set(result) == set(wanted), 'event_property_missing')
    return result


class _WindowsProcessIdentity:
    """The recorder's single retained process/image measurement owner.

    Instantiated only for an explicit measurement/recording action. It cannot
    launch a process, start tracing, read tokens/jobs, or grant permission.
    """

    def __init__(self, deadline):
        _need(type(deadline) in (int, float) and math.isfinite(deadline)
              and time.monotonic() < deadline <= time.monotonic() + 51, 'deadline_invalid')
        _need(os.name == 'nt' and C.sizeof(C.c_void_p) == 8, 'platform_unsupported')
        self.deadline = deadline
        self.processes, self.images = {}, {}
        self.a = _windows_types()
        self.kernel = C.WinDLL('kernel32.dll', winmode=0x800, use_last_error=True)
        self.ntdll = C.WinDLL('ntdll.dll', winmode=0x800, use_last_error=True)
        P, U32 = C.c_void_p, C.c_uint32
        self.OpenProcess = _api(self.kernel, 'OpenProcess', P, U32, C.c_int, U32)
        self.CloseHandle = _api(self.kernel, 'CloseHandle', C.c_int, P)
        self.GetTimes = _api(self.kernel, 'GetProcessTimes', C.c_int, P, P, P, P, P)
        self.GetImage = _api(self.kernel, 'QueryFullProcessImageNameW', C.c_int, P, U32, C.c_wchar_p, P)
        self.BasicInfo = _api(self.ntdll, 'NtQueryInformationProcess', C.c_long, P, U32, P, U32, P)
        self.CreateFile = _api(self.kernel, 'CreateFileW', P, C.c_wchar_p, U32, U32, P, U32, U32, P)
        self.FileInfo = _api(self.kernel, 'GetFileInformationByHandle', C.c_int, P, P)
        self.ReadFile = _api(self.kernel, 'ReadFile', C.c_int, P, P, U32, P, P)
        self._tick()

    def _tick(self):
        _need(time.monotonic() < self.deadline, 'deadline_exceeded')

    def _own_handle(self, handle):
        _need(_uint(handle, 2**(C.sizeof(C.c_void_p) * 8)) and handle != C.c_void_p(-1).value, 'handle_unavailable')
        _need(handle not in self.processes.values()
              and all(handle != row[0] for row in self.images.values()), 'handle_reused')

    def _open_process(self, pid):
        _need(_uint(pid, 2**32), 'process_identity_invalid')
        if pid not in self.processes:
            _need(len(self.processes) < 32, 'chain_invalid')
            self._tick()
            handle = self.OpenProcess(0x100000 | 0x1000, False, pid)
            self._own_handle(handle)
            self.processes[pid] = handle
            self._tick()

    def _creation(self, pid):
        self._tick()
        values = [self.a.FILETIME() for _ in range(4)]
        status = self.GetTimes(self.processes[pid], *(C.byref(v) for v in values))
        _need(type(status) is int and status != 0, 'process_times_unavailable')
        self._tick()
        value = values[0].low | values[0].high << 32
        _need(_uint(value), 'process_times_unavailable')
        return value

    def _parent(self, pid):
        self._tick()
        info, returned = self.a.PROCESS_BASIC_INFORMATION(), C.c_uint32()
        status = self.BasicInfo(self.processes[pid], 0, C.byref(info), C.sizeof(info), C.byref(returned))
        self._tick()
        _need(type(status) is int and status == 0 and returned.value == C.sizeof(info) and info.UniqueProcessId == pid
              and _uint(info.InheritedFromUniqueProcessId, 2**32)
              and info.InheritedFromUniqueProcessId != pid, 'process_identity_unavailable')
        return info.InheritedFromUniqueProcessId

    def _file_info(self, handle):
        self._tick()
        value = self.a.FILE_INFORMATION()
        status = self.FileInfo(handle, C.byref(value))
        _need(type(status) is int and status != 0, 'image_metadata_unavailable')
        self._tick()
        _need(not value.FileAttributes & (0x10 | 0x400) and value.NumberOfLinks == 1, 'image_type_refused')
        _need(0 < (value.FileSizeHigh << 32 | value.FileSizeLow) < 2**31, 'image_size_invalid')
        return bytes(value)

    def _image(self, pid, expected_path=None):
        self._tick()
        buffer, length = C.create_unicode_buffer(32768), C.c_uint32(32768)
        status = self.GetImage(self.processes[pid], 0, buffer, C.byref(length))
        _need(type(status) is int and status != 0, 'image_unavailable')
        self._tick()
        image = buffer.value
        _need(0 < length.value < 32768 and len(image) == length.value, 'image_path_invalid')
        from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import _native_nonprivate_path
        _native_nonprivate_path(image)
        _need(expected_path is None or image.casefold() == expected_path.casefold(), 'image_path_changed')
        if pid in self.images:
            handle, path, metadata, digest, count = self.images[pid]
            _need(image == path and self._file_info(handle) == metadata, 'image_changed')
            return digest, count
        self._tick()
        _need(len(self.images) < 16, 'chain_invalid')
        handle = self.CreateFile(image, 0x80000000, 1, None, 3, 0x00200000, None)
        self._own_handle(handle)
        self.images[pid] = (handle, image, None, None, None)
        self._tick()
        before = self._file_info(handle)
        metadata = self.a.FILE_INFORMATION.from_buffer_copy(before)
        size = metadata.FileSizeHigh << 32 | metadata.FileSizeLow
        digest, total, chunk = hashlib.sha256(), 0, C.create_string_buffer(65536)
        while True:
            self._tick()
            count = C.c_uint32()
            status = self.ReadFile(handle, chunk, len(chunk), C.byref(count), None)
            _need(type(status) is int and status != 0, 'image_read_failed')
            self._tick()
            _need(count.value <= len(chunk), 'image_read_invalid')
            if not count.value:
                break
            total += count.value
            _need(total <= size and total < 2**31, 'image_size_invalid')
            digest.update(chunk.raw[:count.value])
        _need(total == size and before == self._file_info(handle), 'image_changed')
        self.images[pid] = (handle, image, before, digest.hexdigest(), total)
        return digest.hexdigest(), total

    def measure(self, pid, parent_pid, *, creation_filetime=None, parent_creation_filetime=None,
                image_sha256=None, image_bytes=None, expected_path=None):
        _need(_uint(pid, 2**32) and _uint(parent_pid, 2**32) and pid != parent_pid
              and pid != os.getpid(), 'chain_invalid')
        self._open_process(pid)
        _need(self._parent(pid) == parent_pid, 'process_parent_changed')
        self._open_process(parent_pid)
        birth, parent_birth = self._creation(pid), self._creation(parent_pid)
        _need(parent_birth <= birth and (creation_filetime is None or birth == creation_filetime)
              and (parent_creation_filetime is None or parent_birth == parent_creation_filetime), 'process_identity_changed')
        digest, count = self._image(pid, expected_path)
        _need((image_sha256 is None or digest == image_sha256)
              and (image_bytes is None or count == image_bytes), 'image_changed')
        _need(self._parent(pid) == parent_pid and self._creation(pid) == birth
              and self._creation(parent_pid) == parent_birth, 'process_identity_changed')
        _need(self._image(pid, expected_path) == (digest, count), 'image_changed')
        self._tick()
        return {'pid': pid, 'parent_pid': parent_pid, 'creation_filetime': birth,
                'parent_creation_filetime': parent_birth, 'image_sha256': digest, 'image_bytes': count}

    def snapshot(self):
        return [self.measure(**row) for row in self.spec['process_chain']]

    def _close_identity(self):
        failed = False
        handles = [row[0] for row in self.images.values()] + list(self.processes.values())
        self.images.clear()
        self.processes.clear()
        for handle in handles:
            try:
                status = self.CloseHandle(handle)
                failed = not (type(status) is int and status != 0) or failed
            except Exception:
                failed = True
        _need(not failed, 'native_cleanup_unconfirmed')


class WindowsEmitterIdentityReader:
    """Inert source-bound adapter; expected context is not measured policy.

    A caller must explicitly invoke measurement before a paused emitter is
    released. No later task child, token, job, file/network enforcement, original
    collector authentication, qualification or execution authority is supplied.
    """

    def __init__(self, context):
        _need(type(context) is dict and set(context) == {'attempt_id', 'session_id',
            'mxc_identity', 'policy_sha256', 'provider_sha256', 'provider_executable'}, 'emitter_context_invalid')
        _need(all(_identifier(context[key]) for key in ('attempt_id', 'session_id', 'mxc_identity'))
              and all(_hash(context[key]) for key in ('policy_sha256', 'provider_sha256'))
              and type(context['provider_executable']) is str
              and 0 < len(context['provider_executable']) < 32768
              and '\0' not in context['provider_executable'], 'emitter_context_invalid')
        self.context = json.loads(_json(context))

    def __call__(self, witness, *, deadline):
        _need(type(deadline) in (int, float) and math.isfinite(deadline)
              and time.monotonic() < deadline <= time.monotonic() + 51, 'deadline_invalid')
        _need(type(witness) is dict and _uint(witness.get('child_process_id'), 2**32)
              and _uint(witness.get('creator_process_id'), 2**32)
              and witness['child_process_id'] != witness['creator_process_id']
              and _uint(witness.get('child_creation_filetime'))
              and witness.get('resumed') is False and witness.get('created') is True
              and witness.get('assigned_before_resume') is True
              and all(witness.get(key) is False for key in ('native_admission', 'qualification', 'execution_authority'))
              and type(witness.get('actual_image_path')) is str
              and witness['actual_image_path'].casefold() == self.context['provider_executable'].casefold(),
              'emitter_witness_invalid')
        measurement = None
        try:
            measurement = _WindowsProcessIdentity(deadline)
            row = measurement.measure(witness['child_process_id'], witness['creator_process_id'],
                creation_filetime=witness['child_creation_filetime'], image_sha256=self.context['provider_sha256'],
                expected_path=self.context['provider_executable'])
        except RecorderUnavailable:
            raise
        except Exception:
            raise RecorderUnavailable('windows_recorder_emitter_measurement_unavailable') from None
        finally:
            if measurement is not None:
                measurement._close_identity()
        _need(time.monotonic() < deadline, 'deadline_exceeded')
        result = {key: self.context[key] for key in ('attempt_id', 'session_id', 'mxc_identity', 'policy_sha256')}
        return _request({'schema': 'AIOS_WINDOWS_WORKER_RECORDING_REQUEST.v1', **result,
                         'process_chain': [row]}, min_chain=1)


class _NativeWindowsSource(_WindowsProcessIdentity):
    """Own retained query handles and one bounded, memory-only ETW session."""

    def __init__(self, spec, deadline, max_events):
        _need(os.name == 'nt' and C.sizeof(C.c_void_p) == 8, 'platform_unsupported')
        spec = _request(spec, min_chain=1)
        self.spec, self.deadline, self.maximum = spec, deadline, max_events
        self.emitter_pid = spec['process_chain'][0]['pid']
        self.a = _windows_types()
        self.processes, self.images, self.events = {}, {}, []
        self.session, self.trace, self.thread = 0, None, None
        self.failure, self.consumer_status = False, None
        self.required_events = threading.Event()
        self.props_buffer = self.logfile = self._callback = None
        super().__init__(deadline)
        # Use the OS system DLL search path only, never the current directory.
        self.advapi = C.WinDLL('advapi32.dll', winmode=0x800, use_last_error=True)
        self.tdh = C.WinDLL('tdh.dll', winmode=0x800, use_last_error=True)
        U32, U64, P = C.c_uint32, C.c_uint64, C.c_void_p
        a = self.a
        self.Wait = _api(self.kernel, 'WaitForSingleObject', U32, P, U32)
        self.ExitCode = _api(self.kernel, 'GetExitCodeProcess', C.c_int, P, P)
        self.SystemTime = _api(self.kernel, 'GetSystemTimeAsFileTime', None, P)
        self.StartTrace = _api(self.advapi, 'StartTraceW', U32, P, C.c_wchar_p, P)
        self.EnableTrace = _api(self.advapi, 'EnableTraceEx2', U32, U64, P, U32, C.c_ubyte, U64, U64, U32, P)
        self.ControlTrace = _api(self.advapi, 'ControlTraceW', U32, U64, C.c_wchar_p, P, U32)
        self.OpenTrace = _api(self.advapi, 'OpenTraceW', U64, C.POINTER(a.EVENT_TRACE_LOGFILE))
        self.ProcessTrace = _api(self.advapi, 'ProcessTrace', U32, P, U32, P, P)
        self.CloseTrace = _api(self.advapi, 'CloseTrace', U32, U64)
        self.EventInfo = _api(self.tdh, 'TdhGetEventInformation', U32, P, U32, P, P, P)
        self.PropertySize = _api(self.tdh, 'TdhGetPropertySize', U32, P, U32, P, U32, P, P)
        self.Property = _api(self.tdh, 'TdhGetProperty', U32, P, U32, P, U32, P, U32, P)
        try:
            for row in spec['process_chain']:
                _need(row['pid'] != os.getpid(), 'self_observation_refused')
                self._open_process(row['pid'])
                self._open_process(row['parent_pid'])
        except Exception:
            self.close()
            raise

    def clock(self):
        value = self.a.FILETIME()
        self.SystemTime(C.byref(value))
        return value.low | value.high << 32

    def attach(self, spec):
        self._tick()
        _need(spec['process_chain'][1:] == self.spec['process_chain'], 'child_chain_mismatch')
        self._open_process(spec['process_chain'][0]['pid'])
        self.spec = spec

    def start(self):
        self._tick()
        _need(self.Wait(self.processes[self.spec['process_chain'][0]['pid']], 0) == 258,
              'emitter_not_running')
        name = 'AIOS.WindowsWorkerRecorder.' + str(self.spec['process_chain'][0]['pid'])
        encoded = name.encode('utf-16-le') + b'\0\0'
        self.props_buffer = C.create_string_buffer(C.sizeof(self.a.EVENT_TRACE_PROPERTIES) + len(encoded))
        props = self.a.EVENT_TRACE_PROPERTIES.from_buffer(self.props_buffer)
        props.Wnode.BufferSize, props.Wnode.Flags, props.Wnode.ClientContext = len(self.props_buffer), 0x20000, 2
        props.BufferSize, props.MinimumBuffers, props.MaximumBuffers = 64, 2, 4
        props.LogFileMode, props.FlushTimer = 0x100, 1
        props.LoggerNameOffset = C.sizeof(self.a.EVENT_TRACE_PROPERTIES)
        C.memmove(C.addressof(self.props_buffer) + props.LoggerNameOffset, encoded, len(encoded))
        session = C.c_uint64()
        _need(self.StartTrace(C.byref(session), name, C.byref(props)) == 0, 'trace_start_failed')
        self.session = session.value  # Own only the newly created session.
        provider = self.a.GUID.from_buffer_copy(uuid.UUID(MXC_PROVIDER).bytes_le)
        pid_filter = C.c_uint32(self.emitter_pid)
        descriptor = self.a.EVENT_FILTER_DESCRIPTOR(C.addressof(pid_filter), C.sizeof(pid_filter), 0x80000004)
        parameters = self.a.ENABLE_TRACE_PARAMETERS()
        parameters.Version, parameters.EnableFilterDesc, parameters.FilterDescCount = 2, C.pointer(descriptor), 1
        enable_timeout = max(1, int((self.deadline - time.monotonic()) * 1000))
        self._tick()
        _need(self.EnableTrace(self.session, C.byref(provider), 1, 5, 0, 0, enable_timeout,
                              C.byref(parameters)) == 0, 'trace_provider_unavailable')
        self._tick()
        self.logfile = self.a.EVENT_TRACE_LOGFILE()
        self.logfile.LoggerName, self.logfile.ProcessTraceMode = name, 0x100 | 0x10000000
        self._callback = self.a.callback(self._event)
        self.logfile.EventRecordCallback = self._callback
        self.trace = self.OpenTrace(C.byref(self.logfile))
        _need(self.trace != 2**64 - 1, 'trace_consumer_unavailable')
        self.thread = threading.Thread(target=self._consume, name='AIOS Windows recorder', daemon=True)
        self.thread.start()

    def _consume(self):
        handle = C.c_uint64(self.trace)
        try:
            self.consumer_status = self.ProcessTrace(C.byref(handle), 1, None, None)
        except Exception:
            self.failure = True

    def _property(self, record, name, kind, in_type):
        text = C.create_unicode_buffer(name)
        descriptor = self.a.PROPERTY_DATA_DESCRIPTOR(C.addressof(text), 0xffffffff, 0)
        size = C.c_uint32()
        _need(self.PropertySize(record, 0, None, 1, C.byref(descriptor), C.byref(size)) == 0
              and 0 < size.value <= 1024, 'event_property_unavailable')
        raw = C.create_string_buffer(size.value)
        _need(self.Property(record, 0, None, 1, C.byref(descriptor), size, raw) == 0,
              'event_property_unavailable')
        return _decode_property(raw.raw, in_type, kind)

    def _event(self, record):
        # No payload decoding for unrelated emitters, providers or after an error.
        try:
            header = record.contents.EventHeader
            if (self.failure or header.ProcessId != self.emitter_pid
                    or bytes(header.ProviderId) != uuid.UUID(MXC_PROVIDER).bytes_le):
                return
            self._tick()
            size = C.c_uint32()
            _need(self.EventInfo(record, 0, None, None, C.byref(size)) == 122
                  and C.sizeof(self.a.TRACE_EVENT_INFO) <= size.value <= 65536, 'event_schema_unavailable')
            raw = C.create_string_buffer(size.value)
            _need(self.EventInfo(record, 0, None, raw, C.byref(size)) == 0, 'event_schema_unavailable')
            info = self.a.TRACE_EVENT_INFO.from_buffer(raw)
            _need(info.EventNameOffset >= C.sizeof(self.a.TRACE_EVENT_INFO), 'event_schema_invalid')
            name = _utf16(raw.raw, info.EventNameOffset)
            if name not in _EVENT_FIELDS:
                return
            _need(len(self.events) < self.maximum, 'event_limit_exceeded')
            mapping = _NATIVE_EVENT_FIELDS[name]
            wanted = {mapping[key]: kind for key, kind in _EVENT_FIELDS[name].items()}
            types = _property_types(raw.raw, self.a, wanted)
            fields = {key: self._property(record, mapping[key], kind, types[mapping[key]])
                      for key, kind in _EVENT_FIELDS[name].items()}
            self.events.append({'provider': MXC_PROVIDER, 'emitter_pid': header.ProcessId,
                'timestamp_filetime': header.TimeStamp, 'name': name, 'fields': fields})
            if set(row['name'] for row in self.events) == set(_EVENT_FIELDS):
                self.required_events.set()
        except Exception:
            self.failure = True

    def wait(self, seconds):
        wait_deadline = min(self.deadline, time.monotonic() + seconds)
        pid = self.spec['process_chain'][0]['pid']
        result = self.Wait(self.processes[pid], max(1, int(seconds * 1000)))
        if result == 258:
            return {'root_exit_confirmed': False, 'exit_code': None}
        _need(result == 0, 'process_wait_failed')
        value = C.c_uint32()
        _need(self.ExitCode(self.processes[pid], C.byref(value)), 'process_exit_unavailable')
        _need(value.value == 0, 'process_outcome_unconfirmed')
        _need(self.required_events.wait(max(0, wait_deadline - time.monotonic())),
              'required_events_missing')
        return {'root_exit_confirmed': True, 'exit_code': value.value}

    def stop(self, seconds):
        stop_deadline = min(self.deadline, time.monotonic() + seconds)
        _need(self.session != 0, 'trace_session_missing')
        props = self.a.EVENT_TRACE_PROPERTIES.from_buffer(self.props_buffer)
        _need(self.ControlTrace(self.session, None, C.byref(props), 1) == 0, 'trace_stop_failed')
        self.session = 0
        if self.thread is not None:
            self.thread.join(max(0, min(stop_deadline - time.monotonic(), 2)))
        complete = self.thread is not None and not self.thread.is_alive() and self.consumer_status == 0
        return {'events': self.events, 'events_lost': props.EventsLost + self.logfile.EventsLost,
            'buffers_lost': props.LogBuffersLost + props.RealTimeBuffersLost,
            'consumer_complete': complete and not self.failure}

    def close(self):
        failed = False
        try:
            if self.session:
                props = self.a.EVENT_TRACE_PROPERTIES.from_buffer(self.props_buffer)
                failed = self.ControlTrace(self.session, None, C.byref(props), 1) != 0
                if not failed:
                    self.session = 0
        except Exception:
            failed = True
        trace, self.trace = self.trace, None
        try:
            if trace not in (None, 2**64 - 1):
                failed = self.CloseTrace(trace) not in (0, 7007) or failed
        except Exception:
            failed = True
        try:
            if self.thread is not None:
                self.thread.join(max(0, min(1, self.deadline - time.monotonic())))
                failed = self.thread.is_alive() or failed
        except Exception:
            failed = True
        try:
            self._close_identity()
        except Exception:
            failed = True
        _need(not failed, 'native_cleanup_unconfirmed')


def build_windows_launch_environment_block(environment):
    """Encode only a supplied map. Do not inspect the machine or grant permission."""
    _need(type(environment) is dict and len(environment) <= 256, 'launch_environment_invalid')
    seen = set()
    entries = []
    units = 1
    try:
        for key, value in environment.items():
            _need(type(key) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,255}', key)
                  and key.lower() not in seen and type(value) is str and len(value) <= 32767 and '\0' not in value,
                  'launch_environment_invalid')
            length = len(value.encode('utf-16-le')) // 2
            _need(length <= 32767, 'launch_environment_invalid')
            units += len(key) + length + 2
            _need(units <= 524288, 'launch_environment_invalid')
            seen.add(key.lower())
            entries.append((key, value))
        entries.sort(key=lambda row: row[0].lower())
        block = ''.join(key + '=' + value + '\0' for key, value in entries) + '\0'
        if not entries:
            block += '\0'
        return block.encode('utf-16-le')
    except UnicodeError as exc:
        raise RecorderUnavailable('windows_recorder_launch_encoding_invalid') from exc


def check_windows_launch_witness(witness, *, api_inputs, observed_identity, process):
    """Check a launch record against supplied facts, without authenticating them.

    No file, process, environment, network, or Windows API is read here. The
    caller must obtain original process identity and reviewed API inputs through
    the existing owners. Matching dictionaries alone never supply permission.
    This record does not describe the sandbox child created inside the worker.
    """
    from pathlib import PureWindowsPath

    fields = {'schema', 'native_admission', 'qualification', 'execution_authority',
        'creator_process_id', 'child_process_id', 'child_creation_filetime',
        'environment_block_bytes', 'actual_image_path', 'application_utf16_sha256',
        'command_line_utf16_sha256', 'directory_utf16_sha256',
        'environment_block_utf16_sha256', 'stdin_utf8_sha256', 'stdin_present',
        'created', 'assigned_before_resume', 'resumed'}
    _need(type(witness) is dict and set(witness) == fields, 'launch_witness_fields_invalid')
    _need(witness['schema'] == 'aios.windows_launch_witness.v1', 'launch_witness_schema_invalid')
    _need(all(witness[key] is False for key in ('native_admission', 'qualification', 'execution_authority')),
          'launch_witness_authority_invalid')
    _need(all(witness[key] is True for key in ('created', 'assigned_before_resume', 'resumed')),
          'launch_witness_incomplete')
    identity_fields = {'creator_process_id', 'child_process_id', 'child_creation_filetime'}
    _need(type(observed_identity) is dict and set(observed_identity) == identity_fields,
          'launch_identity_invalid')
    for key in identity_fields:
        maximum = 2**63 if key == 'child_creation_filetime' else 2**32
        _need(_uint(witness[key], maximum) and _uint(observed_identity[key], maximum)
              and witness[key] == observed_identity[key], 'launch_identity_mismatch')
    _need(witness['creator_process_id'] != witness['child_process_id'], 'launch_identity_invalid')
    process_fields = {'root_process_id', 'cleanup_state', 'root_exit_confirmed', 'tree_exit_confirmed',
        'drains_completed', 'stdin_completed', 'stdin_writer_joined', 'stdin_bytes_written',
        'stdin_error_code', 'stdin_close_error_code', 'cleanup_error_code', 'cancellation_error_code',
        'timed_out', 'startup_failed', 'process_error_present', 'exit_code', 'child_exit_code'}
    _need(type(process) is dict and set(process) == process_fields, 'launch_process_fields_invalid')
    _need(process['cleanup_state'] == 'CONFIRMED'
          and _uint(process['root_process_id'], 2**32)
          and process['root_process_id'] == witness['child_process_id']
          and all(process[key] is True for key in ('root_exit_confirmed', 'tree_exit_confirmed',
              'drains_completed', 'stdin_completed', 'stdin_writer_joined'))
          and all(process[key] is False for key in ('timed_out', 'startup_failed', 'process_error_present')),
          'launch_process_uncertain')
    _need(all(type(process[key]) is int and process[key] == 0 for key in ('stdin_error_code',
        'stdin_close_error_code', 'cleanup_error_code', 'cancellation_error_code', 'exit_code', 'child_exit_code')),
        'launch_process_failed')
    _need(type(api_inputs) is dict and set(api_inputs) == {'executable', 'command_line',
        'working_directory', 'environment', 'stdin_utf8'}, 'launch_inputs_invalid')
    for key in ('executable', 'working_directory'):
        value = api_inputs[key]
        _need(type(value) is str and 0 < len(value) <= 32766 and '\0' not in value
              and PureWindowsPath(value).is_absolute() and not value.startswith(('\\\\', '//'))
              and '..' not in PureWindowsPath(value).parts, 'launch_path_invalid')
    command = api_inputs['command_line']
    _need(type(command) is str and len(command) <= 32766 and '\0' not in command, 'launch_command_invalid')
    _need(type(witness['actual_image_path']) is str and len(witness['actual_image_path']) <= 32766
          and witness['actual_image_path'].lower() == api_inputs['executable'].lower(), 'launch_image_mismatch')
    environment_bytes = build_windows_launch_environment_block(api_inputs['environment'])
    try:
        encoded = {key: api_inputs[key].encode('utf-16-le')
                   for key in ('executable', 'command_line', 'working_directory')}
        _need(len(encoded['command_line']) // 2 <= 32766, 'launch_command_invalid')
        stdin = api_inputs['stdin_utf8']
        _need(stdin is None or (type(stdin) is str and len(stdin) <= 16777216), 'launch_input_invalid')
        stdin_size = 0
        stdin_digest = hashlib.sha256()
        if stdin is not None:
            # Each temporary encoding is at most 16 KiB, including non-BMP text.
            # Never make a full unbounded UTF-8 copy before checking its size.
            for offset in range(0, len(stdin), 4096):
                chunk = stdin[offset:offset + 4096].encode('utf-8')
                stdin_size += len(chunk)
                _need(stdin_size <= 16777216, 'launch_input_invalid')
                stdin_digest.update(chunk)
    except UnicodeError as exc:
        raise RecorderUnavailable('windows_recorder_launch_encoding_invalid') from exc
    _need(_uint(witness['environment_block_bytes'], 1048577)
          and witness['environment_block_bytes'] == len(environment_bytes), 'launch_environment_size_mismatch')
    _need(witness['stdin_present'] is (stdin is not None)
          and type(process['stdin_bytes_written']) is int
          and process['stdin_bytes_written'] == stdin_size, 'launch_input_incomplete')
    values = {'application_utf16_sha256': encoded['executable'],
        'command_line_utf16_sha256': encoded['command_line'],
        'directory_utf16_sha256': encoded['working_directory'],
        'environment_block_utf16_sha256': environment_bytes}
    _need(all(_hash(witness[key]) and witness[key] == hashlib.sha256(value).hexdigest()
              for key, value in values.items()), 'launch_input_digest_mismatch')
    _need(_hash(witness['stdin_utf8_sha256'])
          and witness['stdin_utf8_sha256'] == stdin_digest.hexdigest(), 'launch_input_digest_mismatch')
    return {'schema': 'AIOS_WINDOWS_LAUNCH_WITNESS_CHECK.v1', 'status': 'CONSISTENT',
        'origin_authenticated': False, 'native_admission': False, 'qualification': False,
        'execution_authority': False, 'witness_sha256': hashlib.sha256(_json(witness)).hexdigest()}


def worker_observation_handoff(recording_request, result):
    """Carry original bounded observation bytes, never a qualification grant."""
    import base64
    spec = _request(recording_request)
    _need(type(result) is dict and result.get('recording_status') == 'RECORDED_REQUIRES_REVIEW'
          and type(result.get('recording_bytes')) is bytes
          and 0 < len(result['recording_bytes']) <= 1048576
          and result.get('recording_sha256') == hashlib.sha256(result['recording_bytes']).hexdigest()
          and all(result.get(key) is False for key in ('native_admission_granted',
              'windows_qualification', 'complete_worker_proof')), 'observation_result_invalid')
    value = {'schema': 'AIOS_WINDOWS_WORKER_OBSERVATION_HANDOFF.v1',
             'recording_request': spec,
             'recording_base64': base64.b64encode(result['recording_bytes']).decode('ascii'),
             'recording_sha256': result['recording_sha256'],
             'authority_granted': False, 'qualification': False}
    check_worker_observation_handoff(value)
    return value


def check_worker_observation_handoff(value):
    """Check supplied bytes and bindings only; no native call or authentication."""
    import base64
    _need(type(value) is dict and set(value) == {'schema', 'recording_request',
        'recording_base64', 'recording_sha256', 'authority_granted', 'qualification'}
        and value['schema'] == 'AIOS_WINDOWS_WORKER_OBSERVATION_HANDOFF.v1'
        and value['authority_granted'] is False and value['qualification'] is False,
        'observation_handoff_invalid')
    spec = _request(value['recording_request'])
    encoded = value['recording_base64']
    _need(type(encoded) is str and 0 < len(encoded) <= 1398104, 'observation_bytes_invalid')
    try:
        raw = base64.b64decode(encoded, validate=True)
        observed = json.loads(raw)
    except Exception:
        raise RecorderUnavailable('windows_recorder_observation_bytes_invalid') from None
    _need(0 < len(raw) <= 1048576 and _hash(value['recording_sha256'])
          and hashlib.sha256(raw).hexdigest() == value['recording_sha256'], 'observation_hash_mismatch')
    _need(type(observed) is dict and set(observed) == {'schema', 'request_sha256', 'attempt_id',
        'session_id', 'process_chain', 'interval', 'events', 'evidence_kind',
        'complete_worker_proof', 'missing_original_roles'}
        and observed['schema'] == 'AIOS_WINDOWS_NATIVE_OBSERVATIONS.v1'
        and observed['request_sha256'] == hashlib.sha256(_json(spec)).hexdigest()
        and observed['attempt_id'] == spec['attempt_id'] and observed['session_id'] == spec['session_id']
        and _json(observed['process_chain']) == _json(spec['process_chain'])
        and observed['evidence_kind'] == 'native_identity_and_projected_etw_only'
        and observed['complete_worker_proof'] is False
        and observed['missing_original_roles'] == list(_MISSING_ROLES), 'observation_binding_invalid')
    interval = observed['interval']
    _need(type(interval) is dict and set(interval) == {'started_filetime', 'ended_filetime'}
          and _uint(interval['started_filetime']) and _uint(interval['ended_filetime'])
          and interval['started_filetime'] <= interval['ended_filetime'], 'observation_interval_invalid')
    _checked_events(observed['events'], spec, interval['started_filetime'], interval['ended_filetime'], 4096)
    return {'status': 'CONSISTENT_REQUIRES_REVIEW', 'recording_request': spec,
            'recording_sha256': value['recording_sha256'], 'authority_granted': False,
            'qualification': False, 'origin_authenticated': False}


def _check_paused_emitter_witness(request, prompt, witness):
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import validate_worker_launch_contract
    from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import _native_windows_arguments
    fields = {'schema', 'native_admission', 'qualification', 'execution_authority',
        'creator_process_id', 'child_process_id', 'child_creation_filetime', 'environment_block_bytes',
        'actual_image_path', 'application_utf16_sha256', 'command_line_utf16_sha256',
        'directory_utf16_sha256', 'environment_block_utf16_sha256', 'stdin_utf8_sha256',
        'stdin_present', 'created', 'assigned_before_resume', 'resumed'}
    _need(type(witness) is dict and set(witness) == fields
          and witness['schema'] == 'aios.windows_launch_witness.v1'
          and all(witness[key] is False for key in ('native_admission', 'qualification',
              'execution_authority', 'resumed'))
          and all(witness[key] is True for key in ('created', 'assigned_before_resume', 'stdin_present'))
          and _uint(witness['creator_process_id'], 2**32)
          and _uint(witness['child_process_id'], 2**32)
          and witness['creator_process_id'] != witness['child_process_id']
          and _uint(witness['child_creation_filetime']), 'paused_emitter_witness_invalid')
    launch = validate_worker_launch_contract(request.get('worker_launch_contract'))
    command = '"' + request['provider_executable'] + '" ' + _native_windows_arguments(request['provider_args'])
    expected = {'application_utf16_sha256': request['provider_executable'],
                'command_line_utf16_sha256': command, 'directory_utf16_sha256': request['repo_root']}
    _need(type(witness['actual_image_path']) is str
          and witness['actual_image_path'].lower() == request['provider_executable'].lower()
          and all(witness[key] == hashlib.sha256(value.encode('utf-16-le')).hexdigest()
                  for key, value in expected.items())
          and type(witness['environment_block_bytes']) is int
          and witness['environment_block_bytes'] == launch['environment_block_bytes']
          and witness['environment_block_utf16_sha256'] == launch['environment_block_utf16_sha256']
          and type(prompt) is str and len(prompt.encode('utf-8')) <= 16777216
          and witness['stdin_utf8_sha256'] == hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
          'paused_emitter_launch_mismatch')
    return json.loads(_json(witness))


class WindowsWorkerObservationHost:
    """One-use source-injected connection over the existing recorder owners.

    The supplied launcher must implement the typed pre-resume and child callbacks.
    The current process CLI has no such physical transport and refuses this
    profile. Construction/import is inert. This class grants no native run.
    """

    def __init__(self, *, emitter_reader, protected_child_reader):
        _need(callable(emitter_reader) and callable(protected_child_reader), 'observation_ports_invalid')
        self._emitter_reader = emitter_reader
        self._child_reader = protected_child_reader
        self.used = False

    def invoke(self, enqueued, launcher):
        from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import (
            validate_worker_observation_contract, bound_path)
        from pathlib import Path
        _need(not self.used and callable(launcher), 'observation_host_reused')
        self.used = True
        prepared, emitter, witness, recorded, child_spec = None, None, None, None, None
        before_used, collection_used = False, False
        try:
            request = json.loads(enqueued['task']['request_json'])
            contract = validate_worker_observation_contract(request.get('worker_observation_contract'))
            prompt = enqueued['task']['prompt_text']

            def before_resume(actual_witness, remaining_milliseconds):
                nonlocal prepared, emitter, witness, before_used
                _need(not before_used, 'observation_before_resume_reused')
                before_used = True
                _need(type(remaining_milliseconds) is int and 0 < remaining_milliseconds <= 3600000,
                      'observation_deadline_invalid')
                deadline = time.monotonic() + min(contract['timeout_seconds'], remaining_milliseconds / 1000)
                witness = _check_paused_emitter_witness(request, prompt, actual_witness)
                emitter = _request(self._emitter_reader(json.loads(_json(witness)), deadline=deadline), min_chain=1)
                _need(time.monotonic() < deadline, 'deadline_exceeded')
                top = emitter['process_chain'][0]
                _need(emitter['attempt_id'] == request['attempt_id']
                      and all(emitter[key] == contract[key] for key in ('session_id', 'mxc_identity', 'policy_sha256'))
                      and top['pid'] == witness['child_process_id']
                      and top['creation_filetime'] == witness['child_creation_filetime']
                      and top['parent_pid'] == witness['creator_process_id']
                      and top['image_sha256'] == request['provider_sha256'], 'observation_emitter_mismatch')
                prepared = prepare_windows_worker_recording(emitter,
                    timeout_seconds=min(contract['timeout_seconds'], remaining_milliseconds / 1000),
                    max_events=contract['max_events'], deadline=deadline)
                prepared.__enter__()
                prepared.remaining()
                return True

            def collect_protected_child():
                nonlocal collection_used, recorded, child_spec
                _need(prepared is not None and not collection_used, 'observation_collection_unprepared')
                collection_used = True
                child_spec = _request(self._child_reader())
                _need({**child_spec, 'process_chain': child_spec['process_chain'][1:]} == emitter,
                      'observation_child_mismatch')
                recorded = record_windows_worker(child_spec, prepared=prepared)
                _need(recorded['recording_status'] == 'RECORDED_REQUIRES_REVIEW', 'observation_collection_failed')
                return recorded

            response = launcher(enqueued, before_resume=before_resume,
                                collect_protected_child=collect_protected_child)
            _need(before_used and collection_used and recorded is not None
                  and type(response) is dict, 'observation_callbacks_incomplete')
            expected = worker_observation_handoff(child_spec, recorded)
            capture_path = bound_path(response.get('execution_path'), root=Path(request['relay_root']) / 'outbox')
            _need(capture_path.stat().st_size <= 16777216, 'observation_capture_oversized')
            capture_raw = capture_path.read_bytes()
            _need(hashlib.sha256(capture_raw).hexdigest() == response.get('execution_sha256'),
                  'observation_capture_hash_mismatch')
            capture = json.loads(capture_raw)
            _need(type(capture) is dict and _json(capture.get('worker_observation')) == _json(expected),
                  'observation_original_not_saved')
            return response
        except Exception:
            raise RecorderUnavailable('windows_recorder_observation_connection_failed') from None
        finally:
            if prepared is not None:
                prepared.close()
