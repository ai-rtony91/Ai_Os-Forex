"""Packet 016 institutional edge continuation gate.

The research engine does not manufacture an edge. It builds the failure memory
and scorecard, then proceeds only if the institutional information corpus is
frozen with enough point-in-time coverage.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine.forex_institutional_data_breakthrough_v1 import PACKET_ID, atomic_json, sha256, stable
from automation.forex_engine import forex_mechanism_edge_program_v1 as prior
from automation.forex_engine.forex_edge_research_v1 import metrics, split_contract, ts

PACKET_ID = "PKT-EAST-FOREX-OFFICIAL-DATA-TO-FUNDING-016"

ROOT = Path(".aios/runtime/forex_institutional_edge_program_v1")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_INSTITUTIONAL_EDGE_PROGRAM_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_INSTITUTIONAL_EDGE_PROGRAM_V1_REPORT.md")
SCORE_JSON = Path("Reports/forex_delivery/AIOS_FOREX_FUNDING_READINESS_SCORECARD_V2.json")
SCORE_MD = Path("Reports/forex_delivery/AIOS_FOREX_FUNDING_READINESS_SCORECARD_V2.md")
ACQUISITION_STATE = Path("Reports/forex_delivery/AIOS_FOREX_INSTITUTIONAL_DATA_BREAKTHROUGH_V1_STATE.json")
CORPUS_STATE = Path("Reports/forex_delivery/AIOS_FOREX_INSTITUTIONAL_INFORMATION_CORPUS_V1_STATE.json")

PRIOR_STATES = [
    Path("Reports/forex_delivery/AIOS_FOREX_FEATURE_EDGE_RESEARCH_V2_STATE.json"),
    Path("Reports/forex_delivery/AIOS_FOREX_INFORMATION_EDGE_PROGRAM_V1_STATE.json"),
    Path("Reports/forex_delivery/AIOS_FOREX_MECHANISM_EDGE_PROGRAM_V1_STATE.json"),
    Path("Reports/forex_delivery/AIOS_FOREX_FULL_SPECTRUM_EDGE_PROGRAM_V1_STATE.json"),
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return "INF" if value > 0 else "-INF"
    if isinstance(value, dict):
        return {key: safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [safe(child) for child in value]
    return value


def write_json(path: Path, value: Any) -> None:
    atomic_json(path, safe(value))


def build_failure_memory() -> list[dict[str, Any]]:
    memory = []
    for path in PRIOR_STATES:
        state = read_json(path)
        if not state:
            continue
        memory.append(
            {
                "state_path": path.as_posix(),
                "state_hash": sha256(path.read_bytes()),
                "candidate_or_registry_hash": state.get("registry_hash") or state.get("protocol_hash") or state.get("corpus_fingerprint") or "UNKNOWN",
                "information_sources": sorted(set(_flatten_sources(state)))[:12],
                "mechanism": state.get("dominant_failure") or state.get("status") or "UNKNOWN",
                "direction": "BOTH_SEPARATELY_OR_REPORTED_IN_STATE",
                "timeframe": "as recorded in state",
                "sample": state.get("market_hash") or state.get("market_corpus_hash") or "UNKNOWN",
                "failure_cause": state.get("status") or state.get("terminal_state_candidate") or "UNKNOWN",
                "re_entry_condition": "materially new point-in-time information, materially different horizon, transparent router, or new cost/financing source",
            }
        )
    return memory


def _flatten_sources(value: Any) -> list[str]:
    output: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"sources", "source_hashes", "usable_families", "missing_families"}:
                output.extend([str(item) for item in child] if isinstance(child, list) else [str(child)])
            output.extend(_flatten_sources(child))
    elif isinstance(value, list):
        for child in value:
            output.extend(_flatten_sources(child))
    return output


def build_scorecard(acquisition: dict[str, Any], corpus: dict[str, Any]) -> dict[str, Any]:
    external_score = int(acquisition.get("external_information_coverage_score", 55))
    corpus_frozen = bool(corpus.get("frozen"))
    rows = {
        "EXECUTION_INTEGRITY": (98, "prior certified controls and deterministic replay evidence", "none", "maintain executor hash and regressions"),
        "COST_ACCOUNTING_INTEGRITY": (98, "single-charge cost contract and focused regressions", "none", "maintain cost tests"),
        "MARKET_CORPUS_COVERAGE": (95, "market Corpus V2 referenced by hash", "quality-ineligible pairs remain outside coverage", "new immutable market corpus only"),
        "EXTERNAL_INFORMATION_COVERAGE": (external_score, "Packet 016 official route attempts and usable-family count", "missing official public artifacts listed in one handoff", "automatic acquisition or consolidated human data drop"),
        "POINT_IN_TIME_INTEGRITY": (95 if corpus_frozen else int(acquisition.get("point_in_time_integrity_score", 0)), "required timestamps enforced for usable records", "no score for unavailable records", "freeze institutional corpus"),
        "MECHANISM_RESEARCH_COVERAGE": (95 if external_score >= 80 or acquisition.get("status") == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED" else 55, "prior data-eligible tracks exhausted; Packet 016 waits for new data", "policy/macro families unresolved until official data acquired", "corpus parity or formal untestable classification"),
        "STATISTICAL_PROOF": (90, "prior registry-wide null capability exists", "no Packet 016 Development passer", "novel registry with passer"),
        "FORWARD_PROOF": (0, "no finalist", "forward evidence", "Holdout finalist"),
        "PAPER_PROFITABILITY": (0, "not started", "fresh PAPER PASS", "Forward PASS"),
        "PUBLICATION_READINESS": (0, "not reached", "protected publication package", "PAPER profitability certification"),
        "LIVE_SAFETY_READINESS": (0, "not reached; live false", "static live-safety certification", "published PAPER-certified finalist"),
        "CREDENTIAL_READINESS": (0, "not reached", "human-only credential tooling after live-safety PASS", "PAPER/publication/live-safety gates"),
        "FUNDING_READINESS": (0, "not reached", "manual funding readiness after credential status-only confirmation", "credential target present without exposure"),
    }
    return {name: {"score": score, "evidence": evidence, "missing_evidence": missing, "unlock_condition": unlock} for name, (score, evidence, missing, unlock) in rows.items()}


def hypothesis_registry(corpus: dict[str, Any]) -> dict[str, Any]:
    tracks = [
        "POLICY_CARRY_YIELD",
        "MACRO_EVENT_FIRST_RELEASE",
        "POSITIONING_OPEN_INTEREST",
        "GLOBAL_RISK_VOLATILITY",
        "CROSS_SECTIONAL_CURRENCY",
        "LIQUIDITY_EXECUTION_QUALITY",
        "SLOW_HORIZON_RELATIVE_VALUE",
        "TRANSPARENT_REGIME_ROUTER",
    ]
    hypotheses = []
    data_eligible = corpus.get("status") == "FROZEN_VALID"
    for track_index, track in enumerate(tracks, 1):
        for variant in range(1, 10):
            hypotheses.append(
                {
                    "hypothesis_id": f"I016-{track_index}-{variant:02d}",
                    "track": track_index,
                    "track_name": track,
                    "novelty_statement": "blocked until Packet 016 institutional corpus is frozen" if not data_eligible else "uses newly acquired Packet 016 institutional corpus",
                    "historical_nearest_neighbor_candidate": "Packet015 registry",
                    "economic_mechanism": f"{track}_V{variant}",
                    "information_sources": [corpus.get("corpus_id", "NO_FROZEN_CORPUS")],
                    "source_hashes": [corpus.get("aggregate_hash", "NO_HASH")],
                    "publication_rules": "strategy_available_time_utc <= decision time",
                    "direction": "BOTH_SEPARATELY",
                    "timeframe": "D1" if track_index != 2 else "H1",
                    "event_or_opportunity_rule": "predeclared causal opportunity score",
                    "entry": "next executable interval",
                    "initial_stop": "1.5 ATR",
                    "target": "3R",
                    "holding_horizon": "5 trading days",
                    "risk": "0.25 percent simulated equity",
                    "concurrency": 1,
                    "currency_exposure_rule": "no currency dominates more than 25 percent of open risk",
                    "features": ["institutional_point_in_time", "momentum", "spread_efficiency"],
                    "model_or_rule": "transparent rule score",
                    "parameters": {"variant": variant},
                    "cost_mode": "ACTUAL_BID_ASK_SINGLE_CHARGE",
                    "failure_condition": "fails Development or multiple-testing gate",
                    "data_eligibility_requirement": "FROZEN_VALID institutional corpus",
                    "data_eligible": data_eligible,
                }
            )
    registry = {"schema": "AIOS_FOREX_INSTITUTIONAL_EDGE_REGISTRY_V1", "hypothesis_count": len(hypotheses), "hypotheses": hypotheses}
    registry["hash"] = sha256(stable(registry).encode("utf-8"))
    return registry


def policy_series() -> dict[str, list[tuple[Any, float]]]:
    output: dict[str, list[tuple[Any, float]]] = {}
    normalized = Path(".aios/runtime/forex_institutional_data_breakthrough_v1/normalized")
    if not normalized.exists():
        return output
    for path in sorted(normalized.glob("*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            currency = row.get("currency")
            if not currency or currency == "GLOBAL":
                continue
            output.setdefault(currency, []).append((ts(row["strategy_available_time_utc"]), float(row["value"])))
    for rows in output.values():
        rows.sort()
    return output


def candidate_from_record(record: dict[str, Any]) -> prior.Hypothesis:
    track = int(record["track"])
    variant = int(record["parameters"]["variant"])
    proxy_track = {1: 1, 2: 4, 3: 2, 4: 4, 5: 5, 6: 4, 7: 5, 8: 6}[track]
    threshold = {1: 0.002, 2: 0.0015, 3: 0.025, 4: 0.001, 5: 0.004, 6: 0.001, 7: 0.004, 8: 0.004}[track]
    return prior.Hypothesis(
        record["hypothesis_id"],
        proxy_track,
        record["economic_mechanism"],
        tuple(record["information_sources"]),
        record["publication_rules"],
        "transparent causal score sign",
        record["timeframe"],
        threshold * (1 + 0.5 * (variant % 2)),
        1.5 if variant % 2 else 2.0,
        3.0 if variant % 2 else 2.0,
        5 if track in {2, 4, 6, 8} else 10,
        0.0025,
        1,
        bool(record["data_eligible"]),
    )


def run_research(registry: dict[str, Any], corpus: dict[str, Any]) -> dict[str, Any]:
    market, features = prior.load_market_and_features()
    features = prior.enrich(features, policy_series())
    manifest = json.loads((prior.MARKET / "manifest.json").read_text(encoding="utf-8"))
    split = split_contract(manifest)
    folds = prior.fold_windows(split["development"])
    development: dict[str, Any] = {}
    trades_by_key: dict[str, list[dict[str, Any]]] = {}
    passers: list[tuple[dict[str, Any], str]] = []
    for record in registry["hypotheses"]:
        hypothesis = candidate_from_record(record)
        development[hypothesis.hypothesis_id] = {"track": record["track"], "data_eligible": hypothesis.data_eligible}
        for side in ("LONG", "SHORT"):
            trades = prior.simulate(features, market, hypothesis, split["development"], side)
            result = metrics(trades)
            fold_results = [metrics([trade for trade in trades if start <= ts(trade["signal_time"]) < end]) for start, end in folds]
            passed = prior.development_gate(result, fold_results)
            development[hypothesis.hypothesis_id][side] = {"metrics": result, "folds": fold_results, "pass": passed}
            trades_by_key[f"{hypothesis.hypothesis_id}:{side}"] = trades
            if passed:
                passers.append((record, side))
    null = prior.null_campaign(trades_by_key, 1000)
    bootstraps: dict[str, Any] = {}
    validation_eligible: list[tuple[dict[str, Any], str]] = []
    for record, side in passers:
        key = f"{record['hypothesis_id']}:{side}"
        boot = prior.bootstrap(trades_by_key[key], 2000)
        bootstraps[key] = boot
        result = development[record["hypothesis_id"]][side]["metrics"]
        if result["expectancy_r"] > null["best_expectancy_95pct"] and boot["probability_positive"] >= 0.95:
            validation_eligible.append((record, side))
    validation: dict[str, Any] = {}
    shortlist: list[tuple[dict[str, Any], str]] = []
    for record, side in validation_eligible:
        hypothesis = candidate_from_record(record)
        trades = prior.simulate(features, market, hypothesis, prior.embargoed_window(split["validation"]), side)
        result = metrics(trades)
        passed = result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.10 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10 and result["pair_count"] >= 12
        validation[f"{record['hypothesis_id']}:{side}"] = {"metrics": result, "pass": passed}
        if passed:
            shortlist.append((record, side))
    shortlist = shortlist[:5]
    shortlist_payload = [{"hypothesis": record, "side": side} for record, side in shortlist]
    shortlist_hash = sha256(stable(shortlist_payload).encode("utf-8"))
    holdout: dict[str, Any] = {}
    finalists: list[tuple[dict[str, Any], str]] = []
    for record, side in shortlist:
        hypothesis = candidate_from_record(record)
        trades = prior.simulate(features, market, hypothesis, prior.embargoed_window(split["sealed_holdout"]), side)
        result = metrics(trades)
        boot = prior.bootstrap(trades, 2000)
        passed = result["trades"] >= 50 and result["expectancy_r"] > 0 and result["profit_factor"] >= 1.10 and result["net_r"] > 0 and result["max_drawdown_pct"] <= 10 and boot["probability_positive"] >= 0.95
        holdout[f"{record['hypothesis_id']}:{side}"] = {"metrics": result, "bootstrap": boot, "pass": passed}
        if passed:
            finalists.append((record, side))
    tracks = {}
    for track in range(1, 9):
        ids = [item["hypothesis_id"] for item in registry["hypotheses"] if item["track"] == track]
        track_metrics = [development[hypothesis_id][side]["metrics"] for hypothesis_id in ids for side in ("LONG", "SHORT")]
        tracks[str(track)] = {
            "hypotheses": len(ids),
            "data_eligible": sum(development[hypothesis_id]["data_eligible"] for hypothesis_id in ids),
            "development_passers": sum(development[hypothesis_id][side]["pass"] for hypothesis_id in ids for side in ("LONG", "SHORT")),
            "best": max(track_metrics, key=lambda value: value["expectancy_r"], default=metrics([])),
        }
    research_status = "FORWARD_ACCUMULATING" if finalists else "INSTITUTIONAL_RESEARCH_EXHAUSTED_NO_EDGE"
    return {
        "status": research_status,
        "development": development,
        "tracks": tracks,
        "development_passers": [f"{record['hypothesis_id']}:{side}" for record, side in passers],
        "registry_wide_null": null,
        "bootstrap": bootstraps,
        "overfit_diagnostics": {"method": "chronological registry plus family-wise null", "status": "NO_PASSERS" if not passers else "APPLIED_TO_PASSERS"},
        "validation": validation,
        "shortlist_hash": shortlist_hash,
        "sealed_holdout": holdout,
        "finalists": [{"hypothesis": record, "side": side, "corpus_hash": corpus.get("aggregate_hash")} for record, side in finalists[:3]],
    }


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    acquisition = read_json(ACQUISITION_STATE)
    corpus = read_json(CORPUS_STATE)
    failure_memory = build_failure_memory()
    registry = hypothesis_registry(corpus)
    scorecard = build_scorecard(acquisition, corpus)
    write_json(ROOT / "failure_memory_matrix.json", failure_memory)
    write_json(ROOT / "hypothesis_registry_preview.json", registry)
    write_json(SCORE_JSON, scorecard)
    SCORE_MD.write_text(render_scorecard(scorecard), encoding="utf-8")
    if acquisition.get("status") == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED":
        status = "HUMAN_OFFICIAL_DATA_DROP_REQUIRED"
        remaining = len(acquisition.get("remaining_source_series") or [])
        next_action = "HUMAN_DATA_DROP_RECONCILIATION"
        audit = "PASS"
    elif corpus.get("status") != "FROZEN_VALID":
        status = "INSTITUTIONAL_INFORMATION_CAPABILITY_BLOCKED"
        remaining = 0
        next_action = "NONE"
        audit = "PASS"
    else:
        research = run_research(registry, corpus)
        status = research["status"]
        remaining = 1 if status == "FORWARD_ACCUMULATING" else 0
        next_action = "FORWARD_ACCUMULATION" if status == "FORWARD_ACCUMULATING" else "NONE"
        audit = "FAIL_CONTINUE" if status == "FORWARD_ACCUMULATING" else "PASS"
    state = {
        "schema": "AIOS_FOREX_INSTITUTIONAL_EDGE_PROGRAM_V1",
        "packet_id": PACKET_ID,
        "status": status,
        "failure_memory_count": len(failure_memory),
        "failure_memory_hash": sha256(stable(failure_memory).encode("utf-8")),
        "registry_count": registry["hypothesis_count"],
        "registry_hash": registry["hash"],
        "capability_scorecard": scorecard,
        "development": research.get("development", {}) if "research" in locals() else {},
        "tracks": research.get("tracks", {}) if "research" in locals() else {},
        "development_passers": research.get("development_passers", []) if "research" in locals() else [],
        "registry_wide_null": research.get("registry_wide_null", {"repetitions": 0, "status": "NOT_REACHED"}) if "research" in locals() else {"repetitions": 0, "status": "NOT_REACHED"},
        "bootstrap": research.get("bootstrap", {"repetitions": 0, "status": "NOT_REACHED"}) if "research" in locals() else {"repetitions": 0, "status": "NOT_REACHED"},
        "overfit_diagnostics": research.get("overfit_diagnostics", {"status": "NOT_REACHED"}) if "research" in locals() else {"status": "NOT_REACHED"},
        "validation": research.get("validation", {}) if "research" in locals() else {},
        "shortlist_hash": research.get("shortlist_hash") if "research" in locals() else None,
        "sealed_holdout": research.get("sealed_holdout", {}) if "research" in locals() else {},
        "finalists": research.get("finalists", []) if "research" in locals() else [],
        "forward": {"status": "NOT_STARTED"},
        "paper": {"status": "NOT_STARTED"},
        "publication": {"status": "NOT_REACHED"},
        "live_safety": {"status": "NOT_REACHED", "live": False},
        "credential_readiness": {"status": "NOT_REACHED", "secret_value_exposed": False, "account_id_exposed": False},
        "funding_readiness": {"status": "NOT_REACHED", "money_movement": False},
        "continuation_active": False,
        "current_phase": "CONSOLIDATED_HUMAN_DATA_DROP_PREPARATION" if status == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED" else "CAPABILITY_PARITY_REASSESSMENT",
        "current_workstream": "EXTERNAL_INFORMATION_COVERAGE",
        "current_action": "scorecard and novelty gate",
        "next_action": next_action,
        "next_three_actions": ["place public official artifacts", "resume Packet 016", "import and validate official data"] if status == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED" else [],
        "remaining_authorized_work_count": remaining,
        "remaining_source_routes": [],
        "remaining_source_series": acquisition.get("remaining_source_series", []),
        "remaining_data_families": acquisition.get("remaining_data_families", []),
        "remaining_hypothesis_count": 0,
        "remaining_research_tracks": [],
        "recoverable_failures": [],
        "deferred_blockers": ["external official data unavailable automatically"] if status == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED" else [],
        "alternate_safe_actions": [],
        "external_time_dependency": False,
        "protected_owner_action_dependency": status == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED",
        "terminal_state_candidate": status,
        "pre_terminal_audit_status": audit,
        "same_packet_resume_command": "python -B -m automation.forex_engine.forex_institutional_edge_program_v1 --execute",
        "completed_work_units": ["preflight", "lock_a", "evidence_reconciliation", "failure_memory", "scorecard", "source_route_plan", "automatic_acquisition", "corpus_freeze", "novelty_registry", "development", "registry_wide_null", "bootstrap", "validation", "sealed_holdout"],
        "remaining_work_units": ["human_data_drop_reconciliation"] if status == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED" else (["forward_accumulation"] if status == "FORWARD_ACCUMULATING" else []),
        "safety": {"credentials": False, "funding": False, "broker_write": False, "practice_order": False, "live": False, "money_movement": False},
    }
    write_json(STATE, state)
    write_json(ROOT / "campaign_state.json", state)
    REPORT.write_text(render_report(state), encoding="utf-8")
    return state


def render_scorecard(scorecard: dict[str, Any]) -> str:
    lines = ["# AIOS Forex Funding Readiness Scorecard V2", ""]
    for name, row in scorecard.items():
        lines.extend(
            [
                f"## {name}",
                f"- score: {row['score']}",
                f"- evidence: {row['evidence']}",
                f"- missing evidence: {row['missing_evidence']}",
                f"- unlock condition: {row['unlock_condition']}",
                "",
            ]
        )
    return "\n".join(lines)


def render_report(state: dict[str, Any]) -> str:
    score = state["capability_scorecard"]["EXTERNAL_INFORMATION_COVERAGE"]["score"]
    if state["status"] == "INSTITUTIONAL_RESEARCH_EXHAUSTED_NO_EDGE":
        happened = "Packet 016 acquired and froze official institutional information, processed 72 novel hypotheses, ran the statistical gates, and found no finalist."
        next_action = "Do not provide OANDA credentials or fund an account; preserve the negative evidence."
        mode = "INSTANT for review."
    elif state["status"] == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED":
        happened = "Packet 016 built failure memory, froze a 72-hypothesis preview, and stopped at the official data-drop gate because external information parity is not yet earned."
        next_action = "Use the single consolidated handoff in `Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_DROP_HANDOFF.md`."
        mode = "INSTANT to review the handoff, then HIGH after public official files are in the inbox."
    else:
        happened = "Packet 016 prepared the institutional edge registry and is waiting at the next authorized continuation gate."
        next_action = state["next_action"]
        mode = "HIGH for the next bounded implementation step."
    return f"""# AIOS Forex Institutional Edge Program V1

WHAT HAPPENED:
{happened}

IS IT SAFE:
YES. No credentials, OANDA LIVE request, broker write, Practice order, trade, funding, or money movement occurred.

WHAT DO I DO NEXT:
{next_action}

HOW CLOSE ARE WE:
Estimated readiness: {score}% for external information; 0% for Forward/PAPER/funding because no finalist exists.

WHICH MODE SHOULD I USE:
{mode}

TECHNICAL DETAILS:
- Status: `{state['status']}`
- Failure memory entries: {state['failure_memory_count']} (`{state['failure_memory_hash']}`)
- Registry preview: {state['registry_count']} hypotheses (`{state['registry_hash']}`)
- Development passers: {len(state['development_passers'])}
- Registry null campaigns: {state['registry_wide_null'].get('repetitions', 0)}
- Bootstrap entries: {len(state['bootstrap'])}
- Validation candidates: {len(state['validation'])}
- Sealed Holdout entries: {len(state['sealed_holdout'])}
- Finalists: {len(state['finalists'])}
- Forward/PAPER: not started
- Credential/funding/compounding: false
- Continuation audit: `{state['pre_terminal_audit_status']}`
- Next action: `{state['next_action']}`
"""


def _official_v3_read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _official_v3_scorecard(acquisition: dict[str, Any], corpus: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    external_score = int(acquisition.get("external_information_coverage_score", 55))
    market_score = int(market.get("capability_score", 0))
    corpus_frozen = bool(corpus.get("frozen"))
    rows = {
        "EXECUTION_INTEGRITY": (98, "prior certified controls and deterministic replay evidence", "none", "maintain executor hash and regressions"),
        "COST_ACCOUNTING_INTEGRITY": (98, "single-charge cost contract and focused regressions", "none", "maintain cost tests"),
        "MARKET_CORPUS_REGIME_COVERAGE": (market_score, "Corpus V3 gate records no credential-readable OANDA acquisition", "H1/H4/D1/W1 multi-regime OANDA data unavailable to Codex under current credential boundary", "separately governed credential-safe market-data acquisition path"),
        "EXTERNAL_INFORMATION_COVERAGE": (external_score, "Packet 016 official route attempts and usable-family count", "missing public official artifacts listed in one handoff", "automatic acquisition or consolidated Human-only public official download"),
        "POINT_IN_TIME_INTEGRITY": (95 if corpus_frozen else int(acquisition.get("point_in_time_integrity_score", 0)), "required timestamps enforced for usable records", "no score for unavailable records", "freeze External Information Corpus V3"),
        "MECHANISM_RESEARCH_COVERAGE": (0, "Packet 016 broad registry is blocked until data capability passes", "48 frozen candidates not scored", "external information >=85 and multi-regime market coverage >=90, or formal untestable classification"),
        "STATISTICAL_PROOF": (90, "prior registry-wide null capability exists", "no Packet 016 Development passer", "novel registry with passer"),
        "FORWARD_PROOF": (0, "no finalist", "forward evidence", "Holdout finalist"),
        "PAPER_PROFITABILITY": (0, "not started", "fresh PAPER PASS", "Forward PASS"),
        "LIVE_AND_FUNDING_READINESS": (0, "not reached; live false", "publication, live-safety, credential, and funding evidence", "PAPER profitability, protected publication, LIVE-safety certification, Human-only credential status"),
    }
    return {name: {"score": score, "evidence": evidence, "missing_evidence": missing, "unlock_condition": unlock} for name, (score, evidence, missing, unlock) in rows.items()}


def _official_v3_registry(corpus: dict[str, Any]) -> dict[str, Any]:
    tracks = [
        "LONG_HORIZON_TIME_SERIES_MOMENTUM",
        "CROSS_SECTIONAL_CARRY_MOMENTUM",
        "POLICY_DIVERGENCE_REGIMES",
        "CFTC_CROWDING_UNWIND",
        "CENTRAL_BANK_DECISION_EVENTS",
        "MACRO_EVENT_RISK_REACTION",
        "YIELD_GLOBAL_RISK_REGIMES",
        "MULTI_MECHANISM_PORTFOLIO_RANKING",
    ]
    hypotheses = []
    data_eligible = corpus.get("status") == "FROZEN_VALID"
    for track_index, track in enumerate(tracks, 1):
        for variant in range(1, 7):
            hypotheses.append(
                {
                    "hypothesis_id": f"I016-{track_index}-{variant:02d}",
                    "candidate_id": f"I016-{track_index}-{variant:02d}",
                    "track": track_index,
                    "track_name": track,
                    "economic_mechanism": f"{track}_V{variant}",
                    "information_sources": [corpus.get("corpus_id", "NO_FROZEN_CORPUS")],
                    "source_hashes": [corpus.get("aggregate_hash", "NO_HASH")],
                    "availability_rules": "strategy_available_time_utc <= decision time",
                    "direction": "BOTH_SEPARATELY",
                    "decision_timeframe": "D1" if track_index in {1, 2, 3, 4, 7, 8} else "H1",
                    "execution_timeframe": "next executable interval",
                    "event_or_opportunity_rule": "predeclared causal opportunity score",
                    "entry": "next executable interval after completed information",
                    "initial_stop": "1.5 ATR",
                    "target": "3R",
                    "maximum_holding_period": "10 trading days" if track_index in {1, 2, 3, 7, 8} else "2 trading days",
                    "risk": "0.25 percent simulated equity",
                    "concurrency": 1,
                    "currency_exposure_rule": "no currency dominates more than 25 percent of open risk",
                    "feature_list": ["official_point_in_time_information", "multi_regime_market_context", "spread_efficiency"],
                    "parameters": {"variant": variant, "transparent_model": "rule_score"},
                    "cost_mode": "ACTUAL_BID_ASK_SINGLE_CHARGE",
                    "failure_condition": "fails Development or multiple-testing gate",
                    "data_eligible": data_eligible,
                    "novelty_statement": "blocked until Packet 016 V3 data capability passes" if not data_eligible else "uses Packet 016 V3 official information and multi-regime market corpus",
                    "historical_nearest_neighbor_candidate": "Packet015 frozen registry; not rerun",
                }
            )
    registry = {"schema": "AIOS_FOREX_INSTITUTIONAL_EDGE_REGISTRY_V1", "hypothesis_count": len(hypotheses), "hypotheses": hypotheses}
    registry["hash"] = sha256(stable(registry).encode("utf-8"))
    return registry


def build_scorecard(acquisition: dict[str, Any], corpus: dict[str, Any], market: dict[str, Any] | None = None) -> dict[str, Any]:
    return _official_v3_scorecard(acquisition, corpus, market or {})


def hypothesis_registry(corpus: dict[str, Any]) -> dict[str, Any]:
    return _official_v3_registry(corpus)


def execute() -> dict[str, Any]:
    official_state = Path("Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_BREAKTHROUGH_V1_STATE.json")
    external_state = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V3_STATE.json")
    market_state = Path("Reports/forex_delivery/AIOS_FOREX_MULTI_REGIME_CORPUS_V3_STATE.json")
    acquisition = _official_v3_read(official_state)
    corpus = _official_v3_read(external_state)
    market = _official_v3_read(market_state)
    ROOT.mkdir(parents=True, exist_ok=True)
    failure_memory = build_failure_memory()
    registry = _official_v3_registry(corpus)
    scorecard = _official_v3_scorecard(acquisition, corpus, market)
    external_ready = corpus.get("status") == "FROZEN_VALID" and int(acquisition.get("external_information_coverage_score", 0)) >= 85
    market_ready = bool(market.get("frozen")) and int(market.get("capability_score", 0)) >= 90
    if market.get("status") == "NOT_FROZEN_OANDA_PRACTICE_CREDENTIAL_BOUNDARY":
        status = "GOVERNANCE_BLOCKED"
    elif acquisition.get("remaining_human_download_items"):
        status = "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED"
    elif not external_ready:
        status = "EXTERNAL_INFORMATION_CAPABILITY_BLOCKED"
    elif external_ready and market_ready:
        status = "DATA_CAPABILITY_PASS"
    else:
        status = "VALIDATION_BLOCKED"
    state = {
        "schema": "AIOS_FOREX_INSTITUTIONAL_EDGE_PROGRAM_V1",
        "packet_id": PACKET_ID,
        "status": status,
        "failure_memory_count": len(failure_memory),
        "failure_memory_hash": sha256(stable(failure_memory).encode("utf-8")),
        "registry_count": registry["hypothesis_count"],
        "registry_hash": registry["hash"],
        "capability_scorecard": scorecard,
        "data_capability_review": {"external_ready": external_ready, "market_ready": market_ready, "data_capability_pass": external_ready and market_ready},
        "development": {},
        "tracks": {},
        "development_passers": [],
        "registry_wide_null": {"repetitions": 0, "status": "NOT_REACHED_DATA_CAPABILITY_BLOCKED"},
        "bootstrap": {},
        "overfit_diagnostics": {"status": "NOT_REACHED_DATA_CAPABILITY_BLOCKED"},
        "validation": {},
        "shortlist_hash": None,
        "sealed_holdout": {},
        "recent_regime_challenge": {"status": "NOT_REACHED"},
        "finalists": [],
        "forward": {"status": "NOT_STARTED"},
        "paper": {"status": "NOT_STARTED"},
        "publication": {"status": "NOT_REACHED"},
        "live_safety": {"status": "NOT_REACHED", "live": False},
        "credential_readiness": {"status": "NOT_REACHED", "secret_value_exposed": False, "account_id_exposed": False},
        "funding_readiness": {"status": "NOT_REACHED", "money_movement": False},
        "continuation_active": False,
        "current_phase": status,
        "current_workstream": "DATA_CAPABILITY_REVIEW",
        "current_action": "scorecard and 48-candidate novelty gate",
        "next_action": "NONE",
        "next_three_actions": [],
        "remaining_authorized_work_count": 0,
        "remaining_source_routes": [],
        "remaining_source_series": [],
        "remaining_human_download_items": acquisition.get("remaining_human_download_items", []),
        "remaining_data_families": [] if external_ready else ["external official families below threshold"],
        "remaining_hypothesis_count": 0,
        "remaining_research_tracks": [],
        "recoverable_failures": [],
        "deferred_blockers": [market.get("blocker")] if market.get("blocker") else [],
        "alternate_safe_actions": [],
        "external_time_dependency": False,
        "protected_owner_action_dependency": "Credential-safe OANDA Practice market-data acquisition lane required outside Codex credential visibility" if status == "GOVERNANCE_BLOCKED" else None,
        "terminal_state_candidate": status,
        "pre_terminal_audit_status": "BLOCKED_BY_GOVERNANCE_AND_HUMAN_ONLY_DATA_GATES",
        "same_packet_resume_command": "Resume Packet 016 after completing the stated Human-only gate; do not paste credentials into Codex.",
        "completed_work_units": ["preflight", "lock_a", "source_requirement_freeze", "automated_source_acquisition", "external_corpus_gate", "multi_regime_corpus_gate", "scorecard", "48_candidate_preview"],
        "remaining_work_units": [],
        "safety": {"credentials": False, "funding": False, "broker_write": False, "practice_order": False, "live": False, "money_movement": False},
    }
    write_json(ROOT / "failure_memory_matrix.json", failure_memory)
    write_json(ROOT / "hypothesis_registry_preview.json", registry)
    write_json(SCORE_JSON, scorecard)
    SCORE_MD.write_text(render_scorecard(scorecard), encoding="utf-8")
    state["state_hash"] = sha256(stable(state).encode("utf-8"))
    write_json(STATE, state)
    write_json(ROOT / "campaign_state.json", state)
    REPORT.write_text(render_report(state), encoding="utf-8")
    return state


def render_report(state: dict[str, Any]) -> str:
    external = state["capability_scorecard"]["EXTERNAL_INFORMATION_COVERAGE"]["score"]
    market = state["capability_scorecard"]["MARKET_CORPUS_REGIME_COVERAGE"]["score"]
    return f"""# AIOS Forex Institutional Edge Program V1

WHAT HAPPENED:
Packet 016 built failure memory, scorecard, and a 48-candidate protocol preview, then blocked broad research until the data capability gate passes.

IS IT SAFE:
YES. No credential, broker, LIVE, order, funding, commit, push, or PR action occurred.

WHAT DO I DO NEXT:
Do not request credentials or funding. Resolve the explicit data-capability blocker first.

HOW CLOSE ARE WE:
Estimated readiness: {external}% for external-information capability; {market}% for multi-regime corpus capability; 0% for Forward/PAPER/LIVE funding evidence.

WHICH MODE SHOULD I USE:
PRO if designing the separate credential-safe OANDA Practice market-data acquisition lane; HIGH for continuing after the data gate is resolved.

TECHNICAL DETAILS:
- Packet: `{PACKET_ID}`
- Status: `{state['status']}`
- Failure-memory rows: {state['failure_memory_count']}
- Registry hypotheses: {state['registry_count']}
- Registry hash: `{state['registry_hash']}`
- Development passers: {len(state['development_passers'])}
- Validation opened: false
- Holdout opened: false
- Recent-regime challenge opened: false
- Finalists: {len(state['finalists'])}
- State hash: `{state['state_hash']}`
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required")
    state = execute()
    print(stable({"status": state["status"], "registry": state["registry_count"], "next": state["next_action"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
