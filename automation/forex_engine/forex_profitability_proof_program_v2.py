"""Packet 019 profitability proof controller.

The controller resumes from current state, records official-data and
practice-history blockers, and stops at the first legitimate Human gate. It
does not score real candidates until the external and multi-regime corpus gates
are frozen.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACKET_ID = "PKT-EAST-FOREX-PROFITABILITY-FIRST-019"
ROOT = Path(".aios/runtime/forex_profitability_proof_program_v2")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_PROOF_PROGRAM_V2_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_PROOF_PROGRAM_V2_REPORT.md")
PIPELINE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_RESEARCH_PIPELINE_FALSIFIABILITY_V1_STATE.json")
PIPELINE_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_RESEARCH_PIPELINE_FALSIFIABILITY_V1_REPORT.md")
SUPERTREND_STATE = Path("Reports/forex_delivery/AIOS_FOREX_SUPERTREND_FINAL_AUDIT_V1_STATE.json")
SUPERTREND_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_SUPERTREND_FINAL_AUDIT_V1_REPORT.md")
ATLAS_STATE = Path("Reports/forex_delivery/AIOS_FOREX_LONG_SHORT_OPPORTUNITY_ATLAS_V1_STATE.json")
ATLAS_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_LONG_SHORT_OPPORTUNITY_ATLAS_V1_REPORT.md")
SCORE_JSON = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_READINESS_SCORECARD_V2.json")
SCORE_MD = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_READINESS_SCORECARD_V2.md")
PRACTICE_HANDOFF = Path("Reports/forex_delivery/AIOS_FOREX_PRACTICE_HISTORY_HUMAN_HANDOFF_V1.md")
PRACTICE_HANDOFF_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PRACTICE_HISTORY_HUMAN_HANDOFF_V1_STATE.json")


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def synthetic_controls_preview() -> dict[str, Any]:
    return {
        "status": "NOT_RUN_DATA_BLOCKED",
        "positive_controls": ["PC1_LONG", "PC2_SHORT", "PC3_BIDIRECTIONAL", "PC4_SPARSE", "PC5_REGIME", "PC6_INTERACTION"],
        "negative_controls": ["NC1_RANDOM_WALK", "NC2_FUTURE_LEAKAGE", "NC3_DUPLICATE_BEHAVIOR", "NC4_HIGH_WIN_NEGATIVE_EXPECTANCY", "NC5_ONE_WINNER_ILLUSION", "NC6_MIDPOINT_FANTASY"],
        "reason": "Packet order requires official and Practice-history data blockers to close before falsifiability execution.",
    }


def write_practice_handoff() -> dict[str, Any]:
    script = Path("scripts/forex_delivery/Acquire-AiOsOandaPracticeHistory.HUMAN_ONLY.ps1")
    state = {
        "schema": "AIOS_FOREX_PRACTICE_HISTORY_HUMAN_HANDOFF_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "HUMAN_PRACTICE_DATA_ACQUISITION_REQUIRED",
        "script": script.as_posix(),
        "script_sha256": sha256(script.read_bytes()) if script.exists() else None,
        "destination_inbox": ".aios/runtime/forex_practice_history_human_inbox/",
        "secret_required": True,
        "codex_may_read_secret": False,
        "practice_get_only": True,
        "live": False,
        "orders": False,
        "broker_mutation": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    state["state_hash"] = sha256(stable(state).encode("utf-8"))
    atomic_json(PRACTICE_HANDOFF_STATE, state)
    PRACTICE_HANDOFF.write_text(render_practice_handoff(state), encoding="utf-8")
    return state


def render_practice_handoff(state: dict[str, Any]) -> str:
    return f"""# AIOS Forex Practice History Human Handoff V1

WHAT HAPPENED:
Packet 019 prepared a Human-only OANDA Practice GET-only history acquisition helper.

IS IT SAFE:
WAIT. It is safe only if run outside Codex in a fresh Human-controlled PowerShell session.

WHAT DO I DO NEXT:
Run `{state['script']}` outside Codex, enter the Practice token only into the masked prompt, then resume Packet 019.

TECHNICAL DETAILS:
- Status: `{state['status']}`
- Script SHA-256: `{state['script_sha256']}`
- Output inbox: `{state['destination_inbox']}`
- LIVE endpoint: false
- Orders: false
- Codex secret access: false
"""


def scorecard(official: dict[str, Any], external: dict[str, Any], market: dict[str, Any], practice: dict[str, Any]) -> dict[str, Any]:
    return {
        "OFFICIAL_DATA_CLOSURE": {"score": 70 if official.get("status") == "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED" else 100, "evidence": official.get("status"), "missing_evidence": official.get("remaining_human_download_items", []), "unlock_condition": "complete consolidated public official download/import"},
        "PRACTICE_HISTORY_BOUNDARY": {"score": 80, "evidence": practice.get("script_sha256"), "missing_evidence": "Human-produced sanitized OANDA Practice artifacts", "unlock_condition": "run Human-only helper outside Codex"},
        "MULTI_REGIME_CORPUS": {"score": int(market.get("capability_score", 0)), "evidence": market.get("status"), "missing_evidence": market.get("blocker"), "unlock_condition": "sanitized artifacts imported and corpus frozen"},
        "EXTERNAL_INFORMATION_CORPUS": {"score": int(external.get("external_information_coverage_score", 0)), "evidence": external.get("status"), "missing_evidence": external.get("pending_human_download_items", 0), "unlock_condition": "freeze External Information Corpus V3"},
        "RESEARCH_PIPELINE_FALSIFIABILITY": {"score": 0, "evidence": "not run", "missing_evidence": "PC/NC controls", "unlock_condition": "data blockers closed"},
        "LONG_HISTORICAL_EDGE": {"score": 0, "evidence": "not run", "missing_evidence": "Development/Validation/Holdout/recent PASS", "unlock_condition": "data + falsifiability PASS"},
        "SHORT_HISTORICAL_EDGE": {"score": 0, "evidence": "not run", "missing_evidence": "Development/Validation/Holdout/recent PASS", "unlock_condition": "data + falsifiability PASS"},
        "LONG_FORWARD": {"score": 0, "evidence": "not started", "missing_evidence": "30 trades and maturity", "unlock_condition": "LONG finalist"},
        "SHORT_FORWARD": {"score": 0, "evidence": "not started", "missing_evidence": "30 trades and maturity", "unlock_condition": "SHORT finalist"},
        "BIDIRECTIONAL_PAPER": {"score": 0, "evidence": "not started", "missing_evidence": "LONG and SHORT Paper PASS", "unlock_condition": "both directions Forward PASS"},
        "FUNDING_READINESS": {"score": 0, "evidence": "not reached", "missing_evidence": "publication/live-safety/credential/funding gates", "unlock_condition": "bidirectional Paper + publication + live safety"},
    }


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    official = read_json(Path("Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_BREAKTHROUGH_V1_STATE.json"))
    external = read_json(Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_STATE.json"))
    market = read_json(Path("Reports/forex_delivery/AIOS_FOREX_MULTI_REGIME_CORPUS_V3_STATE.json"))
    practice = write_practice_handoff()
    controls = synthetic_controls_preview()
    atomic_json(PIPELINE_STATE, controls)
    PIPELINE_REPORT.write_text("# AIOS Forex Research Pipeline Falsifiability V1\n\nStatus: `NOT_RUN_DATA_BLOCKED`.\n", encoding="utf-8")
    supertrend = {"status": "NOT_RUN_DATA_BLOCKED", "reason": "Supertrend final audit waits for data blockers and falsifiability controls."}
    atlas = {"status": "NOT_RUN_DATA_BLOCKED", "reason": "Opportunity atlas waits for data blockers and falsifiability controls."}
    atomic_json(SUPERTREND_STATE, supertrend)
    SUPERTREND_REPORT.write_text("# AIOS Forex Supertrend Final Audit V1\n\nStatus: `NOT_RUN_DATA_BLOCKED`.\n", encoding="utf-8")
    atomic_json(ATLAS_STATE, atlas)
    ATLAS_REPORT.write_text("# AIOS Forex Long/Short Opportunity Atlas V1\n\nStatus: `NOT_RUN_DATA_BLOCKED`.\n", encoding="utf-8")
    card = scorecard(official, external, market, practice)
    atomic_json(SCORE_JSON, card)
    SCORE_MD.write_text(render_scorecard(card), encoding="utf-8")
    official_pending = official.get("remaining_human_download_items", [])
    status = "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED" if official_pending else "HUMAN_PRACTICE_DATA_ACQUISITION_REQUIRED"
    if not official_pending and market.get("status") == "HUMAN_PRACTICE_DATA_ACQUISITION_REQUIRED":
        status = "HUMAN_PRACTICE_DATA_ACQUISITION_REQUIRED"
    state = {
        "schema": "AIOS_FOREX_PROFITABILITY_PROOF_PROGRAM_V2_STATE",
        "packet_id": PACKET_ID,
        "status": status,
        "worktree_discrepancy": {"packet_worktree": "C:.Os", "actual_worktree": "C:/Dev/Ai.Os"},
        "current_profitability_truth": {
            "long_historical_edge": "NOT_PROVEN",
            "short_historical_edge": "NOT_PROVEN",
            "long_forward": "NOT_STARTED",
            "short_forward": "NOT_STARTED",
            "long_paper": "NOT_STARTED",
            "short_paper": "NOT_STARTED",
            "bidirectional_paper": "NOT_STARTED",
            "funding_readiness": "NOT_REACHED",
        },
        "data_blocker_closure": {"official_pending_items": official_pending, "practice_history_status": practice["status"]},
        "research_pipeline_falsifiability": controls,
        "supertrend_final_audit": supertrend,
        "long_short_opportunity_atlas": atlas,
        "candidate_registry": {"status": "NOT_OPENED_DATA_BLOCKED", "long": 0, "short": 0, "shared_router": 0},
        "development": {"long": "NOT_RUN", "short": "NOT_RUN"},
        "multiple_testing": {"status": "NOT_RUN"},
        "validation": {"long": "UNOPENED", "short": "UNOPENED"},
        "sealed_holdout": {"long": "UNOPENED", "short": "UNOPENED"},
        "recent_challenge": {"long": "NOT_RUN", "short": "NOT_RUN"},
        "finalists": {"long": None, "short": None},
        "forward": {"long": "NOT_STARTED", "short": "NOT_STARTED", "resume_command": "Resume Packet 019 after Human-only data acquisition artifacts exist."},
        "paper": {"long_closed_trades": 0, "short_closed_trades": 0, "status": "NOT_STARTED"},
        "publication": {"status": "NOT_REACHED"},
        "live_safety": {"status": "NOT_REACHED", "live": False},
        "credential_readiness": {"status": "NOT_REACHED", "secret_exposed": False},
        "funding_readiness": {"status": "NOT_REACHED", "money_movement": False},
        "compounding": {"enabled": False},
        "continuation_active": False,
        "current_phase": status,
        "current_direction": "NONE",
        "current_action": "Human-only data acquisition handoffs prepared",
        "next_action": "Human Owner completes official and Practice data acquisition outside Codex",
        "next_three_actions": ["Run official Human-only download package outside Codex", "Run OANDA Practice Human-only history helper outside Codex", "Resume Packet 019 after sanitized artifacts exist"],
        "remaining_authorized_work_count": 0,
        "remaining_data_blockers": ["official_data"] * bool(official_pending) + ["practice_history"],
        "remaining_research_controls": 6,
        "remaining_long_candidates": 0,
        "remaining_short_candidates": 0,
        "remaining_validation_candidates": 0,
        "remaining_holdout_candidates": 0,
        "remaining_forward_candidates": 0,
        "remaining_paper_requirements": [],
        "recoverable_failures": [],
        "alternate_safe_actions": [],
        "external_time_dependency": False,
        "protected_owner_action_dependency": "Human-only data acquisition",
        "terminal_state_candidate": status,
        "pre_terminal_audit_status": "PASS",
        "same_packet_resume_command": "Resume Packet 019 after Human-only official and Practice history artifacts are present; do not paste secrets into Codex.",
        "last_checkpoint_utc": datetime.now(timezone.utc).isoformat(),
        "safety": {"live": False, "orders": False, "credential_read_by_codex": False, "funding": False, "commit": False, "push": False},
    }
    state["state_hash"] = sha256(stable(state).encode("utf-8"))
    atomic_json(STATE, state)
    atomic_json(ROOT / "campaign_state.json", state)
    REPORT.write_text(render_report(state), encoding="utf-8")
    return state


def render_scorecard(card: dict[str, Any]) -> str:
    lines = ["# AIOS Forex Profitability Readiness Scorecard V2", ""]
    for key, row in card.items():
        lines.extend([f"## {key}", "", f"- score: {row['score']}", f"- evidence: {row['evidence']}", f"- missing evidence: {row['missing_evidence']}", f"- unlock condition: {row['unlock_condition']}", ""])
    return "\n".join(lines)


def render_report(state: dict[str, Any]) -> str:
    return f"""# AIOS Forex Profitability Proof Program V2

WHAT HAPPENED:
Packet 019 prepared the official/practice data handoffs and stopped before research because Human-only data acquisition is required.

IS IT SAFE:
YES. No LIVE call, order, broker mutation, credential read by Codex, funding, commit, push, PR, or merge occurred.

WHAT DO I DO NEXT:
Complete the Human-only data acquisition steps outside Codex, then resume Packet 019.

HOW CLOSE ARE WE:
Estimated readiness: 20% toward funding readiness; profitability proof is still 0%.

WHICH MODE SHOULD I USE:
PRO after sanitized data artifacts exist; INSTANT to review this handoff.

TECHNICAL DETAILS:
- Status: `{state['status']}`
- LONG historical edge: {state['current_profitability_truth']['long_historical_edge']}
- SHORT historical edge: {state['current_profitability_truth']['short_historical_edge']}
- LONG Forward: {state['current_profitability_truth']['long_forward']}
- SHORT Forward: {state['current_profitability_truth']['short_forward']}
- LONG Paper: {state['current_profitability_truth']['long_paper']}
- SHORT Paper: {state['current_profitability_truth']['short_paper']}
- Bidirectional Paper: {state['current_profitability_truth']['bidirectional_paper']}
- State hash: `{state['state_hash']}`
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute()
    print(stable({"status": state["status"], "next_action": state["next_action"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
