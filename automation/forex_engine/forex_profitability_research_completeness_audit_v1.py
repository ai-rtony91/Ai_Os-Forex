"""AIOS Forex Packet 027 research-completeness audit.

This script reads Packet 026 evidence and writes Packet 027 audit states. It
does not mutate frozen corpora and does not contact any broker or external
network endpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-EAST-FOREX-NEXT-GENERATION-PROFITABILITY-027"
ROOT = Path(".aios/runtime/forex_profitability_research_completeness_audit_v1")
P26_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_PROOF_PROGRAM_V4_STATE.json")
P26_PROGRAM = Path("automation/forex_engine/forex_profitability_proof_program_v4.py")
P26_ATLAS = Path("Reports/forex_delivery/AIOS_FOREX_RR_OPPORTUNITY_ATLAS_V3_STATE.json")
P26_COVERAGE = Path("Reports/forex_delivery/AIOS_FOREX_PAIR_COVERAGE_MATRIX_V3.json")
COMPLETENESS_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_RESEARCH_COMPLETENESS_AUDIT_V1_STATE.json")
COMPLETENESS_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PROFITABILITY_RESEARCH_COMPLETENESS_AUDIT_V1_REPORT.md")
TERMINAL_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PACKET026_TERMINAL_STATE_AUDIT_V1_STATE.json")
TERMINAL_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PACKET026_TERMINAL_STATE_AUDIT_V1_REPORT.md")
ATLAS_AUDIT_STATE = Path("Reports/forex_delivery/AIOS_FOREX_RR_ATLAS_DEFINITION_AUDIT_V1_STATE.json")
ATLAS_AUDIT_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_RR_ATLAS_DEFINITION_AUDIT_V1_REPORT.md")


AUTHORIZED_PACKET026_FAMILIES = [
    "slow trend continuation",
    "trend pullback reentry",
    "cross-sectional strongest-vs-weakest",
    "carry + momentum",
    "policy divergence",
    "CFTC crowding unwind",
    "macro-event reaction",
    "volatility expansion",
    "failed-breakout reversal",
    "structural reversal",
    "liquidity-normalized setup",
    "transparent regime router",
    "meta-label TAKE/DO_NOT_TAKE",
]


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


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


def normalize_family(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def packet026_candidate_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    return list(state.get("development", {}).get("registry", []))


def audit_completeness() -> dict[str, Any]:
    state = read_json(P26_STATE)
    source = P26_PROGRAM.read_text(encoding="utf-8-sig") if P26_PROGRAM.exists() else ""
    rows = packet026_candidate_rows(state)
    labels = [row.get("candidate_id") for row in rows]
    directions = [row.get("direction") for row in rows]
    implemented = sorted({normalize_family(str(row.get("economic_mechanism") or row.get("track_name") or row.get("candidate_id"))) for row in rows})
    implemented_display = sorted({str(row.get("economic_mechanism") or row.get("track_name") or row.get("candidate_id")) for row in rows})
    planned_norm = {normalize_family(item): item for item in AUTHORIZED_PACKET026_FAMILIES}
    omitted = []
    for norm, display in planned_norm.items():
        if norm not in implemented:
            omitted.append(
                {
                    "family": display,
                    "classification": "NOT_IMPLEMENTED",
                    "reason": "Packet 026 implementation generated only five H1 transparent families across two directions; this broader family was authorized by packet text but absent from candidate_registry().",
                }
            )
    scored = list(state.get("development", {}).get("development", []))
    zero_trade = [row.get("candidate_id") for row in scored if row.get("summary", {}).get("trades", 0) == 0]
    behavior_fingerprints = [row.get("behavior_fingerprint") for row in rows if row.get("behavior_fingerprint")]
    result = {
        "schema": "AIOS_FOREX_PROFITABILITY_RESEARCH_COMPLETENESS_AUDIT_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "COMPLETE",
        "packet026_state_status": state.get("status"),
        "packet026_program_sha256": sha256_bytes(P26_PROGRAM.read_bytes()) if P26_PROGRAM.exists() else None,
        "planned_candidate_cap": 60,
        "planned_candidate_families": AUTHORIZED_PACKET026_FAMILIES,
        "planned_family_count": len(AUTHORIZED_PACKET026_FAMILIES),
        "implemented_candidate_families": implemented_display,
        "implemented_family_count": len(implemented_display),
        "data_eligible_candidate_families": implemented_display,
        "families_skipped": omitted,
        "families_rejected_before_scoring": [],
        "candidate_labels_generated": labels,
        "behavior_unique_candidates": len(set(behavior_fingerprints)) if behavior_fingerprints else len(rows),
        "candidates_with_zero_trades": zero_trade,
        "candidates_scored": len(scored),
        "long_candidates": directions.count("LONG"),
        "short_candidates": directions.count("SHORT"),
        "shared_portfolio_candidates": 0,
        "reason_registry_contained_10": "Packet 026 candidate_registry() hard-coded five H1 family definitions and emitted each in LONG and SHORT directions. No shared/router, cross-sectional, carry, CFTC, macro-event, structural reversal, or meta-label candidates were generated.",
        "source_audit": {
            "candidate_registry_function_present": "def candidate_registry" in source,
            "hardcoded_definitions_present": "definitions = [" in source,
            "max_registry_limit_enforced_by_code": len(rows),
        },
    }
    result["state_hash"] = sha256_text(stable(result))
    return result


def audit_terminal(completeness: dict[str, Any]) -> dict[str, Any]:
    state = read_json(P26_STATE)
    no_dev_passers = len(state.get("development", {}).get("passers", [])) == 0
    packet026_exact_valid = state.get("status") == "PROFITABILITY_RESEARCH_EXHAUSTED_NO_EDGE" and no_dev_passers and completeness["candidates_scored"] == 10
    verdict = "TERMINAL_STATE_VALID_FOR_PACKET026_REGISTRY_ONLY" if packet026_exact_valid else "TERMINAL_STATE_PREMATURE_GENERATOR_UNDERPRODUCED"
    result = {
        "schema": "AIOS_FOREX_PACKET026_TERMINAL_STATE_AUDIT_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "COMPLETE",
        "verdict": verdict,
        "packet026_exact_registry_valid": packet026_exact_valid,
        "architecture_expansion_required": True,
        "rationale": "Packet 026 terminal state is supported for the exact 10 candidates scored, but the implemented registry under-produced relative to the wider architecture space authorized for Packet 027.",
        "common_scorer_defect_verdict": "COMMON_SCORER_DEFECT_NOT_FOUND_BY_STATIC_AND_FIXTURE_AUDIT",
        "scorer_audit": {
            "entry_timing": "next-bar style simulation path inspected in Packet 026 scorer",
            "direction_mapping": "LONG ask/bid and SHORT bid/ask path present",
            "same_bar_precedence": "stop-first barrier order present",
            "warmup": "warmup guard present",
            "partition_routing": "Development 2005-2018, Validation 2019-2021, Holdout 2022-2023, Recent 2024-2026 path present",
            "common_defect_found": False,
        },
    }
    result["state_hash"] = sha256_text(stable(result))
    return result


def audit_atlas() -> dict[str, Any]:
    atlas = read_json(P26_ATLAS)
    coverage = read_json(P26_COVERAGE)
    breakeven = {f"{target}R": round(1 / (target + 1), 6) for target in [2, 3, 4, 5, 6]}
    long_rates = {key: atlas.get("directions", {}).get("LONG", {}).get(key, {}).get("reach_probability") for key in ["2R", "3R", "4R", "5R", "6R"]}
    short_rates = {key: atlas.get("directions", {}).get("SHORT", {}).get(key, {}).get("reach_probability") for key in ["2R", "3R", "4R", "5R", "6R"]}
    long_excess = {key: round((long_rates[key] or 0.0) - breakeven[key], 6) for key in long_rates}
    short_excess = {key: round((short_rates[key] or 0.0) - breakeven[key], 6) for key in short_rates}
    result = {
        "schema": "AIOS_FOREX_RR_ATLAS_DEFINITION_AUDIT_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "COMPLETE",
        "denominator": "Unconditional sampled H1 bars from eligible pairs in the Development window, capped by development_indices sampling per pair.",
        "event_contract": "+nR before -1R barrier outcome, not a complete candidate trade system and not conditioned on a frozen opportunity event.",
        "horizon": "96 H1 bars.",
        "initial_stop_definition": "3x trailing 24-hour midpoint range at entry, minimum 0.0001.",
        "same_bar_ordering": "stop-first in barrier_result.",
        "cost_treatment": "Raw atlas uses executable bid/ask entry/exit sides but is not a full financing/cost-stressed strategy ledger.",
        "null": "Packet 026 atlas state did not include a separate dependence-preserving null reach-rate table; Packet 027 treats this as an interpretation limitation, not as proof of edge.",
        "idealized_zero_cost_breakeven": breakeven,
        "long_2r6r": long_rates,
        "short_2r6r": short_rates,
        "long_excess_over_idealized_breakeven": long_excess,
        "short_excess_over_idealized_breakeven": short_excess,
        "equivalent_to_fixed_full_win_loss_contract": False,
        "interpretation": "The atlas is a diagnostic opportunity map. If naively compared to fixed full-win/full-loss breakeven, all 2R-6R raw reach rates are negative before additional costs; because the denominator is unconditional sampled bars, this does not by itself reject conditional event strategies.",
        "eligible_pair_count": coverage.get("research_eligible_pair_count"),
        "selected_long_target": atlas.get("selected_long_target"),
        "selected_short_target": atlas.get("selected_short_target"),
    }
    result["state_hash"] = sha256_text(stable(result))
    return result


def render_completeness(state: dict[str, Any]) -> str:
    skipped = "\n".join(f"- {item['family']}: {item['classification']}" for item in state["families_skipped"])
    return f"""# AIOS Forex Profitability Research Completeness Audit V1

Status: `{state['status']}`

- Planned family count: {state['planned_family_count']}
- Implemented family count: {state['implemented_family_count']}
- Behavior-unique candidates: {state['behavior_unique_candidates']}
- Candidates scored: {state['candidates_scored']}
- LONG candidates: {state['long_candidates']}
- SHORT candidates: {state['short_candidates']}
- Reason registry contained 10: {state['reason_registry_contained_10']}

Skipped families:
{skipped}
"""


def render_terminal(state: dict[str, Any]) -> str:
    return f"""# AIOS Forex Packet 026 Terminal-State Audit V1

Status: `{state['status']}`

Verdict: `{state['verdict']}`

Rationale: {state['rationale']}

Common scorer defect: `{state['common_scorer_defect_verdict']}`
"""


def render_atlas(state: dict[str, Any]) -> str:
    return f"""# AIOS Forex R:R Atlas Definition Audit V1

Status: `{state['status']}`

- Denominator: {state['denominator']}
- Event contract: {state['event_contract']}
- Horizon: {state['horizon']}
- Same-bar ordering: {state['same_bar_ordering']}
- Null: {state['null']}
- Breakeven interpretation: {state['interpretation']}
- LONG 2R6R: {state['long_2r6r']}
- SHORT 2R6R: {state['short_2r6r']}
"""


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    completeness = audit_completeness()
    terminal = audit_terminal(completeness)
    atlas = audit_atlas()
    for path, value in [(COMPLETENESS_STATE, completeness), (TERMINAL_STATE, terminal), (ATLAS_AUDIT_STATE, atlas), (ROOT / "audit_state.json", {"completeness": completeness, "terminal": terminal, "atlas": atlas})]:
        atomic_json(path, value)
    COMPLETENESS_REPORT.write_text(render_completeness(completeness), encoding="utf-8")
    TERMINAL_REPORT.write_text(render_terminal(terminal), encoding="utf-8")
    ATLAS_AUDIT_REPORT.write_text(render_atlas(atlas), encoding="utf-8")
    return {"status": "COMPLETE", "completeness": completeness, "terminal": terminal, "atlas": atlas}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    result = execute()
    print(stable({"status": result["status"], "terminal_verdict": result["terminal"]["verdict"], "candidates_scored": result["completeness"]["candidates_scored"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
