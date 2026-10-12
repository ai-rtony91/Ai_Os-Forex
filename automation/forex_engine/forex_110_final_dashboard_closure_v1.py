"""Forex 110 final dashboard closure and protected handoff.

This module composes repo-local proof-chain artifacts into an owner-review
closure state. It is report-only and grants no broker, credential, demo, live,
order, money, scheduler, daemon, webhook, or background-loop authority.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


PACKET_ID = "PKT-FOREX-110-FINAL-DASHBOARD-CLOSURE-AND-PROTECTED-HANDOFF-V1"
ENGINE_VERSION = "forex_110_final_dashboard_closure_v1"

DEFAULT_REPORT_ROOT = Path("Reports") / "forex_delivery"

TRUTH_LOCK_STATE = "AIOS_FOREX_110_PROFIT_EVIDENCE_TRUTH_LOCK_V1_STATE.json"
PERIOD_STATE = "AIOS_FOREX_110_PERSISTENT_PROFITABILITY_PERIOD_EVIDENCE_V1_STATE.json"
PERIOD_SOURCE = "AIOS_FOREX_110_PERSISTENT_PROFITABILITY_PERIOD_SOURCE_V1.md"
WALKFORWARD_STATE = "AIOS_FOREX_110_WALKFORWARD_OOS_SUFFICIENCY_TRUTH_LOCK_V1_STATE.json"
C2_HARNESS_STATE = "AIOS_FOREX_110_C2_REAL_WALKFORWARD_OOS_HARNESS_V1_STATE.json"
C2_SOURCE_STATE = "AIOS_FOREX_110_C2_WALKFORWARD_OOS_SOURCE_COLLECTION_V1_STATE.json"
C2_GENERATION_STATE = "AIOS_FOREX_110_C2_WALKFORWARD_OOS_EVIDENCE_GENERATION_V1_STATE.json"

PROTECTED_PERMISSION_FLAGS = {
    "broker_api_used": False,
    "credentials_used": False,
    "env_read": False,
    "account_identifiers_used": False,
    "order_execution": False,
    "demo_authorized": False,
    "live_authorized": False,
    "scheduler_started": False,
    "daemon_started": False,
    "webhook_started": False,
    "background_loop_started": False,
    "next_demo_trade_allowed": False,
    "broker_action_allowed": False,
    "real_money_allowed": False,
    "compounding_allowed": False,
    "bank_movement_allowed": False,
    "live_trading_allowed": False,
    "credential_access_allowed": False,
    "order_submission_allowed": False,
    "owner_approval_created": False,
}


def run_forex_110_final_dashboard_closure_v1(
    report_root: str | Path = DEFAULT_REPORT_ROOT,
) -> dict[str, Any]:
    """Return the final Forex 110 owner-review closure state."""

    root = Path(report_root)
    truth_lock = _read_json(root / TRUTH_LOCK_STATE)
    period_state = _read_json(root / PERIOD_STATE)
    walkforward = _read_json(root / WALKFORWARD_STATE)
    c2_harness = _read_json(root / C2_HARNESS_STATE)
    c2_source = _read_json(root / C2_SOURCE_STATE)
    c2_generation = _read_json(root / C2_GENERATION_STATE)

    profit_truth_lock_status = str(truth_lock.get("truth_lock_status", "UNKNOWN"))
    profit_proof_status = str(truth_lock.get("profit_proof_status", "UNKNOWN"))
    persistent_profitability_status = _persistent_status(truth_lock, period_state)
    walkforward_oos_status = _walkforward_status(walkforward, c2_generation)
    c2_source_status = _c2_source_status(c2_source, c2_harness, c2_generation)

    proof_chain_ready = (
        profit_truth_lock_status == "PROVEN"
        and profit_proof_status == "PROVEN"
        and persistent_profitability_status == "READY"
        and walkforward_oos_status == "PROVEN"
        and c2_source_status == "PROVEN"
    )

    dashboard_user_sections = _dashboard_user_sections()
    clickable_emoji_windows = _clickable_emoji_windows()
    critical_only_display_rules = _critical_only_display_rules()
    hidden_heavy_data_rules = _hidden_heavy_data_rules()
    end_user_overwhelm_prevention_rules = _overwhelm_prevention_rules()
    attack_to_finish = _attack_to_finish(proof_chain_ready)

    result: dict[str, Any] = {
        "packet_id": PACKET_ID,
        "engine_version": ENGINE_VERSION,
        "closure_status": "READY_FOR_OWNER_REVIEW" if proof_chain_ready else "BLOCKED",
        "repo_safe_completion_status": (
            "FOREX_110_REPO_SAFE_PROOF_CHAIN_REVIEW_READY"
            if proof_chain_ready
            else "FOREX_110_REPO_SAFE_PROOF_CHAIN_BLOCKED"
        ),
        "profit_truth_lock_status": profit_truth_lock_status,
        "profit_proof_status": profit_proof_status,
        "persistent_profitability_status": persistent_profitability_status,
        "walkforward_oos_status": walkforward_oos_status,
        "c2_source_status": c2_source_status,
        "dashboard_completion_status": "COMPLETE" if proof_chain_ready else "BLOCKED",
        "total_completion_label": (
            "FOREX_110_REPO_SAFE_COMPLETE_OWNER_REVIEW_REQUIRED"
            if proof_chain_ready
            else "FOREX_110_REPO_SAFE_INCOMPLETE"
        ),
        "dashboard_user_sections": dashboard_user_sections,
        "clickable_emoji_windows": clickable_emoji_windows,
        "critical_only_display_rules": critical_only_display_rules,
        "hidden_heavy_data_rules": hidden_heavy_data_rules,
        "end_user_overwhelm_prevention_rules": end_user_overwhelm_prevention_rules,
        "protected_boundary_status": "LOCKED_FALSE",
        "bitwarden_blocked_until_forex_110_complete": True,
        "next_safe_action": (
            "Owner review of the Forex 110 closure index and protected boundary handoff. "
            "Do not start Bitwarden, secrets, demo, live, broker, order, money, "
            "scheduler, daemon, webhook, or background-loop lanes until closure is landed."
        ),
        "proof_chain_sources": [
            TRUTH_LOCK_STATE,
            PERIOD_STATE,
            PERIOD_SOURCE,
            WALKFORWARD_STATE,
            C2_HARNESS_STATE,
            C2_SOURCE_STATE,
            C2_GENERATION_STATE,
        ],
        "owner_review_required": True,
        "profit_guarantee_created": False,
        "autonomous_real_money_trading_authorized": False,
        "protected_permission_flags": dict(PROTECTED_PERMISSION_FLAGS),
        "all_protected_permission_flags_false": True,
        "ATTACK_TO_FINISH": attack_to_finish,
    }
    result.update(PROTECTED_PERMISSION_FLAGS)
    return result


def build_report_markdown(result: Mapping[str, Any]) -> str:
    """Build the final dashboard closure report."""

    return "\n".join(
        [
            "# AIOS Forex 110 Final Dashboard Closure V1",
            "",
            f"Packet ID: `{result['packet_id']}`",
            f"Closure status: `{result['closure_status']}`",
            f"Repo-safe completion status: `{result['repo_safe_completion_status']}`",
            f"Total completion label: `{result['total_completion_label']}`",
            "",
            "## Proof Chain",
            f"- Profit truth lock: `{result['profit_truth_lock_status']}`",
            f"- Profit proof: `{result['profit_proof_status']}`",
            f"- Persistent profitability: `{result['persistent_profitability_status']}`",
            f"- Walk-forward/OOS: `{result['walkforward_oos_status']}`",
            f"- C2 source: `{result['c2_source_status']}`",
            "",
            "## Protected Boundary",
            f"- Boundary status: `{result['protected_boundary_status']}`",
            "- Demo/live/broker/order/money/credential authority remains `false`.",
            "- Owner review is required before any demo, live, broker, order, money, or credential action.",
            "- No profit guarantee is created.",
            "- No autonomous real-money trading is authorized.",
            "",
            "## Dashboard Rule",
            "Show high-level state only. Keep raw evidence, long logs, broker-heavy state, metadata, and proof internals behind report links.",
            "",
            "## Next Safe Action",
            str(result["next_safe_action"]),
            "",
            _attack_to_finish_markdown(result["ATTACK_TO_FINISH"]),
            "",
        ]
    )


def build_completion_index_markdown(result: Mapping[str, Any]) -> str:
    """Build the concise Forex 110 completion index."""

    sources = result.get("proof_chain_sources") or []
    lines = [
        "# AIOS Forex 110 Completion Index V1",
        "",
        (
            "Forex 110 repo-safe proof chain is review-ready."
            if result.get("closure_status") == "READY_FOR_OWNER_REVIEW"
            else "Forex 110 repo-safe proof chain remains blocked."
        ),
        "",
        "## Review State",
        f"- Closure status: `{result['closure_status']}`",
        f"- Repo-safe completion: `{result['repo_safe_completion_status']}`",
        f"- Dashboard completion: `{result['dashboard_completion_status']}`",
        f"- Protected boundary: `{result['protected_boundary_status']}`",
        "",
        "## Proof Chain",
        f"- C2 walk-forward/OOS source: `{result['c2_source_status']}`",
        f"- Walk-forward/OOS proof: `{result['walkforward_oos_status']}`",
        f"- Profit truth lock: `{result['profit_truth_lock_status']}`",
        f"- Profit proof: `{result['profit_proof_status']}`",
        f"- Persistent profitability: `{result['persistent_profitability_status']}`",
        "",
        "## Source Links",
    ]
    lines.extend(f"- `Reports/forex_delivery/{source}`" for source in sources)
    lines.extend(
        [
            "",
            "## Safety",
            "- Demo/live/broker/order/money/credential permissions remain locked false.",
            "- Owner review is required before any protected action.",
            "- This index creates no profit guarantee and no trading approval.",
            "",
        ]
    )
    return "\n".join(lines)


def build_dashboard_contract_markdown(result: Mapping[str, Any]) -> str:
    """Build the end-user dashboard UX contract."""

    lines = [
        "# AIOS Forex Dashboard End User UX Contract V1",
        "",
        "The dashboard must help the owner understand state without exposing heavy proof internals by default.",
        "",
        "## Required User Sections",
    ]
    lines.extend(f"- {section}" for section in result["dashboard_user_sections"])
    lines.extend(
        [
            "",
            "## Critical-Only Display Rules",
            *_prefixed(result["critical_only_display_rules"]),
            "",
            "## Hidden Heavy Data Rules",
            *_prefixed(result["hidden_heavy_data_rules"]),
            "",
            "## Overwhelm Prevention Rules",
            *_prefixed(result["end_user_overwhelm_prevention_rules"]),
            "",
            "## Protected Boundary",
            "- Broker/API, credential, account identifier, order execution, demo, live, scheduler, daemon, webhook, and background-loop state must display as locked unless a later owner-approved packet changes authority.",
            "- No Bitwarden or secrets lane starts until Forex 110 closure is landed.",
            "",
        ]
    )
    return "\n".join(lines)


def build_clickable_emoji_window_map_markdown(result: Mapping[str, Any]) -> str:
    """Build the clickable emoji/window dashboard map."""

    lines = [
        "# AIOS Forex Dashboard Clickable Emoji Window Map V1",
        "",
        "| Window | Opens | Default display | Hidden behind link |",
        "|---|---|---|---|",
    ]
    for window in result["clickable_emoji_windows"]:
        lines.append(
            "| {label} | `{target}` | {summary} | {hidden} |".format(
                label=window["label"],
                target=window["target"],
                summary=window["default_summary"],
                hidden=window["hidden_detail"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def build_protected_boundary_handoff_markdown(result: Mapping[str, Any]) -> str:
    """Build the protected boundary handoff."""

    lines = [
        "# AIOS Forex Final Protected Boundary Handoff V1",
        "",
        f"Protected boundary status: `{result['protected_boundary_status']}`",
        "",
        "## Locked False",
    ]
    lines.extend(
        f"- {key}: `{str(value).lower()}`"
        for key, value in result["protected_permission_flags"].items()
    )
    lines.extend(
        [
            "",
            "## Owner Gate",
            "Owner review is required before demo, live, broker, order, money, credential, scheduler, daemon, webhook, or background-loop action.",
            "",
            "## No Authority Granted",
            "- No profit guarantee.",
            "- No autonomous real-money trading.",
            "- No broker/API access.",
            "- No credential or `.env` access.",
            "",
        ]
    )
    return "\n".join(lines)


def build_bitwarden_blocker_markdown(result: Mapping[str, Any]) -> str:
    """Build the post-110 Bitwarden blocker handoff."""

    return "\n".join(
        [
            "# AIOS Forex Post-110 Next Project Blocker Bitwarden V1",
            "",
            f"Bitwarden blocked until Forex 110 complete: `{str(result['bitwarden_blocked_until_forex_110_complete']).lower()}`",
            "",
            "No Bitwarden, secrets, credential, `.env`, broker API, demo, live, order, or money lane may start from this packet.",
            "",
            "## Safe Next Action",
            "Land Forex 110 closure first. After owner review and explicit approval, create a separate scoped packet for any secrets or Bitwarden work.",
            "",
        ]
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _persistent_status(
    truth_lock: Mapping[str, Any],
    period_state: Mapping[str, Any],
) -> str:
    status = str(truth_lock.get("persistent_profitability_status", "UNKNOWN"))
    if status == "PERSISTENT_PROFITABILITY_READY":
        return "READY"
    if period_state.get("period_evidence_status") == "PROVEN_PERSISTENT_PROFITABILITY_PERIODS":
        return "READY"
    return status


def _walkforward_status(
    walkforward: Mapping[str, Any],
    c2_generation: Mapping[str, Any],
) -> str:
    if walkforward.get("truth_lock_status") == "PROVEN":
        return "PROVEN"
    if c2_generation.get("c2_oos_evidence_status") == "PROVEN":
        return "PROVEN"
    return str(walkforward.get("walk_forward_oos_status", "UNKNOWN"))


def _c2_source_status(
    c2_source: Mapping[str, Any],
    c2_harness: Mapping[str, Any],
    c2_generation: Mapping[str, Any],
) -> str:
    if (
        c2_source.get("source_collection_status") == "PROVEN_REAL_SANITIZED_LOCAL_C2_SOURCE"
        and c2_harness.get("harness_status") == "PROVEN_REAL_WALKFORWARD_OOS_HARNESS"
        and c2_generation.get("c2_oos_evidence_status") == "PROVEN"
    ):
        return "PROVEN"
    return "BLOCKED"


def _dashboard_user_sections() -> list[str]:
    return [
        "Command Center",
        "Safety Gate",
        "Candidate",
        "Evidence",
        "Profit Proof",
        "Broker Boundary",
        "Reports",
        "SOS / Owner Wake",
        "Settings Placeholder",
        "Secrets Later",
    ]


def _clickable_emoji_windows() -> list[dict[str, str]]:
    return [
        {
            "label": "🏛 Command Center",
            "target": "command_center",
            "default_summary": "Forex 110 review-ready state and next safe action.",
            "hidden_detail": "Full proof-chain internals stay behind report links.",
        },
        {
            "label": "🛡 Safety Gate",
            "target": "safety_gate",
            "default_summary": "Protected permissions are locked false.",
            "hidden_detail": "Policy details and gate evidence stay behind report links.",
        },
        {
            "label": "🎯 Candidate",
            "target": "candidate",
            "default_summary": "Top candidate is review-ready only.",
            "hidden_detail": "Candidate scoring internals stay behind report links.",
        },
        {
            "label": "📁 Evidence",
            "target": "evidence",
            "default_summary": "Repo-safe evidence chain is available.",
            "hidden_detail": "Raw evidence, long logs, and metadata stay behind report links.",
        },
        {
            "label": "💰 Profit Proof",
            "target": "profit_proof",
            "default_summary": "Profit proof is proven for owner review only.",
            "hidden_detail": "No profit guarantee; detailed math stays behind report links.",
        },
        {
            "label": "🚧 Broker Boundary",
            "target": "broker_boundary",
            "default_summary": "Broker/API/order/live/demo authority is false.",
            "hidden_detail": "Broker-heavy state stays behind report links.",
        },
        {
            "label": "📄 Reports",
            "target": "reports",
            "default_summary": "Open closure index, UX contract, and boundary handoff.",
            "hidden_detail": "Long report body opens only by click.",
        },
        {
            "label": "🚨 SOS / Owner Wake",
            "target": "sos_owner_wake",
            "default_summary": "Show only critical owner action requirements.",
            "hidden_detail": "Escalation evidence stays behind report links.",
        },
        {
            "label": "⚙️ Settings Placeholder",
            "target": "settings_placeholder",
            "default_summary": "Placeholder only; no runtime authority.",
            "hidden_detail": "Settings implementation deferred to a later approved packet.",
        },
        {
            "label": "🔐 Secrets Later",
            "target": "secrets_later",
            "default_summary": "Bitwarden and secrets work remains blocked.",
            "hidden_detail": "Secrets workflow requires a separate owner-approved packet.",
        },
    ]


def _critical_only_display_rules() -> list[str]:
    return [
        "Show closure status, proof-chain state, protected boundary state, and next safe action first.",
        "Display owner-review requirement near any demo, live, broker, order, money, or credential reference.",
        "Display locked false flags as summaries, not as operational controls.",
        "Never display a profit guarantee or autonomous real-money trading claim.",
    ]


def _hidden_heavy_data_rules() -> list[str]:
    return [
        "Keep raw evidence, long logs, metadata, proof internals, and broker-heavy state behind report links.",
        "Keep account identifiers, credentials, `.env`, broker API details, and secret paths out of the dashboard.",
        "Open detailed proof reports only after an intentional user click.",
        "Use repo-safe report links instead of embedding heavy state in first-view dashboard panels.",
    ]


def _overwhelm_prevention_rules() -> list[str]:
    return [
        "Use one concise state label per window.",
        "Prefer review-ready, locked, blocked, and next-action labels over dense proof text.",
        "Collapse non-critical evidence by default.",
        "Keep SOS / Owner Wake reserved for real owner action, not routine proof detail.",
    ]


def _attack_to_finish(proof_chain_ready: bool) -> dict[str, str]:
    return {
        "blocker_id": "NO_BLOCKER" if proof_chain_ready else "MISSING_EVIDENCE_FIELD",
        "blocker_status": "READY_FOR_OWNER_REVIEW" if proof_chain_ready else "BLOCKED",
        "exact_blocker": "NONE" if proof_chain_ready else "Forex 110 proof chain did not satisfy all closure statuses.",
        "canonical_owner_file": "docs/trading_lab/forex/FOREX_110_FINAL_DASHBOARD_CLOSURE_V1.md",
        "test_file": "tests/forex_engine/test_forex_110_final_dashboard_closure_v1.py",
        "runner_script": "scripts/forex_delivery/run_forex_110_final_dashboard_closure_v1.py",
        "missing_evidence_field": "NONE" if proof_chain_ready else "closure_status",
        "unlock_status_required": "READY_FOR_OWNER_REVIEW",
        "next_packet_name": "NONE",
        "owner_action_required": "review Reports/forex_delivery/AIOS_FOREX_110_COMPLETION_INDEX_V1.md",
        "stop_condition": "NONE" if proof_chain_ready else "proof chain incomplete",
        "no_bloat_guard": (
            "Use this focused closure layer; do not create duplicate dashboard authority, "
            "secret authority, broker authority, or proof engines."
        ),
    }


def _attack_to_finish_markdown(block: Mapping[str, str]) -> str:
    lines = ["## ATTACK_TO_FINISH"]
    lines.extend(f"- {key}: `{value}`" for key, value in block.items())
    return "\n".join(lines)


def _prefixed(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


__all__ = [
    "ENGINE_VERSION",
    "PACKET_ID",
    "build_bitwarden_blocker_markdown",
    "build_clickable_emoji_window_map_markdown",
    "build_completion_index_markdown",
    "build_dashboard_contract_markdown",
    "build_protected_boundary_handoff_markdown",
    "build_report_markdown",
    "run_forex_110_final_dashboard_closure_v1",
]
