"""Offline Forex promotion readiness pipeline model.

This module is repo-safe and offline-only. It evaluates local evidence and gate
state to produce promotion artifacts for the next governed owner/broker review
lane without touching credentials, broker APIs, or live execution paths.
"""

from __future__ import annotations

from argparse import ArgumentParser
import json
from dataclasses import dataclass
from pathlib import Path


PIPELINE_ID = "AIOS_FOREX_PROMOTION_PIPELINE_V1"
SAFETY_BOUNDARY = (
    "No broker/API access, no credentials, no demo-order placement, no live "
    "trading, no money movement, no scheduler installation, no daemon "
    "installation, and no webhook creation are performed."
)

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = DEFAULT_REPO_ROOT / "Reports" / "forex_delivery"
DEFAULT_PIPELINE_REPORT_PATH = (
    DEFAULT_REPORT_DIR / "AIOS_FOREX_PROMOTION_PIPELINE_V1_REPORT.md"
)
DEFAULT_STATE_PATH = DEFAULT_REPORT_DIR / "AIOS_FOREX_PROMOTION_PIPELINE_V1_STATE.json"
DEFAULT_CHECKPOINT_PATH = (
    DEFAULT_REPORT_DIR / "AIOS_FOREX_PROMOTION_PIPELINE_V1_CHECKPOINT.md"
)
DEFAULT_OWNER_APPROVAL_CARD_PATH = (
    DEFAULT_REPORT_DIR / "AIOS_FOREX_PROMOTION_PIPELINE_V1_OWNER_APPROVAL_CARD.md"
)
DEFAULT_NEXT_CODEX_PACKET_PATH = (
    DEFAULT_REPORT_DIR / "AIOS_FOREX_PROMOTION_PIPELINE_NEXT_CODEX_PACKET_V1.md"
)

DECISION_STATUS_GATE_SELECTED = "PROMOTION_GATE_SELECTED"
DECISION_STATUS_OWNER_REQUIRED = "OWNER_APPROVAL_REQUIRED"
DECISION_STATUS_BROKER_REQUIRED = "BROKER_READINESS_REQUIRED"
DECISION_STATUS_BLOCKED = "PROMOTION_BLOCKED"
DECISION_STATUS_READY_FOR_REVIEW = "PROMOTION_READY_FOR_REVIEW"
DECISION_STATUS_COMPLETE = "PROMOTION_COMPLETE"

NEXT_ACTION_COLLECT_MISSING = "COLLECT_MISSING_EVIDENCE"
NEXT_ACTION_PREPARE_OWNER_APPROVAL = "PREPARE_OWNER_APPROVAL"
NEXT_ACTION_PREPARE_BROKER_READINESS = "PREPARE_BROKER_READINESS_REVIEW"
NEXT_ACTION_RESOLVE_BLOCKERS = "RESOLVE_BLOCKERS"
NEXT_ACTION_OPEN_REVIEW = "OPEN_PROMOTION_REVIEW"
NEXT_ACTION_NO_ACTION = "NO_ACTION_REQUIRED"

DEFAULT_ALLOWED_PATHS = (
    "automation/forex_engine/forex_promotion_pipeline_v1.py",
    "tests/forex_engine/test_forex_promotion_pipeline_v1.py",
    "scripts/forex_delivery/Invoke-ForexPromotionPipeline.V1.ps1",
    "Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_REPORT.md",
    "Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_STATE.json",
    "Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_CHECKPOINT.md",
    "Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_OWNER_APPROVAL_CARD.md",
    "Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_NEXT_CODEX_PACKET_V1.md",
    "automation/forex_engine/forex_autonomous_campaign_manager_v1.py",
    "Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_V1_STATE.json",
    "Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_V1_CHECKPOINT.md",
    "Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_NEXT_CODEX_PROMPT_V1.md",
)

DEFAULT_FORBIDDEN_PATHS = (
    ".env",
    ".env.*",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "secrets/*",
    "credentials/*",
    "services/*",
    "apps/*",
    "telemetry/*",
)


@dataclass(frozen=True)
class PromotionGate:
    gate_id: str
    title: str
    required_evidence: tuple[str, ...]
    human_gate: bool = False
    broker_gate: bool = False
    hard_stop_if_missing: bool = True


@dataclass(frozen=True)
class PromotionState:
    pipeline_id: str
    available_evidence: tuple[str, ...]
    passed_gates: tuple[str, ...]
    blocked_reasons: tuple[str, ...] = ()
    owner_approved: bool = False
    broker_ready: bool = False


@dataclass(frozen=True)
class PromotionDecision:
    status: str
    selected_gate_id: str
    next_action: str
    missing_evidence: tuple[str, ...]
    required_owner_actions: tuple[str, ...]
    safety_boundary: str


def build_default_promotion_gates() -> tuple[PromotionGate, ...]:
    return (
        PromotionGate(
            gate_id="PAPER_EVIDENCE_SUFFICIENCY",
            title="Paper evidence sufficiency gate",
            required_evidence=(
                "flow2_evidence_countdown_complete",
                "paper_trade_sample_present",
                "profitability_evaluator_present",
            ),
        ),
        PromotionGate(
            gate_id="STRATEGY_VALIDATION_EVIDENCE",
            title="Strategy validation evidence gate",
            required_evidence=(
                "walkforward_validation_present",
                "strategy_harness_present",
                "negative_expectancy_block_reviewed",
            ),
        ),
        PromotionGate(
            gate_id="DEMO_ENVIRONMENT_READINESS",
            title="Demo environment readiness gate",
            required_evidence=(
                "demo_readiness_report_present",
                "broker_demo_adapter_present",
                "protected_demo_order_gate_present",
            ),
        ),
        PromotionGate(
            gate_id="RISK_LIMIT_VERIFICATION",
            title="Risk limit verification gate",
            required_evidence=(
                "max_loss_policy_present",
                "daily_stop_policy_present",
                "position_size_policy_present",
            ),
        ),
        PromotionGate(
            gate_id="BROKER_ACCOUNT_READINESS",
            title="Broker account readiness gate",
            required_evidence=(
                "broker_readiness_checklist_present",
                "account_capability_review_present",
            ),
            broker_gate=True,
        ),
        PromotionGate(
            gate_id="OWNER_APPROVAL_GATE",
            title="Owner approval gate",
            required_evidence=("owner_approval_card_present",),
            human_gate=True,
        ),
        PromotionGate(
            gate_id="LIVE_ARMING_REVIEW",
            title="Live arming review gate",
            required_evidence=(
                "live_arming_checklist_present",
                "final_governance_review_present",
            ),
            human_gate=True,
            broker_gate=True,
        ),
    )


def collect_available_promotion_evidence(
    repo_root: Path = DEFAULT_REPO_ROOT,
) -> tuple[str, ...]:
    """Collect evidence by conservative path presence checks only."""

    candidate_files_by_evidence = {
        "flow2_evidence_countdown_complete": [
            "Reports/forex_delivery/AIOS_FOREX_FLOW2_SUPERVISED_DEMO_EVIDENCE_COUNTDOWN_CAPTURE_V1_REPORT.md",
        ],
        "paper_trade_sample_present": [
            "Reports/forex_delivery/AIOS_FOREX_PAPER_SESSION_SAMPLE_GENERATOR_V1_REPORT.md",
        ],
        "profitability_evaluator_present": [
            "Reports/forex_delivery/AIOS_FOREX_PAPER_PROFITABILITY_EVALUATOR_V1_REPORT.md",
        ],
        "walkforward_validation_present": [
            "automation/forex_engine/walkforward_validation_harness.py",
            "Reports/forex_delivery/AIOS_FOREX_WALKFORWARD_VALIDATION_HARNESS_V1_REPORT.md",
        ],
        "strategy_harness_present": [
            "automation/forex_engine/strategy_evaluation_harness.py",
            "Reports/forex_delivery/AIOS_FOREX_STRATEGY_EVALUATION_HARNESS_V1_REPORT.md",
        ],
        "negative_expectancy_block_reviewed": [
            "Reports/forex_delivery/AIOS_FOREX_STRATEGY_EVALUATION_HARNESS_V1_REPORT.md",
        ],
        "demo_readiness_report_present": [
            "Reports/forex_delivery/AIOS_FOREX_DEMO_READINESS_SPINE_V1_REPORT.md",
            "Reports/forex_delivery/AIOS_FOREX_DEMO_READINESS_PROFIT_TRUST_SPINE_V1.md",
        ],
        "broker_demo_adapter_present": [
            "automation/forex_engine/paper_demo_broker_adapter.py",
        ],
        "protected_demo_order_gate_present": [
            "Reports/forex_delivery/AIOS_FOREX_C1_DEMO_ORDER_INTENT_OWNER_APPROVAL_GATE_V1_REPORT.md",
        ],
        "max_loss_policy_present": [
            "Reports/forex_delivery/AIOS_FOREX_RISK_GOVERNOR_V1_REPORT.md",
            "Reports/forex_delivery/AIOS_FOREX_TAKE_PROFIT_RISK_GATE_CLOSURE_V1.md",
        ],
        "daily_stop_policy_present": [
            "Reports/forex_delivery/AIOS_FOREX_RISK_GOVERNOR_V1_REPORT.md",
            "Reports/forex_delivery/AIOS_FOREX_C1_RISK_POSITION_SIZING_REVIEW_V1_REPORT.md",
        ],
        "position_size_policy_present": [
            "Reports/forex_delivery/AIOS_FOREX_RISK_GOVERNOR_V1_REPORT.md",
            "Reports/forex_delivery/AIOS_FOREX_C1_RISK_POSITION_SIZING_REVIEW_V1_REPORT.md",
        ],
        "broker_readiness_checklist_present": [
            "Reports/forex_delivery/AIOS_FOREX_BROKER_INTEGRATION_READINESS_FINAL_REVIEW_PACKET_J_V1.md",
        ],
        "account_capability_review_present": [
            "Reports/forex_delivery/AIOS_FOREX_C1_SUPERVISED_DEMO_BROKER_ACCOUNT_READINESS_BRIDGE_V1_REPORT.md",
        ],
        "owner_approval_card_present": [
            "Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_OWNER_APPROVAL_CARD.md",
        ],
        "live_arming_checklist_present": [
            "Reports/forex_delivery/AIOS_FOREX_ONE_SHOT_LIVE_MICRO_TRADE_ARMING_REVIEW_DRY_RUN_V1.md",
            "Reports/forex_delivery/AIOS_FOREX_LIVE_ARMING_EVIDENCE_GAP_DRY_RUN_V1_REPORT.md",
        ],
        "final_governance_review_present": [
            "Reports/forex_delivery/AIOS_FOREX_FINAL_CLOSURE_AUDIT_LANE_V1_REPORT.md",
        ],
    }

    root = Path(repo_root).resolve()
    available: list[str] = []
    for evidence_id, candidate_paths in candidate_files_by_evidence.items():
        if any((root / path).exists() for path in candidate_paths):
            available.append(evidence_id)
    return tuple(available)


def _is_gate_evidence_missing(
    gate: PromotionGate,
    available_evidence: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(evidence_id for evidence_id in gate.required_evidence if evidence_id not in available_evidence)


def evaluate_promotion_pipeline(
    state: PromotionState,
    *,
    gates: tuple[PromotionGate, ...] | None = None,
    repo_root: Path = DEFAULT_REPO_ROOT,
) -> PromotionDecision:
    if state.blocked_reasons:
        return PromotionDecision(
            status=DECISION_STATUS_BLOCKED,
            selected_gate_id="",
            next_action=NEXT_ACTION_RESOLVE_BLOCKERS,
            missing_evidence=(),
            required_owner_actions=state.blocked_reasons,
            safety_boundary=SAFETY_BOUNDARY,
        )

    gates = gates or build_default_promotion_gates()
    available_evidence = collect_available_promotion_evidence(repo_root)

    for gate in gates:
        missing = _is_gate_evidence_missing(gate, available_evidence)
        if missing and gate.hard_stop_if_missing:
            return PromotionDecision(
                status=DECISION_STATUS_GATE_SELECTED,
                selected_gate_id=gate.gate_id,
                next_action=NEXT_ACTION_COLLECT_MISSING,
                missing_evidence=missing,
                required_owner_actions=(
                    f"Collect evidence for gate {gate.gate_id}: {', '.join(missing)}",
                ),
                safety_boundary=SAFETY_BOUNDARY,
            )

        if gate.broker_gate and not state.broker_ready:
            return PromotionDecision(
                status=DECISION_STATUS_BROKER_REQUIRED,
                selected_gate_id=gate.gate_id,
                next_action=NEXT_ACTION_PREPARE_BROKER_READINESS,
                missing_evidence=(),
                required_owner_actions=(
                    "Complete broker/account readiness evidence and explicit broker approval path.",
                ),
                safety_boundary=SAFETY_BOUNDARY,
            )

        if gate.human_gate and not state.owner_approved:
            return PromotionDecision(
                status=DECISION_STATUS_OWNER_REQUIRED,
                selected_gate_id=gate.gate_id,
                next_action=NEXT_ACTION_PREPARE_OWNER_APPROVAL,
                missing_evidence=(),
                required_owner_actions=(
                    "Obtain explicit owner approval and confirm policy boundaries.",
                ),
                safety_boundary=SAFETY_BOUNDARY,
            )

    return PromotionDecision(
        status=DECISION_STATUS_COMPLETE,
        selected_gate_id="",
        next_action=NEXT_ACTION_OPEN_REVIEW,
        missing_evidence=(),
        required_owner_actions=(
            "Prepare final promotion handoff packet and preserve evidence set.",
        ),
        safety_boundary=SAFETY_BOUNDARY,
    )


def build_state_payload(
    *,
    state: PromotionState,
    decision: PromotionDecision,
    available_evidence: tuple[str, ...],
) -> dict[str, object]:
    return {
        "pipeline_id": state.pipeline_id,
        "status": decision.status,
        "selected_gate_id": decision.selected_gate_id,
        "next_action": decision.next_action,
        "available_evidence": list(available_evidence),
        "missing_evidence": list(decision.missing_evidence),
        "required_owner_actions": list(decision.required_owner_actions),
        "broker_gate": decision.selected_gate_id in {
            "BROKER_ACCOUNT_READINESS",
            "LIVE_ARMING_REVIEW",
        } or state.broker_ready,
        "human_gate": decision.selected_gate_id in {
            "OWNER_APPROVAL_GATE",
            "LIVE_ARMING_REVIEW",
        } or state.owner_approved,
        "safety_boundary": decision.safety_boundary,
        "owner_approved": state.owner_approved,
        "broker_ready": state.broker_ready,
    }


def _comma_sep(values: tuple[str, ...] | list[str]) -> str:
    if not values:
        return "- None"
    return "\n".join(f"- {value}" for value in values)


def _next_safe_command(decision: PromotionDecision) -> str:
    if decision.status == DECISION_STATUS_GATE_SELECTED:
        return "Collect the missing evidence files and rerun this promotion pipeline."
    if decision.status == DECISION_STATUS_BROKER_REQUIRED:
        return (
            "Gather broker/account readiness evidence artifacts and rerun "
            "with --broker-ready once evidence is confirmed."
        )
    if decision.status == DECISION_STATUS_OWNER_REQUIRED:
        return (
            "Obtain explicit owner approval actions and rerun "
            "with --owner-approved when confirmed."
        )
    if decision.status == DECISION_STATUS_BLOCKED:
        return "Resolve blockers before continuing promotion pipeline progress."
    return "Open the generated next packet and review the owner approval handoff."


def _render_gate_lines(
    gates: tuple[PromotionGate, ...],
    state: PromotionState,
) -> str:
    lines = []
    for gate in gates:
        status = "passed" if gate.gate_id in state.passed_gates else "pending"
        lines.append(f"- {gate.gate_id}: {gate.title}")
        lines.append(f"  required_evidence: {', '.join(gate.required_evidence)}")
        lines.append(f"  human_gate: {str(gate.human_gate).lower()}")
        lines.append(f"  broker_gate: {str(gate.broker_gate).lower()}")
        lines.append(f"  status: {status}")
    return "\n".join(lines)


def build_promotion_checkpoint(
    *,
    state: PromotionState,
    decision: PromotionDecision,
    available_evidence: tuple[str, ...],
    gates: tuple[PromotionGate, ...] | None = None,
) -> str:
    gates = gates or build_default_promotion_gates()
    return f"""# AIOS Forex Promotion Pipeline Checkpoint

Pipeline ID: {state.pipeline_id}
Status: {decision.status}
Selected gate: {decision.selected_gate_id}
Next action: {decision.next_action}
Safety boundary: {decision.safety_boundary}

## Available evidence
{_comma_sep(available_evidence)}

## Missing evidence
{_comma_sep(decision.missing_evidence)}

## Owner actions required
{_comma_sep(decision.required_owner_actions)}

## Broker-gated items
- BROKER_ACCOUNT_READINESS
- LIVE_ARMING_REVIEW

## Human-gated items
- OWNER_APPROVAL_GATE
- LIVE_ARMING_REVIEW

## Gates
{_render_gate_lines(gates, state)}

## Safety boundary
{SAFETY_BOUNDARY}

## Next safe command
{_next_safe_command(decision)}
"""


def build_owner_approval_card(
    *,
    state: PromotionState,
    decision: PromotionDecision,
    gates: tuple[PromotionGate, ...] | None = None,
    available_evidence: tuple[str, ...] = (),
) -> str:
    gates = gates or build_default_promotion_gates()
    passed_gate_ids = set(state.passed_gates)
    failed_gate_ids = tuple(gate.gate_id for gate in gates if gate.gate_id not in passed_gate_ids)

    return f"""# AIOS Forex Promotion Pipeline Owner Approval Card

## Automated readiness findings

### What passed
{_comma_sep(state.passed_gates)}

### What is missing
{_comma_sep(decision.missing_evidence)}

### What is broker-gated
- BROKER_ACCOUNT_READINESS
- LIVE_ARMING_REVIEW

### What is human-gated
- OWNER_APPROVAL_GATE
- LIVE_ARMING_REVIEW

## Owner actions
- confirm broker/demo/live intent in a separate owner process
- confirm acceptable risk policy and any required limits
- confirm credentials will not be pasted into chat
- confirm whether the next intended stage is demo-only or live-arming review

## Current pipeline context
Pipeline ID: {state.pipeline_id}
Current status: {decision.status}
Selected gate: {decision.selected_gate_id}
Next action: {decision.next_action}
Failed gates (if any): {_comma_sep(failed_gate_ids)}
Available evidence count: {len(available_evidence)}

AIOS is not authorized to place trades from this packet.
"""


def build_report(
    state: PromotionState,
    decision: PromotionDecision,
    available: tuple[str, ...],
) -> str:
    return f"""# AIOS Forex Promotion Pipeline V1 Report

Pipeline ID: {state.pipeline_id}
Decision status: {decision.status}
Selected gate: {decision.selected_gate_id}
Next action: {decision.next_action}
Safety boundary: {decision.safety_boundary}

## Passed evidence
{_comma_sep(state.passed_gates)}

## Missing evidence
{_comma_sep(decision.missing_evidence)}

## Owner actions required
{_comma_sep(decision.required_owner_actions)}

## Broker-gated
- BROKER_ACCOUNT_READINESS
- LIVE_ARMING_REVIEW

## Human-gated
- OWNER_APPROVAL_GATE
- LIVE_ARMING_REVIEW

## Safety boundary
{SAFETY_BOUNDARY}

## Next safe command
{_next_safe_command(decision)}

## Available evidence
{_comma_sep(available)}
"""


def build_next_codex_packet(
    *,
    state: PromotionState,
    decision: PromotionDecision,
    state_path: Path = DEFAULT_STATE_PATH,
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH,
    owner_approval_card_path: Path = DEFAULT_OWNER_APPROVAL_CARD_PATH,
    next_codex_path: Path = DEFAULT_NEXT_CODEX_PACKET_PATH,
) -> str:
    allowed = "\n- ".join(DEFAULT_ALLOWED_PATHS)
    forbidden = "\n- ".join(DEFAULT_FORBIDDEN_PATHS)

    return f"""CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

## IDENTITY MARKER
PROJECT: AI_OS
REPOSITORY: ai-rtony91/Ai_Os
WORKTREE: C:\\\\Dev\\\\Ai.Os
PACKET_ID: AIOS_FOREX_PROMOTION_PIPELINE_AUTOMATOR_V1
MODE: APPLY
ZONE: FOREX_PROMOTION_READINESS
LANE: Forex / promotion pipeline / readiness gates
SUPERVISOR IDENTITY: ChatGPT planning supervisor
WORKER IDENTITY: Codex

## CURRENT STATE
Pipeline ID: {state.pipeline_id}
Status: {decision.status}
Selected gate: {decision.selected_gate_id}
Next action: {decision.next_action}

## ALLOWED PATHS
- {allowed}

## FORBIDDEN PATHS
- {forbidden}

## APPROVAL AUTHORITY
- run required validators listed below
- do not edit broker/API/credential/order/live files
- preserve existing campaign manager artifacts

## VALIDATOR CHAIN
python -m py_compile automation/forex_engine/forex_promotion_pipeline_v1.py
python -m pytest tests/forex_engine/test_forex_promotion_pipeline_v1.py -q
pwsh -File scripts/forex_delivery/Invoke-ForexPromotionPipeline.V1.ps1 -DryRun -NoPublish -MaxMinutes 30
python -m py_compile automation/forex_engine/forex_autonomous_campaign_manager_v1.py
python -m pytest tests/forex_engine/test_forex_autonomous_campaign_manager_v1.py -q
git diff --check -- automation/forex_engine/forex_promotion_pipeline_v1.py tests/forex_engine/test_forex_promotion_pipeline_v1.py scripts/forex_delivery/Invoke-ForexPromotionPipeline.V1.ps1 Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_REPORT.md Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_STATE.json Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_CHECKPOINT.md Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_OWNER_APPROVAL_CARD.md Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_NEXT_CODEX_PACKET_V1.md automation/forex_engine/forex_autonomous_campaign_manager_v1.py Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_V1_STATE.json Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_V1_CHECKPOINT.md Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_NEXT_CODEX_PROMPT_V1.md

## STOP POINT
STOP when PROMOTION_COMPLETE or PROMOTION_BLOCKED.

## CURRENT WORK FILES
STATE_PATH:{state_path}
CHECKPOINT_PATH:{checkpoint_path}
OWNER_APPROVAL_CARD_PATH:{owner_approval_card_path}
NEXT_CODEX_PACKET_PATH:{next_codex_path}

## NEXT SAFE ACTION
Use the generated report and evidence artifacts to complete current gate requirements.

## FINAL REPORT FORMAT
PROMOTION_PIPELINE_STATUS:
CURRENT_BRANCH:
CURRENT_HEAD:
FILES_CREATED:
FILES_CHANGED:
VALIDATORS_RUN:
VALIDATORS_PASSED:
VALIDATORS_FAILED:
PROMOTION_STATUS:
SELECTED_GATE:
NEXT_ACTION:
MISSING_EVIDENCE:
OWNER_ACTIONS_REQUIRED:
BROKER_GATE:
HUMAN_GATE:
CHECKPOINT_PATH:
OWNER_APPROVAL_CARD_PATH:
NEXT_CODEX_PACKET_PATH:
PR_CREATED:
PR_MERGED:
FINAL_GIT_STATUS:
SAFETY_BOUNDARY:
BROKER_API_ACCESS:
CREDENTIALS_USED:
ORDER_EXECUTION:
LIVE_TRADING:
MONEY_MOVEMENT:
SCHEDULERS_DAEMONS_WEBHOOKS:
NEXT_SAFE_ACTION:
STOP_REASON:
"""


def parse_args() -> argparse.Namespace:
    parser = ArgumentParser()
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--checkpoint-path", default=str(DEFAULT_CHECKPOINT_PATH))
    parser.add_argument("--owner-approval-card-path", default=str(DEFAULT_OWNER_APPROVAL_CARD_PATH))
    parser.add_argument("--next-codex-packet-path", default=str(DEFAULT_NEXT_CODEX_PACKET_PATH))
    parser.add_argument("--report-path", default=str(DEFAULT_PIPELINE_REPORT_PATH))
    parser.add_argument("--owner-approved", action="store_true")
    parser.add_argument("--broker-ready", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    return parser.parse_args()


def _stop_reason(status: str) -> str:
    if status == DECISION_STATUS_GATE_SELECTED:
        return DECISION_STATUS_GATE_SELECTED
    if status == DECISION_STATUS_OWNER_REQUIRED:
        return DECISION_STATUS_OWNER_REQUIRED
    if status == DECISION_STATUS_BROKER_REQUIRED:
        return DECISION_STATUS_BROKER_REQUIRED
    if status == DECISION_STATUS_BLOCKED:
        return "HARD_BLOCKERS"
    if status == DECISION_STATUS_COMPLETE:
        return DECISION_STATUS_COMPLETE
    return DECISION_STATUS_READY_FOR_REVIEW


def _collect_default_passed_gates(
    gates: tuple[PromotionGate, ...],
    available_evidence: tuple[str, ...],
    *,
    owner_approved: bool = False,
    broker_ready: bool = False,
) -> tuple[str, ...]:
    passed_gate_ids: list[str] = []
    for gate in gates:
        if _is_gate_evidence_missing(gate, available_evidence):
            continue
        if gate.broker_gate and not broker_ready:
            continue
        if gate.human_gate and not owner_approved:
            continue
        passed_gate_ids.append(gate.gate_id)
    return tuple(passed_gate_ids)


def evaluate_and_write_artifacts(
    *,
    repo_root: Path = DEFAULT_REPO_ROOT,
    state_path: Path = DEFAULT_STATE_PATH,
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH,
    owner_approval_card_path: Path = DEFAULT_OWNER_APPROVAL_CARD_PATH,
    next_codex_packet_path: Path = DEFAULT_NEXT_CODEX_PACKET_PATH,
    report_path: Path = DEFAULT_PIPELINE_REPORT_PATH,
    owner_approved: bool = False,
    broker_ready: bool = False,
) -> tuple[PromotionState, PromotionDecision, tuple[str, ...]]:
    gates = build_default_promotion_gates()
    available_evidence = collect_available_promotion_evidence(repo_root)
    state = PromotionState(
        pipeline_id=PIPELINE_ID,
        available_evidence=available_evidence,
        passed_gates=_collect_default_passed_gates(
            gates,
            available_evidence,
            owner_approved=owner_approved,
            broker_ready=broker_ready,
        ),
        blocked_reasons=(),
        owner_approved=owner_approved,
        broker_ready=broker_ready,
    )
    decision = evaluate_promotion_pipeline(
        state,
        gates=gates,
        repo_root=repo_root,
    )

    payload = build_state_payload(
        state=state,
        decision=decision,
        available_evidence=available_evidence,
    )

    state_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    checkpoint_path.write_text(
        build_promotion_checkpoint(
            state=state,
            decision=decision,
            available_evidence=available_evidence,
            gates=gates,
        ),
        encoding="utf-8",
    )
    owner_approval_card_path.write_text(
        build_owner_approval_card(
            state=state,
            decision=decision,
            gates=gates,
            available_evidence=available_evidence,
        ),
        encoding="utf-8",
    )
    next_codex_packet_path.write_text(
        build_next_codex_packet(
            state=state,
            decision=decision,
            state_path=state_path,
            checkpoint_path=checkpoint_path,
            owner_approval_card_path=owner_approval_card_path,
            next_codex_path=next_codex_packet_path,
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        build_report(state=state, decision=decision, available=available_evidence),
        encoding="utf-8",
    )
    return state, decision, available_evidence


def main() -> None:
    args = parse_args()
    state, decision, available_evidence = evaluate_and_write_artifacts(
        repo_root=Path(args.repo_root).resolve(),
        state_path=Path(args.state_path),
        checkpoint_path=Path(args.checkpoint_path),
        owner_approval_card_path=Path(args.owner_approval_card_path),
        next_codex_packet_path=Path(args.next_codex_packet_path),
        report_path=Path(args.report_path),
        owner_approved=args.owner_approved,
        broker_ready=args.broker_ready,
    )
    payload = {
        **build_state_payload(
            state=state,
            decision=decision,
            available_evidence=available_evidence,
        ),
        "stop_reason": _stop_reason(decision.status),
    }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
