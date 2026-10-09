"""Paper-only deterministic next-candidate discovery and replacement ranking."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from automation.forex_engine import failure_regime_analysis_s_v1
from automation.forex_engine import profit_objective_accelerator_l_v1 as accelerator

MODE = "FOREX_NEXT_CANDIDATE_DISCOVERY_U_V1"
PACKET_ID = "AIOS_FOREX_NEXT_CANDIDATE_DISCOVERY_PACKET_U_V1"
REPORTS_DIR = Path("Reports/forex_delivery")
DEFAULT_REPORT_ROOT = Path(__file__).resolve().parents[2] / REPORTS_DIR
REPORT_PACKET = "AIOS_FOREX_NEXT_CANDIDATE_DISCOVERY_PACKET_U_V1_REPORT.md"
REPORT_LEADERBOARD = "AIOS_FOREX_CANDIDATE_LEADERBOARD_V1.md"
REPORT_REPLACEMENT = "AIOS_FOREX_CANDIDATE_REPLACEMENT_ANALYSIS_V1.md"

ANCHOR_CANDIDATE_ID = "c1-eur-buy"
ANCHOR_STRATEGY_ID = "paper_long_run_supervisor_v2"
ANCHOR_DIRECTION = "LONG"
CAMPAIGN_STATE_PATHS = (
    REPORTS_DIR / "AIOS_FOREX_P1_30_TRADE_CAMPAIGN_V1_STATE.json",
    REPORTS_DIR / "AIOS_FOREX_SUPERTREND_30_TRADE_CAMPAIGN_STATE.json",
)


def _safety() -> dict[str, bool]:
    return {
        "paper_only": True,
        "broker_connected": False,
        "credentials_used": False,
        "account_id_present": False,
        "network_used": False,
        "order_execution": False,
        "demo_trading": False,
        "live_trading": False,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if num != num:
        return default
    return num


def _load_campaign_state(report_root: Path = DEFAULT_REPORT_ROOT) -> dict[str, Any]:
    for name in CAMPAIGN_STATE_PATHS:
        path = report_root / name.name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _deterministic_candidate_profiles() -> list[dict[str, Any]]:
    profiles = [
        {
            "candidate_id": ANCHOR_CANDIDATE_ID,
            "strategy_id": ANCHOR_STRATEGY_ID,
            "direction": ANCHOR_DIRECTION,
            "trade_pnl_list": [],
            "candidate_label": "baseline_anchor",
        },
        {
            "candidate_id": "c2-usd-buy",
            "strategy_id": "paper_momentum_supervisor_v3",
            "direction": "LONG",
            "trade_pnl_list": [],
            "candidate_label": "new_candidate_long_a",
        },
        {
            "candidate_id": "c3-eur-sell",
            "strategy_id": "paper_mean_reversion_v2",
            "direction": "SHORT",
            "trade_pnl_list": [],
            "candidate_label": "new_candidate_short_a",
        },
        {
            "candidate_id": "c4-jpy-buy",
            "strategy_id": "paper_breakout_supervisor_v2",
            "direction": "LONG",
            "trade_pnl_list": [],
            "candidate_label": "new_candidate_long_b",
        },
        {
            "candidate_id": "c5-gbp-buy",
            "strategy_id": "paper_continuation_supervisor_v2",
            "direction": "LONG",
            "trade_pnl_list": [],
            "candidate_label": "new_candidate_long_c",
        },
    ]
    return profiles


def build_candidate_profiles() -> list[dict[str, Any]]:
    return _deterministic_candidate_profiles()


def score_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        evaluated = accelerator.evaluate_profitability_candidate(
            strategy_id=str(candidate.get("strategy_id", "")),
            candidate_id=str(candidate.get("candidate_id", "")),
            direction=str(candidate.get("direction", "")),
            trade_pnl_list=list(candidate.get("trade_pnl_list", [])),
            thresholds=accelerator.DEFAULT_THRESHOLDS,
        )
        scored.append(
            {
                "candidate_id": evaluated["candidate_id"],
                "strategy_id": evaluated["strategy_id"],
                "direction": evaluated["direction"],
                "expectancy": _safe_float(evaluated["expectancy"]),
                "profit_factor": _safe_float(evaluated["profit_factor"]),
                "win_rate": _safe_float(evaluated["win_rate"]),
                "max_drawdown": _safe_float(evaluated["max_drawdown"]),
                "closed_trade_count": int(evaluated["sample_size"]),
                "consecutive_losses": int(evaluated["consecutive_losses"]),
                "promotion_status": evaluated["promotion_status"],
                "blocker_reasons": list(evaluated["blocked_reasons"]),
                "candidate_label": str(candidate.get("candidate_label", "")),
            },
        )
    return scored


def rank_candidates(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        scored,
        key=lambda item: (
            item["blocker_reasons"] == [],
            item["expectancy"],
            item["profit_factor"],
            item["win_rate"],
            -item["max_drawdown"],
            -item["consecutive_losses"],
            item["candidate_id"],
        ),
        reverse=True,
    )


def build_leaderboard(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = rank_candidates(candidates)
    champion = ranked[0] if ranked else {}
    runner_up = ranked[1] if len(ranked) > 1 else {}
    rejected = [item for item in ranked if item.get("promotion_status") != accelerator.PROMOTION_STATUS_PROFIT_OBJECTIVE_READY]

    anchor_indexed = next((item for item in ranked if item.get("candidate_id") == ANCHOR_CANDIDATE_ID), {})
    anchor_ready = bool(anchor_indexed) and anchor_indexed.get("promotion_status") == accelerator.PROMOTION_STATUS_PROFIT_OBJECTIVE_READY
    exceeds_anchor = []
    if anchor_indexed:
        for item in ranked:
            if item["candidate_id"] == ANCHOR_CANDIDATE_ID:
                continue
            if (
                item["expectancy"] > anchor_indexed["expectancy"]
                and item["profit_factor"] >= anchor_indexed["profit_factor"]
                and item["win_rate"] >= anchor_indexed["win_rate"]
            ):
                exceeds_anchor.append(item)

    return {
        "anchor_candidate": anchor_indexed,
        "champion": champion,
        "runner_up": runner_up,
        "ranked": ranked,
        "rejected": rejected,
        "candidates_exceed_anchor": exceeds_anchor,
        "any_candidate_exceeds_anchor": bool(exceeds_anchor),
        "replacement_needed": bool(
            champion
            and champion.get("candidate_id") != ANCHOR_CANDIDATE_ID
            and not anchor_ready,
        ),
    }


def build_replacement_analysis(
    leaderboard: dict[str, Any],
) -> dict[str, Any]:
    champion = leaderboard.get("champion", {})
    anchor = leaderboard.get("anchor_candidate", {})
    rejection_list = leaderboard.get("rejected", [])
    exceeds = leaderboard.get("candidates_exceed_anchor", [])
    return {
        "anchor_candidate_id": ANCHOR_CANDIDATE_ID,
        "anchor_promotion_status": anchor.get("promotion_status", ""),
        "anchor_blockers": list(anchor.get("blocker_reasons", [])),
        "champion_candidate_id": champion.get("candidate_id", ""),
        "champion_exceeds_anchor": bool(exceeds),
        "replacement_candidate_ids": [item.get("candidate_id", "") for item in exceeds],
        "replacement_recommendation": (
            "replace"
            if champion and champion.get("candidate_id") != ANCHOR_CANDIDATE_ID and not anchor.get("blocked")
            else "retain_anchor_and_continue"
            if anchor.get("promotion_status") == accelerator.PROMOTION_STATUS_PROFIT_OBJECTIVE_READY
            else "re-evaluate_strategy_family"
        ),
        "rejected_candidates": [item["candidate_id"] for item in rejection_list],
        "rejected_count": len(rejection_list),
        "runner_up_candidate_id": leaderboard.get("runner_up", {}).get("candidate_id", ""),
        "replacement_ready": champion.get("promotion_status", "") == accelerator.PROMOTION_STATUS_PROFIT_OBJECTIVE_READY
        and champion.get("candidate_id") != ANCHOR_CANDIDATE_ID,
    }


def run_next_candidate_discovery(
    *, write_reports: bool = True, report_root: str | Path = DEFAULT_REPORT_ROOT
) -> dict[str, Any]:
    root = Path(report_root)
    campaign_state = _load_campaign_state(root)
    evidence_available = False
    profile_candidates = build_candidate_profiles()
    scored_candidates = score_candidates(profile_candidates)
    leaderboard = build_leaderboard(scored_candidates)
    replacement = build_replacement_analysis(leaderboard)
    failure_payload = failure_regime_analysis_s_v1.run_failure_regime_analysis(write_reports=False)
    result = {
        "mode": MODE,
        "packet_id": PACKET_ID,
        "safety": _safety(),
        "candidates": scored_candidates,
        "leaderboard": leaderboard,
        "replacement_analysis": replacement,
        "champion": leaderboard.get("champion", {}),
        "runner_up": leaderboard.get("runner_up", {}),
        "candidate_count": len(scored_candidates),
        "campaign_state": {
            "accepted_qualifying_trades": int(_safe_float(campaign_state.get("accepted_qualifying_trades"), 0.0)),
            "campaign_status": str(campaign_state.get("campaign_status", "")),
            "p1_status": str(campaign_state.get("p1_status", "")),
            "target_qualifying_trades": int(_safe_float(campaign_state.get("target_qualifying_trades"), 0.0)),
        },
        "genuine_campaign_evidence": evidence_available,
        "accelerator_mode": accelerator.MODE,
        "failure_context": {
            "last_packet": failure_payload.get("packet_id"),
            "verdict": failure_payload.get("verdict"),
            "confidence_score": failure_payload.get("confidence_score"),
        },
    }

    if write_reports:
        result["report_paths"] = write_reports_fn(result, root)
    return result


def write_reports_fn(
    payload: dict[str, Any], report_root: str | Path = DEFAULT_REPORT_ROOT
) -> dict[str, Path]:
    report_dir = Path(report_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    packet_path = report_dir / REPORT_PACKET
    leaderboard_path = report_dir / REPORT_LEADERBOARD
    replacement_path = report_dir / REPORT_REPLACEMENT
    packet_path.write_text(_build_packet_report(payload), encoding="utf-8")
    leaderboard_path.write_text(_build_leaderboard_report(payload), encoding="utf-8")
    replacement_path.write_text(_build_replacement_report(payload), encoding="utf-8")
    return {
        "packet": packet_path,
        "leaderboard": leaderboard_path,
        "replacement": replacement_path,
    }


def _build_packet_report(payload: dict[str, Any]) -> str:
    leaderboard = payload["leaderboard"]
    replacement = payload["replacement_analysis"]
    return f"""# AIOS Forex Next Candidate Discovery Packet U V1

## Paper-only scope
- paper_only: True
- no broker connectivity
- no credentials
- no account IDs
- no network
- no order execution
- no demo trading
- no live trading

## Candidate discovery summary
- generated candidates: `{payload['candidate_count']}`
- current anchor: `{ANCHOR_CANDIDATE_ID}`
- anchor present: `{bool(leaderboard['anchor_candidate'])}`
- any candidate exceeds anchor: `{leaderboard['any_candidate_exceeds_anchor']}`
- champion: `{leaderboard['champion'].get('candidate_id', 'N/A')}`
- runner-up: `{leaderboard['runner_up'].get('candidate_id', 'N/A')}`
- replacement needed: `{leaderboard['replacement_needed']}`
- replacement recommendation: `{replacement['replacement_recommendation']}`
"""


def _build_leaderboard_report(payload: dict[str, Any]) -> str:
    ranked = payload["leaderboard"]["ranked"]
    return """# AIOS Forex Candidate Leaderboard V1

| rank | candidate_id | strategy_id | direction | expectancy | profit_factor | win_rate | drawdown | trades | blockers |
|---|---|---|---|---:|---:|---:|---:|---:|---|
""" + "\n".join(
        f"| {idx} | {row['candidate_id']} | {row['strategy_id']} | {row['direction']} | "
        f"{row['expectancy']:.4f} | {row['profit_factor']:.4f} | {row['win_rate']:.4f} | "
        f"{row['max_drawdown']:.4f} | {row['closed_trade_count']} | {', '.join(row['blocker_reasons']) or 'none'} |"
        for idx, row in enumerate(ranked, start=1)
    ) + "\n"


def _build_replacement_report(payload: dict[str, Any]) -> str:
    replacement = payload["replacement_analysis"]
    return f"""# AIOS Forex Candidate Replacement Analysis V1

## Replacement analysis
- anchor candidate: `{replacement['anchor_candidate_id']}`
- anchor promotion status: `{replacement['anchor_promotion_status']}`
- anchor blockers: `{', '.join(replacement['anchor_blockers']) or 'none'}`
- champion candidate: `{replacement['champion_candidate_id'] or 'none'}`
- champion exceeds anchor: `{replacement['champion_exceeds_anchor']}`
- replacement candidates: `{', '.join(replacement['replacement_candidate_ids']) or 'none'}`
- runner-up: `{replacement['runner_up_candidate_id'] or 'none'}`
- rejected candidates: `{', '.join(replacement['rejected_candidates']) or 'none'}`
- rejected count: `{replacement['rejected_count']}`
- replacement ready: `{replacement['replacement_ready']}`
- recommendation: `{replacement['replacement_recommendation']}`

## Outcome
- failure verdict context: `{payload['failure_context']['verdict']}`
- replacement confidence score context: `{payload['failure_context']['confidence_score']}`
"""


__all__ = [
    "build_candidate_profiles",
    "score_candidates",
    "rank_candidates",
    "build_leaderboard",
    "build_replacement_analysis",
    "run_next_candidate_discovery",
]
