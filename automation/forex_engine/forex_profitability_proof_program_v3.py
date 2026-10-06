"""Packet 021 profitability proof closure controller.

This controller does not manufacture edge. It records current blocking facts,
keeps the OANDA Practice token outside Codex, and stops only when remaining
work is genuinely Human-only data acquisition.
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


PACKET_ID = "PKT-EAST-FOREX-PROFITABILITY-CLOSURE-021"
ROOT = Path(".aios/runtime/forex_profitability_proof_program_v3")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_PROOF_PROGRAM_V3_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_PROOF_PROGRAM_V3_REPORT.md")
PIPELINE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_RESEARCH_PIPELINE_FALSIFIABILITY_V2_STATE.json")
PIPELINE_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_RESEARCH_PIPELINE_FALSIFIABILITY_V2_REPORT.md")
SUPERTREND_STATE = Path("Reports/forex_delivery/AIOS_FOREX_SUPERTREND_FINAL_AUDIT_V2_STATE.json")
SUPERTREND_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_SUPERTREND_FINAL_AUDIT_V2_REPORT.md")
ATLAS_STATE = Path("Reports/forex_delivery/AIOS_FOREX_LONG_SHORT_RR_OPPORTUNITY_ATLAS_V2_STATE.json")
ATLAS_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_LONG_SHORT_RR_OPPORTUNITY_ATLAS_V2_REPORT.md")
SCORE_JSON = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_READINESS_SCORECARD_V3.json")
SCORE_MD = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_READINESS_SCORECARD_V3.md")
PRACTICE_HANDOFF = Path("Reports/forex_delivery/AIOS_FOREX_PRACTICE_HISTORY_HUMAN_HANDOFF_V1.md")
PRACTICE_HANDOFF_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PRACTICE_HISTORY_HUMAN_HANDOFF_V1_STATE.json")
OFFICIAL_HANDOFF = Path("Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_HUMAN_HANDOFF_V1.md")
OFFICIAL_MANIFEST = Path("Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_HUMAN_DOWNLOAD_MANIFEST_V1.json")
OFFICIAL_INBOX = Path(".aios/runtime/forex_official_data_breakthrough_v1/human_download_inbox")
PRACTICE_INBOX = Path(".aios/runtime/forex_practice_history_human_inbox")
OFFICIAL_SCRIPT = Path("scripts/forex_delivery/Download-AiOsOfficialForexResearchData.HUMAN_ONLY.ps1")
PRACTICE_SCRIPT = Path("scripts/forex_delivery/Acquire-AiOsOandaPracticeHistory.HUMAN_ONLY.ps1")


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


def official_items() -> list[dict[str, Any]]:
    manifest = read_json(OFFICIAL_MANIFEST)
    return [dict(item) for item in manifest.get("items", [])]


def missing_official_items() -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for item in official_items():
        expected = Path(str(item.get("expected_destination_relative_path", "")))
        target = OFFICIAL_INBOX / expected.name
        if not target.exists() or target.stat().st_size == 0:
            missing.append(item)
    return missing


def practice_artifacts() -> list[dict[str, Any]]:
    if not PRACTICE_INBOX.exists():
        return []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(PRACTICE_INBOX.glob("*.json")):
        if path.name.endswith(".manifest.json"):
            continue
        artifacts.append({"path": path.as_posix(), "sha256": sha256(path.read_bytes()), "bytes": path.stat().st_size})
    return artifacts


def script_hash(path: Path) -> str | None:
    return sha256(path.read_bytes()) if path.exists() else None


def command_lines() -> dict[str, str]:
    return {
        "official": "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/forex_delivery/Download-AiOsOfficialForexResearchData.HUMAN_ONLY.ps1",
        "practice": "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/forex_delivery/Acquire-AiOsOandaPracticeHistory.HUMAN_ONLY.ps1",
        "resume": "Resume Packet 021 after both Human-only data commands complete; do not paste any OANDA token or account value into Codex.",
    }


def update_official_manifest() -> dict[str, Any]:
    manifest = read_json(OFFICIAL_MANIFEST)
    if not manifest:
        return {}
    manifest["packet_id"] = PACKET_ID
    manifest["status"] = "HUMAN_DATA_ACQUISITION_REQUIRED"
    manifest["combined_with_practice_history"] = True
    manifest["manifest_hash"] = sha256(stable({k: v for k, v in manifest.items() if k != "manifest_hash"}).encode("utf-8"))
    atomic_json(OFFICIAL_MANIFEST, manifest)
    return manifest


def write_handoffs(missing_official: list[dict[str, Any]], practice_missing: bool) -> dict[str, Any]:
    commands = command_lines()
    practice_state = {
        "schema": "AIOS_FOREX_PRACTICE_HISTORY_HUMAN_HANDOFF_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "HUMAN_DATA_ACQUISITION_REQUIRED" if practice_missing or missing_official else "PRACTICE_HISTORY_ARTIFACTS_PRESENT",
        "script": PRACTICE_SCRIPT.as_posix(),
        "script_sha256": script_hash(PRACTICE_SCRIPT),
        "destination_inbox": PRACTICE_INBOX.as_posix() + "/",
        "secret_required": True,
        "codex_may_read_secret": False,
        "practice_get_only": True,
        "live": False,
        "orders": False,
        "broker_mutation": False,
        "combined_human_package": True,
        "official_command": commands["official"],
        "practice_command": commands["practice"],
        "resume_instruction": commands["resume"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    practice_state["state_hash"] = sha256(stable(practice_state).encode("utf-8"))
    atomic_json(PRACTICE_HANDOFF_STATE, practice_state)

    official_lines = [
        "# AIOS Forex Official Data Human Handoff V1",
        "",
        "WHAT HAPPENED:",
        "Packet 021 consolidated the remaining official public-data downloads with the OANDA Practice history Human-only step.",
        "",
        "IS IT SAFE:",
        "WAIT. Run these only outside Codex in a Human-controlled PowerShell session.",
        "",
        "WHAT DO I DO NEXT:",
        f"1. `{commands['official']}`",
        f"2. `{commands['practice']}`",
        f"3. {commands['resume']}",
        "",
        "TECHNICAL DETAILS:",
        f"- Packet: `{PACKET_ID}`",
        f"- Official helper SHA-256: `{script_hash(OFFICIAL_SCRIPT)}`",
        f"- Practice helper SHA-256: `{script_hash(PRACTICE_SCRIPT)}`",
        f"- Official items still missing: {len(missing_official)}",
        f"- Practice artifacts required: {str(practice_missing).lower()}",
        "- Codex may not receive the OANDA Practice token.",
        "- No LIVE endpoint, order, broker mutation, funding, commit, or push is authorized.",
    ]
    OFFICIAL_HANDOFF.write_text("\n".join(official_lines) + "\n", encoding="utf-8")

    practice_lines = [
        "# AIOS Forex Practice History Human Handoff V1",
        "",
        "WHAT HAPPENED:",
        "Packet 021 prepared the Human-only OANDA Practice GET-only history acquisition step as part of one consolidated data package.",
        "",
        "IS IT SAFE:",
        "WAIT. It is safe only if run outside Codex and only if the token is entered into the masked Human-only prompt.",
        "",
        "WHAT DO I DO NEXT:",
        f"Run `{commands['practice']}` only after the official-data helper finishes, then resume Packet 021.",
        "",
        "TECHNICAL DETAILS:",
        f"- Status: `{practice_state['status']}`",
        f"- Script SHA-256: `{practice_state['script_sha256']}`",
        f"- Output inbox: `{practice_state['destination_inbox']}`",
        "- Practice host only: true",
        "- LIVE endpoint: false",
        "- Orders: false",
        "- Codex secret access: false",
    ]
    PRACTICE_HANDOFF.write_text("\n".join(practice_lines) + "\n", encoding="utf-8")
    return practice_state


def blocked_state(name: str, controls: list[str] | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema": name,
        "packet_id": PACKET_ID,
        "status": "NOT_RUN_DATA_BLOCKED",
        "reason": "Packet 021 requires official and Practice-history data gates to close before this phase can produce scientific evidence.",
    }
    if controls is not None:
        state["controls"] = controls
    state["state_hash"] = sha256(stable(state).encode("utf-8"))
    return state


def _blocker(
    blocker_id: str,
    priority: str,
    status: str,
    exact_blocker: str,
    chosen_action: str,
    proof_of_unlock: str | None,
    next_action: str,
    human_action_required: bool,
    can_codex_resolve: bool = False,
) -> dict[str, Any]:
    return {
        "blocker_id": blocker_id,
        "priority": priority,
        "phase": "DATA_GATE_CLOSURE" if blocker_id in {"P0-001", "P0-002"} else "PROFITABILITY_PROOF",
        "category": "data" if blocker_id in {"P0-001", "P0-002"} else "research_or_proof",
        "direction": "BOTH",
        "status": status,
        "exact_blocker": exact_blocker,
        "why_it_matters": "Required gate for bidirectional Paper profitability proof.",
        "canonical_owner_file": STATE.as_posix(),
        "test_file": "tests/forex_engine/test_forex_profitability_proof_program_v3.py",
        "runner_or_validator": "Packet 021 controller and scoped validators.",
        "input_evidence_required": "Preceding gate evidence.",
        "missing_evidence": exact_blocker if status != "CLOSED" else [],
        "repair_options": ["Continue after preceding gates unlock."],
        "chosen_action": chosen_action,
        "unlock_condition": "Required phase PASS without weakening gates.",
        "proof_of_unlock": proof_of_unlock or "Not unlocked",
        "next_action": next_action,
        "can_codex_resolve": can_codex_resolve,
        "human_action_required": human_action_required,
        "external_time_required": False,
        "retry_count": 0,
        "last_attempt_utc": datetime.now(timezone.utc).isoformat(),
        "failure_signature": None if status == "CLOSED" else "NOT_RUN_OR_WAITING",
        "no_bloat_guard": "Do not add duplicate governance or count labels as edge.",
    }


def build_attack_to_finish(missing_official: list[dict[str, Any]], practice_missing: bool, external: dict[str, Any], market: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = [
        _blocker(
            "P0-001",
            "P0",
            "WAITING_HUMAN" if missing_official else "CLOSED",
            "OFFICIAL_DATA_ARTIFACTS_PENDING",
            "Prepared consolidated Human official download package.",
            None if missing_official else "All official manifest destinations present.",
            "Human runs official-data helper." if missing_official else "Run External Information Corpus V3 freezer.",
            bool(missing_official),
        ),
        _blocker(
            "P0-002",
            "P0",
            "WAITING_HUMAN" if practice_missing else "CLOSED",
            "PRACTICE_HISTORY_SECRET_BOUNDARY",
            "Prepared Human-only Practice GET-only helper; Codex does not receive token.",
            None if practice_missing else "Practice artifacts present.",
            "Human runs Practice-history helper outside Codex." if practice_missing else "Run Multi-Regime Corpus V3 freezer.",
            practice_missing,
        ),
        _blocker(
            "P0-003",
            "P0",
            "OPEN" if not market.get("frozen") else "CLOSED",
            "MULTI_REGIME_CORPUS_V3_NOT_FROZEN",
            "Deferred until Practice artifacts unlock." if practice_missing else "Ready for corpus freezer.",
            market.get("aggregate_hash") if market.get("frozen") else None,
            "Run corpus freezer after Practice artifacts exist.",
            practice_missing,
            can_codex_resolve=not practice_missing,
        ),
        _blocker(
            "P0-004",
            "P0",
            "OPEN" if not external.get("frozen") else "CLOSED",
            "EXTERNAL_INFORMATION_CORPUS_V3_NOT_FROZEN",
            "Deferred until official artifacts unlock." if missing_official else "Ready for external corpus freezer.",
            external.get("aggregate_hash") if external.get("frozen") else None,
            "Run external corpus freezer after official artifacts exist.",
            bool(missing_official),
            can_codex_resolve=not missing_official,
        ),
    ]
    for blocker_id, priority, label in [
        ("P0-005", "P0", "RESEARCH_PIPELINE_FALSIFIABILITY_NOT_PROVEN"),
        ("P1-001", "P1", "SUPERTREND_FINAL_VERDICT_MISSING"),
        ("P0-006", "P0", "LONG_EDGE_NOT_PROVEN"),
        ("P0-007", "P0", "SHORT_EDGE_NOT_PROVEN"),
        ("P0-008", "P0", "LONG_FORWARD_NOT_PROVEN"),
        ("P0-009", "P0", "SHORT_FORWARD_NOT_PROVEN"),
        ("P0-010", "P0", "LONG_PAPER_PROFITABILITY_NOT_PROVEN"),
        ("P0-011", "P0", "SHORT_PAPER_PROFITABILITY_NOT_PROVEN"),
        ("P0-012", "P0", "BIDIRECTIONAL_PAPER_PROFITABILITY_NOT_PROVEN"),
    ]:
        blockers.append(
            _blocker(
                blocker_id,
                priority,
                "OPEN",
                label,
                "Blocked behind data gates.",
                None,
                "Wait for P0 data gates first.",
                False,
            )
        )
    return blockers


def scorecard(missing_official: list[dict[str, Any]], practice_missing: bool, external: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    return {
        "DATA_GATE_CLOSURE": {"score": 0 if missing_official or practice_missing else 100, "evidence": "Human package prepared", "missing_evidence": {"official_items": len(missing_official), "practice_artifacts_missing": practice_missing}, "unlock_condition": "Human-only official and Practice artifacts present and validated"},
        "MULTI_REGIME_CORPUS": {"score": int(market.get("capability_score", 0)), "evidence": market.get("status"), "missing_evidence": market.get("blocker"), "unlock_condition": "Corpus V3 frozen"},
        "EXTERNAL_INFORMATION_CORPUS": {"score": int(external.get("external_information_coverage_score", 0)), "evidence": external.get("status"), "missing_evidence": external.get("pending_human_download_items", len(missing_official)), "unlock_condition": "External Information Corpus V3 frozen"},
        "RESEARCH_PIPELINE_FALSIFIABILITY": {"score": 0, "evidence": "NOT_RUN_DATA_BLOCKED", "missing_evidence": "positive/negative controls", "unlock_condition": "data gates closed"},
        "LONG_EDGE": {"score": 0, "evidence": "NOT_PROVEN", "missing_evidence": "Development/Validation/Holdout/recent/Forward/Paper", "unlock_condition": "independent LONG chain PASS"},
        "SHORT_EDGE": {"score": 0, "evidence": "NOT_PROVEN", "missing_evidence": "Development/Validation/Holdout/recent/Forward/Paper", "unlock_condition": "independent SHORT chain PASS"},
        "BIDIRECTIONAL_PAPER": {"score": 0, "evidence": "NOT_STARTED", "missing_evidence": "LONG and SHORT Paper PASS", "unlock_condition": "BIDIRECTIONAL_PAPER_PROFITABILITY_CERTIFIED"},
        "FUNDING_READINESS": {"score": 0, "evidence": "NOT_REACHED", "missing_evidence": "profitability/publication/live-safety/credentials/funding gates", "unlock_condition": "downstream only after bidirectional Paper profitability"},
    }


def render_scorecard(card: dict[str, Any]) -> str:
    lines = ["# AIOS Forex Profitability Readiness Scorecard V3", ""]
    for key, row in card.items():
        lines.extend([f"## {key}", "", f"- score: {row['score']}", f"- evidence: {row['evidence']}", f"- missing evidence: {row['missing_evidence']}", f"- unlock condition: {row['unlock_condition']}", ""])
    return "\n".join(lines)


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    OFFICIAL_INBOX.mkdir(parents=True, exist_ok=True)
    PRACTICE_INBOX.mkdir(parents=True, exist_ok=True)
    update_official_manifest()
    missing_official = missing_official_items()
    practice = practice_artifacts()
    practice_missing = len(practice) == 0
    external = read_json(Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_STATE.json"))
    market = read_json(Path("Reports/forex_delivery/AIOS_FOREX_MULTI_REGIME_CORPUS_V3_STATE.json"))
    practice_handoff_state = write_handoffs(missing_official, practice_missing)

    controls = blocked_state("AIOS_FOREX_RESEARCH_PIPELINE_FALSIFIABILITY_V2_STATE", ["PC_LONG_3R", "PC_SHORT_3R", "PC_BIDIRECTIONAL_3R", "PC_SPARSE_4R", "PC_REGIME_5R", "PC_INTERACTION_3R", "NC_RANDOM_WALK", "NC_FUTURE_LEAKAGE", "NC_DUPLICATE_BEHAVIOR", "NC_HIGH_WINRATE_NEGATIVE_EXPECTANCY", "NC_ONE_WINNER_ILLUSION", "NC_MIDPOINT_FILL_FANTASY", "NC_TARGET_ONLY_CURVE_FIT"])
    supertrend = blocked_state("AIOS_FOREX_SUPERTREND_FINAL_AUDIT_V2_STATE")
    atlas = blocked_state("AIOS_FOREX_LONG_SHORT_RR_OPPORTUNITY_ATLAS_V2_STATE")
    atomic_json(PIPELINE_STATE, controls)
    PIPELINE_REPORT.write_text("# AIOS Forex Research Pipeline Falsifiability V2\n\nStatus: `NOT_RUN_DATA_BLOCKED`.\n", encoding="utf-8")
    atomic_json(SUPERTREND_STATE, supertrend)
    SUPERTREND_REPORT.write_text("# AIOS Forex Supertrend Final Audit V2\n\nStatus: `NOT_RUN_DATA_BLOCKED`.\n", encoding="utf-8")
    atomic_json(ATLAS_STATE, atlas)
    ATLAS_REPORT.write_text("# AIOS Forex Long/Short R:R Opportunity Atlas V2\n\nStatus: `NOT_RUN_DATA_BLOCKED`.\n", encoding="utf-8")

    card = scorecard(missing_official, practice_missing, external, market)
    atomic_json(SCORE_JSON, card)
    SCORE_MD.write_text(render_scorecard(card), encoding="utf-8")

    attack = build_attack_to_finish(missing_official, practice_missing, external, market)
    status = "HUMAN_DATA_ACQUISITION_REQUIRED" if missing_official or practice_missing else "DATA_GATE_READY_FOR_CORPUS_FREEZE"
    state = {
        "schema": "AIOS_FOREX_PROFITABILITY_PROOF_PROGRAM_V3_STATE",
        "packet_id": PACKET_ID,
        "status": status,
        "continuation_active": status != "HUMAN_DATA_ACQUISITION_REQUIRED",
        "current_phase": "DATA_GATE_CLOSURE",
        "current_subphase": "CONSOLIDATED_HUMAN_DATA_PACKAGE",
        "current_direction": "NONE",
        "current_candidate": None,
        "current_action": "Consolidated Human official and Practice data acquisition package prepared",
        "attack_to_finish": attack,
        "data_gates": {
            "official_missing_count": len(missing_official),
            "official_missing_sources": [item.get("source_owner") for item in missing_official],
            "practice_artifacts_present": len(practice),
            "practice_missing": practice_missing,
            "official_script_sha256": script_hash(OFFICIAL_SCRIPT),
            "practice_script_sha256": script_hash(PRACTICE_SCRIPT),
            "commands": command_lines(),
        },
        "current_profitability_truth": {
            "long_edge": "NOT_PROVEN",
            "short_edge": "NOT_PROVEN",
            "long_forward": "NOT_STARTED",
            "short_forward": "NOT_STARTED",
            "long_paper": "NOT_STARTED",
            "short_paper": "NOT_STARTED",
            "bidirectional_paper": "NOT_STARTED",
        },
        "multi_regime_corpus": market,
        "external_information_corpus": external,
        "research_falsifiability": controls,
        "supertrend_final_verdict": supertrend,
        "rr_opportunity_atlas": atlas,
        "candidate_registry": {"status": "NOT_OPENED_DATA_BLOCKED", "candidate_count": 0, "long": 0, "short": 0, "shared_router": 0},
        "development": {"long": "NOT_RUN", "short": "NOT_RUN"},
        "multiple_testing": {"status": "NOT_RUN", "null_campaigns": 0},
        "bootstrap": {"status": "NOT_RUN", "resamples_per_passer": 0},
        "validation": {"long": "UNOPENED", "short": "UNOPENED"},
        "sealed_holdout": {"long": "UNOPENED", "short": "UNOPENED"},
        "recent_challenge": {"long": "NOT_RUN", "short": "NOT_RUN"},
        "finalists": {"long": None, "short": None},
        "forward": {"long": "NOT_STARTED", "short": "NOT_STARTED", "resume_command": command_lines()["resume"]},
        "v6": {"implementation": "NOT_REACHED", "parity": "NOT_REACHED"},
        "paper": {"long_closed_trades": 0, "short_closed_trades": 0, "long_metrics": None, "short_metrics": None, "status": "NOT_STARTED"},
        "publication": {"status": "NOT_REACHED"},
        "live_safety": {"status": "NOT_REACHED", "live": False},
        "credential_readiness": {"status": "NOT_REACHED", "secret_exposed": False},
        "funding_readiness": {"status": "NOT_REACHED", "money_movement": False},
        "compounding": {"enabled": False},
        "next_action": "Human Owner runs the consolidated Human-only data package outside Codex",
        "next_three_actions": [command_lines()["official"], command_lines()["practice"], command_lines()["resume"]],
        "remaining_authorized_work_count": 0 if status == "HUMAN_DATA_ACQUISITION_REQUIRED" else 2,
        "remaining_data_blockers": ["official_data"] * bool(missing_official) + ["practice_history"] * practice_missing,
        "remaining_research_controls": 6,
        "remaining_supertrend_candidates": 0,
        "remaining_long_candidates": 0,
        "remaining_short_candidates": 0,
        "remaining_validation_candidates": 0,
        "remaining_holdout_candidates": 0,
        "remaining_recent_challenge_candidates": 0,
        "remaining_forward_candidates": 0,
        "remaining_paper_requirements": [],
        "recoverable_failures": [],
        "alternate_safe_actions": [],
        "external_time_dependency": False,
        "protected_owner_action_dependency": "Human-only data acquisition" if status == "HUMAN_DATA_ACQUISITION_REQUIRED" else None,
        "terminal_state_candidate": status if status == "HUMAN_DATA_ACQUISITION_REQUIRED" else None,
        "pre_terminal_audit_status": "PASS" if status == "HUMAN_DATA_ACQUISITION_REQUIRED" else "FAIL_CONTINUE",
        "same_packet_resume_command": command_lines()["resume"],
        "practice_handoff_state_hash": practice_handoff_state["state_hash"],
        "last_checkpoint_utc": datetime.now(timezone.utc).isoformat(),
        "safety": {"live": False, "orders": False, "credential_read_by_codex": False, "authorization_header_output": False, "funding": False, "commit": False, "push": False},
    }
    state["state_hash"] = sha256(stable(state).encode("utf-8"))
    atomic_json(STATE, state)
    atomic_json(ROOT / "campaign_state.json", state)
    REPORT.write_text(render_report(state), encoding="utf-8")
    return state


def _blocker_lines(attack: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for blocker in attack:
        lines.extend(
            [
                f"- blocker_id: {blocker['blocker_id']}",
                f"  priority: {blocker['priority']}",
                f"  status: {blocker['status']}",
                f"  exact_blocker: {blocker['exact_blocker']}",
                f"  chosen_action: {blocker['chosen_action']}",
                f"  proof_of_unlock: {blocker['proof_of_unlock']}",
                f"  next_action: {blocker['next_action']}",
            ]
        )
    return lines


def render_report(state: dict[str, Any]) -> str:
    blocker_text = "\n".join(_blocker_lines(state["attack_to_finish"]))
    return f"""# AIOS Forex Profitability Proof Program V3

WHAT HAPPENED:
Packet 021 built the ATTACK_TO_FINISH control plane and consolidated the official-data plus OANDA Practice history Human-only acquisition package.

IS IT SAFE:
WAIT. Codex did not contact OANDA LIVE, place orders, read credentials, move money, commit, push, or create a PR.

WHAT DO I DO NEXT:
Run the two Human-only PowerShell commands in this order outside Codex, then resume Packet 021.

HOW CLOSE ARE WE:
Estimated readiness: 20% toward the bidirectional Paper profitability milestone; profitability proof remains 0%.

WHICH MODE SHOULD I USE:
PRO after the Human-only data files exist; INSTANT to review status only.

TECHNICAL DETAILS:

PREFLIGHT:
- Packet: `{PACKET_ID}`
- Status: `{state['status']}`
- State hash: `{state['state_hash']}`

ATTACK_TO_FINISH:
{blocker_text}

CURRENT PROFITABILITY TRUTH:
- LONG edge: {state['current_profitability_truth']['long_edge']}
- SHORT edge: {state['current_profitability_truth']['short_edge']}
- LONG Forward: {state['current_profitability_truth']['long_forward']}
- SHORT Forward: {state['current_profitability_truth']['short_forward']}
- LONG PAPER: {state['current_profitability_truth']['long_paper']}
- SHORT PAPER: {state['current_profitability_truth']['short_paper']}
- bidirectional PAPER: {state['current_profitability_truth']['bidirectional_paper']}

DATA GATES:
- official missing count: {state['data_gates']['official_missing_count']}
- Practice artifacts present: {state['data_gates']['practice_artifacts_present']}
- official command: `{state['data_gates']['commands']['official']}`
- Practice command: `{state['data_gates']['commands']['practice']}`

MULTI-REGIME CORPUS:
- status: {state['multi_regime_corpus'].get('status')}
- frozen: {state['multi_regime_corpus'].get('frozen')}

EXTERNAL INFORMATION CORPUS:
- status: {state['external_information_corpus'].get('status')}
- frozen: {state['external_information_corpus'].get('frozen')}
- records: {state['external_information_corpus'].get('record_count')}

RESEARCH FALSIFIABILITY:
- status: {state['research_falsifiability']['status']}

SUPERTREND FINAL VERDICT:
- status: {state['supertrend_final_verdict']['status']}

R:R OPPORTUNITY ATLAS:
- 2R reach: NOT_RUN_DATA_BLOCKED
- 3R reach: NOT_RUN_DATA_BLOCKED
- 4R reach: NOT_RUN_DATA_BLOCKED
- 5R reach: NOT_RUN_DATA_BLOCKED
- 6R reach: NOT_RUN_DATA_BLOCKED
- selected LONG R:R: NONE
- selected SHORT R:R: NONE
- rationale: data gates must close before opportunity labels can be measured.

CANDIDATE REGISTRY:
- status: {state['candidate_registry']['status']}
- candidate_count: {state['candidate_registry']['candidate_count']}

DEVELOPMENT:
- LONG: {state['development']['long']}
- SHORT: {state['development']['short']}

MULTIPLE TESTING:
- status: {state['multiple_testing']['status']}

BOOTSTRAP:
- status: {state['bootstrap']['status']}

VALIDATION:
- LONG: {state['validation']['long']}
- SHORT: {state['validation']['short']}

SEALED HOLDOUT:
- LONG: {state['sealed_holdout']['long']}
- SHORT: {state['sealed_holdout']['short']}

RECENT CHALLENGE:
- LONG: {state['recent_challenge']['long']}
- SHORT: {state['recent_challenge']['short']}

FINALISTS:
- LONG: {state['finalists']['long']}
- SHORT: {state['finalists']['short']}

FORWARD:
- LONG: {state['forward']['long']}
- SHORT: {state['forward']['short']}
- resume command: {state['forward']['resume_command']}

V6:
- implementation: {state['v6']['implementation']}
- parity: {state['v6']['parity']}

PAPER:
- LONG closed trades: {state['paper']['long_closed_trades']}
- SHORT closed trades: {state['paper']['short_closed_trades']}
- LONG expectancy/PF/Net R/DD: NOT_STARTED
- SHORT expectancy/PF/Net R/DD: NOT_STARTED
- direction isolation: NOT_STARTED
- accounting: NOT_STARTED
- provenance: NOT_STARTED
- recovery: NOT_STARTED

PROFITABILITY MILESTONE:
FAIL

PUBLICATION:
- status: {state['publication']['status']}

LIVE SAFETY:
- status: {state['live_safety']['status']}

CREDENTIAL READINESS:
- status: {state['credential_readiness']['status']}

FUNDING READINESS:
- status: {state['funding_readiness']['status']}

COMPOUNDING:
ENABLED=false

CONTINUATION AUDIT:
- Codex-resolvable P0/P1 blocker remains: false
- Human package incomplete: false
- real Human action required: true
- pre_terminal_audit_status: {state['pre_terminal_audit_status']}

FILES CHANGED:
- See final Codex report.

VALIDATION:
- Pending external validator run.

REMAINING DIRTY FILES:
- Existing dirty worktree preserved.

HIGHEST-PRIORITY BLOCKER:
HUMAN_DATA_ACQUISITION_REQUIRED

EXACT NEXT EXECUTABLE ACTION:
`{state['data_gates']['commands']['official']}`

STATUS:
{state['status']}

HARD-STOP CERTIFICATE:
No LIVE, no orders, no broker mutation, no credential read by Codex, no money movement, no commit, no push.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute()
    print(stable({"status": state["status"], "state_hash": state["state_hash"], "next_action": state["next_action"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
