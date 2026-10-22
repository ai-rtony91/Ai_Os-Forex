from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

import automation.forex_engine.forex_p1_supertrend_session_postmortem_v1 as module


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    ROOT
    / "schemas"
    / "aios"
    / "forex"
    / "AIOS_FOREX_P1_SUPERTREND_SESSION_POSTMORTEM.v1.schema.json"
)


def trade(number: int, realized_pl: float) -> dict:
    minute = number * 3
    return {
        "trade_id": f"supertrend-paper-{number:03d}",
        "evidence_type": "paper",
        "strategy_id": "supertrend_pullback_v1",
        "strategy_name": "supertrend_pullback_v1",
        "mode": "PAPER_ONLY",
        "paper_only": True,
        "instrument": "EUR_USD",
        "direction": "BUY",
        "entry_timestamp_utc": f"2026-08-10T10:{minute:02d}:00Z",
        "exit_timestamp_utc": f"2026-08-10T10:{minute + 1:02d}:00Z",
        "entry_price": 1.1,
        "exit_price": 1.101 if realized_pl >= 0 else 1.099,
        "stop_price": 1.099,
        "target_price": 1.101,
        "quantity_or_units": 100,
        "realized_pl": realized_pl,
        "fees": 0,
        "risk_amount": 10,
        "exit_reason": "paper_target" if realized_pl >= 0 else "paper_stop",
        "entry_rationale": "sanitized supervised paper strategy signal",
        "evidence_source": "long_run_paper_supervisor",
        "reviewed_by": "human_owner",
        "review_timestamp_utc": f"2026-08-10T10:{minute + 1:02d}:00Z",
    }


def evidence(values: tuple[float, ...] = (10.0, -4.0, 0.0)) -> tuple[dict, dict]:
    records = [trade(index, value) for index, value in enumerate(values, start=1)]
    cumulative = 0.0
    results = []
    for index, record in enumerate(records, start=1):
        cumulative = round(cumulative + record["realized_pl"], 8)
        results.append(
            {
                "trade_number": index,
                "trade_id": record["trade_id"],
                "strategy_name": "supertrend_pullback_v1",
                "entry": record["entry_price"],
                "exit": record["exit_price"],
                "realized_paper_pl": record["realized_pl"],
                "cumulative_paper_pl": cumulative,
                "win_or_loss": (
                    "WIN"
                    if record["realized_pl"] > 0
                    else "LOSS"
                    if record["realized_pl"] < 0
                    else "FLAT"
                ),
            }
        )
    gross_profit = round(sum(value for value in values if value > 0), 8)
    gross_loss = round(abs(sum(value for value in values if value < 0)), 8)
    net_pl = round(sum(values), 8)
    equity = peak = drawdown = 0.0
    for value in values:
        equity = round(equity + value, 8)
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    ledger = {
        "version": module.LEDGER_VERSION,
        "records": records,
        **{name: False for name in module.LEDGER_SAFETY_FLAGS},
    }
    campaign = {
        "campaign_version": module.CAMPAIGN_VERSION,
        "campaign_status": "COMPLETE",
        "stop_reason": "TARGET_REACHED",
        "accepted_qualifying_trades": len(records),
        "current_trade_number": len(records),
        "qualifying_strategy_name": "supertrend_pullback_v1",
        "strategy_qualifying_trade_counts": {"supertrend_pullback_v1": len(records)},
        "trade_results": results,
        "net_pl": net_pl,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": round(gross_profit / gross_loss, 8) if gross_loss else "INFINITE",
        "maximum_drawdown": round(drawdown, 8),
        "expectancy": round(net_pl / len(values), 8),
        "p1_status": "READY_FOR_P2_REVIEW",
        "started_utc": "2026-08-10T10:00:00Z",
        "updated_utc": "2026-08-10T11:00:00Z",
        "completed_utc": "2026-08-10T11:00:00Z",
        **{name: False for name in module.CAMPAIGN_SAFETY_FLAGS},
    }
    return ledger, campaign


def build(values: tuple[float, ...] = (10.0, -4.0, 0.0)) -> dict:
    return module.build_supertrend_session_postmortem(*evidence(values))


def test_valid_deterministic_paper_session_is_schema_valid():
    result = build()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(result)
    assert result["calculated_metrics"]["trade_count"]["value"] == 3
    assert result["calculated_metrics"]["wins"]["value"] == 1
    assert result["calculated_metrics"]["losses"]["value"] == 1
    assert result["calculated_metrics"]["breakevens"]["value"] == 1
    invalid = copy.deepcopy(result)
    invalid["calculated_metrics"]["profit_factor"]["unexpected"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(invalid)


def test_identical_evidence_produces_identical_substantive_output():
    first = build()
    second = build()
    assert first == second
    assert module.stable_json(first) == module.stable_json(second)


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda ledger, campaign: ledger.update(records=[]), "postmortem_records_missing"),
        (lambda ledger, campaign: ledger.pop("records"), "postmortem_records_missing"),
        (
            lambda ledger, campaign: campaign.pop("accepted_qualifying_trades"),
            "postmortem_campaign_count_invalid",
        ),
    ],
)
def test_missing_evidence_fails_closed(mutate, error):
    ledger, campaign = evidence()
    mutate(ledger, campaign)
    with pytest.raises(module.PostmortemValidationError, match=f"^{error}$"):
        module.build_supertrend_session_postmortem(ledger, campaign)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda ledger, campaign: ledger.__setitem__("records", "not-a-list"),
        lambda ledger, campaign: ledger["records"].__setitem__(0, "not-a-record"),
        lambda ledger, campaign: campaign.__setitem__("campaign_status", "RUNNING"),
    ],
)
def test_malformed_or_unsupported_evidence_fails_closed(mutation):
    ledger, campaign = evidence()
    mutation(ledger, campaign)
    with pytest.raises(module.PostmortemValidationError):
        module.build_supertrend_session_postmortem(ledger, campaign)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda ledger, campaign: campaign.__setitem__("accepted_qualifying_trades", 99),
        lambda ledger, campaign: campaign.__setitem__("net_pl", 999),
        lambda ledger, campaign: campaign["trade_results"][0].__setitem__(
            "trade_id", "invented-trade"
        ),
        lambda ledger, campaign: ledger["records"][0].__setitem__(
            "strategy_name", "different_strategy"
        ),
    ],
)
def test_contradictory_evidence_fails_closed(mutation):
    ledger, campaign = evidence()
    mutation(ledger, campaign)
    with pytest.raises(module.PostmortemValidationError):
        module.build_supertrend_session_postmortem(ledger, campaign)


def test_trades_and_pnl_are_derived_only_from_reconciled_records():
    ledger, campaign = evidence((7.5, -2.25))
    result = module.build_supertrend_session_postmortem(ledger, campaign)
    assert result["evidence_lineage"]["trade_ids"] == [
        record["trade_id"] for record in ledger["records"]
    ]
    assert result["calculated_metrics"]["trade_count"]["value"] == len(ledger["records"])
    assert result["calculated_metrics"]["realized_paper_pl"]["value"] == 5.25


def test_unavailable_profit_factor_is_explicit_null():
    result = build((3.0, 2.0))
    metric = result["calculated_metrics"]["profit_factor"]
    assert metric == {
        "status": "UNAVAILABLE",
        "value": None,
        "reason": "NO_LOSING_TRADES",
    }
    assert result["unavailable_information"] == [
        {"field": "profit_factor", "reason": "NO_LOSING_TRADES"}
    ]


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_nan_and_infinity_are_rejected(nonfinite):
    ledger, campaign = evidence()
    ledger["records"][0]["realized_pl"] = nonfinite
    with pytest.raises(module.PostmortemValidationError, match="postmortem_trade_numeric_invalid"):
        module.build_supertrend_session_postmortem(ledger, campaign)
    with pytest.raises(module.PostmortemValidationError, match="postmortem_output_not_json_safe"):
        module.stable_json({"not_finite": nonfinite})


@pytest.mark.parametrize(
    ("key", "secret"),
    [
        ("authorization", "Bearer packet-secret"),
        ("account_id", "001-002-003"),
        ("broker_payload", {"private": "broker response body"}),
        ("note", "password=do-not-persist"),
    ],
)
def test_sensitive_material_never_appears_in_output_or_errors(key, secret):
    ledger, campaign = evidence()
    ledger["records"][0][key] = secret
    with pytest.raises(module.PostmortemValidationError) as raised:
        module.build_supertrend_session_postmortem(ledger, campaign)
    rendered_error = str(raised.value)
    assert "packet-secret" not in rendered_error
    assert "001-002-003" not in rendered_error
    assert "broker response body" not in rendered_error
    assert "do-not-persist" not in rendered_error
    clean = module.stable_json(build())
    assert "authorization" not in clean.lower()
    assert "account_id" not in clean.lower()
    assert "broker_payload" not in clean.lower()


def test_every_canonical_safety_field_accepts_exact_false():
    assert module.CANONICAL_FALSE_SAFETY_FIELDS
    assert all(
        module._contains_sensitive({field: False}) is False
        for field in module.CANONICAL_FALSE_SAFETY_FIELDS
    )


def test_every_canonical_safety_field_rejects_true():
    assert all(
        module._contains_sensitive({field: True}) is True
        for field in module.CANONICAL_FALSE_SAFETY_FIELDS
    )


@pytest.mark.parametrize(
    "invalid",
    [0, 1, "false", "False", "0", "", None, [], {}],
    ids=(
        "zero-int", "one-int", "lowercase-false", "uppercase-false",
        "zero-string", "empty-string", "none", "empty-list", "empty-object",
    ),
)
def test_canonical_safety_field_rejects_non_boolean_false(invalid):
    assert module._contains_sensitive({"credentials_loaded": invalid}) is True


def test_unrecognized_sensitive_key_is_rejected_even_when_false():
    assert module._contains_sensitive({"credential_cache_present": False}) is True


def test_nested_sensitive_material_remains_rejected():
    evidence_value = {
        "safe_metadata": {
            "nested": {"authorization": "Bearer nested-secret"},
        }
    }
    assert module._contains_sensitive(evidence_value) is True


def test_clean_postmortem_fixture_is_not_rejected_as_sensitive():
    result = build()
    assert result["schema"] == module.SCHEMA


def test_paper_only_and_no_broker_no_network_safety_flags_are_enforced():
    result = build()
    assert result["safety_flags"]["paper_only"] is True
    assert all(
        value is False
        for key, value in result["safety_flags"].items()
        if key != "paper_only"
    )
    ledger, campaign = evidence()
    ledger["broker_call_performed"] = True
    with pytest.raises(module.PostmortemValidationError, match="postmortem_ledger_authority_invalid"):
        module.build_supertrend_session_postmortem(ledger, campaign)


def test_missing_required_safety_flag_uses_authority_error():
    ledger, campaign = evidence()
    ledger.pop("broker_call_performed")
    with pytest.raises(
        module.PostmortemValidationError,
        match="^postmortem_ledger_authority_invalid$",
    ):
        module.build_supertrend_session_postmortem(ledger, campaign)


@pytest.mark.parametrize("invalid", [0, 1, "false", None])
def test_non_boolean_required_safety_flag_uses_authority_error(invalid):
    ledger, campaign = evidence()
    ledger["credentials_loaded"] = invalid
    with pytest.raises(
        module.PostmortemValidationError,
        match="^postmortem_ledger_authority_invalid$",
    ):
        module.build_supertrend_session_postmortem(ledger, campaign)


def test_valid_false_safety_flags_proceed_to_sensitive_scan():
    ledger, campaign = evidence()
    ledger["records"][0]["safe_metadata"] = {
        "nested": {"authorization": "Bearer nested-secret"}
    }
    with pytest.raises(
        module.PostmortemValidationError,
        match="^postmortem_sensitive_evidence_rejected$",
    ):
        module.build_supertrend_session_postmortem(ledger, campaign)


def test_stale_evidence_fails_closed():
    ledger, campaign = evidence()
    campaign["updated_utc"] = campaign["completed_utc"] = "2026-08-20T11:00:00Z"
    with pytest.raises(module.PostmortemValidationError, match="postmortem_evidence_stale"):
        module.build_supertrend_session_postmortem(ledger, campaign)


def test_module_introduces_no_prohibited_runtime_capability():
    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    imports = [line.strip() for line in source.splitlines() if line.startswith(("import ", "from "))]
    prohibited_imports = ("requests", "urllib", "httpx", "socket", "subprocess", "keyring")
    assert not any(name in line for line in imports for name in prohibited_imports)
    assert not hasattr(module, "place_order")
    assert not hasattr(module, "load_credentials")
    assert not hasattr(module, "create_scheduled_task")


def test_input_objects_are_not_modified():
    ledger, campaign = evidence()
    before = copy.deepcopy((ledger, campaign))
    module.build_supertrend_session_postmortem(ledger, campaign)
    assert (ledger, campaign) == before
