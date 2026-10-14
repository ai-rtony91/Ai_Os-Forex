"""Validate generated Codex prompts and atomically enqueue relay tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import uuid
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


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
REGISTRY_SCHEMA = "AIOS_CODEX_PACKET_TITLE_REGISTRY.v1"
REGISTRY_RELATIVE_PATH = Path("automation/orchestration/relay/AIOS_CODEX_PACKET_TITLE_REGISTRY_V1.json")
PACKET_DIRECTORY = Path("automation/orchestration/relay/packets")
ENTRY_FIELDS = {
    "title", "packet_id", "status", "packet_path", "packet_sha256", "approval_mode",
    "protected_action_flags", "replacement_title",
}


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


def _validate_prompt_bytes(path: Path, raw: bytes) -> ValidatedPrompt:
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


def validate_prompt(path: Path) -> ValidatedPrompt:
    path = path.resolve(strict=True)
    return _validate_prompt_bytes(path, path.read_bytes())


def normalize_title_request(request: str) -> str:
    title = request.strip()
    if not title or "\n" in title or "\r" in title:
        raise PromptValidationError("title request must be exactly one non-empty line")
    return title


def load_title_registry(repository_root: Path, registry_path: Path | None = None) -> dict[str, object]:
    root = repository_root.resolve(strict=True)
    path = (registry_path or (root / REGISTRY_RELATIVE_PATH)).resolve(strict=True)
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromptValidationError("title registry is malformed or unreadable") from exc
    if set(registry) != {"schema", "entries"} or registry["schema"] != REGISTRY_SCHEMA or not isinstance(registry["entries"], list):
        raise PromptValidationError("title registry schema is invalid")
    active_titles: set[str] = set()
    packet_ids: set[str] = set()
    for entry in registry["entries"]:
        if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS:
            raise PromptValidationError("registry entry fields are invalid")
        if entry["status"] not in {"ACTIVE", "INACTIVE", "SUPERSEDED"}:
            raise PromptValidationError("unsupported registry status")
        if entry["approval_mode"] not in {"STANDARD", "OWNER_TITLE_INVOCATION"}:
            raise PromptValidationError("unsupported approval mode")
        if not all(isinstance(entry[key], str) for key in ENTRY_FIELDS - {"protected_action_flags"}):
            raise PromptValidationError("registry string field is invalid")
        classify_authority(entry["protected_action_flags"])
        if entry["packet_id"] in packet_ids:
            raise PromptValidationError("duplicate packet ID")
        packet_ids.add(entry["packet_id"])
        if entry["status"] == "ACTIVE":
            if entry["title"] in active_titles:
                raise PromptValidationError("duplicate active title")
            active_titles.add(entry["title"])
    return registry


def _packet_path(repository_root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise PromptValidationError("packet path must be relative and cannot traverse")
    root = repository_root.resolve(strict=True)
    packet_root = (root / PACKET_DIRECTORY).resolve(strict=True)
    try:
        candidate = (root / relative).resolve(strict=True)
    except OSError as exc:
        raise PromptValidationError("registered packet file is missing") from exc
    if not candidate.is_relative_to(packet_root):
        raise PromptValidationError("packet path escapes the canonical packet directory")
    return candidate


def resolve_registered_title(request: str, repository_root: Path, registry_path: Path | None = None) -> dict[str, object]:
    title = normalize_title_request(request)
    registry = load_title_registry(repository_root, registry_path)
    matches = [entry for entry in registry["entries"] if entry["title"] == title]
    if not matches:
        raise PromptValidationError("title is not registered")
    entry = matches[0]
    if entry["status"] != "ACTIVE":
        replacement = entry["replacement_title"] or "none"
        raise PromptValidationError(f"title is {entry['status'].lower()}; replacement_title={replacement}")
    packet = _packet_path(repository_root, entry["packet_path"])
    return {**entry, "schema": registry["schema"], "resolved_packet_path": packet}


def validate_registered_packet(resolution: Mapping[str, object]) -> ValidatedPrompt:
    path = resolution["resolved_packet_path"]
    if not isinstance(path, Path):
        raise PromptValidationError("resolved packet path is invalid")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != resolution["packet_sha256"]:
        raise PromptValidationError("registered packet digest mismatch")
    prompt = _validate_prompt_bytes(path, raw)
    if prompt.packet_id != resolution["packet_id"]:
        raise PromptValidationError("registry packet ID does not match stored packet")
    declared = _section(prompt.text, "PROTECTED ACTION FLAGS")
    if declared:
        packet_flags: dict[str, object] = {}
        for line in declared.splitlines():
            match = re.fullmatch(r"\s*-\s+([a-z_]+):\s+(true|false)\s*", line, re.I)
            if match:
                packet_flags[match.group(1)] = match.group(2).lower() == "true"
        classify_authority(packet_flags)
        if packet_flags != resolution["protected_action_flags"]:
            raise PromptValidationError("registry protected flags do not match stored packet")
    return prompt


def _title_approval_required(resolution: Mapping[str, object], prompt: ValidatedPrompt) -> bool:
    _, flags = classify_authority(resolution["protected_action_flags"])
    if resolution["approval_mode"] == "STANDARD":
        return any(flags.values())
    true_flags = {name for name, enabled in flags.items() if enabled}
    if not true_flags:
        return False
    if true_flags == {"branch_change"}:
        text = prompt.text.lower()
        bounded = "branch_change: true" in text and "non-destructive" in text and "approved origin" in text
        if bounded:
            return False
    return True


def classify_authority(flags: Mapping[str, object]) -> tuple[bool, dict[str, bool]]:
    if set(flags) != set(PROTECTED_FLAGS):
        missing = sorted(set(PROTECTED_FLAGS) - set(flags))
        extra = sorted(set(flags) - set(PROTECTED_FLAGS))
        raise PromptValidationError(f"protected flags mismatch; missing={missing}, extra={extra}")
    if any(type(value) is not bool for value in flags.values()):
        raise PromptValidationError("every protected-action flag must be boolean")
    normalized = {name: flags[name] for name in PROTECTED_FLAGS}
    return any(normalized.values()), normalized


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
) -> dict[str, object]:
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


def enqueue_registered_title(
    request: str,
    repository_root: Path,
    relay_root: Path,
    *,
    registry_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    resolution = resolve_registered_title(request, repository_root, registry_path)
    prompt = validate_registered_packet(resolution)
    flags = resolution["protected_action_flags"]
    approval_required = _title_approval_required(resolution, prompt)
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
        "invocation_type": "registered_title",
        "requested_title": resolution["title"],
        "registry_schema": resolution["schema"],
        "registry_packet_sha256": resolution["packet_sha256"],
    }
    target_state = "approvals" if approval_required else "inbox"
    target = relay_root / target_state / f"{task['id']}.task.json"
    if dry_run:
        return {"status": "DRY_RUN", "target": str(target), "task": task}
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
    return {"status": "APPROVAL_REQUIRED" if approval_required else "ENQUEUED", "target": str(target), "task": task}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", type=Path, nargs="?")
    parser.add_argument("--title")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--relay-root", type=Path, default=Path("relay"))
    parser.add_argument("--flags-json")
    parser.add_argument("--resolve-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if bool(args.prompt) == bool(args.title):
        parser.error("provide exactly one prompt path or --title")
    if args.title:
        resolution = resolve_registered_title(args.title, args.repository_root)
        validate_registered_packet(resolution)
        if args.resolve_only:
            result = {key: resolution[key] for key in (
                "status", "title", "packet_id", "packet_path", "packet_sha256", "approval_mode", "protected_action_flags"
            )}
        else:
            result = enqueue_registered_title(args.title, args.repository_root, args.relay_root, dry_run=args.dry_run)
    else:
        if not args.flags_json or args.resolve_only:
            parser.error("--prompt requires --flags-json and cannot use --resolve-only")
        result = enqueue_prompt(args.prompt, args.relay_root, json.loads(args.flags_json), dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
