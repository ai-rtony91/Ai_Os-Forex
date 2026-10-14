from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import (
    PROTECTED_FLAGS,
    PromptValidationError,
    enqueue_registered_title,
    enqueue_prompt,
    load_title_registry,
    normalize_title_request,
    resolve_registered_title,
    validate_registered_packet,
    validate_prompt,
)


def prompt_text(allowed: tuple[str, ...] = ("safe/file.py",)) -> str:
    paths = "\n".join(f"- {path}" for path in allowed)
    return f"""CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED
IDENTITY MARKER: AI_OS
SUPERVISOR IDENTITY: OWNER
WORKER IDENTITY: CODEX
PACKET ID: PACKET-1
MODE: APPLY
ZONE: LOCAL
LANE: TEST

ALLOWED PATHS
{paths}

FORBIDDEN PATHS
- AGENTS.md

APPROVAL AUTHORITY
Local edits only.

VALIDATOR CHAIN
python -m pytest

STOP POINT
Stop after validation.

MISSION
Perform bounded local work.

PREFLIGHT
git status --short

FINAL REPORT FORMAT
STATUS:
END OF PACKET
"""


@pytest.fixture
def flags() -> dict[str, bool]:
    return {name: False for name in PROTECTED_FLAGS}


def write_prompt(tmp_path: Path, text: str | None = None) -> Path:
    path = tmp_path / "next.md"
    path.write_text(text or prompt_text(), encoding="utf-8")
    return path


def test_valid_prompt_becomes_one_task_and_preserves_content(tmp_path: Path, flags: dict[str, bool]) -> None:
    prompt = write_prompt(tmp_path)
    relay = tmp_path / "relay"
    result = enqueue_prompt(prompt, relay, flags)
    task = json.loads(Path(result["target"]).read_text(encoding="utf-8"))
    assert result["status"] == "ENQUEUED"
    assert list((relay / "inbox").glob("*.task.json")) == [Path(result["target"])]
    assert task["prompt_text"] == prompt.read_text(encoding="utf-8")
    assert task["prompt_sha256"] == hashlib.sha256(prompt.read_bytes()).hexdigest()
    assert task["worker"] == task["provider"] == "codex"


def test_missing_required_field_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(PromptValidationError, match="missing required"):
        validate_prompt(write_prompt(tmp_path, prompt_text().replace("PREFLIGHT", "CHECKS")))


def test_placeholder_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(PromptValidationError, match="placeholder"):
        validate_prompt(write_prompt(tmp_path, prompt_text() + "\nTODO\n"))


def test_duplicate_digest_is_not_requeued(tmp_path: Path, flags: dict[str, bool]) -> None:
    prompt = write_prompt(tmp_path)
    relay = tmp_path / "relay"
    enqueue_prompt(prompt, relay, flags)
    duplicate = enqueue_prompt(prompt, relay, flags)
    assert duplicate["status"] == "DUPLICATE"
    assert len(list((relay / "inbox").glob("*.task.json"))) == 1


def test_negative_declarations_do_not_trigger_approval(tmp_path: Path, flags: dict[str, bool]) -> None:
    prompt = write_prompt(tmp_path, prompt_text() + "\nDo not commit, merge, contact OANDA, or trade live.\n")
    result = enqueue_prompt(prompt, tmp_path / "relay", flags)
    assert result["status"] == "ENQUEUED"


def test_positive_flag_routes_to_approvals(tmp_path: Path, flags: dict[str, bool]) -> None:
    flags["commit"] = True
    result = enqueue_prompt(write_prompt(tmp_path), tmp_path / "relay", flags)
    assert result["status"] == "APPROVAL_REQUIRED"
    assert "/approvals/" in str(result["target"])


def test_missing_or_malformed_flags_fail_closed(tmp_path: Path, flags: dict[str, bool]) -> None:
    flags.pop("commit")
    with pytest.raises(PromptValidationError, match="flags mismatch"):
        enqueue_prompt(write_prompt(tmp_path), tmp_path / "relay", flags)
    flags["commit"] = "false"  # type: ignore[assignment]
    with pytest.raises(PromptValidationError, match="boolean"):
        enqueue_prompt(write_prompt(tmp_path), tmp_path / "other", flags)


def test_dry_run_does_not_write_task(tmp_path: Path, flags: dict[str, bool]) -> None:
    result = enqueue_prompt(write_prompt(tmp_path), tmp_path / "relay", flags, dry_run=True)
    assert result["status"] == "DRY_RUN"
    assert not Path(result["target"]).exists()


def test_sha_mismatch_contract_is_present_in_worker() -> None:
    worker = Path("automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1").read_text(encoding="utf-8")
    assert "Get-FileHash -LiteralPath $promptPath -Algorithm SHA256" in worker
    assert "PROMPT_SHA256_MISMATCH" in worker


def test_allowed_path_mismatch_contract_is_present_in_worker() -> None:
    worker = Path("automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1").read_text(encoding="utf-8")
    assert "ALLOWED_PATH_MISMATCH" in worker
    assert "Task allowed paths do not match the validated prompt." in worker


def title_repo(tmp_path: Path, *, title: str = "EXACT-TITLE", status: str = "ACTIVE", approval: str = "OWNER_TITLE_INVOCATION") -> tuple[Path, Path, dict[str, object]]:
    packet = tmp_path / "automation/orchestration/relay/packets/packet.md"
    packet.parent.mkdir(parents=True)
    packet.write_text(prompt_text(), encoding="utf-8")
    entry: dict[str, object] = {
        "title": title,
        "packet_id": "PACKET-1",
        "status": status,
        "packet_path": "automation/orchestration/relay/packets/packet.md",
        "packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
        "approval_mode": approval,
        "protected_action_flags": {name: False for name in PROTECTED_FLAGS},
        "replacement_title": "NEW-TITLE" if status == "SUPERSEDED" else "",
    }
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"schema": "AIOS_CODEX_PACKET_TITLE_REGISTRY.v1", "entries": [entry]}), encoding="utf-8")
    return registry, packet, entry


def test_exact_title_and_surrounding_whitespace_resolve(tmp_path: Path) -> None:
    registry, packet, _ = title_repo(tmp_path)
    for request in ("EXACT-TITLE", "  EXACT-TITLE\n"):
        resolution = resolve_registered_title(request, tmp_path, registry)
        assert resolution["resolved_packet_path"] == packet.resolve()
        assert validate_registered_packet(resolution).packet_id == "PACKET-1"


@pytest.mark.parametrize("input_text", ["", "EXACT-TITLE\nEXACT-TITLE", "run EXACT-TITLE", "exact-title", "EXACT-TITEL", "UNKNOWN"])
def test_nonexact_title_requests_fail_closed(tmp_path: Path, input_text: str) -> None:
    registry, _, _ = title_repo(tmp_path)
    with pytest.raises(PromptValidationError):
        resolve_registered_title(input_text, tmp_path, registry)


@pytest.mark.parametrize("status", ["INACTIVE", "SUPERSEDED"])
def test_nonactive_title_is_rejected(tmp_path: Path, status: str) -> None:
    registry, _, _ = title_repo(tmp_path, status=status)
    match = "replacement_title=NEW-TITLE" if status == "SUPERSEDED" else "inactive"
    with pytest.raises(PromptValidationError, match=match):
        resolve_registered_title("EXACT-TITLE", tmp_path, registry)


def test_duplicate_active_title_and_packet_id_are_rejected(tmp_path: Path) -> None:
    registry, _, entry = title_repo(tmp_path)
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["entries"].append({**entry})
    registry.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PromptValidationError, match="duplicate packet ID"):
        load_title_registry(tmp_path, registry)
    data["entries"][1]["packet_id"] = "PACKET-2"
    registry.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PromptValidationError, match="duplicate active title"):
        load_title_registry(tmp_path, registry)


@pytest.mark.parametrize("bad_path", ["/absolute/packet.md", "automation/orchestration/relay/packets/../escape.md"])
def test_unsafe_packet_paths_are_rejected(tmp_path: Path, bad_path: str) -> None:
    registry, _, entry = title_repo(tmp_path)
    entry["packet_path"] = bad_path
    registry.write_text(json.dumps({"schema": "AIOS_CODEX_PACKET_TITLE_REGISTRY.v1", "entries": [entry]}), encoding="utf-8")
    with pytest.raises(PromptValidationError, match="relative|traverse"):
        resolve_registered_title("EXACT-TITLE", tmp_path, registry)


def test_missing_digest_invalid_and_identity_mismatch_fail(tmp_path: Path) -> None:
    registry, packet, entry = title_repo(tmp_path)
    entry["packet_path"] = "automation/orchestration/relay/packets/missing.md"
    registry.write_text(json.dumps({"schema": "AIOS_CODEX_PACKET_TITLE_REGISTRY.v1", "entries": [entry]}), encoding="utf-8")
    with pytest.raises(PromptValidationError, match="missing"):
        resolve_registered_title("EXACT-TITLE", tmp_path, registry)
    entry["packet_path"] = "automation/orchestration/relay/packets/packet.md"
    entry["packet_sha256"] = "0" * 64
    registry.write_text(json.dumps({"schema": "AIOS_CODEX_PACKET_TITLE_REGISTRY.v1", "entries": [entry]}), encoding="utf-8")
    with pytest.raises(PromptValidationError, match="digest"):
        validate_registered_packet(resolve_registered_title("EXACT-TITLE", tmp_path, registry))
    packet.write_text("invalid", encoding="utf-8")
    entry["packet_sha256"] = hashlib.sha256(packet.read_bytes()).hexdigest()
    registry.write_text(json.dumps({"schema": "AIOS_CODEX_PACKET_TITLE_REGISTRY.v1", "entries": [entry]}), encoding="utf-8")
    with pytest.raises(PromptValidationError):
        validate_registered_packet(resolve_registered_title("EXACT-TITLE", tmp_path, registry))
    packet.write_text(prompt_text().replace("PACKET ID: PACKET-1", "PACKET ID: OTHER"), encoding="utf-8")
    entry["packet_sha256"] = hashlib.sha256(packet.read_bytes()).hexdigest()
    registry.write_text(json.dumps({"schema": "AIOS_CODEX_PACKET_TITLE_REGISTRY.v1", "entries": [entry]}), encoding="utf-8")
    with pytest.raises(PromptValidationError, match="packet ID"):
        validate_registered_packet(resolve_registered_title("EXACT-TITLE", tmp_path, registry))


@pytest.mark.parametrize("mutation,match", [("missing", "flags mismatch"), ("string", "boolean"), ("extra", "flags mismatch")])
def test_registry_protected_flags_are_exact_booleans(tmp_path: Path, mutation: str, match: str) -> None:
    registry, _, entry = title_repo(tmp_path)
    flags = entry["protected_action_flags"]
    if mutation == "missing": flags.pop("commit")
    elif mutation == "string": flags["commit"] = "false"
    else: flags["unexpected"] = False
    registry.write_text(json.dumps({"schema": "AIOS_CODEX_PACKET_TITLE_REGISTRY.v1", "entries": [entry]}), encoding="utf-8")
    with pytest.raises(PromptValidationError, match=match):
        load_title_registry(tmp_path, registry)


@pytest.mark.parametrize("flag", [None, "branch_change", "commit", "push", "merge", "broker_or_oanda", "live_trading"])
def test_owner_title_approval_boundary_and_metadata(tmp_path: Path, flag: str | None) -> None:
    registry, packet, entry = title_repo(tmp_path)
    if flag:
        entry["protected_action_flags"][flag] = True
    if flag == "branch_change":
        packet.write_text(prompt_text() + "\nbranch_change: true; bounded non-destructive approved origin restoration.\n", encoding="utf-8")
        entry["packet_sha256"] = hashlib.sha256(packet.read_bytes()).hexdigest()
    registry.write_text(json.dumps({"schema": "AIOS_CODEX_PACKET_TITLE_REGISTRY.v1", "entries": [entry]}), encoding="utf-8")
    result = enqueue_registered_title("EXACT-TITLE", tmp_path, tmp_path / "relay", registry_path=registry, dry_run=True)
    task = result["task"]
    assert task["approval_required"] is (flag not in (None, "branch_change"))
    assert task["invocation_type"] == "registered_title"
    assert task["requested_title"] == "EXACT-TITLE"
    assert task["registry_packet_sha256"] == entry["packet_sha256"]
    assert task["prompt_text"] == packet.read_text(encoding="utf-8")


def test_registered_title_duplicate_digest_is_not_requeued(tmp_path: Path) -> None:
    registry, _, _ = title_repo(tmp_path)
    relay = tmp_path / "relay"
    enqueue_registered_title("EXACT-TITLE", tmp_path, relay, registry_path=registry)
    assert enqueue_registered_title("EXACT-TITLE", tmp_path, relay, registry_path=registry)["status"] == "DUPLICATE"


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    registry, packet, entry = title_repo(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text(prompt_text(), encoding="utf-8")
    packet.unlink()
    try:
        packet.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")
    entry["packet_sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    registry.write_text(json.dumps({"schema": "AIOS_CODEX_PACKET_TITLE_REGISTRY.v1", "entries": [entry]}), encoding="utf-8")
    with pytest.raises(PromptValidationError, match="escapes"):
        resolve_registered_title("EXACT-TITLE", tmp_path, registry)


def test_initial_registry_packet_and_authoritative_rule() -> None:
    root = Path.cwd()
    resolution = resolve_registered_title("AIOS-PACKET-RESTORE-PR1379-BRANCH-V1", root)
    assert validate_registered_packet(resolution).packet_id == resolution["packet_id"]
    assert hashlib.sha256(Path(resolution["resolved_packet_path"]).read_bytes()).hexdigest() == resolution["packet_sha256"]
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "## AI_OS Registered Packet Title Invocation Rule" in agents
    assert "AI_OS EXECUTION TOKEN" not in normalize_title_request("AIOS-PACKET-RESTORE-PR1379-BRANCH-V1")
