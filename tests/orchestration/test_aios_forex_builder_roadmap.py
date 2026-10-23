from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "automation" / "orchestration" / "aios_forex_builder_roadmap.py"
ADAPTER_PATH = REPO_ROOT / "automation" / "orchestration" / "aios_candidate_packet_evidence_adapter.py"
PLANNER_PATH = REPO_ROOT / "automation" / "orchestration" / "aios_packet_queue_planner.py"
CANONICAL_SPEC_PACKET_ID = "PKT-AIOS-FOREX-BUILDER-CANONICAL-SPEC"
CANONICAL_SPEC_PATH = "docs/trading_lab/AIOS_FOREX_BUILDER_SPEC.md"
CANONICAL_SPEC_FILE = REPO_ROOT / "docs" / "trading_lab" / "AIOS_FOREX_BUILDER_SPEC.md"
DATA_SCHEMAS_PACKET_ID = "PKT-AIOS-FOREX-BUILDER-DATA-SCHEMAS"
DATA_SCHEMAS_DOC_PATH = "docs/trading_lab/AIOS_FOREX_BUILDER_DATA_SCHEMAS.md"
DATA_SCHEMAS_MODULE_PATH = "automation/forex_engine/schema_contracts.py"
DATA_SCHEMAS_TEST_PATH = "tests/forex_engine/test_schema_contracts.py"
BACKTEST_PACKET_ID = "PKT-AIOS-FOREX-BUILDER-BACKTEST-HARNESS"
RISK_PACKET_ID = "PKT-AIOS-FOREX-BUILDER-RISK-CONTRACT"
DASHBOARD_PACKET_ID = "PKT-AIOS-FOREX-BUILDER-DASHBOARD-CONTRACT"
PAPER_FORWARD_PACKET_ID = "PKT-AIOS-FOREX-BUILDER-PAPER-FORWARD-SIMULATOR"
EVIDENCE_PACKET_ID = "PKT-AIOS-FOREX-BUILDER-EVIDENCE-AGGREGATOR"
MONTH_END_PACKET_ID = "PKT-AIOS-FOREX-BUILDER-MONTH-END-READINESS"
APPROVED_EXECUTOR_PACKET_ID = "PKT-AIOS-APPROVED-EXECUTOR-LOOP-LITE"
DAILY_LOOP_PACKET_ID = "PKT-AIOS-DAILY-CONTRIBUTION-LOOP-LITE"
PAPER_FORWARD_EVIDENCE_V1_PACKET_ID = "PKT-AIOS-PAPER-FORWARD-EVIDENCE-EXPANSION-V1"
PAPER_FORWARD_EVIDENCE_V2_PACKET_ID = "PKT-AIOS-PAPER-FORWARD-EVIDENCE-EXPANSION-V2"
RISK_GOVERNOR_PACKET_ID = "PKT-AIOS-RISK-GOVERNOR-PAPER-FORWARD-THRESHOLDS"
STRESS_OUT_OF_SAMPLE_PACKET_ID = "PKT-AIOS-PAPER-FORWARD-STRESS-AND-OUT-OF-SAMPLE-V1"
BROKER_PAPER_SANDBOX_CONTRACT_PACKET_ID = "PKT-AIOS-BROKER-PAPER-SANDBOX-READINESS-CONTRACT"
STRESS_REPAIR_PACKET_ID = "PKT-AIOS-PAPER-FORWARD-STRESS-REPAIR-V1"
OOS_EXPANSION_PACKET_ID = "PKT-AIOS-PAPER-FORWARD-OOS-EXPANSION-V1"
OOS_REPAIR_PACKET_ID = "PKT-AIOS-PAPER-FORWARD-OOS-REPAIR-V1"
LOW_VOL_EDGE_REDESIGN_PACKET_ID = "PKT-AIOS-PAPER-FORWARD-LOW-VOL-EDGE-REDESIGN-V1"
LOW_VOL_EDGE_RESEARCH_V2_PACKET_ID = "PKT-AIOS-PAPER-FORWARD-LOW-VOL-EDGE-RESEARCH-V2"
STRESS_REPAIR_V2_PACKET_ID = "PKT-AIOS-PAPER-FORWARD-STRESS-REPAIR-V2"
PRESECURITY_GATE_PACKET_ID = "PKT-AIOS-BROKER-PAPER-PRESECURITY-GATE-V1"
PRESECURITY_REPAIR_PACKET_ID = "PKT-AIOS-BROKER-PAPER-PRESECURITY-GATE-REPAIR-V1"
SANDBOX_ADAPTER_STUB_PACKET_ID = "PKT-AIOS-BROKER-PAPER-SANDBOX-ADAPTER-STUB-CONTRACT"
SANDBOX_ADAPTER_STUB_REPAIR_PACKET_ID = "PKT-AIOS-BROKER-PAPER-SANDBOX-ADAPTER-STUB-CONTRACT-REPAIR-V1"
DRYRUN_INTENT_LEDGER_PACKET_ID = "PKT-AIOS-BROKER-PAPER-DRYRUN-INTENT-LEDGER-V1"
DRYRUN_INTENT_LEDGER_REPAIR_PACKET_ID = "PKT-AIOS-BROKER-PAPER-DRYRUN-INTENT-LEDGER-REPAIR-V1"
DRYRUN_RISK_GOVERNOR_PACKET_ID = "PKT-AIOS-BROKER-PAPER-DRYRUN-RISK-GOVERNOR-V1"
DRYRUN_RISK_GOVERNOR_REPAIR_PACKET_ID = "PKT-AIOS-BROKER-PAPER-DRYRUN-RISK-GOVERNOR-REPAIR-V1"
DRYRUN_REPLAY_HARNESS_PACKET_ID = "PKT-AIOS-BROKER-PAPER-DRYRUN-REPLAY-HARNESS-V1"
DRYRUN_REPLAY_HARNESS_REPAIR_PACKET_ID = "PKT-AIOS-BROKER-PAPER-DRYRUN-REPLAY-HARNESS-REPAIR-V1"
DRYRUN_REPLAY_EVIDENCE_GATE_PACKET_ID = "PKT-AIOS-BROKER-PAPER-DRYRUN-REPLAY-EVIDENCE-GATE-V1"
DRYRUN_REPLAY_EVIDENCE_GATE_REPAIR_PACKET_ID = "PKT-AIOS-BROKER-PAPER-DRYRUN-REPLAY-EVIDENCE-GATE-REPAIR-V1"
BROKER_PAPER_ADAPTER_PLAN_APPROVAL_GATE_PACKET_ID = "PKT-AIOS-BROKER-PAPER-ADAPTER-PLAN-APPROVAL-GATE-V1"
APPROVED_EXECUTOR_LOCAL_APPLY_PACKET_ID = "PKT-AIOS-APPROVED-EXECUTOR-LOCAL-APPLY-LOOP"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def roadmap_result() -> dict[str, object]:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    return module.build_forex_builder_roadmap({})


def roadmap_candidates() -> list[dict[str, object]]:
    result = roadmap_result()
    candidates = result["roadmap_candidates"]
    assert isinstance(candidates, list)
    return candidates


def canonical_spec_candidate() -> dict[str, object]:
    matches = [
        candidate
        for candidate in roadmap_candidates()
        if candidate["packet_id"] == CANONICAL_SPEC_PACKET_ID
    ]
    assert len(matches) == 1
    return matches[0]


def data_schemas_candidate() -> dict[str, object]:
    matches = [
        candidate
        for candidate in roadmap_candidates()
        if candidate["packet_id"] == DATA_SCHEMAS_PACKET_ID
    ]
    assert len(matches) == 1
    return matches[0]


def assert_preview_only(result: dict[str, object]) -> None:
    assert result["commands_executed"] == []
    assert result["files_written"] == []
    assert result["workers_dispatched"] is False
    assert result["queues_mutated"] is False
    assert result["approvals_mutated"] is False
    safety = result["safety"]
    assert isinstance(safety, dict)
    assert safety["preview_only"] is True
    assert safety["evidence_only"] is True
    assert safety["command_execution"] is False
    assert safety["filesystem_writes"] is False
    assert safety["reports_written"] is False
    assert safety["network_access"] is False


def test_roadmap_status_is_ready() -> None:
    result = roadmap_result()

    assert result["schema"] == "AIOS_FOREX_BUILDER_ROADMAP_CANDIDATE_SOURCE.v1"
    assert result["roadmap_status"] == "ready"


def test_today_goal_alignment_is_present_and_aligned() -> None:
    result = roadmap_result()

    alignment = result["today_goal_alignment"]
    assert isinstance(alignment, dict)
    assert alignment["aligned"] is True
    assert "industrial-grade forex trading bot builder" in alignment["milestone"]
    assert alignment["non_live_only"] is True


def test_roadmap_candidates_are_emitted() -> None:
    candidates = roadmap_candidates()

    assert len(candidates) == 35


def test_first_candidate_is_canonical_spec_packet() -> None:
    candidates = roadmap_candidates()

    assert candidates[0]["packet_id"] == CANONICAL_SPEC_PACKET_ID
    assert candidates[0]["title"] == "Create canonical forex builder product spec"
    assert candidates[0]["lane"] == "forex-builder-spec"


def test_canonical_spec_candidate_exists_and_points_to_spec() -> None:
    candidate = canonical_spec_candidate()

    assert CANONICAL_SPEC_PATH in candidate["required_files"]


def test_data_schemas_candidate_exists_and_points_to_schema_contracts() -> None:
    candidate = data_schemas_candidate()

    assert candidate["lane"] == "forex-builder-data-schemas"
    assert DATA_SCHEMAS_DOC_PATH in candidate["required_files"]
    assert DATA_SCHEMAS_MODULE_PATH in candidate["required_files"]
    assert DATA_SCHEMAS_TEST_PATH in candidate["required_files"]


def test_monthly_forex_candidates_appear_in_safe_order() -> None:
    packet_ids = [candidate["packet_id"] for candidate in roadmap_candidates()]

    assert packet_ids[:35] == [
        CANONICAL_SPEC_PACKET_ID,
        DATA_SCHEMAS_PACKET_ID,
        BACKTEST_PACKET_ID,
        RISK_PACKET_ID,
        DASHBOARD_PACKET_ID,
        PAPER_FORWARD_PACKET_ID,
        EVIDENCE_PACKET_ID,
        MONTH_END_PACKET_ID,
        APPROVED_EXECUTOR_PACKET_ID,
        DAILY_LOOP_PACKET_ID,
        PAPER_FORWARD_EVIDENCE_V1_PACKET_ID,
        PAPER_FORWARD_EVIDENCE_V2_PACKET_ID,
        RISK_GOVERNOR_PACKET_ID,
        STRESS_OUT_OF_SAMPLE_PACKET_ID,
        BROKER_PAPER_SANDBOX_CONTRACT_PACKET_ID,
        STRESS_REPAIR_PACKET_ID,
        OOS_EXPANSION_PACKET_ID,
        OOS_REPAIR_PACKET_ID,
        LOW_VOL_EDGE_REDESIGN_PACKET_ID,
        LOW_VOL_EDGE_RESEARCH_V2_PACKET_ID,
        PRESECURITY_GATE_PACKET_ID,
        SANDBOX_ADAPTER_STUB_PACKET_ID,
        SANDBOX_ADAPTER_STUB_REPAIR_PACKET_ID,
        DRYRUN_INTENT_LEDGER_PACKET_ID,
        DRYRUN_INTENT_LEDGER_REPAIR_PACKET_ID,
        DRYRUN_RISK_GOVERNOR_PACKET_ID,
        DRYRUN_RISK_GOVERNOR_REPAIR_PACKET_ID,
        DRYRUN_REPLAY_HARNESS_PACKET_ID,
        DRYRUN_REPLAY_HARNESS_REPAIR_PACKET_ID,
        DRYRUN_REPLAY_EVIDENCE_GATE_PACKET_ID,
        DRYRUN_REPLAY_EVIDENCE_GATE_REPAIR_PACKET_ID,
        BROKER_PAPER_ADAPTER_PLAN_APPROVAL_GATE_PACKET_ID,
        PRESECURITY_REPAIR_PACKET_ID,
        STRESS_REPAIR_V2_PACKET_ID,
        APPROVED_EXECUTOR_LOCAL_APPLY_PACKET_ID,
    ]


def test_backtest_risk_dashboard_candidates_point_to_new_contract_files() -> None:
    candidates = {candidate["packet_id"]: candidate for candidate in roadmap_candidates()}

    assert "automation/forex_engine/backtest_harness.py" in candidates[BACKTEST_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_backtest_harness.py" in candidates[BACKTEST_PACKET_ID]["required_files"]
    assert "automation/forex_engine/risk_contract.py" in candidates[RISK_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_risk_contract.py" in candidates[RISK_PACKET_ID]["required_files"]
    assert "automation/forex_engine/forex_dashboard_contract.py" in candidates[DASHBOARD_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_forex_dashboard_contract.py" in candidates[DASHBOARD_PACKET_ID]["required_files"]


def test_paper_forward_evidence_and_readiness_candidates_exist() -> None:
    candidates = {candidate["packet_id"]: candidate for candidate in roadmap_candidates()}

    assert "automation/forex_engine/paper_forward_simulator.py" in candidates[PAPER_FORWARD_PACKET_ID]["required_files"]
    assert "automation/forex_engine/evidence_aggregator.py" in candidates[EVIDENCE_PACKET_ID]["required_files"]
    assert "automation/forex_engine/month_end_readiness.py" in candidates[MONTH_END_PACKET_ID]["required_files"]
    assert "docs/orchestration/AIOS_APPROVED_EXECUTOR_LOOP_LITE.md" in candidates[APPROVED_EXECUTOR_PACKET_ID]["required_files"]
    assert "docs/orchestration/AIOS_DAILY_CONTRIBUTION_LOOP_LITE.md" in candidates[DAILY_LOOP_PACKET_ID]["required_files"]
    assert "automation/forex_engine/evidence_bundle_runner.py" in candidates[PAPER_FORWARD_EVIDENCE_V1_PACKET_ID]["required_files"]
    assert "automation/forex_engine/paper_forward_evidence_v2.py" in candidates[PAPER_FORWARD_EVIDENCE_V2_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_paper_forward_evidence_v2_demo.py" in candidates[PAPER_FORWARD_EVIDENCE_V2_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_PAPER_FORWARD_EVIDENCE_V2.md" in candidates[PAPER_FORWARD_EVIDENCE_V2_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_paper_forward_evidence_v2.py" in candidates[PAPER_FORWARD_EVIDENCE_V2_PACKET_ID]["required_files"]
    assert "automation/forex_engine/risk_governor_thresholds.py" in candidates[RISK_GOVERNOR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/opportunity_capture.py" in candidates[RISK_GOVERNOR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_risk_governor_demo.py" in candidates[RISK_GOVERNOR_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_RISK_GOVERNOR_THRESHOLDS.md" in candidates[RISK_GOVERNOR_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_OPPORTUNITY_CAPTURE.md" in candidates[RISK_GOVERNOR_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_opportunity_capture.py" in candidates[RISK_GOVERNOR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/paper_forward_stress.py" in candidates[STRESS_OUT_OF_SAMPLE_PACKET_ID]["required_files"]
    assert "automation/forex_engine/out_of_sample_validator.py" in candidates[STRESS_OUT_OF_SAMPLE_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_stress_and_oos_demo.py" in candidates[STRESS_OUT_OF_SAMPLE_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_STRESS_AND_OUT_OF_SAMPLE.md" in candidates[STRESS_OUT_OF_SAMPLE_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_BROKER_PAPER_SANDBOX_GATE.md" in candidates[STRESS_OUT_OF_SAMPLE_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_paper_forward_stress.py" in candidates[STRESS_OUT_OF_SAMPLE_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_out_of_sample_validator.py" in candidates[STRESS_OUT_OF_SAMPLE_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_sandbox_readiness.py" in candidates[BROKER_PAPER_SANDBOX_CONTRACT_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_broker_paper_sandbox_readiness_demo.py" in candidates[BROKER_PAPER_SANDBOX_CONTRACT_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_BROKER_PAPER_SANDBOX_READINESS_CONTRACT.md" in candidates[BROKER_PAPER_SANDBOX_CONTRACT_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_sandbox_readiness.py" in candidates[BROKER_PAPER_SANDBOX_CONTRACT_PACKET_ID]["required_files"]
    assert candidates[BROKER_PAPER_SANDBOX_CONTRACT_PACKET_ID]["broker_allowed"] is False
    assert candidates[BROKER_PAPER_SANDBOX_CONTRACT_PACKET_ID]["orders_allowed"] is False
    assert "automation/forex_engine/stress_repair.py" in candidates[STRESS_REPAIR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_stress_repair_demo.py" in candidates[STRESS_REPAIR_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_STRESS_REPAIR.md" in candidates[STRESS_REPAIR_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_stress_repair.py" in candidates[STRESS_REPAIR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/oos_expansion.py" in candidates[OOS_EXPANSION_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_oos_expansion_demo.py" in candidates[OOS_EXPANSION_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_OOS_EXPANSION.md" in candidates[OOS_EXPANSION_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_oos_expansion.py" in candidates[OOS_EXPANSION_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_out_of_sample_validator.py" in candidates[OOS_EXPANSION_PACKET_ID]["required_files"]
    assert "automation/forex_engine/oos_repair.py" in candidates[OOS_REPAIR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_oos_repair_demo.py" in candidates[OOS_REPAIR_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_OOS_REPAIR.md" in candidates[OOS_REPAIR_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_oos_repair.py" in candidates[OOS_REPAIR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/low_vol_edge_redesign.py" in candidates[LOW_VOL_EDGE_REDESIGN_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_low_vol_edge_redesign_demo.py" in candidates[LOW_VOL_EDGE_REDESIGN_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_LOW_VOL_EDGE_REDESIGN.md" in candidates[LOW_VOL_EDGE_REDESIGN_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_low_vol_edge_redesign.py" in candidates[LOW_VOL_EDGE_REDESIGN_PACKET_ID]["required_files"]
    assert "automation/forex_engine/low_vol_edge_redesign.py" in candidates[LOW_VOL_EDGE_RESEARCH_V2_PACKET_ID]["required_files"]
    assert "automation/forex_engine/stress_repair.py" in candidates[STRESS_REPAIR_V2_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_stress_repair.py" in candidates[STRESS_REPAIR_V2_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_presecurity_gate.py" in candidates[PRESECURITY_GATE_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_broker_paper_presecurity_gate_demo.py" in candidates[PRESECURITY_GATE_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_BROKER_PAPER_PRESECURITY_GATE.md" in candidates[PRESECURITY_GATE_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_presecurity_gate.py" in candidates[PRESECURITY_GATE_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_sandbox_readiness.py" in candidates[PRESECURITY_GATE_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_presecurity_gate.py" in candidates[PRESECURITY_REPAIR_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_BROKER_PAPER_PRESECURITY_GATE.md" in candidates[PRESECURITY_REPAIR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_adapter_stub_contract.py" in candidates[SANDBOX_ADAPTER_STUB_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_broker_paper_adapter_stub_contract_demo.py" in candidates[SANDBOX_ADAPTER_STUB_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_BROKER_PAPER_ADAPTER_STUB_CONTRACT.md" in candidates[SANDBOX_ADAPTER_STUB_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_adapter_stub_contract.py" in candidates[SANDBOX_ADAPTER_STUB_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_adapter_stub_contract.py" in candidates[SANDBOX_ADAPTER_STUB_REPAIR_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_adapter_stub_contract.py" in candidates[SANDBOX_ADAPTER_STUB_REPAIR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_dryrun_intent_ledger.py" in candidates[DRYRUN_INTENT_LEDGER_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_broker_paper_dryrun_intent_ledger_demo.py" in candidates[DRYRUN_INTENT_LEDGER_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_sandbox_readiness.py" in candidates[DRYRUN_INTENT_LEDGER_PACKET_ID]["required_files"]
    assert "automation/forex_engine/month_end_readiness.py" in candidates[DRYRUN_INTENT_LEDGER_PACKET_ID]["required_files"]
    assert "automation/forex_engine/forex_dashboard_contract.py" in candidates[DRYRUN_INTENT_LEDGER_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_BROKER_PAPER_DRYRUN_INTENT_LEDGER.md" in candidates[DRYRUN_INTENT_LEDGER_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_dryrun_intent_ledger.py" in candidates[DRYRUN_INTENT_LEDGER_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_dryrun_intent_ledger.py" in candidates[DRYRUN_INTENT_LEDGER_REPAIR_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_dryrun_intent_ledger.py" in candidates[DRYRUN_INTENT_LEDGER_REPAIR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_dryrun_risk_governor.py" in candidates[DRYRUN_RISK_GOVERNOR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/run_broker_paper_dryrun_risk_governor_demo.py" in candidates[DRYRUN_RISK_GOVERNOR_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_BROKER_PAPER_DRYRUN_RISK_GOVERNOR.md" in candidates[DRYRUN_RISK_GOVERNOR_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_dryrun_risk_governor.py" in candidates[DRYRUN_RISK_GOVERNOR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_dryrun_risk_governor.py" in candidates[DRYRUN_RISK_GOVERNOR_REPAIR_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_dryrun_risk_governor.py" in candidates[DRYRUN_RISK_GOVERNOR_REPAIR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_dryrun_replay_harness.py" in candidates[DRYRUN_REPLAY_HARNESS_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_dryrun_replay_harness.py" in candidates[DRYRUN_REPLAY_HARNESS_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_dryrun_replay_harness.py" in candidates[DRYRUN_REPLAY_HARNESS_REPAIR_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_dryrun_replay_harness.py" in candidates[DRYRUN_REPLAY_HARNESS_REPAIR_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_dryrun_replay_evidence_gate.py" in candidates[DRYRUN_REPLAY_EVIDENCE_GATE_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_dryrun_replay_evidence_gate.py" in candidates[DRYRUN_REPLAY_EVIDENCE_GATE_PACKET_ID]["required_files"]
    assert "automation/forex_engine/broker_paper_dryrun_replay_evidence_gate.py" in candidates[DRYRUN_REPLAY_EVIDENCE_GATE_REPAIR_PACKET_ID]["required_files"]
    assert "tests/forex_engine/test_broker_paper_dryrun_replay_evidence_gate.py" in candidates[DRYRUN_REPLAY_EVIDENCE_GATE_REPAIR_PACKET_ID]["required_files"]
    assert "docs/trading_lab/AIOS_FOREX_BUILDER_BROKER_PAPER_ADAPTER_PLAN_APPROVAL_GATE.md" in candidates[BROKER_PAPER_ADAPTER_PLAN_APPROVAL_GATE_PACKET_ID]["required_files"]
    assert "docs/orchestration/AIOS_APPROVED_EXECUTOR_LOCAL_APPLY_LOOP.md" in candidates[APPROVED_EXECUTOR_LOCAL_APPLY_PACKET_ID]["required_files"]


def test_data_schemas_candidate_preserves_non_live_safety_flags() -> None:
    candidate = data_schemas_candidate()

    assert candidate["non_live_only"] is True
    assert candidate["broker_allowed"] is False
    assert candidate["live_trading_allowed"] is False
    assert candidate["credentials_allowed"] is False
    assert candidate["orders_allowed"] is False
    assert candidate["webhooks_allowed"] is False


def test_canonical_spec_document_exists_and_preserves_non_live_boundaries() -> None:
    text = CANONICAL_SPEC_FILE.read_text(encoding="utf-8")
    lower_text = text.lower()

    assert "aios builds an industrial-grade forex bot builder through safe staged development" in lower_text
    assert "phase 0: canonical spec" in lower_text
    assert "phase 6: broker integration only after separate future protected approval" in lower_text
    for required_boundary in (
        "no broker integration",
        "no oanda/live exchange integration",
        "no live orders",
        "no paper orders unless separately approved later",
        "no credentials, secrets, or env reads or writes",
        "no webhooks",
        "no scheduler or daemon execution",
        "no real-money trading",
        "no account mutation",
        "no network market automation",
    ):
        assert required_boundary in lower_text


def test_all_candidates_are_non_live() -> None:
    for candidate in roadmap_candidates():
        assert candidate["non_live_only"] is True
        assert candidate["broker_allowed"] is False
        assert candidate["live_trading_allowed"] is False
        assert candidate["credentials_allowed"] is False
        assert candidate["orders_allowed"] is False
        assert candidate["webhooks_allowed"] is False


def test_all_candidates_have_required_planner_fields() -> None:
    required_fields = {
        "packet_id",
        "title",
        "lane",
        "priority",
        "milestone_value",
        "risk_level",
        "status",
        "required_files",
        "validators",
    }

    for candidate in roadmap_candidates():
        assert required_fields.issubset(candidate)
        assert candidate["required_files"]
        assert candidate["validators"]


def test_forbidden_lanes_include_protected_boundaries() -> None:
    result = roadmap_result()
    forbidden_lanes = result["forbidden_lanes"]

    assert "broker integration" in forbidden_lanes
    assert "OANDA/live exchange integration" in forbidden_lanes
    assert "live orders" in forbidden_lanes
    assert "credentials/secrets/env reads/writes" in forbidden_lanes
    assert "webhooks" in forbidden_lanes
    assert "scheduler/daemon execution" in forbidden_lanes


def test_next_recommended_candidate_is_canonical_spec_packet() -> None:
    result = roadmap_result()
    next_candidate = result["next_recommended_candidate"]

    assert isinstance(next_candidate, dict)
    assert next_candidate["packet_id"] == CANONICAL_SPEC_PACKET_ID


def test_roadmap_routes_after_oos_repair_and_requires_presecurity_gate() -> None:
    result = roadmap_result()
    routing = result["post_oos_repair_routing"]

    assert result["current_selected_packet"] == DRYRUN_REPLAY_EVIDENCE_GATE_PACKET_ID
    assert routing["current_selected_packet_after_pr_750"] == OOS_REPAIR_PACKET_ID
    assert routing["current_selected_packet_after_pr_751_752"] == LOW_VOL_EDGE_REDESIGN_PACKET_ID
    assert routing["current_selected_packet_after_pr_753"] == PRESECURITY_GATE_PACKET_ID
    assert routing["current_selected_packet_after_pr_754"] == SANDBOX_ADAPTER_STUB_PACKET_ID
    assert routing["current_selected_packet_after_pr_755"] == DRYRUN_INTENT_LEDGER_PACKET_ID
    assert routing["current_selected_packet_after_pr_756"] == DRYRUN_RISK_GOVERNOR_PACKET_ID
    assert routing["current_selected_packet_after_pr_757"] == DRYRUN_REPLAY_HARNESS_PACKET_ID
    assert routing["current_selected_packet_after_pr_758"] == DRYRUN_REPLAY_EVIDENCE_GATE_PACKET_ID
    assert routing["conditional_next_packets"]["oos_repair_watchlist"] == LOW_VOL_EDGE_REDESIGN_PACKET_ID
    assert routing["conditional_next_packets"]["low_vol_redesign_watchlist"] == LOW_VOL_EDGE_RESEARCH_V2_PACKET_ID
    assert routing["conditional_next_packets"]["oos_pass_stress_watchlist"] == STRESS_REPAIR_V2_PACKET_ID
    assert routing["conditional_next_packets"]["oos_and_stress_pass"] == PRESECURITY_GATE_PACKET_ID
    assert routing["conditional_next_packets"]["presecurity_gate_fail"] == PRESECURITY_REPAIR_PACKET_ID
    assert routing["conditional_next_packets"]["presecurity_gate_watchlist"] == PRESECURITY_REPAIR_PACKET_ID
    assert routing["conditional_next_packets"]["presecurity_gate_pass"] == SANDBOX_ADAPTER_STUB_PACKET_ID
    assert routing["conditional_next_packets"]["stub_contract_fail"] == SANDBOX_ADAPTER_STUB_REPAIR_PACKET_ID
    assert routing["conditional_next_packets"]["stub_contract_watchlist"] == SANDBOX_ADAPTER_STUB_REPAIR_PACKET_ID
    assert routing["conditional_next_packets"]["stub_contract_pass"] == DRYRUN_INTENT_LEDGER_PACKET_ID
    assert routing["conditional_next_packets"]["dryrun_ledger_fail"] == DRYRUN_INTENT_LEDGER_REPAIR_PACKET_ID
    assert routing["conditional_next_packets"]["dryrun_ledger_watchlist"] == DRYRUN_INTENT_LEDGER_REPAIR_PACKET_ID
    assert routing["conditional_next_packets"]["dryrun_ledger_pass"] == DRYRUN_RISK_GOVERNOR_PACKET_ID
    assert routing["conditional_next_packets"]["dryrun_risk_governor_fail"] == DRYRUN_RISK_GOVERNOR_REPAIR_PACKET_ID
    assert routing["conditional_next_packets"]["dryrun_risk_governor_watchlist"] == DRYRUN_RISK_GOVERNOR_REPAIR_PACKET_ID
    assert routing["conditional_next_packets"]["dryrun_risk_governor_pass"] == DRYRUN_REPLAY_HARNESS_PACKET_ID
    assert routing["conditional_next_packets"]["dryrun_replay_harness_fail"] == DRYRUN_REPLAY_HARNESS_REPAIR_PACKET_ID
    assert routing["conditional_next_packets"]["dryrun_replay_harness_watchlist"] == DRYRUN_REPLAY_HARNESS_REPAIR_PACKET_ID
    assert routing["conditional_next_packets"]["dryrun_replay_harness_pass"] == DRYRUN_REPLAY_EVIDENCE_GATE_PACKET_ID
    assert (
        routing["conditional_next_packets"]["dryrun_replay_evidence_gate_fail"]
        == DRYRUN_REPLAY_EVIDENCE_GATE_REPAIR_PACKET_ID
    )
    assert (
        routing["conditional_next_packets"]["dryrun_replay_evidence_gate_watchlist"]
        == DRYRUN_REPLAY_EVIDENCE_GATE_REPAIR_PACKET_ID
    )
    assert (
        routing["conditional_next_packets"]["dryrun_replay_evidence_gate_pass"]
        == BROKER_PAPER_ADAPTER_PLAN_APPROVAL_GATE_PACKET_ID
    )
    assert result["security_gate_required_before_broker_paper"] is True
    assert result["required_security_packet"] == PRESECURITY_GATE_PACKET_ID
    assert "broker-paper requires secrets/network/broker boundaries" in result["security_gate_reason"]


def test_roadmap_selects_low_vol_redesign_when_oos_repair_remains_watchlist() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    result = module.build_forex_builder_roadmap(
        {
            "oos_repair": {"repaired_classification": "WATCHLIST"},
            "stress_repair": {"repaired_classification": "WATCHLIST"},
        }
    )

    assert result["post_oos_repair_next_safe_packet"] == LOW_VOL_EDGE_REDESIGN_PACKET_ID
    assert result["post_oos_repair_next_safe_candidate"]["packet_id"] == LOW_VOL_EDGE_REDESIGN_PACKET_ID


def test_roadmap_selects_low_vol_research_when_low_vol_redesign_remains_watchlist() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    result = module.build_forex_builder_roadmap(
        {
            "oos_repair": {"repaired_classification": "WATCHLIST"},
            "low_vol_edge_redesign": {"classification": "WATCHLIST"},
            "stress_repair": {"repaired_classification": "WATCHLIST"},
        }
    )

    assert result["post_low_vol_redesign_next_safe_packet"] == LOW_VOL_EDGE_RESEARCH_V2_PACKET_ID
    assert result["post_low_vol_redesign_next_safe_candidate"]["packet_id"] == LOW_VOL_EDGE_RESEARCH_V2_PACKET_ID


def test_roadmap_selects_presecurity_gate_when_oos_and_stress_pass() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    result = module.build_forex_builder_roadmap(
        {
            "oos_repair": {"repaired_classification": "PAPER_FORWARD_READY"},
            "low_vol_edge_redesign": {"classification": "PAPER_FORWARD_READY"},
            "stress_repair": {"repaired_classification": "PAPER_FORWARD_READY"},
        }
    )

    assert result["post_oos_repair_next_safe_packet"] == PRESECURITY_GATE_PACKET_ID
    assert result["post_oos_repair_next_safe_candidate"]["packet_id"] == PRESECURITY_GATE_PACKET_ID


def test_roadmap_selects_presecurity_repair_when_presecurity_fails_or_watchlist() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    for classification in ("FAIL", "WATCHLIST"):
        result = module.build_forex_builder_roadmap(
            {
                "oos_repair": {"repaired_classification": "PAPER_FORWARD_READY"},
                "low_vol_edge_redesign": {"classification": "PAPER_FORWARD_READY"},
                "stress_repair": {"repaired_classification": "PAPER_FORWARD_READY"},
                "presecurity_gate": {"classification": classification},
            }
        )

        assert result["post_presecurity_gate_next_safe_packet"] == PRESECURITY_REPAIR_PACKET_ID
        assert result["post_presecurity_gate_next_safe_candidate"]["packet_id"] == PRESECURITY_REPAIR_PACKET_ID


def test_roadmap_selects_adapter_stub_contract_when_presecurity_passes() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    result = module.build_forex_builder_roadmap(
        {
            "oos_repair": {"repaired_classification": "PAPER_FORWARD_READY"},
            "low_vol_edge_redesign": {"classification": "PAPER_FORWARD_READY"},
            "stress_repair": {"repaired_classification": "PAPER_FORWARD_READY"},
            "presecurity_gate": {"classification": "PRESECURITY_READY"},
        }
    )

    assert result["post_presecurity_gate_next_safe_packet"] == SANDBOX_ADAPTER_STUB_PACKET_ID
    assert result["post_presecurity_gate_next_safe_candidate"]["packet_id"] == SANDBOX_ADAPTER_STUB_PACKET_ID


def test_roadmap_selects_stub_repair_when_adapter_stub_fails_or_watchlist() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    for classification in ("FAIL", "WATCHLIST"):
        result = module.build_forex_builder_roadmap(
            {
                "presecurity_gate": {"classification": "PRESECURITY_READY"},
                "broker_paper_adapter_stub_contract": {"classification": classification},
            }
        )

        assert result["post_adapter_stub_contract_next_safe_packet"] == SANDBOX_ADAPTER_STUB_REPAIR_PACKET_ID
        assert (
            result["post_adapter_stub_contract_next_safe_candidate"]["packet_id"]
            == SANDBOX_ADAPTER_STUB_REPAIR_PACKET_ID
        )


def test_roadmap_selects_dryrun_intent_ledger_when_adapter_stub_passes() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    result = module.build_forex_builder_roadmap(
        {
            "presecurity_gate": {"classification": "PRESECURITY_READY"},
            "broker_paper_adapter_stub_contract": {"classification": "STUB_CONTRACT_READY"},
        }
    )

    assert result["post_adapter_stub_contract_next_safe_packet"] == DRYRUN_INTENT_LEDGER_PACKET_ID
    assert result["post_adapter_stub_contract_next_safe_candidate"]["packet_id"] == DRYRUN_INTENT_LEDGER_PACKET_ID


def test_roadmap_selects_dryrun_ledger_repair_when_ledger_fails_or_watchlists() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    for classification in ("FAIL", "WATCHLIST"):
        result = module.build_forex_builder_roadmap(
            {
                "presecurity_gate": {"classification": "PRESECURITY_READY"},
                "broker_paper_adapter_stub_contract": {"classification": "STUB_CONTRACT_READY"},
                "broker_paper_dryrun_intent_ledger": {"classification": classification},
            }
        )

        assert result["post_dryrun_intent_ledger_next_safe_packet"] == DRYRUN_INTENT_LEDGER_REPAIR_PACKET_ID
        assert (
            result["post_dryrun_intent_ledger_next_safe_candidate"]["packet_id"]
            == DRYRUN_INTENT_LEDGER_REPAIR_PACKET_ID
        )


def test_roadmap_selects_dryrun_risk_governor_when_ledger_passes() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    result = module.build_forex_builder_roadmap(
        {
            "presecurity_gate": {"classification": "PRESECURITY_READY"},
            "broker_paper_adapter_stub_contract": {"classification": "STUB_CONTRACT_READY"},
            "broker_paper_dryrun_intent_ledger": {"classification": "DRYRUN_LEDGER_READY"},
        }
    )

    assert result["post_dryrun_intent_ledger_next_safe_packet"] == DRYRUN_RISK_GOVERNOR_PACKET_ID
    assert result["post_dryrun_intent_ledger_next_safe_candidate"]["packet_id"] == DRYRUN_RISK_GOVERNOR_PACKET_ID


def test_roadmap_selects_dryrun_risk_governor_repair_when_governor_fails_or_watchlists() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    for classification in ("FAIL", "WATCHLIST"):
        result = module.build_forex_builder_roadmap(
            {
                "presecurity_gate": {"classification": "PRESECURITY_READY"},
                "broker_paper_adapter_stub_contract": {"classification": "STUB_CONTRACT_READY"},
                "broker_paper_dryrun_intent_ledger": {"classification": "DRYRUN_LEDGER_READY"},
                "broker_paper_dryrun_risk_governor": {"classification": classification},
            }
        )

        assert result["post_dryrun_risk_governor_next_safe_packet"] == DRYRUN_RISK_GOVERNOR_REPAIR_PACKET_ID
        assert (
            result["post_dryrun_risk_governor_next_safe_candidate"]["packet_id"]
            == DRYRUN_RISK_GOVERNOR_REPAIR_PACKET_ID
        )


def test_roadmap_selects_dryrun_replay_harness_when_risk_governor_passes() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    result = module.build_forex_builder_roadmap(
        {
            "presecurity_gate": {"classification": "PRESECURITY_READY"},
            "broker_paper_adapter_stub_contract": {"classification": "STUB_CONTRACT_READY"},
            "broker_paper_dryrun_intent_ledger": {"classification": "DRYRUN_LEDGER_READY"},
            "broker_paper_dryrun_risk_governor": {"classification": "DRYRUN_RISK_GOVERNOR_READY"},
        }
    )

    assert result["post_dryrun_risk_governor_next_safe_packet"] == DRYRUN_REPLAY_HARNESS_PACKET_ID
    assert result["post_dryrun_risk_governor_next_safe_candidate"]["packet_id"] == DRYRUN_REPLAY_HARNESS_PACKET_ID


def test_roadmap_selects_replay_harness_repair_when_replay_fails_or_watchlists() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    for classification in ("FAIL", "WATCHLIST"):
        result = module.build_forex_builder_roadmap(
            {
                "presecurity_gate": {"classification": "PRESECURITY_READY"},
                "broker_paper_adapter_stub_contract": {"classification": "STUB_CONTRACT_READY"},
                "broker_paper_dryrun_intent_ledger": {"classification": "DRYRUN_LEDGER_READY"},
                "broker_paper_dryrun_risk_governor": {"classification": "DRYRUN_RISK_GOVERNOR_READY"},
                "broker_paper_dryrun_replay_harness": {"classification": classification},
            }
        )

        assert result["post_dryrun_replay_harness_next_safe_packet"] == DRYRUN_REPLAY_HARNESS_REPAIR_PACKET_ID
        assert (
            result["post_dryrun_replay_harness_next_safe_candidate"]["packet_id"]
            == DRYRUN_REPLAY_HARNESS_REPAIR_PACKET_ID
        )


def test_roadmap_selects_replay_evidence_gate_when_replay_harness_passes() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    result = module.build_forex_builder_roadmap(
        {
            "presecurity_gate": {"classification": "PRESECURITY_READY"},
            "broker_paper_adapter_stub_contract": {"classification": "STUB_CONTRACT_READY"},
            "broker_paper_dryrun_intent_ledger": {"classification": "DRYRUN_LEDGER_READY"},
            "broker_paper_dryrun_risk_governor": {"classification": "DRYRUN_RISK_GOVERNOR_READY"},
            "broker_paper_dryrun_replay_harness": {"classification": "DRYRUN_REPLAY_HARNESS_READY"},
        }
    )

    assert result["post_dryrun_replay_harness_next_safe_packet"] == DRYRUN_REPLAY_EVIDENCE_GATE_PACKET_ID
    assert (
        result["post_dryrun_replay_harness_next_safe_candidate"]["packet_id"]
        == DRYRUN_REPLAY_EVIDENCE_GATE_PACKET_ID
    )


def test_roadmap_selects_replay_evidence_repair_when_evidence_gate_fails_or_watchlists() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    for classification in ("FAIL", "WATCHLIST"):
        result = module.build_forex_builder_roadmap(
            {
                "presecurity_gate": {"classification": "PRESECURITY_READY"},
                "broker_paper_adapter_stub_contract": {"classification": "STUB_CONTRACT_READY"},
                "broker_paper_dryrun_intent_ledger": {"classification": "DRYRUN_LEDGER_READY"},
                "broker_paper_dryrun_risk_governor": {"classification": "DRYRUN_RISK_GOVERNOR_READY"},
                "broker_paper_dryrun_replay_harness": {"classification": "DRYRUN_REPLAY_HARNESS_READY"},
                "broker_paper_dryrun_replay_evidence_gate": {"classification": classification},
            }
        )

        assert result["post_dryrun_replay_evidence_gate_next_safe_packet"] == DRYRUN_REPLAY_EVIDENCE_GATE_REPAIR_PACKET_ID
        assert (
            result["post_dryrun_replay_evidence_gate_next_safe_candidate"]["packet_id"]
            == DRYRUN_REPLAY_EVIDENCE_GATE_REPAIR_PACKET_ID
        )


def test_roadmap_selects_adapter_plan_approval_gate_when_replay_evidence_passes() -> None:
    module = load_module("aios_forex_builder_roadmap", MODULE_PATH)
    result = module.build_forex_builder_roadmap(
        {
            "presecurity_gate": {"classification": "PRESECURITY_READY"},
            "broker_paper_adapter_stub_contract": {"classification": "STUB_CONTRACT_READY"},
            "broker_paper_dryrun_intent_ledger": {"classification": "DRYRUN_LEDGER_READY"},
            "broker_paper_dryrun_risk_governor": {"classification": "DRYRUN_RISK_GOVERNOR_READY"},
            "broker_paper_dryrun_replay_harness": {"classification": "DRYRUN_REPLAY_HARNESS_READY"},
            "broker_paper_dryrun_replay_evidence_gate": {"classification": "DRYRUN_REPLAY_EVIDENCE_READY"},
        }
    )

    assert result["post_dryrun_replay_evidence_gate_next_safe_packet"] == BROKER_PAPER_ADAPTER_PLAN_APPROVAL_GATE_PACKET_ID
    assert (
        result["post_dryrun_replay_evidence_gate_next_safe_candidate"]["packet_id"]
        == BROKER_PAPER_ADAPTER_PLAN_APPROVAL_GATE_PACKET_ID
    )


def test_output_is_compatible_with_candidate_adapter_and_packet_queue_planner() -> None:
    adapter = load_module("aios_candidate_packet_evidence_adapter", ADAPTER_PATH)
    planner = load_module("aios_packet_queue_planner", PLANNER_PATH)
    from automation.orchestration.aios_repo_state_evidence import collect_planner_repository_state
    observed = collect_planner_repository_state(REPO_ROOT)
    assert observed is not None
    result = load_module("roadmap_state", MODULE_PATH).build_forex_builder_roadmap(repository_state=observed)

    adapter_result = adapter.build_candidate_packet_evidence(
        {"candidate_packets": result["roadmap_candidates"]}
    )
    plan = planner.build_packet_queue_planner(adapter_result["candidate_packets"])

    assert adapter_result["candidate_packets"][0]["packet_id"] == CANONICAL_SPEC_PACKET_ID
    assert plan["queue_status"] == "selected"
    assert plan["selected_packet"]["packet_id"] == CANONICAL_SPEC_PACKET_ID
    assert plan["codex_ready_packet_preview"]["packet_ready"] is True
    assert plan["selected_packet"]["repository_state"] == observed


def test_roadmap_without_repository_observation_is_not_packet_ready() -> None:
    adapter = load_module("adapter_missing_state", ADAPTER_PATH)
    planner = load_module("planner_missing_state", PLANNER_PATH)
    normalized = adapter.build_candidate_packet_evidence(roadmap_result())
    preview = planner.build_packet_queue_planner(normalized)["codex_ready_packet_preview"]
    assert preview["packet_ready"] is False
    assert preview["reason_code"] == "repository_state_missing"


def test_no_candidate_writes_to_broker_trading_credentials_order_webhook_paths() -> None:
    forbidden_segments = {"broker", "trading", "credentials", "credential", "order", "orders", "webhook", "webhooks"}

    for candidate in roadmap_candidates():
        for path in candidate["required_files"]:
            parts = str(path).replace("\\", "/").lower().split("/")
            assert not forbidden_segments.intersection(parts)


def test_no_candidate_allows_network() -> None:
    for candidate in roadmap_candidates():
        assert candidate["network_allowed"] is False


def test_no_candidate_allows_scheduler_or_daemon() -> None:
    for candidate in roadmap_candidates():
        assert candidate["scheduler_allowed"] is False
        assert candidate["daemon_allowed"] is False


def test_commands_executed_is_empty() -> None:
    assert roadmap_result()["commands_executed"] == []


def test_files_written_is_empty() -> None:
    assert roadmap_result()["files_written"] == []


def test_workers_dispatched_false() -> None:
    assert roadmap_result()["workers_dispatched"] is False


def test_queues_mutated_false() -> None:
    assert roadmap_result()["queues_mutated"] is False


def test_approvals_mutated_false() -> None:
    assert roadmap_result()["approvals_mutated"] is False


def test_safety_preview_only_true() -> None:
    assert_preview_only(roadmap_result())


def test_source_does_not_import_subprocess_network_or_file_write_tools() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line.strip()
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    )

    for forbidden in ("subprocess", "socket", "urllib", "requests", "http", "pathlib", "os", "shutil"):
        assert forbidden not in import_lines
    for forbidden_call in ("open(", "Path(", "write_text(", "write_bytes("):
        assert forbidden_call not in source
