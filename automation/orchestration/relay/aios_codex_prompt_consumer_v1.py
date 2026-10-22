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
