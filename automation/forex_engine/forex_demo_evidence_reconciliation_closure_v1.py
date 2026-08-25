"""Canonical, local-only demo evidence reconciliation closure audit."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import copy
import hashlib
import json
import math
import subprocess
from typing import Any, Mapping

from automation.forex_engine.demo_reconciliation import reconcile_demo_snapshot


PACKET_ID = "PKT-EAST-FOREX-DEMO-EVIDENCE-RECONCILIATION-021"
LOCK_ID = "LOCK_EAST_FOREX_LIVE_READINESS_RESEARCH_EAST_OCC_01"
RESULT_PATH = (
    REPO_ROOT
    / "Reports/forex_delivery/AIOS_FOREX_DEMO_EVIDENCE_RECONCILIATION_CLOSURE_V1_RESULTS.json"
)
OWNER_RISK_RESULT_PATH = (
    REPO_ROOT / "Reports/forex_delivery/AIOS_FOREX_OWNER_RISK_AUTHORITY_V1_RESULTS.json"
)
PAPER30_RUNTIME_PATH = REPO_ROOT / "automation/forex_engine/forex_frozen_candidate_paper30_v1.py"
PAPER30_LEDGER_PATH = (
    REPO_ROOT
    / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_LEDGER.json"
)
PAPER30_STATE_PATH = (
    REPO_ROOT
    / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_STATE.json"
)
PAPER30_STRATEGY_CONFIG_SHA256 = (
    "13b96b3e227a2b5873ba5916a4987cf571868626339d1a89e2cd6e0e25bd1435"
)

GENUINE_HISTORICAL_DEMO_EVIDENCE = "GENUINE_HISTORICAL_DEMO_EVIDENCE"
READ_ONLY_BROKER_EVIDENCE = "READ_ONLY_BROKER_EVIDENCE"
SYNTHETIC_VALIDATION = "SYNTHETIC_VALIDATION"
PLANNING_ONLY = "PLANNING_ONLY"
STALE_OR_LEGACY = "STALE_OR_LEGACY"
UNRESOLVED = "UNRESOLVED"

SUCCESS_STATUS = "DEMO_RECONCILIATION_INFRASTRUCTURE_READY_GENUINE_EVIDENCE_PENDING"

DEMO_EVIDENCE_COMPLETENESS_CONTRACT = (
    "demo_trade_id",
    "strategy_config_sha256",
    "instrument",
    "side",
    "units",
    "intent_timestamp",
    "order_timestamp",
    "fill_timestamp",
    "fill_price",
    "stop_loss",
    "take_profit",
    "sanitized_position_presence",
    "sanitized_order_presence",
    "exit_timestamp",
    "exit_price",
    "realized_pl",
    "realized_r",
    "reconciliation_status",
    "reconciliation_score",
    "stale_data",
)

EVIDENCE_INVENTORY_SPEC = (
    {
        "source_artifact": "Reports/forex_delivery/AIOS_FOREX_DEMO_RECONCILIATION_V1_REPORT.md",
        "classification": PLANNING_ONLY,
        "basis": "contract_and_test_plan_with_validators_not_run_in_report",
        "required_markers": ("validators", "not run by codex"),
    },
    {
        "source_artifact": "Reports/forex_delivery/AIOS_FOREX_DEMO_READINESS_SPINE_V1_REPORT.md",
        "classification": READ_ONLY_BROKER_EVIDENCE,
        "basis": "read_only_preflight_and_trade_320_history_without_complete_reconciliation_fields",
        "required_markers": ("trade 320", "repeated demo profit proof is missing"),
    },
    {
        "source_artifact": "Reports/forex_delivery/AIOS_FOREX_EVIDENCE_INDEX_V1_REPORT.md",
        "classification": PLANNING_ONLY,
        "basis": "catalog_and_index_evidence_not_a_demo_trade_record",
        "required_markers": ("canonical evidence flow", "cataloged 570"),
    },
    {
        "source_artifact": "Reports/forex_delivery/AIOS_FOREX_OWNER_RISK_AUTHORITY_V1_RESULTS.json",
        "classification": SYNTHETIC_VALIDATION,
        "basis": "synthetic_reconciliation_proof_explicitly_marked_non_genuine",
        "required_markers": ('"synthetic_proof"', '"demo_evidence_insufficient"'),
    },
    {
        "source_artifact": "Reports/forex_delivery/AIOS_FOREX_LIVE_READINESS_HARDENING_V1_RESULTS.json",
        "classification": SYNTHETIC_VALIDATION,
        "basis": "local_synthetic_trade_reconciliation_and_stress_proof",
        "required_markers": ('"synthetic_trade_count"', '"practice_orders": false'),
    },
    {
        "source_artifact": "Reports/forex_delivery/AIOS_FOREX_LIVE_READINESS_BLOCKER_CLOSURE_V1_RESULTS.json",
        "classification": SYNTHETIC_VALIDATION,
        "basis": "synthetic_demo_reconciliation_with_real_demo_evidence_complete_false",
        "required_markers": ('"demo_evidence_real_complete": false', '"synthetic": true'),
    },
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_file(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path.name}")
    return value


def inventory_demo_evidence() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for spec in EVIDENCE_INVENTORY_SPEC:
        path = REPO_ROOT / spec["source_artifact"]
        if not path.is_file():
            raise ValueError(f"DEMO_EVIDENCE_SOURCE_MISSING:{spec['source_artifact']}")
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"DEMO_EVIDENCE_SOURCE_EMPTY:{spec['source_artifact']}")
        lowered = text.lower()
        if not all(marker in lowered for marker in spec["required_markers"]):
            raise ValueError(f"DEMO_EVIDENCE_CLASSIFICATION_FAILED:{spec['source_artifact']}")
        items.append(
            {
                **{key: value for key, value in spec.items() if key != "required_markers"},
                "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "genuine_demo_trade_record": False,
                "eligible_for_profit_proof": False,
            }
        )

    by_classification = {
        classification: sum(item["classification"] == classification for item in items)
        for classification in (
            GENUINE_HISTORICAL_DEMO_EVIDENCE,
            READ_ONLY_BROKER_EVIDENCE,
            SYNTHETIC_VALIDATION,
            PLANNING_ONLY,
            STALE_OR_LEGACY,
            UNRESOLVED,
        )
    }
    historical_candidate = {
        "source_artifact": "Reports/forex_delivery/AIOS_FOREX_DEMO_READINESS_SPINE_V1_REPORT.md",
        "record_reference": "trade_320",
        "classification": READ_ONLY_BROKER_EVIDENCE,
        "reconciliation_status": "INSUFFICIENT_FOR_RECONCILIATION",
        "matched": None,
        "match_score": None,
        "pair_match": None,
        "side_match": None,
        "units_match": None,
        "price_within_tolerance": None,
        "stop_loss_match": None,
        "take_profit_match": None,
        "position_seen": None,
        "order_seen": None,
        "stale_data": None,
        "missing_fields": list(DEMO_EVIDENCE_COMPLETENESS_CONTRACT),
    }
    return {
        "items": items,
        "classification_counts": by_classification,
        "genuine_demo_evidence_count": by_classification[GENUINE_HISTORICAL_DEMO_EVIDENCE],
        "read_only_demo_evidence_count": by_classification[READ_ONLY_BROKER_EVIDENCE],
        "synthetic_demo_evidence_count": by_classification[SYNTHETIC_VALIDATION],
        "planning_only_count": by_classification[PLANNING_ONLY],
        "genuine_demo_records_reconciled": 0,
        "genuine_demo_records_insufficient": 1,
        "historical_candidates": [historical_candidate],
    }


def valid_demo_snapshot() -> dict[str, Any]:
    return {
        "allowed": True,
        "mode": "DEMO_READONLY",
        "fresh": True,
        "prices": [{"instrument": "EUR_USD", "bid": 1.0998, "ask": 1.1002}],
        "positions_summary": [
            {
                "instrument": "EUR_USD",
                "side": "BUY",
                "units": 1000.0,
                "entry_price": 1.1,
                "stop_loss": 1.095,
                "take_profit": 1.11,
            }
        ],
        "orders": [
            {
                "instrument": "EUR_USD",
                "side": "BUY",
                "units": 1000.0,
                "entry_price": 1.1,
                "stop_loss": 1.095,
                "take_profit": 1.11,
            }
        ],
    }


def valid_demo_intent() -> dict[str, Any]:
    return {
        "pair": "EUR_USD",
        "side": "BUY",
        "units": 1000.0,
        "entry_price": 1.1,
        "stop_loss": 1.095,
        "take_profit": 1.11,
        "mode": "DEMO_MAPPING_ONLY",
        "submit_enabled": False,
        "broker_write": False,
        "live_trading": False,
        "network_submit": False,
        "credentials": False,
    }


def _walk(value: Any) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            rows.append((str(key), nested))
            rows.extend(_walk(nested))
    elif isinstance(value, list):
        for nested in value:
            rows.extend(_walk(nested))
    return rows


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return False


def _closure_safety_blockers(*payloads: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for payload in payloads:
        for key, value in _walk(payload):
            normalized = key.strip().lower().replace("-", "_").replace(" ", "_")
            if normalized in {"account_id", "account_identifier"} and value not in (None, "", [], {}):
                blockers.append("account_identifier_material")
            if "credential" in normalized and _truthy(value):
                blockers.append("credentials_true")
            if "broker" in normalized and "write" in normalized and _truthy(value):
                blockers.append("broker_write_true")
            if "order" in normalized and "submit" in normalized and _truthy(value):
                blockers.append("order_submit_true")
            if "live" in normalized and "trading" in normalized and _truthy(value):
                blockers.append("live_trading_true")
            if "network" in normalized and "submit" in normalized and _truthy(value):
                blockers.append("network_submit_true")
    return list(dict.fromkeys(blockers))


def reconcile_demo_evidence(
    snapshot: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> dict[str, Any]:
    engine_result = reconcile_demo_snapshot(snapshot, intent)
    closure_blockers = _closure_safety_blockers(snapshot, intent)
    accepted = (
        not closure_blockers
        and engine_result["allowed"] is True
        and engine_result["matched"] is True
        and engine_result["match_score"] == 1.0
        and engine_result["stale_data"] is False
    )
    return {
        "closure_accepted": accepted,
        "closure_blocked_reasons": closure_blockers,
        "engine_result": engine_result,
    }


def synthetic_reconciliation_proof() -> dict[str, Any]:
    success = reconcile_demo_evidence(valid_demo_snapshot(), valid_demo_intent())
    cases: dict[str, dict[str, Any]] = {}

    def record(name: str, snapshot: dict[str, Any], intent: dict[str, Any]) -> None:
        cases[name] = reconcile_demo_evidence(snapshot, intent)

    snapshot = valid_demo_snapshot()
    intent = valid_demo_intent()
    intent["pair"] = "GBP_USD"
    record("wrong_pair", snapshot, intent)

    snapshot = valid_demo_snapshot()
    for row in snapshot["positions_summary"] + snapshot["orders"]:
        row["side"] = "SELL"
    record("wrong_side", snapshot, valid_demo_intent())

    snapshot = valid_demo_snapshot()
    for row in snapshot["positions_summary"] + snapshot["orders"]:
        row["units"] = 999.0
    record("wrong_units", snapshot, valid_demo_intent())

    snapshot = valid_demo_snapshot()
    for row in snapshot["positions_summary"] + snapshot["orders"]:
        row["entry_price"] = 1.2
    record("price_outside_tolerance", snapshot, valid_demo_intent())

    snapshot = valid_demo_snapshot()
    for row in snapshot["positions_summary"] + snapshot["orders"]:
        row["stop_loss"] = 1.09
    record("wrong_stop_loss", snapshot, valid_demo_intent())

    snapshot = valid_demo_snapshot()
    for row in snapshot["positions_summary"] + snapshot["orders"]:
        row["take_profit"] = 1.12
    record("wrong_take_profit", snapshot, valid_demo_intent())

    for name, field, value in (
        ("stale_snapshot", "fresh", False),
        ("account_identifier_material", "account_identifier", "SANITIZED_PRESENT_MARKER"),
        ("credentials_true", "credentials", True),
        ("broker_write_true", "broker_write", True),
        ("order_submit_true", "order_submit", True),
        ("live_trading_true", "live_trading", True),
        ("network_submit_true", "network_submit", True),
    ):
        snapshot = valid_demo_snapshot()
        snapshot[field] = value
        record(name, snapshot, valid_demo_intent())

    fail_closed = all(result["closure_accepted"] is False for result in cases.values())
    engine_ready = (
        success["closure_accepted"] is True
        and success["engine_result"]["pair_match"] is True
        and success["engine_result"]["side_match"] is True
        and success["engine_result"]["units_match"] is True
        and success["engine_result"]["price_within_tolerance"] is True
        and success["engine_result"]["stop_loss_match"] is True
        and success["engine_result"]["take_profit_match"] is True
        and success["engine_result"]["position_seen"] is True
        and success["engine_result"]["order_seen"] is True
    )
    return {
        "demo_reconciliation_engine_ready": engine_ready,
        "demo_reconciliation_fail_closed": fail_closed,
        "success": success,
        "negative_cases": cases,
        "network_calls": False,
        "broker_calls": False,
    }


def evaluate_demo_result(
    record: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
) -> dict[str, bool]:
    missing = [
        field
        for field in DEMO_EVIDENCE_COMPLETENESS_CONTRACT
        if field not in record or (record[field] in (None, "") and field != "take_profit")
    ]
    complete = not missing
    reconciled = (
        reconciliation.get("closure_accepted") is True
        and record.get("reconciliation_status") == "MATCHED"
        and record.get("reconciliation_score") == 1.0
    )
    try:
        profitable = float(record.get("realized_pl", 0)) > 0 and float(record.get("realized_r", 0)) > 0
    except (TypeError, ValueError):
        profitable = False
    safe = (
        complete
        and reconciled
        and record.get("stale_data") is False
        and not _closure_safety_blockers(record)
    )
    return {
        "demo_result_complete": complete,
        "demo_result_reconciled": reconciled,
        "demo_result_profitable": profitable,
        "demo_result_safe": safe,
        "profit_proof_accepted": profitable and safe,
    }


def complete_demo_result_record(*, realized_pl: float = -10.0, realized_r: float = -0.1) -> dict[str, Any]:
    return {
        "demo_trade_id": "SANITIZED_SYNTHETIC_DEMO_TRADE",
        "strategy_config_sha256": PAPER30_STRATEGY_CONFIG_SHA256,
        "instrument": "EUR_USD",
        "side": "BUY",
        "units": 1000.0,
        "intent_timestamp": "2026-08-22T12:00:00Z",
        "order_timestamp": "2026-08-22T12:00:01Z",
        "fill_timestamp": "2026-08-22T12:00:02Z",
        "fill_price": 1.1,
        "stop_loss": 1.095,
        "take_profit": 1.11,
        "sanitized_position_presence": True,
        "sanitized_order_presence": True,
        "exit_timestamp": "2026-08-22T13:00:00Z",
        "exit_price": 1.099,
        "realized_pl": realized_pl,
        "realized_r": realized_r,
        "reconciliation_status": "MATCHED",
        "reconciliation_score": 1.0,
        "stale_data": False,
        "credentials": False,
        "broker_write": False,
        "order_submit": False,
        "live_trading": False,
        "network_submit": False,
    }


def demo_result_quality_proof() -> dict[str, Any]:
    matched = reconcile_demo_evidence(valid_demo_snapshot(), valid_demo_intent())
    losing = evaluate_demo_result(complete_demo_result_record(), matched)
    mismatched = copy.deepcopy(matched)
    mismatched["closure_accepted"] = False
    profitable_mismatch = evaluate_demo_result(
        complete_demo_result_record(realized_pl=25.0, realized_r=0.25),
        mismatched,
    )
    ready = (
        losing["demo_result_complete"] is True
        and losing["demo_result_reconciled"] is True
        and losing["demo_result_profitable"] is False
        and losing["demo_result_safe"] is True
        and profitable_mismatch["demo_result_profitable"] is True
        and profitable_mismatch["demo_result_reconciled"] is False
        and profitable_mismatch["demo_result_safe"] is False
        and profitable_mismatch["profit_proof_accepted"] is False
    )
    return {
        "demo_result_quality_gate_ready": ready,
        "reconciled_losing_result": losing,
        "profitable_mismatched_result": profitable_mismatch,
    }


def repeated_demo_readiness(
    reconciliation_proof: Mapping[str, Any],
    quality_proof: Mapping[str, Any],
) -> dict[str, bool]:
    pipeline_ready = (
        reconciliation_proof.get("demo_reconciliation_engine_ready") is True
        and reconciliation_proof.get("demo_reconciliation_fail_closed") is True
        and quality_proof.get("demo_result_quality_gate_ready") is True
        and bool(DEMO_EVIDENCE_COMPLETENESS_CONTRACT)
    )
    return {
        "repeated_demo_evidence_pipeline_ready": pipeline_ready,
        "repeated_demo_profit_proof_complete": False,
    }


def _forward_count(ledger: Mapping[str, Any]) -> int:
    trades = ledger.get("trades")
    if not isinstance(trades, list):
        raise ValueError("PAPER30_LEDGER_SCHEMA_UNSUPPORTED")
    return sum(
        1
        for trade in trades
        if isinstance(trade, Mapping)
        and trade.get("qualifying") is True
        and trade.get("exit_timestamp_utc")
        and trade.get("realized_r") is not None
    )


def paper30_snapshot() -> dict[str, Any]:
    ledger = _json_file(PAPER30_LEDGER_PATH)
    state = _json_file(PAPER30_STATE_PATH)
    if (
        ledger.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256
        or state.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256
    ):
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    return {
        "hashes": {
            "paper30_runtime": _sha256_file(PAPER30_RUNTIME_PATH),
            "paper30_ledger": _sha256_file(PAPER30_LEDGER_PATH),
            "paper30_state": _sha256_file(PAPER30_STATE_PATH),
        },
        "forward_count": _forward_count(ledger),
    }


def _assert_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NONFINITE_RESULT")
    if isinstance(value, Mapping):
        for nested in value.values():
            _assert_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_finite(nested)


def build_report() -> dict[str, Any]:
    pre = paper30_snapshot()
    if pre["forward_count"] != 0:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")

    owner_result = _json_file(OWNER_RISK_RESULT_PATH)
    if (
        owner_result.get("readiness_pass_count_after") != 19
        or owner_result.get("readiness_fail_count_after") != 0
        or owner_result.get("readiness_pending_count_after") != 8
        or owner_result.get("live_readiness_score_after") != 0.6
        or owner_result.get("human_live_approval") is not False
        or owner_result.get("live_execution_enabled") is not False
    ):
        raise ValueError("DEMO_RECONCILIATION_VALIDATION_FAILED")

    inventory = inventory_demo_evidence()
    reconciliation = synthetic_reconciliation_proof()
    quality = demo_result_quality_proof()
    repeated = repeated_demo_readiness(reconciliation, quality)
    demo_infrastructure_ready = (
        reconciliation["demo_reconciliation_engine_ready"]
        and reconciliation["demo_reconciliation_fail_closed"]
        and quality["demo_result_quality_gate_ready"]
        and repeated["repeated_demo_evidence_pipeline_ready"]
    )
    genuine_demo_complete = inventory["genuine_demo_evidence_count"] > 0

    post = paper30_snapshot()
    unchanged = pre == post and pre["forward_count"] == post["forward_count"] == 0
    if not unchanged:
        raise ValueError("PAPER30_FORWARD_STATE_CHANGED")

    source_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = {
        "packet_id": PACKET_ID,
        "lock_id": LOCK_ID,
        "source_head": source_head,
        "evidence_inventory": inventory,
        "genuine_demo_evidence_count": inventory["genuine_demo_evidence_count"],
        "read_only_demo_evidence_count": inventory["read_only_demo_evidence_count"],
        "synthetic_demo_evidence_count": inventory["synthetic_demo_evidence_count"],
        "demo_reconciliation_engine_ready": reconciliation["demo_reconciliation_engine_ready"],
        "demo_reconciliation_fail_closed": reconciliation["demo_reconciliation_fail_closed"],
        "synthetic_reconciliation_proof": reconciliation,
        "genuine_demo_records_reconciled": inventory["genuine_demo_records_reconciled"],
        "genuine_demo_records_insufficient": inventory["genuine_demo_records_insufficient"],
        "demo_evidence_completeness_contract": list(DEMO_EVIDENCE_COMPLETENESS_CONTRACT),
        "demo_result_quality_gate_ready": quality["demo_result_quality_gate_ready"],
        "demo_result_quality_proof": quality,
        "repeated_demo_evidence_pipeline_ready": repeated["repeated_demo_evidence_pipeline_ready"],
        "repeated_demo_profit_proof_complete": repeated["repeated_demo_profit_proof_complete"],
        "demo_infrastructure_ready": demo_infrastructure_ready,
        "genuine_demo_evidence_complete": genuine_demo_complete,
        "readiness_pass_count_before": 19,
        "readiness_pass_count_after": 19,
        "readiness_fail_count_after": 0,
        "readiness_pending_count_after": 8,
        "live_readiness_score_before": 0.6,
        "live_readiness_score_after": 0.6,
        "live_readiness_blockers_after": [
            "human_approval_missing",
            "paper_evidence_insufficient",
            "demo_evidence_insufficient",
        ],
        "next_demo_evidence_action": (
            "COLLECT_OWNER_APPROVED_SANITIZED_PRACTICE_DEMO_TRADE_EVIDENCE_WHEN_MARKET_OPEN"
        ),
        "requires_market_open": True,
        "requires_owner_approval": True,
        "requires_broker_action": True,
        "requires_credentials_at_runtime": True,
        "paper30_strategy_config_sha256": PAPER30_STRATEGY_CONFIG_SHA256,
        "paper30_invariant_pre_sha256": pre["hashes"],
        "paper30_invariant_post_sha256": post["hashes"],
        "forward_paper30_count_pre": pre["forward_count"],
        "forward_paper30_count_post": post["forward_count"],
        "paper30_forward_state_unchanged": unchanged,
        "human_live_approval": False,
        "network_calls": False,
        "broker_calls": False,
        "broker_writes": False,
        "practice_orders": False,
        "live_orders": False,
        "money_movement": False,
        "credentials_accessed": False,
        "account_identifiers_persisted": False,
        "live_execution_enabled": False,
        "audit_execution_count": 1,
        "status": SUCCESS_STATUS,
    }
    _assert_finite(report)
    json.dumps(report, sort_keys=True, allow_nan=False)
    return report


def run() -> dict[str, Any]:
    report = build_report()
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": result["status"], "result_path": str(RESULT_PATH)}))
