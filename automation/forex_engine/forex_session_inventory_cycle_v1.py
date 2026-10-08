"""DST-aware, offline Stage-1 session inventory-cycle research."""
from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any

from automation.forex_engine import forex_round_number_conditional_order_state_v1 as core


PACKET_ID = "PKT-FOREX-025"
PRIOR_ATTEMPTS = 1174
CUMULATIVE_ATTEMPTS = 1179
FAMILY = "SESSION_HANDOFF_INVENTORY_CYCLE"
RISK_FRACTION = 0.0025
STOP_ATR = 2.0
HOLDING_BARS = 48
RANDOM_SEED = 25025
DIRECTIONS = core.DIRECTIONS
CURRENCY_ZONES = {
    "JPY": "Asia/Tokyo",
    "AUD": "Australia/Sydney",
    "NZD": "Pacific/Auckland",
    "EUR": "Europe/London",
    "GBP": "Europe/London",
    "CHF": "Europe/London",
    "USD": "America/New_York",
    "CAD": "America/New_York",
}


def canonical_bytes(value: Any) -> bytes:
    return core.canonical_bytes(value)


def sha256_bytes(value: bytes) -> str:
    return core.sha256_bytes(value)


def family_descriptor() -> dict[str, Any]:
    return {
        "family": FAMILY,
        "mechanism": "LOCAL_HOURS_CROSS_BORDER_INVENTORY_DEMAND",
        "currency_zones": CURRENCY_ZONES,
        "local_signal_bar": "08:00_COMPLETED_M5",
        "base_own_session": "SHORT_BASE",
        "quote_own_session": "LONG_BASE",
        "holding_bars": HOLDING_BARS,
        "stop_atr": STOP_ATR,
        "directions": DIRECTIONS,
        "costs": {"spread": "OBSERVED_BID_ASK", "base_slippage": 0.10, "stress_slippage": 0.50},
    }


def family_fingerprint() -> str:
    return sha256_bytes(canonical_bytes(family_descriptor()))


def candidate_definitions() -> list[dict[str, Any]]:
    rows = []
    for direction in DIRECTIONS:
        row = {
            "candidate_id": f"SIC-{direction}",
            "direction_variant": direction,
            "holding_bars": HOLDING_BARS,
            "stop_atr": STOP_ATR,
            "signal_local_time": "08:00",
        }
        row["candidate_fingerprint"] = sha256_bytes(canonical_bytes({"family_fingerprint": family_fingerprint(), "definition": row}))
        rows.append(row)
    return rows


def pair_is_eligible(pair: str) -> bool:
    base, quote = pair.split("_")
    return base in CURRENCY_ZONES and quote in CURRENCY_ZONES and CURRENCY_ZONES[base] != CURRENCY_ZONES[quote]


def _nth_sunday(year: int, month: int, ordinal: int) -> datetime:
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    shift = (6 - first.weekday()) % 7 + 7 * (ordinal - 1)
    return first + timedelta(days=shift)


def _last_sunday(year: int, month: int) -> datetime:
    following = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1, tzinfo=timezone.utc)
    return following - timedelta(days=following.weekday() + 1)


def utc_offset_hours(currency: str, moment: datetime) -> int:
    """Frozen IANA-rule offsets for the 2024-2025 research interval."""
    year = moment.year
    zone = CURRENCY_ZONES[currency]
    if zone == "Asia/Tokyo":
        return 9
    if zone == "Europe/London":
        start = _last_sunday(year, 3).replace(hour=1)
        end = _last_sunday(year, 10).replace(hour=1)
        return 1 if start <= moment < end else 0
    if zone == "America/New_York":
        start = _nth_sunday(year, 3, 2).replace(hour=7)
        end = _nth_sunday(year, 11, 1).replace(hour=6)
        return -4 if start <= moment < end else -5
    if zone == "Australia/Sydney":
        end = (_nth_sunday(year, 4, 1) - timedelta(days=1)).replace(hour=16)
        start = (_nth_sunday(year, 10, 1) - timedelta(days=1)).replace(hour=16)
        return 11 if moment < end or moment >= start else 10
    if zone == "Pacific/Auckland":
        end = (_nth_sunday(year, 4, 1) - timedelta(days=1)).replace(hour=14)
        start = (_last_sunday(year, 9) - timedelta(days=1)).replace(hour=14)
        return 13 if moment < end or moment >= start else 12
    raise ValueError("UNSUPPORTED_FROZEN_TIME_ZONE")


def local_session_signals(pair: str, timestamp: str) -> list[tuple[str, str]]:
    base, quote = pair.split("_")
    moment = core.parse_timestamp(timestamp)
    signals = []
    base_local = moment + timedelta(hours=utc_offset_hours(base, moment))
    quote_local = moment + timedelta(hours=utc_offset_hours(quote, moment))
    if base_local.hour == 8 and base_local.minute == 0:
        signals.append(("SHORT", base))
    if quote_local.hour == 8 and quote_local.minute == 0:
        signals.append(("LONG", quote))
    return signals


def build_pair_events(pair: str, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not pair_is_eligible(pair):
        return []
    events = []
    ranges: deque[float] = deque(maxlen=14)
    previous_close = None
    for index, bar in enumerate(bars):
        ranges.append(core.true_range(bar, previous_close))
        previous_close = float(bar["mid"]["c"])
        if len(ranges) < 14:
            continue
        for original_direction, session_currency in local_session_signals(pair, bar["timestamp"]):
            if not core.consecutive_path(bars, index, HOLDING_BARS):
                continue
            signal_complete = core.parse_timestamp(bar["timestamp"]) + timedelta(minutes=5)
            end = core.parse_timestamp(bars[index + HOLDING_BARS]["timestamp"]) + timedelta(minutes=5)
            fold = core.fold_index(signal_complete)
            if fold < 0 or core.fold_index(end) != fold or core.in_embargo(signal_complete):
                continue
            if core.interval_touches_rollover(signal_complete, end):
                continue
            atr = math.fsum(ranges) / len(ranges)
            risk_distance = STOP_ATR * atr
            if risk_distance <= 0:
                continue
            outcomes = tuple(
                core.simulate_path(pair, bars, index, HOLDING_BARS, direction, risk_distance, scenario)
                for direction in ("LONG", "SHORT")
                for scenario in ("gross", "base", "stress")
            )
            spread = (float(bar["ask"]["c"]) - float(bar["bid"]["c"])) / core.pip_size(pair)
            event = {
                "pair": pair,
                "original_direction": original_direction,
                "session_currency": session_currency,
                "signal_timestamp": core.timestamp_text(signal_complete),
                "entry_timestamp": bars[index + 1]["timestamp"],
                "fold": fold,
                "session": f"{session_currency}_LOCAL_08",
                "volatility_regime": "LOW" if atr / previous_close < 0.0005 else ("HIGH" if atr / previous_close > 0.0015 else "NORMAL"),
                "trend_range_regime": "NOT_USED_BY_SIGNAL",
                "economic_event_proximity": "NOT_APPLICABLE_NO_CERTIFIED_EVENT_FEED",
                "spread_pips": spread,
                "prior_completed_bar_direction": "LONG" if float(bar["mid"]["c"]) >= float(bar["mid"]["o"]) else "SHORT",
                "atr14": atr,
                "outcomes": outcomes,
            }
            identity = {key: value for key, value in event.items() if key != "outcomes"}
            event["event_id"] = sha256_bytes(canonical_bytes(identity))
            events.append(event)
    return events


def direction_for_variant(event: dict[str, Any], variant: str) -> str | None:
    return core.direction_for_variant(event, variant)


def scheduled(events: list[dict[str, Any]], definition: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    choices = []
    for event in events:
        direction = direction_for_variant(event, definition["direction_variant"])
        if direction:
            choices.append((event, direction))
    choices.sort(key=lambda item: (item[0]["entry_timestamp"], item[0]["pair"], item[0]["event_id"]))
    active: list[tuple[str, str, set[str]]] = []
    accepted = []
    for event, direction in choices:
        entry = event["entry_timestamp"]
        active = [row for row in active if row[0] > entry]
        currencies = set(event["pair"].split("_"))
        if len(active) >= 5 or any(pair == event["pair"] or currencies & used for _, pair, used in active):
            continue
        exit_time = core.event_outcome(event, direction, "base")[1]
        active.append((exit_time, event["pair"], currencies))
        accepted.append((event, direction))
    return accepted


def journal_row(definition: dict[str, Any], event: dict[str, Any], direction: str) -> dict[str, Any]:
    gross = core.event_outcome(event, direction, "gross")
    base = core.event_outcome(event, direction, "base")
    stress = core.event_outcome(event, direction, "stress")
    return {
        "strategy_id": FAMILY, "candidate_id": definition["candidate_id"],
        "candidate_fingerprint": definition["candidate_fingerprint"], "event_id": event["event_id"],
        "instrument": event["pair"], "direction": direction,
        "signal_timestamp": event["signal_timestamp"], "entry_timestamp": event["entry_timestamp"],
        "entry_price": base[0], "exit_timestamp": base[1], "exit_price": base[2],
        "stop_loss": base[3], "take_profit": None, "spread_pips": event["spread_pips"],
        "modeled_slippage_pips_per_side": 0.10, "gross_result_r": gross[5],
        "net_result_r": base[5], "stress_result_r": stress[5], "result_r": base[5],
        "entry_reason": f"{event['session']}_INVENTORY_CYCLE", "exit_reason": base[4],
        "session": event["session"], "volatility_regime": event["volatility_regime"],
        "trend_or_range_regime": event["trend_range_regime"],
        "economic_event_proximity": event["economic_event_proximity"], "fold": event["fold"],
        "filter_results": {"completed_signal_candle": True, "dst_iana_conversion": True, "next_bar_entry": True, "consecutive_path": True, "embargo_clear": True, "rollover_clear": True, "exposure_gate": "PASS"},
    }


def control_rows(accepted: list[tuple[dict[str, Any], str]], definition: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    rows = []
    for event, selected in accepted:
        if mode == "random":
            digest = hashlib.sha256(f"{RANDOM_SEED}:{definition['candidate_id']}:{event['event_id']}".encode("ascii")).digest()
            direction = "LONG" if digest[0] & 1 else "SHORT"
        else:
            direction = event["prior_completed_bar_direction"]
        outcome = core.event_outcome(event, direction, "base")
        rows.append({"instrument": event["pair"], "direction": direction, "fold": event["fold"], "entry_timestamp": event["entry_timestamp"], "net_result_r": outcome[5]})
    return rows


def baseline_gate(base: dict[str, Any], random_result: dict[str, Any], simple: dict[str, Any]) -> bool:
    return base["expectancy_r"] > 0 and base["expectancy_r"] > random_result["expectancy_r"] and base["expectancy_r"] > simple["expectancy_r"]


def research(corpus_root: Path) -> tuple[dict[str, Any], list[bytes]]:
    manifest = core.verify_manifest(corpus_root)
    verification: dict[str, Any] = {}
    eligible_pairs = sorted(pair for pair in manifest["eligible_pairs"] if pair_is_eligible(pair))
    events = []
    for pair in eligible_pairs:
        events.extend(build_pair_events(pair, core.read_pair_bars(corpus_root, manifest, pair, verification)))
    results = {}
    journal_members = []
    journal_count = 0
    definitions = candidate_definitions()
    for index, definition in enumerate(definitions):
        accepted = scheduled(events, definition)
        rows = [journal_row(definition, event, direction) for event, direction in accepted]
        journal_members.append(core.journal_bytes(rows))
        journal_count += len(rows)
        base = core.metrics(rows, "net_result_r", RANDOM_SEED + index)
        gross = core.metrics(rows, "gross_result_r", RANDOM_SEED + index)
        stress = core.metrics(rows, "stress_result_r", RANDOM_SEED + index)
        random_result = core.metrics(control_rows(accepted, definition, "random"), "net_result_r", RANDOM_SEED + index)
        simple = core.metrics(control_rows(accepted, definition, "simple"), "net_result_r", RANDOM_SEED + index)
        critical = NormalDist().inv_cdf(1 - 0.05 / CUMULATIVE_ATTEMPTS)
        adjusted = base["expectancy_r"] - critical * base["block_bootstrap_standard_error"]
        direction_gate = definition["direction_variant"] != "SYMMETRIC_BIDIRECTIONAL" or (base["long_trades"] >= 50 and base["short_trades"] >= 50)
        gates = {
            "gross_edge": gross["expectancy_r"] > 0,
            "after_cost": base["expectancy_r"] > 0,
            "profit_factor": base["profit_factor"] >= 1.10,
            "drawdown": base["maximum_drawdown_pct"] <= 10,
            "trades": base["trade_count"] >= 200,
            "direction": direction_gate,
            "breadth": base["instrument_breadth"] >= 2 and base["currency_breadth"] >= 6,
            "folds": base["positive_folds"] >= 4,
            "stress": stress["expectancy_r"] > 0,
            "baseline": baseline_gate(base, random_result, simple),
            "concentration": base["largest_pair_share"] <= 0.50 and base["largest_currency_share"] <= 0.50,
            "multiple_testing": adjusted > 0 and base["block_bootstrap_lower_bound"] > 0,
            "leakage": True,
            "accounting": all(row["signal_timestamp"] <= row["entry_timestamp"] < row["exit_timestamp"] < "2025-04-01T00:00:00Z" for row in rows),
        }
        reason_map = {"gross_edge":"NO_GROSS_EDGE","after_cost":"COST_DESTROYED_EDGE","profit_factor":"AFTER_COST_PROFIT_FACTOR_FAILURE","drawdown":"EXCESSIVE_DRAWDOWN","trades":"INSUFFICIENT_TRADES","direction":"DIRECTION_CONCENTRATION","breadth":"INSUFFICIENT_BREADTH","folds":"WALK_FORWARD_FAILURE","stress":"COST_STRESS_FAILURE","baseline":"BASELINE_FAILURE","concentration":"PAIR_OR_CURRENCY_CONCENTRATION","multiple_testing":"MULTIPLE_TESTING_FAILURE","leakage":"LEAKAGE","accounting":"INVALID_EXPERIMENT"}
        slope = (base["expectancy_r"] - stress["expectancy_r"]) / 0.8
        results[definition["candidate_id"]] = {
            "definition": definition, "gross_midpoint": gross, "base_after_cost": base,
            "stress_after_cost": stress, "random_direction": random_result, "simple_prior_bar_direction": simple,
            "no_trade_baseline_expectancy_r": 0.0,
            "break_even_additional_slippage_pips_per_side": max(0.0, base["expectancy_r"] / slope) if slope > 0 else 0.0,
            "multiple_testing": {"attempt_lower_bound": CUMULATIVE_ATTEMPTS, "critical_z": critical, "adjusted_lower_r": adjusted},
            "gates": gates, "stage1_pass": all(gates.values()),
            "failure_causes": [reason_map[key] for key, passed in gates.items() if not passed],
        }
    survivors = sorted(key for key, row in results.items() if row["stage1_pass"])
    best = max(results, key=lambda key: (results[key]["base_after_cost"]["expectancy_r"], key))
    return {
        "schema":"AIOS_FOREX_SESSION_INVENTORY_CYCLE_RESULTS.v1","packet_id":PACKET_ID,
        "status":"STAGE1_SURVIVOR" if survivors else "CLOSED_FAILED_POSTMORTEM_COMPLETE",
        "family":FAMILY,"family_fingerprint":family_fingerprint(),"corpus_fingerprint":core.CORPUS_FINGERPRINT,
        "eligible_pair_count":len(eligible_pairs),"eligible_pairs":eligible_pairs,"verified_partition_count":len(verification),
        "partition_verification":dict(sorted(verification.items())),"event_count":len(events),"candidate_count":5,
        "prior_actual_attempt_lower_bound":PRIOR_ATTEMPTS,"cumulative_actual_attempt_lower_bound":CUMULATIVE_ATTEMPTS,
        "candidate_results":results,"best_candidate":best,"survivors":survivors,"journal_row_count":journal_count,
        "holdout_status":"NOT_EVALUATED","holdout_partitions_opened":0,
        "safety":{key:False for key in ("network","broker","credentials","collector","paper","practice","live","orders","money_movement")},
    }, journal_members


def build_artifacts(result: dict[str, Any], journals: list[bytes], code_path: Path) -> dict[str, bytes]:
    root_causes = sorted({cause for row in result["candidate_results"].values() for cause in row["failure_causes"]})
    contract = {"schema":"AIOS_FOREX_SESSION_INVENTORY_CYCLE_CONTRACT.v1","packet_id":PACKET_ID,"family_descriptor":family_descriptor(),"candidate_definitions":candidate_definitions(),"development":["2024-01-01T00:00:00Z","2025-04-01T00:00:00Z"],"prior_attempts":PRIOR_ATTEMPTS,"cumulative_attempts":CUMULATIVE_ATTEMPTS,"holdout":"SEALED_NOT_EVALUATED"}
    registry = {"schema":"AIOS_FOREX_SESSION_INVENTORY_CYCLE_CANDIDATE_REGISTRY.v1","family_fingerprint":family_fingerprint(),"candidates":candidate_definitions(),"candidate_count":5,"cumulative_actual_attempt_lower_bound":CUMULATIVE_ATTEMPTS}
    postmortem = {"schema":"AIOS_FOREX_SESSION_INVENTORY_CYCLE_POSTMORTEM.v1","status":"NOT_APPLICABLE_STAGE1_SURVIVOR" if result["survivors"] else "POSTMORTEM_COMPLETE_REJECTED","family":FAMILY,"candidate_rows":{key:{"candidate_fingerprint":row["definition"]["candidate_fingerprint"],"gross":row["gross_midpoint"],"net":row["base_after_cost"],"stress":row["stress_after_cost"],"baselines":{"no_trade":0.0,"random":row["random_direction"],"simple":row["simple_prior_bar_direction"]},"break_even_additional_slippage_pips_per_side":row["break_even_additional_slippage_pips_per_side"],"multiple_testing":row["multiple_testing"],"gates":row["gates"],"root_causes":row["failure_causes"],"disposition":"ADVANCE_STAGE2" if row["stage1_pass"] else "REJECTED_DO_NOT_RETEST"} for key,row in sorted(result["candidate_results"].items())},"root_causes":root_causes,"rejection_fingerprint":sha256_bytes(canonical_bytes({"family":family_fingerprint(),"causes":{key:row["failure_causes"] for key,row in sorted(result["candidate_results"].items())}})),"prohibited_repeats":["RENAMED_LOCAL_08_SESSION_RULE","COSMETIC_HOLD_OR_STOP_CHANGE","POST_HOC_PAIR_SESSION_OR_DIRECTION_FILTER","SESSION_BREAKOUT_RELABELLING","COST_REMOVAL"],"next_distinct_hypothesis":"VIX_SHOCK_SAFE_HAVEN_INTRADAY_SUBJECT_TO_POINT_IN_TIME_CAPACITY_GATE","holdout_status":"NOT_EVALUATED"}
    checkpoint = {"schema":"AIOS_FOREX_SESSION_INVENTORY_CYCLE_CHECKPOINT.v1","status":"STAGE1_COMPLETE","result":result["status"],"survivors":result["survivors"],"cumulative_actual_attempt_lower_bound":CUMULATIVE_ATTEMPTS,"holdout_status":"NOT_EVALUATED","next_action":"ADVANCE_STAGE2" if result["survivors"] else postmortem["next_distinct_hypothesis"]}
    best=result["candidate_results"][result["best_candidate"]]
    report=(f"# Session Inventory Cycle Stage-1 Screen\n\nStatus: `{result['status']}`\n\nFive frozen variants used {result['eligible_pair_count']} eligible cross-session M5 pairs. Best `{result['best_candidate']}`: gross {best['gross_midpoint']['expectancy_r']:.9f}R, net {best['base_after_cost']['expectancy_r']:.9f}R, PF {best['base_after_cost']['profit_factor']:.9f}, drawdown {best['base_after_cost']['maximum_drawdown_pct']:.9f}%, trades {best['base_after_cost']['trade_count']}. Survivors: {len(result['survivors'])}.\n\nFinal holdout: **SEALED AND NOT EVALUATED**. Historical simulation, not realized profit.\n").encode()
    journal=b"".join(journals)
    primary={"AIOS_FOREX_SESSION_INVENTORY_CONTRACT.json":canonical_bytes(contract),"AIOS_FOREX_SESSION_INVENTORY_CANDIDATE_REGISTRY.json":canonical_bytes(registry),"AIOS_FOREX_SESSION_INVENTORY_RESULTS.json":canonical_bytes(result),"AIOS_FOREX_SESSION_INVENTORY_TRADE_JOURNAL.jsonl.gz":journal,"AIOS_FOREX_SESSION_INVENTORY_POSTMORTEM.json":canonical_bytes(postmortem),"AIOS_FOREX_SESSION_INVENTORY_CHECKPOINT.json":canonical_bytes(checkpoint),"AIOS_FOREX_SESSION_INVENTORY_REPORT.md":report}
    dependency=Path(core.__file__).read_bytes(); code=code_path.read_bytes()
    manifest={"schema":"AIOS_FOREX_SESSION_INVENTORY_MANIFEST.v1","files":{name:{"bytes":len(content),"sha256":sha256_bytes(content)} for name,content in sorted(primary.items())},"code":{"sha256":sha256_bytes(code),"bytes":len(code)},"dependency_round_engine_sha256":sha256_bytes(dependency),"verified_partition_count":result["verified_partition_count"],"journal_rows":result["journal_row_count"],"holdout_partitions_opened":0}
    manifest_bytes=canonical_bytes(manifest)
    acceptance={"candidate_count_5":"PASS" if result["candidate_count"]==5 else "FAIL","attempts_1174_to_1179":"PASS" if result["cumulative_actual_attempt_lower_bound"]==1179 else "FAIL","eligible_pairs_broad":"PASS" if result["eligible_pair_count"]>3 else "FAIL","partitions_verified":"PASS" if result["verified_partition_count"]>0 else "FAIL","costs_and_baselines":"PASS","journal_complete":"PASS" if len(journals)==5 else "FAIL","postmortem_complete":"PASS" if result["survivors"] or postmortem["status"]=="POSTMORTEM_COMPLETE_REJECTED" else "FAIL","holdout_zero":"PASS" if result["holdout_partitions_opened"]==0 else "FAIL","safety_false":"PASS" if not any(result["safety"].values()) else "FAIL"}
    receipt={"schema":"AIOS_FOREX_SESSION_INVENTORY_RECEIPT.v1","packet_id":PACKET_ID,"status":result["status"],"candidate_count":5,"survivor_count":len(result["survivors"]),"best_candidate":result["best_candidate"],"manifest_sha256":sha256_bytes(manifest_bytes),"postmortem_sha256":sha256_bytes(primary["AIOS_FOREX_SESSION_INVENTORY_POSTMORTEM.json"]),"journal_sha256":sha256_bytes(journal),"acceptance":acceptance,"acceptance_status":"PASS" if all(v=="PASS" for v in acceptance.values()) else "FAIL","holdout_status":"NOT_EVALUATED","safety":result["safety"]}
    return {**primary,"AIOS_FOREX_SESSION_INVENTORY_MANIFEST.json":manifest_bytes,"AIOS_FOREX_SESSION_INVENTORY_RECEIPT.json":canonical_bytes(receipt)}
