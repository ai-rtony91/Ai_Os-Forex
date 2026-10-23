from __future__ import annotations

import ast
import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
import shutil

from automation.forex_engine.forex_workflow_autonomy_router_v1 import (
    ACTIVE_LANE,
    WORKFLOW_BLOCKED_ON_OWNER_SAFETY_EVIDENCE,
    run_forex_workflow_autonomy_router_v1,
)
from automation.validators import aios_governance_validator


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    ROOT
    / "scripts"
    / "forex_delivery"
    / "run_forex_workflow_autonomy_router_v1.py"
)
DEFAULT_DISCOVERY_REPORT_PATH = (
    ROOT
    / "Reports"
    / "forex_delivery"
    / "AIOS_FOREX_OWNER_SAFETY_EVIDENCE_DISCOVERY_V1_REPORT.md"
)

FORBIDDEN_IMPORT_ROOTS = {
    "requests",
    "socket",
    "urllib",
    "dotenv",
    "oanda",
    "oandapyV20",
    "apscheduler",
    "schedule",
    "sched",
    "daemon",
    "webhook",
}


def test_router_reads_missing_owner_safety_evidence_state(tmp_path: Path) -> None:
    discovery = (
        "# test\n"
        "## KILL_SWITCH_EVIDENCE_CANDIDATE\n"
        "- Status: DISCOVERED_WEAK_CANDIDATE\n"
        "- Safe to cite in owner intake: false\n"
    )

    with _temp_workflow_state(
        tmp_path / "tmp_state_missing_controls",
        discovery,
        ["kill_switch_state"],
        [],
    ) as state:
        result = run_forex_workflow_autonomy_router_v1(
            discovery_report_path=state["discovery"],
            collection_state_path=state["collection"],
            verification_prep_state_path=state["verification"],
            critical_safety_closure_state_path=state["critical"],
            finish_line_state_path=state["finish_line"],
            governor_state_path=state["governor"],
        )

        assert result["workflow_status"] == WORKFLOW_BLOCKED_ON_OWNER_SAFETY_EVIDENCE
        assert result["active_blockers"] == ["kill_switch_state"]
        assert result["active_blocker"] == "kill_switch_state"


def test_router_reads_discovery_weak_candidates(tmp_path: Path) -> None:
    discovery = (
        "# discovery\n"
        "## KILL_SWITCH_EVIDENCE_CANDIDATE\n"
        "- Status: DISCOVERED_WEAK_CANDIDATE\n"
        "- Safe to cite in owner intake: false\n\n"
        "## DAILY_STOP_EVIDENCE_CANDIDATE\n"
        "- Status: NOT_READY\n"
        "- Safe to cite in owner intake: false\n"
    )

    with _temp_workflow_state(
        tmp_path / "tmp_state_discovery",
        discovery,
        [],
        ["daily_stop_state"],
    ) as state:
        result = run_forex_workflow_autonomy_router_v1(
            discovery_report_path=state["discovery"],
            collection_state_path=state["collection"],
            verification_prep_state_path=state["verification"],
            critical_safety_closure_state_path=state["critical"],
            finish_line_state_path=state["finish_line"],
            governor_state_path=state["governor"],
        )

        assert any(
            "Discovery candidate weak for kill_switch_state" in reason
            for reason in result["decision_reasons"]
        )
        assert any(
            "Discovery candidate weak for daily_stop_state" in reason
            for reason in result["decision_reasons"]
        )


def test_router_selects_blocked_status_and_lane(tmp_path: Path) -> None:
    with _temp_workflow_state(
        tmp_path / "tmp_state_blocked_lane",
        " ",
        ["daily_stop_state"],
        ["max_loss_state"],
    ) as state:
        result = run_forex_workflow_autonomy_router_v1(
            discovery_report_path=state["discovery"],
            collection_state_path=state["collection"],
            verification_prep_state_path=state["verification"],
            critical_safety_closure_state_path=state["critical"],
            finish_line_state_path=state["finish_line"],
            governor_state_path=state["governor"],
        )

        assert result["workflow_status"] == WORKFLOW_BLOCKED_ON_OWNER_SAFETY_EVIDENCE
        assert result["active_lane"] == ACTIVE_LANE
        assert result["active_phase"]


def test_router_locks_forbidden_modes(tmp_path: Path) -> None:
    with _temp_workflow_state(
        tmp_path / "tmp_state_locked_modes",
        " ",
        ["kill_switch_state"],
        [],
    ) as state:
        result = run_forex_workflow_autonomy_router_v1(
            discovery_report_path=state["discovery"],
            collection_state_path=state["collection"],
            verification_prep_state_path=state["verification"],
            critical_safety_closure_state_path=state["critical"],
            finish_line_state_path=state["finish_line"],
            governor_state_path=state["governor"],
        )
        locked_modes = result["locked_modes"]
        for mode in (
            "broker_probe",
            "demo_proof",
            "live_micro",
            "live_trading",
            "vacation_mode",
        ):
            assert locked_modes.get(mode) is True

        action = result["next_safe_action"].lower()
        assert "keep broker" in action
        assert "demo" in action
        assert "live micro" in action
        assert "live trading" in action
        assert "vacation" in action


def test_router_never_verifies_or_invents_evidence(tmp_path: Path) -> None:
    with _temp_workflow_state(
        tmp_path / "tmp_state_never_verified",
        " ",
        ["kill_switch_state"],
        [],
    ) as state:
        result = run_forex_workflow_autonomy_router_v1(
            discovery_report_path=state["discovery"],
            collection_state_path=state["collection"],
            verification_prep_state_path=state["verification"],
            critical_safety_closure_state_path=state["critical"],
            finish_line_state_path=state["finish_line"],
            governor_state_path=state["governor"],
        )
        assert result["evidence_invented"] is False
        assert result["evidence_verified_by_this_packet"] is False
        assert result["owner_intake_modified"] is False


def test_router_does_not_modify_intake_json(tmp_path: Path) -> None:
    with _temp_workflow_state(
        tmp_path / "tmp_state_no_modify",
        " ",
        ["kill_switch_state"],
        [],
    ) as state:
        before = state["verification"].read_text(encoding="utf-8")
        _ = run_forex_workflow_autonomy_router_v1(
            discovery_report_path=state["discovery"],
            collection_state_path=state["collection"],
            verification_prep_state_path=state["verification"],
            critical_safety_closure_state_path=state["critical"],
            finish_line_state_path=state["finish_line"],
            governor_state_path=state["governor"],
        )
        after = state["verification"].read_text(encoding="utf-8")
        assert before == after


def test_router_safety_boundary_blocks_execution_modes(tmp_path: Path) -> None:
    with _temp_workflow_state(
        tmp_path / "tmp_state_boundary",
        " ",
        ["monitoring_ready"],
        [],
    ) as state:
        result = run_forex_workflow_autonomy_router_v1(
            discovery_report_path=state["discovery"],
            collection_state_path=state["collection"],
            verification_prep_state_path=state["verification"],
            critical_safety_closure_state_path=state["critical"],
            finish_line_state_path=state["finish_line"],
            governor_state_path=state["governor"],
        )
        boundary = result["safety_boundary"]
        assert boundary["broker_api_allowed"] is False
        assert boundary["credentials_allowed"] is False
        assert boundary["order_execution_allowed"] is False
        assert boundary["live_trading_authorized"] is False
        assert boundary["account_identifier_persistence_allowed"] is False


def test_router_writes_state_report_and_next_packet(tmp_path: Path) -> None:
    with _temp_workflow_state(
        tmp_path / "writes",
        " ",
        ["max_loss_state"],
        ["daily_stop_state"],
    ) as state:
        state_output = tmp_path / "state.json"
        report_output = tmp_path / "report.md"
        packet_output = tmp_path / "next.md"

        completed = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--discovery-report-path",
                str(state["discovery"]),
                "--collection-state-path",
                str(state["collection"]),
                "--verification-prep-state-path",
                str(state["verification"]),
                "--critical-safety-closure-state-path",
                str(state["critical"]),
                "--finish-line-state-path",
                str(state["finish_line"]),
                "--governor-state-path",
                str(state["governor"]),
                "--write-state",
                "--write-report",
                "--write-next-packet",
                "--state-output-path",
                str(state_output),
                "--report-output-path",
                str(report_output),
                "--next-packet-output-path",
                str(packet_output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)
        state_payload = json.loads(state_output.read_text(encoding="utf-8"))
        packet_text = packet_output.read_text(encoding="utf-8")

        assert payload["state_output_path"] == str(state_output)
        assert payload["report_output_path"] == str(report_output)
        assert payload["next_packet_output_path"] == str(packet_output)
        assert state_payload["workflow_status"] == WORKFLOW_BLOCKED_ON_OWNER_SAFETY_EVIDENCE
        assert state_payload["active_lane"] == ACTIVE_LANE
        assert report_output.exists()
        assert packet_output.exists()
        assert packet_text.startswith("CODEX-ONLY PROMPT")
        assert "@filename" not in packet_text


def test_generated_next_packet_passes_governance_validator(tmp_path: Path) -> None:
    with _temp_workflow_state(
        tmp_path / "tmp_state_validator",
        " ",
        ["kill_switch_state"],
        [],
    ) as state:
        result = run_forex_workflow_autonomy_router_v1(
            discovery_report_path=state["discovery"],
            collection_state_path=state["collection"],
            verification_prep_state_path=state["verification"],
            critical_safety_closure_state_path=state["critical"],
            finish_line_state_path=state["finish_line"],
            governor_state_path=state["governor"],
        )
        packet_text = result["next_packet_text"]
        validation = aios_governance_validator.validate_packet_text(
            packet_text,
            "AIOS_FOREX_WORKFLOW_AUTONOMY_ROUTER_NEXT_CODEX_PACKET_V1.md",
        )
        assert packet_text.startswith("CODEX-ONLY PROMPT")
        assert validation["status"] == "PASS"


def test_no_forbidden_imports_or_environment_access() -> None:
    source = Path(__file__).resolve().parents[2] / "automation" / "forex_engine" / "forex_workflow_autonomy_router_v1.py"
    tree_text = source.read_text(encoding="utf-8")
    ast_tree = ast.parse(tree_text)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(ast_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module.split(".")[0]
        for node in ast.walk(ast_tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )

    assert imports.isdisjoint(FORBIDDEN_IMPORT_ROOTS)
    assert "os.environ" not in tree_text
    assert ".env" not in tree_text or "Do not read .env." in tree_text


@contextmanager
def _temp_workflow_state(
    base_dir: Path,
    discovery_body: str,
    owner_evidence_missing: list[str],
    verification_missing: list[str],
):
    base_dir.mkdir(parents=True, exist_ok=True)
    discovery = base_dir / "discovery.md"
    collection = base_dir / "collection.json"
    verification = base_dir / "verification.json"
    critical = base_dir / "critical.json"
    finish_line = base_dir / "finish_line.json"
    governor = base_dir / "governor.json"

    discovery.write_text(discovery_body, encoding="utf-8")
    collection.write_text(
        json.dumps({"owner_evidence_missing": owner_evidence_missing}, indent=2),
        encoding="utf-8",
    )
    verification.write_text(
        json.dumps({"missing_controls": verification_missing}, indent=2),
        encoding="utf-8",
    )
    critical.write_text("{}", encoding="utf-8")
    finish_line.write_text("{}", encoding="utf-8")
    governor.write_text("{}", encoding="utf-8")

    try:
        yield {
            "discovery": discovery,
            "collection": collection,
            "verification": verification,
            "critical": critical,
            "finish_line": finish_line,
            "governor": governor,
        }
    finally:
        for path in (discovery, collection, verification, critical, finish_line, governor):
            if path.exists():
                path.unlink()
        if base_dir.exists():
            shutil.rmtree(base_dir)
