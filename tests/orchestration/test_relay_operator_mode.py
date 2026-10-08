"""Tests for .\aios.ps1 -Mode relay and relay operator state aggregation."""

import json
import subprocess
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AIOS = REPO_ROOT / "aios.ps1"
RELAY_STATE_SCRIPT = REPO_ROOT / "automation/orchestration/review_bridge/Get-AiOsRelayOperatorState.DRY_RUN.ps1"
NEW_RELAY_MESSAGE_SCRIPT = REPO_ROOT / "automation/orchestration/relay_bus/New-AiOsRelayMessage.DRY_RUN.ps1"
RELAY_ACTORS_SOURCE = REPO_ROOT / "control/relay_bus/actors/AIOS_RELAY_ACTORS.json"
RELAY_BUS_STATE_SCRIPT = REPO_ROOT / "automation/orchestration/relay_bus/Get-AiOsRelayBusState.DRY_RUN.ps1"
SOS_POLICY_SCRIPT = REPO_ROOT / "automation/orchestration/relay_bus/Get-AiOsSosEscalationPolicy.DRY_RUN.ps1"
RELAY_REVIEW_RESOLVER_SCRIPT = REPO_ROOT / "automation/orchestration/relay_bus/Resolve-AiOsRelayHumanReview.DRY_RUN.ps1"


def _run_script_json(script: Path, args: list[str], cwd: Path) -> dict:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-OutputJson",
        *args,
    ]
    raw = subprocess.check_output(cmd, cwd=str(cwd), text=True)
    return json.loads(raw.strip())


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _init_relay_dirs(root: Path) -> Path:
    base = root / "control" / "review_bridge"
    (base / "codex_reports").mkdir(parents=True, exist_ok=True)
    (base / "chatgpt_prompts").mkdir(parents=True, exist_ok=True)
    (base / "pasteback").mkdir(parents=True, exist_ok=True)
    (base / "archive").mkdir(parents=True, exist_ok=True)
    return base


def _init_relay_bus_root(root: Path) -> None:
    control_root = root / "control" / "relay_bus"
    (control_root / "actors").mkdir(parents=True, exist_ok=True)
    (control_root / "messages" / "inbox").mkdir(parents=True, exist_ok=True)
    (control_root / "messages" / "outbox").mkdir(parents=True, exist_ok=True)
    (control_root / "messages" / "archive").mkdir(parents=True, exist_ok=True)
    (control_root / "pasteback").mkdir(parents=True, exist_ok=True)
    (control_root / "evidence").mkdir(parents=True, exist_ok=True)
    for marker in (
        control_root / "messages" / "inbox" / ".gitkeep",
        control_root / "messages" / "outbox" / ".gitkeep",
        control_root / "messages" / "archive" / ".gitkeep",
        control_root / "evidence" / ".gitkeep",
        control_root / "pasteback" / ".gitkeep",
    ):
        marker.write_text("", encoding="utf-8")
    shutil.copy2(RELAY_ACTORS_SOURCE, control_root / "actors" / "AIOS_RELAY_ACTORS.json")


def _seed_actor_relay_message(
    root: Path,
    message_id: str,
    payload_text: str,
    message_type: str = "codex_final_report",
) -> None:
    subprocess.check_output(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(NEW_RELAY_MESSAGE_SCRIPT),
            "-Actor",
            "codex_cli",
            "-TargetActor",
            "powershell_operator",
            "-PacketId",
            message_id,
            "-Branch",
            "feature/relay-sos-policy-surface-v1",
            "-MessageType",
            message_type,
            "-Intent",
            "handoff summary",
            "-Status",
            "pending",
            "-PayloadText",
            json.dumps({"message_id": message_id, "content": payload_text}),
            "-Mode",
            "APPLY",
        ],
        cwd=str(root),
    )


def _write_actor_relay_message(
    root: Path,
    message_id: str,
    payload_text: str,
    message_type: str = "codex_final_report",
    status: str = "pending",
) -> None:
    message = {
        "schema": "AIOS_RELAY_MESSAGE.v1",
        "message_id": f"{message_id}_{status}",
        "created_utc": "2026-06-13T00:00:00Z",
        "actor": "codex_cli",
        "target_actor": "powershell_operator",
        "packet_id": message_id,
        "branch": "feature/relay-sos-policy-surface-v1",
        "message_type": message_type,
        "intent": "handoff summary",
        "status": status,
        "payload_text": payload_text,
        "evidence": {},
        "next_action": "resolve in review",
        "requires_human_review": True,
        "execution_allowed": False,
        "can_continue_without_anthony": False,
    }
    message_path = root / "control" / "relay_bus" / "messages" / "inbox" / f"{message_id}.json"
    message_path.write_text(json.dumps(message), encoding="utf-8")


def test_relay_state_reports_empty(tmp_path: Path) -> None:
    tmp_root = tmp_path
    _init_relay_dirs(tmp_root)

    out = _run_script_json(RELAY_STATE_SCRIPT, [], tmp_root)

    assert out["mode"] == "DRY_RUN_READ_ONLY"
    assert out["actor_relay_bus_status"] == "EMPTY"
    assert out["actor_relay_next_action"] == "Use New-AiOsRelayMessage.DRY_RUN.ps1 with Mode APPLY to write the first relay message."
    assert out["exact_next_action"] == out["actor_relay_next_action"]
    assert out["relay_status"] == "EMPTY"
    assert out["needs_codex_report"] is True
    assert out["needs_chatgpt_prompt"] is False
    assert out["needs_chatgpt_review"] is False
    assert out["needs_pasteback"] is False
    for legacy_field in (
        "related_existing_notes",
        "related_existing_scripts",
        "needs_codex_report",
        "needs_chatgpt_prompt",
        "needs_chatgpt_review",
        "needs_pasteback",
    ):
        assert legacy_field in out
    assert "AIOS_CODEX_CHATGPT_POWERSHELL_RELAY_V1.md" in out["related_existing_notes"][0]


def test_relay_state_prefers_actor_relay_when_needs_human_review(tmp_path: Path) -> None:
    root = tmp_path
    _init_relay_dirs(root)
    _init_relay_bus_root(root)
    _seed_actor_relay_message(
        root=root,
        message_id="AIOS-RELAY-STATE-NEEDS-HUMAN",
        payload_text="Pending human review for normal handoff summary.",
    )

    relay_bus_state = _run_script_json(RELAY_BUS_STATE_SCRIPT, [], root)
    assert relay_bus_state["relay_status"] == "NEEDS_HUMAN_REVIEW"

    operator_script = root / "automation" / "orchestration" / "review_bridge" / "Get-AiOsRelayOperatorState.DRY_RUN.ps1"
    relay_bus_script = root / "automation" / "orchestration" / "relay_bus" / "Get-AiOsRelayBusState.DRY_RUN.ps1"
    operator_script.parent.mkdir(parents=True, exist_ok=True)
    relay_bus_script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RELAY_STATE_SCRIPT, operator_script)
    shutil.copy2(RELAY_BUS_STATE_SCRIPT, relay_bus_script)

    out = _run_script_json(operator_script, [], root)

    assert out["actor_relay_bus_status"] == "NEEDS_HUMAN_REVIEW"
    assert out["actor_relay_next_action"] == (
        "powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/relay_bus/Resolve-AiOsRelayHumanReview.DRY_RUN.ps1 -OutputJson"
    )
    assert out["exact_next_action"] == out["actor_relay_next_action"]


def test_relay_state_reports_routine_sos_classification(tmp_path: Path) -> None:
    root = tmp_path
    _init_relay_dirs(root)
    _init_relay_bus_root(root)
    _write_actor_relay_message(
        root=root,
        message_id="AIOS-RELAY-STATE-ROUTINE",
        payload_text="Prepare routine Codex report handoff review.",
    )

    operator_script = root / "automation" / "orchestration" / "review_bridge" / "Get-AiOsRelayOperatorState.DRY_RUN.ps1"
    relay_bus_script = root / "automation" / "orchestration" / "relay_bus" / "Get-AiOsRelayBusState.DRY_RUN.ps1"
    sos_policy_script = root / "automation" / "orchestration" / "relay_bus" / "Get-AiOsSosEscalationPolicy.DRY_RUN.ps1"
    resolver_script = root / "automation" / "orchestration" / "relay_bus" / "Resolve-AiOsRelayHumanReview.DRY_RUN.ps1"
    operator_script.parent.mkdir(parents=True, exist_ok=True)
    relay_bus_script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RELAY_STATE_SCRIPT, operator_script)
    shutil.copy2(RELAY_BUS_STATE_SCRIPT, relay_bus_script)
    shutil.copy2(SOS_POLICY_SCRIPT, sos_policy_script)
    shutil.copy2(RELAY_REVIEW_RESOLVER_SCRIPT, resolver_script)

    out = _run_script_json(operator_script, [], root)

    assert out["actor_relay_bus_status"] == "NEEDS_HUMAN_REVIEW"
    assert out["sos_escalation_status"] == "ROUTINE_REVIEW"
    assert out["sos_anthony_required"] is False
    assert out["sos_routine_review_allowed"] is True
    assert isinstance(out["sos_safe_next_action"], str)
    assert out["sos_matched_categories"] == []


def test_relay_state_reports_sos_escalation_classification(tmp_path: Path) -> None:
    root = tmp_path
    _init_relay_dirs(root)
    _init_relay_bus_root(root)
    _write_actor_relay_message(
        root=root,
        message_id="AIOS-RELAY-STATE-SOS",
        payload_text="Contains API credential: AIOS_TG_BOT_TOKEN=abc123 for handoff review.",
    )

    operator_script = root / "automation" / "orchestration" / "review_bridge" / "Get-AiOsRelayOperatorState.DRY_RUN.ps1"
    relay_bus_script = root / "automation" / "orchestration" / "relay_bus" / "Get-AiOsRelayBusState.DRY_RUN.ps1"
    sos_policy_script = root / "automation" / "orchestration" / "relay_bus" / "Get-AiOsSosEscalationPolicy.DRY_RUN.ps1"
    resolver_script = root / "automation" / "orchestration" / "relay_bus" / "Resolve-AiOsRelayHumanReview.DRY_RUN.ps1"
    operator_script.parent.mkdir(parents=True, exist_ok=True)
    relay_bus_script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RELAY_STATE_SCRIPT, operator_script)
    shutil.copy2(RELAY_BUS_STATE_SCRIPT, relay_bus_script)
    shutil.copy2(SOS_POLICY_SCRIPT, sos_policy_script)
    shutil.copy2(RELAY_REVIEW_RESOLVER_SCRIPT, resolver_script)

    out = _run_script_json(operator_script, [], root)

    assert out["actor_relay_bus_status"] == "NEEDS_HUMAN_REVIEW"
    assert out["sos_escalation_status"] == "SOS_ESCALATION"
    assert out["sos_anthony_required"] is True
    assert out["sos_routine_review_allowed"] is False
    assert "SECRETS_AND_CREDENTIALS" in out["sos_matched_categories"]
    assert "wake Anthony" in out["sos_safe_next_action"] or "Anthony escalation" in out["sos_safe_next_action"]


def test_relay_state_does_not_write_files(tmp_path: Path) -> None:
    tmp_root = tmp_path
    _init_relay_dirs(tmp_root)

    before_files = {path.relative_to(tmp_root).as_posix() for path in tmp_root.rglob("*") if path.is_file()}
    out = _run_script_json(RELAY_STATE_SCRIPT, [], tmp_root)
    after_files = {path.relative_to(tmp_root).as_posix() for path in tmp_root.rglob("*") if path.is_file()}

    assert out["mode"] == "DRY_RUN_READ_ONLY"
    assert before_files == after_files
    assert out["exact_next_action"] == out["actor_relay_next_action"]


def test_relay_state_empty_bus_has_not_applicable_sos_fields(tmp_path: Path) -> None:
    root = tmp_path
    _init_relay_dirs(root)

    out = _run_script_json(RELAY_STATE_SCRIPT, [], root)

    assert out["sos_escalation_status"] == "NOT_APPLICABLE"
    assert out["sos_anthony_required"] is False
    assert out["sos_routine_review_allowed"] is False
    assert out["sos_safe_next_action"] == ""
    assert out["sos_matched_categories"] == []


def test_relay_state_needs_chatgpt_prompt_after_report(tmp_path: Path) -> None:
    root = tmp_path
    relay_root = _init_relay_dirs(root)

    _write_json(
        relay_root / "codex_reports" / "report.json",
        {
            "packet_id": "AIOS-RELAY-STATE-01",
            "branch": "feature/relay-test",
        },
    )

    out = _run_script_json(RELAY_STATE_SCRIPT, [], root)
    assert out["relay_status"] == "NEEDS_CHATGPT_PROMPT"
    assert out["needs_codex_report"] is False
    assert out["needs_chatgpt_prompt"] is True
    assert out["needs_chatgpt_review"] is False
    assert out["needs_pasteback"] is True


def test_relay_state_needs_chatgpt_review_after_prompt(tmp_path: Path) -> None:
    root = tmp_path
    relay_root = _init_relay_dirs(root)

    _write_json(relay_root / "codex_reports" / "report.json", {"packet_id": "AIOS-RELAY-STATE-02", "branch": "feature/relay-test"})
    (relay_root / "chatgpt_prompts" / "prompt.txt").write_text("prompt", encoding="utf-8")

    out = _run_script_json(RELAY_STATE_SCRIPT, [], root)
    assert out["relay_status"] == "NEEDS_CHATGPT_REVIEW"
    assert out["needs_chatgpt_review"] is True
    assert out["needs_pasteback"] is True


def test_relay_state_readies_when_pasteback_passes(tmp_path: Path) -> None:
    root = tmp_path
    relay_root = _init_relay_dirs(root)

    _write_json(relay_root / "codex_reports" / "report.json", {"packet_id": "AIOS-RELAY-STATE-03", "branch": "feature/relay-test"})
    (relay_root / "chatgpt_prompts" / "prompt.txt").write_text("prompt", encoding="utf-8")
    _write_json(relay_root / "pasteback" / "pasteback.json", {
        "packet_id": "AIOS-RELAY-STATE-03",
        "safety_scan_passed": True,
    })

    out = _run_script_json(RELAY_STATE_SCRIPT, [], root)
    assert out["relay_status"] == "PASTEBACK_READY"
    assert out["pasteback_ready"] is True
    assert out["pasteback_safety_status"] == "PASSED"
    assert out["needs_pasteback"] is False


def test_relay_state_flags_review_required_when_pasteback_fails(tmp_path: Path) -> None:
    root = tmp_path
    relay_root = _init_relay_dirs(root)

    _write_json(relay_root / "codex_reports" / "report.json", {"packet_id": "AIOS-RELAY-STATE-04", "branch": "feature/relay-test"})
    (relay_root / "chatgpt_prompts" / "prompt.txt").write_text("prompt", encoding="utf-8")
    _write_json(relay_root / "pasteback" / "pasteback.json", {
        "packet_id": "AIOS-RELAY-STATE-04",
        "safety_scan_passed": False,
    })

    out = _run_script_json(RELAY_STATE_SCRIPT, [], root)
    assert out["relay_status"] == "PASTEBACK_REVIEW_REQUIRED"
    assert out["pasteback_ready"] is False
    assert out["pasteback_safety_status"] == "FAILED"


def test_aios_mode_relay_aggregates_and_exposes_next_action() -> None:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(AIOS),
        "-Mode",
        "relay",
    ]
    output = subprocess.check_output(cmd, cwd=str(REPO_ROOT), text=True)
    relay_start = output.find("{")
    relay_end = output.rfind("}")
    assert relay_start >= 0 and relay_end > relay_start
    relay_state = json.loads(output[relay_start : relay_end + 1])
    assert relay_state["schema"] == "AIOS_RELAY_OPERATOR_STATE.v1"
    assert "exact_next_action" in relay_state
    assert "Relay operator state helper is unavailable" not in output


def test_aios_mode_relay_read_only() -> None:
    text = AIOS.read_text(encoding="utf-8")
    assert "\"relay\" {" in text
    start = text.index('"relay" {')
    end = text.index('"packet" {')
    relay_block = text[start:end]

    for forbidden in (
        "git push",
        "git commit",
        "git merge",
        "gh pr merge",
        "gh pr create",
        "daemon",
        "runtime/",
    ):
        assert forbidden not in relay_block


def test_aios_mode_relay_is_read_only_no_file_mutation() -> None:
    before = {path.relative_to(REPO_ROOT).as_posix() for path in REPO_ROOT.rglob("*") if path.is_file()}

    output = subprocess.check_output(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(AIOS),
            "-Mode",
            "relay",
        ],
        cwd=str(REPO_ROOT),
        text=True,
    )

    after = {path.relative_to(REPO_ROOT).as_posix() for path in REPO_ROOT.rglob("*") if path.is_file()}

    relay_start = output.find("{")
    relay_end = output.rfind("}")

    assert before == after
    assert relay_start >= 0 and relay_end > relay_start
    relay_state = json.loads(output[relay_start : relay_end + 1])
    assert relay_state["mode"] == "DRY_RUN_READ_ONLY"
