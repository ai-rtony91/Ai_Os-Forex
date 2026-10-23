"""Validate generated Codex prompts and atomically enqueue relay tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from automation.orchestration.aios_resume_state import (
    SOURCE_FILES as _PUBLICATION_SOURCE_FILES,
)


REQUIRED_MARKERS = (
    "AI_OS EXECUTION TOKEN",
    "AI_OS BOOTSTRAP REQUIRED",
    "IDENTITY MARKER",
    "SUPERVISOR IDENTITY",
    "WORKER IDENTITY",
    "PACKET ID",
    "MODE",
    "ZONE",
    "LANE",
    "ALLOWED PATHS",
    "FORBIDDEN PATHS",
    "APPROVAL AUTHORITY",
    "VALIDATOR CHAIN",
    "STOP POINT",
    "MISSION",
    "PREFLIGHT",
    "FINAL REPORT FORMAT",
)
PROTECTED_FLAGS = (
    "staging",
    "commit",
    "push",
    "pull_request",
    "merge",
    "branch_change",
    "scheduler_or_service",
    "credentials_or_secrets",
    "broker_or_oanda",
    "order_submission",
    "live_trading",
    "money_movement",
)
PLACEHOLDER = re.compile(r"(?:\bTODO\b|\bTBD\b|@filename|path/to/file|\[REAL-FILENAME\]|\{feature\})", re.I)


class PromptValidationError(ValueError):
    """The prompt is not safe to enqueue."""


@dataclass(frozen=True)
class ValidatedPrompt:
    path: Path
    text: str
    sha256: str
    packet_id: str
    mode: str
    allowed_paths: tuple[str, ...]


def _section(text: str, name: str) -> str:
    pattern = re.compile(
        rf"(?ims)^\s*(?:##\s*)?{re.escape(name)}\s*:?[ \t]*\r?\n(.*?)(?=^\s*(?:##\s*)?[A-Z][A-Z0-9 _/-]+\s*:?[ \t]*\r?$|\Z)"
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _field(text: str, name: str) -> str:
    match = re.search(rf"(?im)^\s*(?:##\s*)?{re.escape(name)}\s*:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def _paths(text: str, section_name: str) -> tuple[str, ...]:
    body = _section(text, section_name)
    return tuple(
        line[2:].strip().replace("\\", "/")
        for line in body.splitlines()
        if line.strip().startswith("- ") and line[2:].strip()
    )


def validate_prompt(path: Path) -> ValidatedPrompt:
    path = path.resolve(strict=True)
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise PromptValidationError("prompt must be UTF-8 without a BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PromptValidationError("prompt must be UTF-8") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text or text.splitlines()[0] != "CODEX-ONLY PROMPT":
        raise PromptValidationError("CODEX-ONLY PROMPT must be the exact first line")
    if PLACEHOLDER.search(text):
        raise PromptValidationError("prompt contains an unresolved placeholder")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        raise PromptValidationError("missing required field(s): " + ", ".join(missing))
    if text.count("AI_OS EXECUTION TOKEN") != 1:
        raise PromptValidationError("execution token must occur exactly once")
    packet_id = _field(text, "PACKET ID") or _field(text, "Packet ID")
    mode = _field(text, "MODE") or _field(text, "Mode")
    allowed_paths = _paths(text, "ALLOWED PATHS")
    forbidden_paths = _paths(text, "FORBIDDEN PATHS")
    if not packet_id or not mode or not allowed_paths or not forbidden_paths:
        raise PromptValidationError("packet id, mode, allowed paths, and forbidden paths must be non-empty")
    if len(set(allowed_paths)) != len(allowed_paths):
        raise PromptValidationError("allowed paths contain duplicates")
    if set(allowed_paths) & set(forbidden_paths):
        raise PromptValidationError("allowed and forbidden paths conflict")
    return ValidatedPrompt(path, text, hashlib.sha256(raw).hexdigest(), packet_id, mode, allowed_paths)


def classify_authority(flags: Mapping[str, object]) -> tuple[bool, dict[str, bool]]:
    if set(flags) != set(PROTECTED_FLAGS):
        missing = sorted(set(PROTECTED_FLAGS) - set(flags))
        extra = sorted(set(flags) - set(PROTECTED_FLAGS))
        raise PromptValidationError(f"protected flags mismatch; missing={missing}, extra={extra}")
    if any(type(value) is not bool for value in flags.values()):
        raise PromptValidationError("every protected-action flag must be boolean")
    normalized = {name: flags[name] for name in PROTECTED_FLAGS}
    return any(normalized.values()), normalized


REQUEST_SCHEMA = "AIOS_RELAY_REQUEST.v1"
BOUND_IMPLEMENTATIONS = (
    "automation/orchestration/relay/aios_codex_prompt_consumer_v1.py",
    "automation/orchestration/relay/aios_self_consuming_codex_cycle_v1.py",
    "automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1",
    "automation/orchestration/preflight/Test-AiOsToolPreflight.ps1",
    "automation/orchestration/cost/Add-AiOsCostLedgerEntry.ps1",
    "automation/orchestration/validators/output/Test-AiOsWorkerOutput.DRY_RUN.ps1",
    "automation/orchestration/timeout/Invoke-AiOsCliWithTimeout.ps1",
    "automation/orchestration/validator_chain_runner/Invoke-AiOsValidatorChain.DRY_RUN.ps1",
    "automation/orchestration/aios_repo_state_evidence.py",
    "automation/orchestration/aios_self_build_apply_result_verifier.py",
    "automation/orchestration/claims/aios_task_claim_control.py",
    "automation/orchestration/cost/Test-AiOsCostCeiling.ps1",
    "automation/orchestration/lock/Test-AiOsFileLock.ps1",
    "services/python_supervisor/notifier.py",
    "automation/orchestration/dashboard/aios_resume_visibility.py",
    "automation/orchestration/notifications/Send-AiOsNotification.ps1",
)
# The new qualified request binds the actual receiving/publication closure,
# not merely the provider entry file. Frozen older requests remain historical.
BOUND_IMPLEMENTATIONS = tuple(dict.fromkeys((*BOUND_IMPLEMENTATIONS,
    "automation/orchestration/aios_abcd_autonomy_runner.py",
    *("automation/orchestration/" + name for name in _PUBLICATION_SOURCE_FILES))))


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _hash(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise PromptValidationError("invalid_digest")
    return value


def bound_path(value: object, *, root: Path | None = None) -> Path:
    if not isinstance(value, str) or not value or value.startswith(("\\\\", "//")) or "\x00" in value:
        raise PromptValidationError("invalid_absolute_path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path.resolve()) != value:
        raise PromptValidationError("noncanonical_path")
    for part in [path, *path.parents]:
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise PromptValidationError("reparse_path_rejected")
    if root is not None:
        try: path.relative_to(root)
        except ValueError as exc: raise PromptValidationError("path_outside_selected_root") from exc
    return path


def source_relative(value: object) -> str:
    if (not isinstance(value, str) or not value or "\\" in value or value.startswith("/") or ":" in value
            or any(part in {"", ".", ".."} for part in value.split("/")) or any(c in value for c in "*?[]\x00\r\n")):
        raise PromptValidationError("invalid_source_path")
    lower = value.casefold()
    if (lower.startswith((".git/", ".env", "credentials/", "secrets/", "automation/orchestration/approval_inbox/"))
            or "/approvals/" in lower or lower == "control/mode/cost_ledger.jsonl"):
        raise PromptValidationError("private_inventory_rejected")
    if (any(part in {".git",".aws",".codex","approval","approvals","secret","secrets","credential","credentials","private"} or part==".env" or part.startswith(".env.") for part in lower.split("/"))
            or lower.startswith(("control/","runtime/")) or lower.endswith((".pem",".pfx",".p12",".key"))):
        raise PromptValidationError("private_inventory_rejected")
    return value


def validate_worker_launch_contract(value):
    """Check reviewed request data; never supply settings or permission."""
    from automation.orchestration.aios_self_build_apply_result_verifier import build_windows_launch_environment_block
    if (type(value) is not dict or set(value) != {'schema', 'environment',
            'environment_block_utf16_sha256', 'environment_block_bytes'}
            or value['schema'] != 'AIOS_SELECTED_WORKER_LAUNCH.v1'):
        raise PromptValidationError('worker_launch_contract_invalid')
    try:
        block = build_windows_launch_environment_block(value['environment'])
    except ValueError as exc:
        raise PromptValidationError('worker_launch_environment_invalid') from exc
    if (type(value['environment_block_bytes']) is not int
            or value['environment_block_bytes'] != len(block)
            or _hash(value['environment_block_utf16_sha256']) != hashlib.sha256(block).hexdigest()):
        raise PromptValidationError('worker_launch_environment_binding_mismatch')
    return json.loads(canonical_json(value))


def validate_worker_observation_contract(value):
    """Validate inert observation metadata; it supplies no host or permission."""
    import math
    fields = {'schema', 'session_id', 'mxc_identity', 'policy_sha256', 'timeout_seconds', 'max_events'}
    if (type(value) is not dict or set(value) != fields
            or value['schema'] != 'AIOS_SELECTED_WORKER_OBSERVATION.v1'
            or any(type(value[key]) is not str or re.fullmatch('[A-Za-z0-9_-]{1,128}', value[key]) is None
                   for key in ('session_id', 'mxc_identity'))
            or type(value['policy_sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}', value['policy_sha256']) is None
            or type(value['timeout_seconds']) not in (int, float)
            or not math.isfinite(value['timeout_seconds']) or not 0 < value['timeout_seconds'] <= 51
            or type(value['max_events']) is not int or not 4 <= value['max_events'] <= 4096):
        raise PromptValidationError('worker_observation_contract_invalid')
    return json.loads(canonical_json(value))


def validate_bound_request(value: object, prompt: ValidatedPrompt | None = None) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("schema") != REQUEST_SCHEMA:
        raise PromptValidationError("bound_request_required")
    request = json.loads(canonical_json(value))
    if "worker_observation_contract" in request:
        observation = validate_worker_observation_contract(request["worker_observation_contract"])
        if "worker_launch_contract" not in request:
            raise PromptValidationError('worker_observation_launch_contract_required')
        if type(request.get('timeout_sec')) is int and observation['timeout_seconds'] > request['timeout_sec']:
            raise PromptValidationError('worker_observation_deadline_exceeds_launch')
    if "worker_launch_contract" in request:
        validate_worker_launch_contract(request["worker_launch_contract"])
    for key in ("campaign_id", "task_id", "packet_id", "attempt_id", "cycle_id"):
        if not isinstance(request.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request[key]):
            raise PromptValidationError("invalid_request_identity")
    if request.get("repository") != "ai-rtony91/Ai_Os-Forex" or request.get("repository_id") != "1227385337":
        raise PromptValidationError("wrong_repository")
    root = bound_path(request.get("repo_root")); relay = bound_path(request.get("relay_root"), root=root)
    if relay == root: raise PromptValidationError("relay_root_is_repository_root")
    identity = request.get("repository_identity")
    if (not isinstance(identity, dict) or identity.get("resolved") is not True or identity.get("repo_root") != str(root)
            or not isinstance(identity.get("branch"), str) or identity["branch"] in {"", "unknown", "detached"}
            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(identity.get("commit", "")))):
        raise PromptValidationError("repository_identity_unresolved")
    bound_path(identity.get("git_dir"))
    claim = request.get("claim_ref")
    if (not isinstance(claim, dict) or set(claim) != {"owner", "task_id", "acquired_at", "identity_sha256"}
            or claim.get("owner") != "TaskClaimController" or claim.get("task_id") != request["task_id"]
            or not isinstance(claim.get("acquired_at"), str) or not claim["acquired_at"]):
        raise PromptValidationError("claim_reference_invalid")
    from datetime import datetime
    try:
        acquired = datetime.fromisoformat(claim["acquired_at"].replace("Z", "+00:00"))
        if acquired.tzinfo is None: raise ValueError()
    except ValueError as exc: raise PromptValidationError("claim_reference_invalid") from exc
    _hash(claim.get("identity_sha256"))
    for key in ("attempt_number", "max_attempts", "timeout_sec"):
        if type(request.get(key)) is not int: raise PromptValidationError("invalid_attempt_or_timeout")
    if not 0 <= request["attempt_number"] < request["max_attempts"] or not 1 <= request["timeout_sec"] <= 3600:
        raise PromptValidationError("attempt_or_timeout_exhausted")
    if request.get("priority") not in {"P0", "P1", "P2", "P3"} or not isinstance(request.get("depends_on"), list) or any(not isinstance(x,str) or not x for x in request["depends_on"]):
        raise PromptValidationError("queue_metadata_invalid")
    for key in ("allowed_paths", "source_paths", "controller_metadata_paths"):
        values=request.get(key)
        if not isinstance(values,list) or len(set(map(str,values))) != len(values): raise PromptValidationError("inventory_invalid")
        for item in values:
            source_relative(item); bound_path(str(root / item),root=root)
    if not request["allowed_paths"] or not set(request["allowed_paths"]).issubset(request["source_paths"]):
        raise PromptValidationError("inventory_coverage_missing")
    validate_preservation_contract(request)
    if set(request["allowed_paths"]) & set(request["controller_metadata_paths"]):
        raise PromptValidationError("worker_metadata_scope_overlap")
    manifest=request.get("source_manifest")
    if not isinstance(manifest,dict) or not manifest or hashlib.sha256(canonical_json(manifest)).hexdigest()!=request.get("source_manifest_sha256"):
        raise PromptValidationError("source_manifest_invalid")
    if not set(BOUND_IMPLEMENTATIONS).issubset(manifest) or set(request["allowed_paths"]) & set(manifest):
        raise PromptValidationError("implementation_binding_missing_or_writable")
    for relative,digest in manifest.items():
        source_relative(relative);_hash(digest)
        path=bound_path(str(root / relative),root=root)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise PromptValidationError("source_binding_changed")
    _hash(request.get("validator_spec_sha256"))
    if request.get("provider")!="codex" or request.get("provider_args") != ["--no-daemon","exec","--sandbox","workspace-write","-"]:
        raise PromptValidationError("provider_contract_unsupported")
    provider=bound_path(request.get("provider_executable"));_hash(request.get("provider_sha256"))
    if not provider.is_file() or hashlib.sha256(provider.read_bytes()).hexdigest()!=request["provider_sha256"]:
        raise PromptValidationError("provider_binding_changed")
    bound_path(request.get("python_executable"));policy=bound_path(request.get("policy_path"),root=root);source_relative(policy.relative_to(root).as_posix())
    source=bound_path(request.get("prompt_path"),root=root);source_relative(source.relative_to(root).as_posix());_hash(request.get("prompt_sha256"))
    actual=prompt or validate_prompt(source)
    if actual.path!=source or actual.sha256!=request["prompt_sha256"] or actual.packet_id!=request["packet_id"] or list(actual.allowed_paths)!=request["allowed_paths"] or actual.mode!="APPLY":
        raise PromptValidationError("packet_request_mismatch")
    return request


def _preservation_runtime_path(request: dict) -> Path:
    """Apply the existing nonprivate inventory rule before payload inspection."""
    runtime = bound_path(request["python_executable"])
    # This helper is also reached before the receiving context authenticates
    # repo_root. Never strip an untrusted anchor and hide its private prefix.
    source_relative(Path(*runtime.parts[1:]).as_posix())
    root = bound_path(request["repo_root"])
    if runtime.is_relative_to(root):
        source_relative(runtime.relative_to(root).as_posix())
    return runtime


def build_preservation_contract(request: dict, *, action_id: str | None = None) -> dict:
    """New request input, never a repin of a previously qualified request.

    In this provider profile one invocation executes the selected dispatch task.
    A distinct action already present on the selected packet must be supplied
    explicitly and is checked again against that original packet by the reader.
    """
    from automation.orchestration.aios_repo_state_evidence import (
        FULL_WORKTREE_CAPTURE_RULES_SHA256,
    )
    return {"schema": "AIOS_SELECTED_PROVIDER_PRESERVATION.v1",
            "action_id": request["task_id"] if action_id is None else action_id,
            "max_files_changed": len(request["allowed_paths"]),
            "rules_sha256": FULL_WORKTREE_CAPTURE_RULES_SHA256,
            "python_sha256": hashlib.sha256(_preservation_runtime_path(request).read_bytes()).hexdigest()}


def validate_preservation_contract(request: dict) -> dict:
    from automation.orchestration.aios_repo_state_evidence import (
        FULL_WORKTREE_CAPTURE_RULES_SHA256,
    )
    value = request.get("preservation_contract")
    if (type(value) is not dict or set(value) != {"schema", "action_id", "max_files_changed", "rules_sha256", "python_sha256"}
            or value["schema"] != "AIOS_SELECTED_PROVIDER_PRESERVATION.v1"
            or type(value["action_id"]) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value["action_id"])
            or type(value["max_files_changed"]) is not int
            or not 1 <= value["max_files_changed"] <= len(request["allowed_paths"])
            or value["rules_sha256"] != FULL_WORKTREE_CAPTURE_RULES_SHA256):
        raise PromptValidationError("preservation_contract_invalid")
    _hash(value["python_sha256"])
    runtime = _preservation_runtime_path(request)
    if not runtime.is_file() or hashlib.sha256(runtime.read_bytes()).hexdigest() != value["python_sha256"]:
        raise PromptValidationError("preservation_runtime_changed")
    return value


def request_binding(request: dict, digest: str) -> dict:
    return {"request_sha256": digest, "task_id": request["task_id"], "packet_id": request["packet_id"],
        "attempt_id": request["attempt_id"], "attempt_number": request["attempt_number"],
        "claim_task_id": request["claim_ref"]["task_id"], "claim_acquired_at": request["claim_ref"]["acquired_at"],
        "claim_identity_sha256": request["claim_ref"]["identity_sha256"], "campaign_id": request["campaign_id"]}


def read_bound_packet(path: str, digest: str, repo_root: str, relay_root: str) -> dict:
    root=bound_path(repo_root); relay=bound_path(relay_root,root=root); selected=bound_path(path,root=relay)
    if selected.parent not in {relay/"inbox",relay/"running"} or not re.fullmatch(r"bound-[0-9a-f]{64}\.task\.json",selected.name):raise PromptValidationError("selected_packet_path_mismatch")
    data=selected.read_bytes()
    if hashlib.sha256(data).hexdigest()!=_hash(digest):raise PromptValidationError("packet_digest_mismatch")
    task=json.loads(data)
    if not isinstance(task,dict) or not isinstance(task.get("request_json"),str):raise PromptValidationError("request_json_missing")
    request=validate_bound_request(json.loads(task["request_json"]))
    if request["repo_root"]!=repo_root or request["relay_root"]!=relay_root:raise PromptValidationError("selected_root_mismatch")
    _, flags=classify_authority(task.get("protected_action_flags",{}))
    expected=_enqueue_bound(validate_prompt(Path(request["prompt_path"])),relay,flags,request,True)
    if expected["status"]=="APPROVAL_REQUIRED" or data!=canonical_json(expected["task"])+b"\n":raise PromptValidationError("packet_binding_mismatch")
    if selected not in {relay/state/(task["id"]+".task.json") for state in ("inbox","running")}:
        raise PromptValidationError("selected_packet_path_mismatch")
    return {"request":request,"task":task,"binding":request_binding(request,task["request_sha256"])}


def _enqueue_bound(prompt: ValidatedPrompt, relay_root: Path, flags: dict[str,bool], request: object, dry_run: bool) -> dict[str,object]:
    request=validate_bound_request(request,prompt)
    if relay_root != Path(request["relay_root"]): raise PromptValidationError("selected_relay_root_mismatch")
    request_json=canonical_json(request).decode("ascii"); digest=hashlib.sha256(request_json.encode("ascii")).hexdigest()
    task={"id":"bound-"+digest,"worker":"codex","provider":"codex","tier":"TIER_1_BOUNDED_APPLY",
        "mission":f"Execute validated prompt {prompt.packet_id}","allowed_paths":list(prompt.allowed_paths),
        "approval_required":False,"protected_action_flags":flags,"prompt_path":str(prompt.path),"prompt_sha256":prompt.sha256,
        "source_packet_id":prompt.packet_id,"source_mode":prompt.mode,"prompt_text":prompt.text,
        "prompt_text_contract":"AIOS_PROMPT_TEXT_UTF8_LF.v1","prompt_encoding":"utf-8","prompt_newlines":"lf",
        "request_json":request_json,"request_sha256":digest,"task_id":request["task_id"],"attempt_id":request["attempt_id"],
        "repo_root":request["repo_root"],"relay_root":request["relay_root"]}
    data=canonical_json(task)+b"\n";target=relay_root/"inbox"/(task["id"]+".task.json")
    answer={"status":"DRY_RUN" if dry_run else "ENQUEUED","target":str(target),"task":task,"packet_sha256":hashlib.sha256(data).hexdigest()}
    if any(flags.values()): return {**answer,"status":"APPROVAL_REQUIRED"}
    if dry_run:return answer
    existing=[]
    for state in ("inbox","running","done","error"):
        path=bound_path(str(relay_root/state/target.name),root=relay_root)
        if path.exists():
            if not path.is_file() or path.read_bytes()!=data:raise PromptValidationError("same_request_content_conflict")
            existing.append(path)
    if len(existing)>1:raise PromptValidationError("duplicate_request_state")
    if existing:return {**answer,"status":"EXISTING_REQUEST","target":str(existing[0])}
    target.parent.mkdir(parents=True,exist_ok=True);bound_path(str(target),root=relay_root)
    try:
        with target.open("xb") as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
    except FileExistsError:
        if target.read_bytes()!=data:raise PromptValidationError("same_request_content_conflict")
        return {**answer,"status":"EXISTING_REQUEST"}
    if target.read_bytes()!=data:raise PromptValidationError("packet_write_incomplete")
    return answer


def _existing_digest(relay_root: Path, digest: str) -> Path | None:
    for state in ("inbox", "running", "done", "error", "approvals"):
        folder = relay_root / state
        if not folder.exists():
            continue
        for packet_path in folder.glob("*.task.json"):
            try:
                if json.loads(packet_path.read_text(encoding="utf-8")).get("prompt_sha256") == digest:
                    return packet_path
            except (OSError, json.JSONDecodeError):
                continue
    return None


def enqueue_prompt(
    prompt_path: Path,
    relay_root: Path,
    protected_action_flags: Mapping[str, object],
    *,
    dry_run: bool = False,
    bound_request: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if bound_request is not None:
        if not isinstance(bound_request,dict) or str(prompt_path)!=bound_request.get("prompt_path"):raise PromptValidationError("selected_prompt_mismatch")
        request=validate_bound_request(bound_request)
        prompt=validate_prompt(prompt_path)
        _,flags=classify_authority(protected_action_flags)
        return _enqueue_bound(prompt,relay_root,flags,request,dry_run)
    prompt = validate_prompt(prompt_path)
    approval_required, flags = classify_authority(protected_action_flags)
    duplicate = _existing_digest(relay_root, prompt.sha256)
    if duplicate:
        return {"status": "DUPLICATE", "prompt_sha256": prompt.sha256, "existing_path": str(duplicate)}
    task = {
        "id": f"codex-prompt-{prompt.sha256[:16]}",
        "worker": "codex",
        "provider": "codex",
        "tier": "TIER_2_APPROVAL" if approval_required else "TIER_1_BOUNDED_APPLY",
        "mission": f"Execute validated prompt {prompt.packet_id}",
        "allowed_paths": list(prompt.allowed_paths),
        "approval_required": approval_required,
        "protected_action_flags": flags,
        "prompt_path": str(prompt.path),
        "prompt_sha256": prompt.sha256,
        "source_packet_id": prompt.packet_id,
        "source_mode": prompt.mode,
        "prompt_text": prompt.text,
        "prompt_text_contract": "AIOS_PROMPT_TEXT_UTF8_LF.v1",
        "prompt_encoding": "utf-8",
        "prompt_newlines": "lf",
    }
    target_state = "approvals" if approval_required else "inbox"
    target = relay_root / target_state / f"{task['id']}.task.json"
    if dry_run:
        return {"status": "DRY_RUN", "target": target.as_posix(), "task": task}
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(task, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return {"status": "APPROVAL_REQUIRED" if approval_required else "ENQUEUED", "target": target.as_posix(), "task": task}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", type=Path)
    parser.add_argument("--relay-root", type=Path, default=Path("relay"))
    parser.add_argument("--flags-json", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = enqueue_prompt(args.prompt, args.relay_root, json.loads(args.flags_json), dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
