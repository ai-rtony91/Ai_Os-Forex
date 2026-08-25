from __future__ import annotations

import copy
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import automation.forex_engine.forex_frozen_candidate_paper30_v1 as paper30_module
from automation.forex_engine.forex_frozen_candidate_paper30_v1 import (
    ATR_PERIOD,
    CONFIRMATION,
    DIRECTION_POLICY,
    FrozenCandidatePaper30,
    GLOBAL_PAPER_POSITION_CAP,
    MACD_FILTER,
    MAX_ACTIVE_POSITIONS_PER_INSTRUMENT,
    PAPER_ONLY,
    PRACTICE_NETWORK_TIMEOUT_SECONDS,
    PRIMARY_EXIT_POLICY,
    SELL_ENABLED,
    SHADOW_5R_AUTHORITY,
    SENTINEL_INSTRUMENT,
    SUPERTREND_FACTOR,
    TIMEFRAME,
    market_data_fresh,
    json_safe_paper30_metrics,
    run_campaign_segment,
    strategy_config,
    strategy_config_sha256,
)
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClientError
import scripts.forex_delivery.run_forex_frozen_candidate_paper30_v1 as launcher


START = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
UNIVERSE = tuple(f"PAIR_{index:02d}" for index in range(68))
UNIVERSE_HASH = "a" * 64
CAMPAIGN_UNIVERSE = tuple(sorted(("EUR_USD", *(f"PAIR_{index:02d}" for index in range(67)))))
CAMPAIGN_UNIVERSE_HASH = "b" * 64
NOW = datetime(2026, 8, 24, 14, 0, tzinfo=timezone.utc)
EXPECTED_STRATEGY_HASH = "13b96b3e227a2b5873ba5916a4987cf571868626339d1a89e2cd6e0e25bd1435"
FIXED_UNIVERSE_HASH = "b6abe559dcaa9faa0a1e48217f97a12dc9043eb9595d2b946bf80f93035be142"


def engine() -> FrozenCandidatePaper30:
    return FrozenCandidatePaper30(UNIVERSE, UNIVERSE_HASH, START)


def open_position(
    paper: FrozenCandidatePaper30,
    instrument: str,
    *,
    minute: int = 1,
    entry: Decimal = Decimal("1.1000"),
    stop: Decimal = Decimal("1.0900"),
) -> None:
    signal_time = START + timedelta(minutes=minute)
    assert paper.observe_signal(instrument, "BUY", signal_time, stop)
    assert (
        paper.apply_quote(
            instrument,
            entry - Decimal("0.0002"),
            entry,
            signal_time + timedelta(seconds=10),
        )
        == "FILLED"
    )


def candle_payload(instrument: str, latest: datetime, count: int = 8) -> dict[str, Any]:
    candles = []
    for index in range(count):
        timestamp = latest - timedelta(minutes=5 * (count - index - 1))
        base = Decimal("1.1000") + Decimal(index) * Decimal("0.0001")
        candles.append(
            {
                "complete": True,
                "time": timestamp.isoformat().replace("+00:00", "Z"),
                "mid": {
                    "o": str(base),
                    "h": str(base + Decimal("0.0003")),
                    "l": str(base - Decimal("0.0003")),
                    "c": str(base + Decimal("0.0001")),
                },
                "volume": 1,
            }
        )
    return {"instrument": instrument, "granularity": "M5", "candles": candles}


class SyntheticPracticeClient:
    environment = "practice"
    timeout_seconds = PRACTICE_NETWORK_TIMEOUT_SECONDS

    def __init__(
        self,
        *,
        sentinel_latest: datetime = NOW - timedelta(minutes=5),
        sentinel_error: BaseException | None = None,
        fail_full_instrument: str | None = None,
        pricing_error: BaseException | None = None,
    ) -> None:
        self.sentinel_latest = sentinel_latest
        self.sentinel_error = sentinel_error
        self.fail_full_instrument = fail_full_instrument
        self.pricing_error = pricing_error
        self.calls: list[tuple[Any, ...]] = []

    def observation_candles(
        self, instrument: str, *, granularity: str, count: int, price: str
    ) -> dict[str, Any]:
        self.calls.append(("observation_candles", instrument, granularity, count, price))
        if count == 5:
            if self.sentinel_error is not None:
                raise self.sentinel_error
            return candle_payload(instrument, self.sentinel_latest, count=5)
        if instrument == self.fail_full_instrument:
            raise OandaReadOnlyClientError("NETWORK_ERROR_SANITIZED")
        return candle_payload(instrument, NOW - timedelta(minutes=5))

    def discover_instruments(self) -> dict[str, Any]:
        self.calls.append(("discover_instruments",))
        return {
            "instruments": [
                {"name": instrument, "type": "CURRENCY"}
                for instrument in CAMPAIGN_UNIVERSE
            ]
        }

    def pricing(self, instruments: tuple[str, ...]) -> dict[str, Any]:
        self.calls.append(("pricing", instruments))
        if self.pricing_error is not None:
            raise self.pricing_error
        return {"prices": []}


def patch_campaign_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        paper30_module,
        "load_fixed_universe",
        lambda: (CAMPAIGN_UNIVERSE, CAMPAIGN_UNIVERSE_HASH),
    )


def test_frozen_strategy_contract_and_68_pair_capacity() -> None:
    config = strategy_config(UNIVERSE_HASH)
    assert len(UNIVERSE) == GLOBAL_PAPER_POSITION_CAP == 68
    assert config == {
        "atr_period": 5,
        "confirmation": "TRUE_2_CLOSE",
        "direction": "BUY_ONLY",
        "exit_policy": "EXIT_A_BASELINE",
        "macd_filter": "NONE",
        "pair_universe_sha256": UNIVERSE_HASH,
        "paper_only": True,
        "supertrend_factor": 2.0,
        "timeframe": "M5",
    }
    assert (TIMEFRAME, DIRECTION_POLICY, ATR_PERIOD, SUPERTREND_FACTOR) == (
        "M5",
        "BUY_ONLY",
        5,
        2.0,
    )
    assert (CONFIRMATION, MACD_FILTER, PRIMARY_EXIT_POLICY) == (
        "TRUE_2_CLOSE",
        "NONE",
        "EXIT_A_BASELINE",
    )
    assert PAPER_ONLY is True and SELL_ENABLED is False
    assert MAX_ACTIVE_POSITIONS_PER_INSTRUMENT == 1


def test_forward_boundary_rejects_backfill_and_sell() -> None:
    paper = engine()
    assert paper.observe_signal("PAIR_00", "BUY", START, "1.09") is False
    assert paper.observe_signal("PAIR_00", "BUY", START - timedelta(minutes=5), "1.09") is False
    assert paper.historical_backfill_trade_count == 0
    with pytest.raises(ValueError, match="SELL_DISABLED"):
        paper.observe_signal("PAIR_00", "SELL", START + timedelta(minutes=1), "1.09")
    assert paper.ledger == []


def test_pending_fill_is_strictly_after_signal_and_no_pyramiding() -> None:
    paper = engine()
    signal_time = START + timedelta(minutes=1)
    assert paper.observe_signal("PAIR_00", "BUY", signal_time, "1.09")
    assert paper.apply_quote("PAIR_00", "1.0998", "1.10", signal_time) == "PENDING"
    assert (
        paper.apply_quote(
            "PAIR_00", "1.0998", "1.10", signal_time + timedelta(seconds=1)
        )
        == "FILLED"
    )
    assert paper.observe_signal(
        "PAIR_00", "BUY", signal_time + timedelta(minutes=5), "1.09"
    ) is False
    assert len(paper.active_positions) == 1


def test_different_instruments_can_hold_parallel_positions() -> None:
    paper = engine()
    open_position(paper, "PAIR_00")
    open_position(paper, "PAIR_01", minute=2)
    assert set(paper.active_positions) == {"PAIR_00", "PAIR_01"}
    assert paper.peak_active_positions == 2


def test_baseline_stop_closes_once_with_r_parity() -> None:
    paper = engine()
    open_position(paper, "PAIR_00")
    position = paper.active_positions["PAIR_00"]
    close_time = START + timedelta(minutes=3)
    assert paper.apply_quote("PAIR_00", "1.0890", "1.0892", close_time) == "CLOSED"
    assert len(paper.ledger) == 1
    trade = paper.ledger[0]
    assert trade["trade_id"] == position.trade_id
    assert trade["exit_reason"] == "SUPERTREND_STOP"
    assert trade["realized_r"] == pytest.approx(-1.1)
    assert trade["r_parity_valid"] is True
    assert paper.r_parity_failures == 0
    assert paper.apply_quote("PAIR_00", "1.08", "1.0802", close_time) == "NO_POSITION"


def test_shadow_is_observation_only_and_cannot_change_primary() -> None:
    paper = engine()
    open_position(paper, "PAIR_00")
    position = paper.active_positions["PAIR_00"]
    original_stop = position.active_stop
    assert (
        paper.apply_quote(
            "PAIR_00",
            "1.1510",
            "1.1512",
            START + timedelta(minutes=2),
        )
        == "ACTIVE"
    )
    position = paper.active_positions["PAIR_00"]
    assert position.shadow_reached["5R"] is True
    assert position.active_stop == original_stop
    assert paper.ledger == []
    assert SHADOW_5R_AUTHORITY == "OBSERVATION_ONLY"
    assert (
        paper.apply_quote(
            "PAIR_00",
            "1.1010",
            "1.1012",
            START + timedelta(minutes=3),
            opposite_confirmed=True,
        )
        == "CLOSED"
    )
    assert paper.ledger[0]["qualifying"] is True
    assert paper.shadow_closed[0]["authority"] == "OBSERVATION_ONLY"


def test_first_30_is_deterministic_and_31st_is_supplemental() -> None:
    paper = engine()
    for index in range(31):
        trade_id = f"trade-{index:02d}"
        paper.ledger.append(
            {
                "trade_id": trade_id,
                "instrument": UNIVERSE[index],
                "exit_timestamp_utc": (
                    START + timedelta(minutes=31 - index)
                ).isoformat().replace("+00:00", "Z"),
                "realized_r": 1.0 if index % 2 == 0 else -0.5,
                "qualifying": True,
                "strategy_config_sha256": paper.strategy_hash,
            }
        )
    expected = sorted(
        paper.ledger,
        key=lambda item: (
            item["exit_timestamp_utc"], item["instrument"], item["trade_id"]
        ),
    )[:30]
    assert paper.formal_trades == expected
    assert len(paper.formal_trades) == 30
    assert paper.paper30_target_reached is True
    assert len(paper.ledger) - len(paper.formal_trades) == 1


def test_stale_market_cannot_create_a_trade_and_artifacts_exclude_credentials() -> None:
    paper = engine()
    assert market_data_fresh(START, START + timedelta(minutes=10)) is True
    assert market_data_fresh(START, START + timedelta(hours=1)) is False
    payload = paper.state_payload()
    rendered = str(payload).lower()
    assert paper.ledger == [] and paper.active_positions == {}
    assert "api_token" not in rendered
    assert "account_id" not in rendered
    assert payload["broker_writes"] is False
    assert payload["practice_orders"] is False
    assert payload["live_orders"] is False


def test_stale_sentinel_prevents_full_scan_and_creates_zero_trades(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    patch_campaign_universe(monkeypatch)
    client = SyntheticPracticeClient(sentinel_latest=NOW - timedelta(hours=1))

    result = run_campaign_segment(
        client,
        cycles=1,
        runtime_root=tmp_path / "runtime",
        report_path=tmp_path / "report.json",
        now_fn=lambda: NOW,
    )

    assert client.calls == [("observation_candles", "EUR_USD", "M5", 5, "M")]
    assert result["status"] == "PAPER30_INTEGRATION_READY_MARKET_CLOSED"
    assert result["paper30_runtime_status"] == "READY_WAITING_FOR_FRESH_MARKET"
    assert result["full_universe_candle_scan_performed"] is False
    assert result["qualifying_trades_created_this_run"] == 0
    assert result["qualifying_closed_trades"] == 0


def test_failed_sentinel_returns_clean_wait_without_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    patch_campaign_universe(monkeypatch)
    client = SyntheticPracticeClient(
        sentinel_error=OandaReadOnlyClientError("NETWORK_ERROR_SANITIZED")
    )

    result = run_campaign_segment(
        client,
        cycles=1,
        runtime_root=tmp_path / "runtime",
        report_path=tmp_path / "report.json",
        now_fn=lambda: NOW,
    )

    assert client.calls == [("observation_candles", "EUR_USD", "M5", 5, "M")]
    assert result["status"] == "PAPER30_READY_WAITING_FOR_PRACTICE_NETWORK"
    assert result["paper30_runtime_status"] == "READY_WAITING_FOR_PRACTICE_NETWORK"
    assert result["network_data_available"] is False
    assert result["network_calls"] == 1
    assert result["qualifying_trades_created_this_run"] == 0


def test_fresh_sentinel_allows_existing_full_campaign_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    patch_campaign_universe(monkeypatch)
    client = SyntheticPracticeClient()

    result = run_campaign_segment(
        client,
        cycles=1,
        runtime_root=tmp_path / "runtime",
        report_path=tmp_path / "report.json",
        now_fn=lambda: NOW,
    )

    sentinel_calls = [call for call in client.calls if call[0] == "observation_candles" and call[3] == 5]
    full_calls = [call for call in client.calls if call[0] == "observation_candles" and call[3] == 500]
    assert sentinel_calls == [("observation_candles", "EUR_USD", "M5", 5, "M")]
    assert len(full_calls) == 68
    assert client.calls.index(sentinel_calls[0]) < client.calls.index(full_calls[0])
    assert result["full_universe_candle_scan_performed"] is True
    assert result["network_data_available"] is True
    assert result["status"] == "PAPER30_FORWARD_CAMPAIGN_RUNNING"


def test_later_network_failure_preserves_ledger_and_active_position(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    patch_campaign_universe(monkeypatch)
    paper = FrozenCandidatePaper30(CAMPAIGN_UNIVERSE, CAMPAIGN_UNIVERSE_HASH, START)
    open_position(paper, "PAIR_00")
    paper.ledger.append(
        {
            "trade_id": "existing-closed-trade",
            "instrument": "PAIR_01",
            "exit_timestamp_utc": (START + timedelta(minutes=3)).isoformat().replace(
                "+00:00", "Z"
            ),
            "realized_r": 0.5,
            "qualifying": True,
            "strategy_config_sha256": paper.strategy_hash,
        }
    )
    ledger_before = copy.deepcopy(paper.ledger)
    active_before = copy.deepcopy(paper.state_payload()["active_positions"])
    monkeypatch.setattr(paper30_module, "_load_or_arm", lambda *_args: paper)
    client = SyntheticPracticeClient(fail_full_instrument="PAIR_02")

    report_path = tmp_path / "report.json"
    result = run_campaign_segment(
        client,
        cycles=1,
        runtime_root=tmp_path / "runtime",
        report_path=report_path,
        now_fn=lambda: NOW,
    )

    assert math.isinf(paper.metrics()["profit_factor"])
    assert result["paper30_metrics"]["profit_factor"] is None
    assert result["paper30_metrics"]["profit_factor_status"] == "POSITIVE_INFINITY"
    assert (
        result["paper30_metrics"]["profit_factor_reason"]
        == "POSITIVE_GROSS_PROFIT_WITH_ZERO_GROSS_LOSS"
    )
    assert json.loads(report_path.read_text(encoding="utf-8")) == result
    json.dumps(result, allow_nan=False)
    assert result["status"] == "PAPER30_READY_WAITING_FOR_PRACTICE_NETWORK"
    assert result["ledger_preserved"] is True
    assert result["active_position_preserved"] is True
    assert paper.ledger == ledger_before
    assert paper.state_payload()["active_positions"] == active_before


def test_keyboard_interrupt_creates_no_trade_and_releases_owned_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    patch_campaign_universe(monkeypatch)
    paper = FrozenCandidatePaper30(CAMPAIGN_UNIVERSE, CAMPAIGN_UNIVERSE_HASH, START)
    ledger_before = copy.deepcopy(paper.ledger)
    monkeypatch.setattr(paper30_module, "_load_or_arm", lambda *_args: paper)
    client = SyntheticPracticeClient(sentinel_error=KeyboardInterrupt())
    runtime_root = tmp_path / "runtime"

    with pytest.raises(KeyboardInterrupt):
        run_campaign_segment(
            client,
            cycles=1,
            runtime_root=runtime_root,
            report_path=tmp_path / "report.json",
            now_fn=lambda: NOW,
        )

    assert paper.ledger == ledger_before == []
    lock_payload = (runtime_root / "AIOS_FOREX_PAPER30_LOCK.json").read_text(
        encoding="utf-8"
    )
    assert '"locked": false' in lock_payload
    assert paper30_module.LOCK_ID in lock_payload


def test_launcher_constructs_practice_client_with_five_second_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: dict[str, Any] = {}

    def client_factory(**kwargs: Any) -> object:
        observed.update(kwargs)
        return object()

    monkeypatch.setattr(launcher, "OandaReadOnlyClient", client_factory)
    monkeypatch.setattr(
        launcher,
        "run_campaign_segment",
        lambda *_args, **_kwargs: {"status": "PAPER30_FORWARD_CAMPAIGN_RUNNING"},
    )
    monkeypatch.setenv("OANDA_API_TOKEN", "runtime-only-test-token")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "runtime-only-test-account")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "paper30-launcher",
            "--cycles",
            "1",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--report-path",
            str(tmp_path / "report.json"),
        ],
    )

    assert launcher.main() == 0
    assert PRACTICE_NETWORK_TIMEOUT_SECONDS == 5
    assert observed["environment"] == "practice"
    assert observed["timeout_seconds"] == 5


def test_frozen_strategy_hash_is_unchanged() -> None:
    assert SENTINEL_INSTRUMENT == "EUR_USD"
    assert strategy_config_sha256(FIXED_UNIVERSE_HASH) == EXPECTED_STRATEGY_HASH


def test_positive_infinite_profit_factor_has_explicit_json_safe_projection() -> None:
    paper = engine()
    paper.ledger.append(
        {
            "trade_id": "winner",
            "instrument": "PAIR_00",
            "exit_timestamp_utc": (START + timedelta(minutes=1)).isoformat().replace(
                "+00:00", "Z"
            ),
            "realized_r": 1.25,
            "qualifying": True,
            "strategy_config_sha256": paper.strategy_hash,
        }
    )

    internal = paper.metrics()
    projected = json_safe_paper30_metrics(internal)

    assert math.isinf(internal["profit_factor"])
    assert internal["profit_factor"] > 0
    assert projected["profit_factor"] is None
    assert projected["profit_factor_status"] == "POSITIVE_INFINITY"
    assert (
        projected["profit_factor_reason"]
        == "POSITIVE_GROSS_PROFIT_WITH_ZERO_GROSS_LOSS"
    )
    json.dumps(projected, allow_nan=False)


def test_finite_profit_factor_remains_numeric_and_unchanged() -> None:
    paper = engine()
    for index, realized_r in enumerate((2.0, -0.5)):
        paper.ledger.append(
            {
                "trade_id": f"finite-{index}",
                "instrument": UNIVERSE[index],
                "exit_timestamp_utc": (
                    START + timedelta(minutes=index + 1)
                ).isoformat().replace("+00:00", "Z"),
                "realized_r": realized_r,
                "qualifying": True,
                "strategy_config_sha256": paper.strategy_hash,
            }
        )

    internal = paper.metrics()
    projected = json_safe_paper30_metrics(internal)

    assert internal["profit_factor"] == 4.0
    assert projected["profit_factor"] == 4.0
    assert projected["profit_factor_status"] == "FINITE"
    assert projected["profit_factor_reason"] is None


def test_zero_profit_zero_loss_profit_factor_contract_remains_finite_zero() -> None:
    internal = engine().metrics()
    projected = json_safe_paper30_metrics(internal)

    assert internal["profit_factor"] == 0.0
    assert projected["profit_factor"] == 0.0
    assert projected["profit_factor_status"] == "FINITE"
    assert projected["profit_factor_reason"] is None


@pytest.mark.parametrize("invalid", [math.nan, -math.inf])
def test_invalid_nonfinite_profit_factor_fails_closed(invalid: float) -> None:
    with pytest.raises(ValueError, match="NONFINITE_METRIC_INVALID"):
        json_safe_paper30_metrics({"profit_factor": invalid})
