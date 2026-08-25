from __future__ import annotations

import hashlib
import json
import math
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from automation.forex_engine.indicators import supertrend
from automation.forex_engine.models import Candle
from automation.forex_engine.oanda_read_only_client import (
    OandaReadOnlyClient,
    OandaReadOnlyClientError,
)


RUNTIME_ID = "AIOS_FOREX_FROZEN_CANDIDATE_PAPER30_V1"
PACKET_ID = "PKT-EAST-FOREX-PAPER30-FAST-NETWORK-GATE-015B-R1"
LOCK_ID = "LOCK_EAST_FOREX_PAPER30_EAST_OCC_01"
WORKER_IDENTITY = "EAST_OCC_01"
LANE = "FOREX_PAPER30"
DEFAULT_RUNTIME_ROOT = Path(".aios/runtime/forex_frozen_candidate_paper30_v1")
DEFAULT_REPORT_PATH = Path(
    "Reports/forex_delivery/AIOS_FOREX_PAPER30_FAST_NETWORK_GATE_V1_RESULTS.json"
)
UNIVERSE_EVIDENCE_PATH = Path(
    "Reports/forex_delivery/AIOS_FOREX_NEW_OOS_DATA_ACQUISITION_V1_RESULTS.json"
)

TIMEFRAME = "M5"
DIRECTION_POLICY = "BUY_ONLY"
ATR_PERIOD = 5
SUPERTREND_FACTOR = 2.0
CONFIRMATION = "TRUE_2_CLOSE"
MACD_FILTER = "NONE"
PRIMARY_EXIT_POLICY = "EXIT_A_BASELINE"
SHADOW_5R_AUTHORITY = "OBSERVATION_ONLY"
PAPER_ONLY = True
SELL_ENABLED = False
MAX_ACTIVE_POSITIONS_PER_INSTRUMENT = 1
GLOBAL_PAPER_POSITION_CAP = 68
PAPER30_TARGET = 30
FRESHNESS_SECONDS = 15 * 60
PRACTICE_NETWORK_TIMEOUT_SECONDS = 5
SENTINEL_INSTRUMENT = "EUR_USD"


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_EXPLICIT_UTC")
    return result.astimezone(timezone.utc)


def _iso_utc(value: str | datetime) -> str:
    return _parse_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _finite_decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("NONFINITE_PRICE")
    return result


def load_fixed_universe(path: Path = UNIVERSE_EVIDENCE_PATH) -> tuple[tuple[str, ...], str]:
    evidence = json.loads(path.read_text(encoding="utf-8"))
    candidates = (
        evidence.get("target_instruments"),
        evidence.get("TARGET_INSTRUMENTS"),
        evidence.get("target_universe", {}).get("instruments")
        if isinstance(evidence.get("target_universe"), dict)
        else None,
    )
    instruments = next((item for item in candidates if isinstance(item, list)), None)
    if instruments is None:
        raise ValueError("FIXED_UNIVERSE_NOT_FOUND")
    universe = tuple(sorted({str(item) for item in instruments}))
    if len(universe) != GLOBAL_PAPER_POSITION_CAP:
        raise ValueError("FIXED_UNIVERSE_COUNT_MISMATCH")
    universe_hash = _canonical_sha256(list(universe))
    recorded_hash = evidence.get("target_universe_sha256") or evidence.get(
        "TARGET_UNIVERSE_SHA256"
    )
    if recorded_hash and str(recorded_hash) != universe_hash:
        raise ValueError("FIXED_UNIVERSE_HASH_MISMATCH")
    return universe, universe_hash


def strategy_config(universe_sha256: str) -> dict[str, Any]:
    return {
        "atr_period": ATR_PERIOD,
        "confirmation": CONFIRMATION,
        "direction": DIRECTION_POLICY,
        "exit_policy": PRIMARY_EXIT_POLICY,
        "macd_filter": MACD_FILTER,
        "pair_universe_sha256": universe_sha256,
        "paper_only": PAPER_ONLY,
        "supertrend_factor": SUPERTREND_FACTOR,
        "timeframe": TIMEFRAME,
    }


def strategy_config_sha256(universe_sha256: str) -> str:
    return _canonical_sha256(strategy_config(universe_sha256))


def _nonfinite_float_count(value: Any) -> int:
    if isinstance(value, float):
        return 0 if math.isfinite(value) else 1
    if isinstance(value, Mapping):
        return sum(_nonfinite_float_count(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_nonfinite_float_count(item) for item in value)
    return 0


def json_safe_paper30_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Project internal PAPER30 metrics into strict JSON without changing arithmetic."""
    result = dict(metrics)
    profit_factor = result.get("profit_factor")
    if isinstance(profit_factor, bool) or not isinstance(profit_factor, (int, float)):
        raise ValueError("NONFINITE_METRIC_INVALID")
    if isinstance(profit_factor, float) and not math.isfinite(profit_factor):
        if math.isinf(profit_factor) and profit_factor > 0:
            result["profit_factor"] = None
            result["profit_factor_status"] = "POSITIVE_INFINITY"
            result[
                "profit_factor_reason"
            ] = "POSITIVE_GROSS_PROFIT_WITH_ZERO_GROSS_LOSS"
        else:
            raise ValueError("NONFINITE_METRIC_INVALID")
    else:
        result["profit_factor_status"] = "FINITE"
        result["profit_factor_reason"] = None
    if _nonfinite_float_count(result):
        raise ValueError("NONFINITE_METRIC_INVALID")
    return result


@dataclass
class PendingEntry:
    instrument: str
    signal_timestamp_utc: str
    initial_stop: str
    strategy_config_sha256: str


@dataclass
class PaperPosition:
    trade_id: str
    instrument: str
    signal_timestamp_utc: str
    fill_timestamp_utc: str
    entry_price: str
    initial_stop: str
    active_stop: str
    initial_risk_price: str
    strategy_config_sha256: str
    shadow_reached: dict[str, bool] = field(default_factory=dict)
    shadow_first_touch_utc: dict[str, str] = field(default_factory=dict)


class FrozenCandidatePaper30:
    """Deterministic PAPER-only state machine; it contains no broker-write path."""

    def __init__(
        self,
        universe: Sequence[str],
        universe_sha256: str,
        campaign_start_utc: str | datetime,
    ) -> None:
        self.universe = tuple(sorted(set(universe)))
        if not self.universe or len(self.universe) > GLOBAL_PAPER_POSITION_CAP:
            raise ValueError("INVALID_FIXED_UNIVERSE")
        self.universe_sha256 = universe_sha256
        self.strategy_hash = strategy_config_sha256(universe_sha256)
        self.campaign_start_utc = _iso_utc(campaign_start_utc)
        self.pending_entries: dict[str, PendingEntry] = {}
        self.active_positions: dict[str, PaperPosition] = {}
        self.consumed_signals: set[str] = set()
        self.ledger: list[dict[str, Any]] = []
        self.shadow_closed: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.peak_active_positions = 0
        self.historical_backfill_trade_count = 0
        self.r_parity_failures = 0

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any], universe: Sequence[str], universe_sha256: str
    ) -> "FrozenCandidatePaper30":
        engine = cls(universe, universe_sha256, payload["campaign_start_utc"])
        if payload.get("strategy_config_sha256") != engine.strategy_hash:
            raise ValueError("PAPER30_STRATEGY_HASH_MISMATCH")
        engine.pending_entries = {
            key: PendingEntry(**value) for key, value in payload.get("pending_entries", {}).items()
        }
        engine.active_positions = {
            key: PaperPosition(**value) for key, value in payload.get("active_positions", {}).items()
        }
        engine.consumed_signals = set(payload.get("consumed_signals", []))
        engine.ledger = list(payload.get("ledger", []))
        engine.shadow_closed = list(payload.get("shadow_closed", []))
        engine.peak_active_positions = int(payload.get("peak_active_positions", 0))
        engine.historical_backfill_trade_count = int(
            payload.get("historical_backfill_trade_count", 0)
        )
        engine.r_parity_failures = int(payload.get("r_parity_failures", 0))
        return engine

    def state_payload(self) -> dict[str, Any]:
        return {
            "schema": RUNTIME_ID,
            "campaign_start_utc": self.campaign_start_utc,
            "strategy_config": strategy_config(self.universe_sha256),
            "strategy_config_sha256": self.strategy_hash,
            "pending_entries": {
                key: asdict(value) for key, value in sorted(self.pending_entries.items())
            },
            "active_positions": {
                key: asdict(value) for key, value in sorted(self.active_positions.items())
            },
            "consumed_signals": sorted(self.consumed_signals),
            "ledger": self.ledger,
            "shadow_closed": self.shadow_closed,
            "peak_active_positions": self.peak_active_positions,
            "historical_backfill_trade_count": self.historical_backfill_trade_count,
            "r_parity_failures": self.r_parity_failures,
            "paper_only": True,
            "broker_writes": False,
            "practice_orders": False,
            "live_orders": False,
            "money_movement": False,
            "credentials_persisted": False,
        }

    def _event(self, kind: str, **fields: Any) -> None:
        self.events.append(
            {
                "event": kind,
                "strategy_config_sha256": self.strategy_hash,
                **fields,
            }
        )

    def observe_signal(
        self,
        instrument: str,
        direction: str,
        signal_timestamp_utc: str | datetime,
        initial_stop: Decimal | float | str,
    ) -> bool:
        if direction != "BUY":
            raise ValueError("SELL_DISABLED")
        if instrument not in self.universe:
            raise ValueError("INSTRUMENT_OUTSIDE_FIXED_UNIVERSE")
        signal_time = _iso_utc(signal_timestamp_utc)
        if _parse_utc(signal_time) <= _parse_utc(self.campaign_start_utc):
            return False
        if self.paper30_target_reached or instrument in self.active_positions:
            return False
        if instrument in self.pending_entries:
            return False
        signal_key = f"{instrument}|{signal_time}|BUY"
        if signal_key in self.consumed_signals:
            return False
        stop = _finite_decimal(initial_stop)
        self.pending_entries[instrument] = PendingEntry(
            instrument=instrument,
            signal_timestamp_utc=signal_time,
            initial_stop=str(stop),
            strategy_config_sha256=self.strategy_hash,
        )
        self.consumed_signals.add(signal_key)
        self._event(
            "PENDING_ENTRY_CREATED",
            instrument=instrument,
            signal_timestamp_utc=signal_time,
        )
        return True

    def apply_quote(
        self,
        instrument: str,
        bid: Decimal | float | str,
        ask: Decimal | float | str,
        quote_timestamp_utc: str | datetime,
        *,
        active_stop_candidate: Decimal | float | str | None = None,
        opposite_confirmed: bool = False,
    ) -> str:
        if instrument not in self.universe:
            raise ValueError("INSTRUMENT_OUTSIDE_FIXED_UNIVERSE")
        bid_price = _finite_decimal(bid)
        ask_price = _finite_decimal(ask)
        quote_time = _iso_utc(quote_timestamp_utc)
        if ask_price < bid_price:
            raise ValueError("INVALID_QUOTE_GEOMETRY")

        pending = self.pending_entries.get(instrument)
        if pending is not None:
            if _parse_utc(quote_time) <= _parse_utc(pending.signal_timestamp_utc):
                return "PENDING"
            entry = ask_price
            stop = _finite_decimal(pending.initial_stop)
            risk = entry - stop
            if risk <= 0:
                del self.pending_entries[instrument]
                self._event("PENDING_ENTRY_REJECTED_INVALID_R", instrument=instrument)
                return "REJECTED_INVALID_R"
            trade_id = hashlib.sha256(
                f"{self.strategy_hash}|{instrument}|{pending.signal_timestamp_utc}|{quote_time}".encode(
                    "utf-8"
                )
            ).hexdigest()
            flags = {label: False for label in ("1R", "1_5R", "2R", "3R", "4R", "5R")}
            self.active_positions[instrument] = PaperPosition(
                trade_id=trade_id,
                instrument=instrument,
                signal_timestamp_utc=pending.signal_timestamp_utc,
                fill_timestamp_utc=quote_time,
                entry_price=str(entry),
                initial_stop=str(stop),
                active_stop=str(stop),
                initial_risk_price=str(risk),
                strategy_config_sha256=self.strategy_hash,
                shadow_reached=flags,
            )
            del self.pending_entries[instrument]
            self.peak_active_positions = max(
                self.peak_active_positions, len(self.active_positions)
            )
            self._event(
                "PAPER_POSITION_OPENED",
                trade_id=trade_id,
                instrument=instrument,
                fill_timestamp_utc=quote_time,
            )
            return "FILLED"

        position = self.active_positions.get(instrument)
        if position is None:
            return "NO_POSITION"
        if _parse_utc(quote_time) <= _parse_utc(position.fill_timestamp_utc):
            return "ACTIVE"

        entry = _finite_decimal(position.entry_price)
        risk = _finite_decimal(position.initial_risk_price)
        thresholds = {
            "1R": Decimal("1"),
            "1_5R": Decimal("1.5"),
            "2R": Decimal("2"),
            "3R": Decimal("3"),
            "4R": Decimal("4"),
            "5R": Decimal("5"),
        }
        for label, multiple in thresholds.items():
            if not position.shadow_reached[label] and bid_price >= entry + multiple * risk:
                position.shadow_reached[label] = True
                position.shadow_first_touch_utc[label] = quote_time

        active_stop = _finite_decimal(position.active_stop)
        if active_stop_candidate is not None:
            candidate = _finite_decimal(active_stop_candidate)
            if candidate < entry and candidate > active_stop:
                active_stop = candidate
                position.active_stop = str(active_stop)

        if bid_price > active_stop and not opposite_confirmed:
            return "ACTIVE"
        reason = "OPPOSITE_TRUE_2_CLOSE" if opposite_confirmed else "SUPERTREND_STOP"
        return self._close_position(position, bid_price, quote_time, reason)

    def _close_position(
        self, position: PaperPosition, exit_price: Decimal, exit_time: str, reason: str
    ) -> str:
        entry = _finite_decimal(position.entry_price)
        risk = _finite_decimal(position.initial_risk_price)
        realized_r = (exit_price - entry) / risk
        cash_r = ((exit_price - entry) * Decimal("1")) / (risk * Decimal("1"))
        parity_valid = abs(realized_r - cash_r) <= Decimal("0.000000001")
        if not parity_valid:
            self.r_parity_failures += 1
        trade = {
            "trade_id": position.trade_id,
            "instrument": position.instrument,
            "direction": "BUY",
            "signal_timestamp_utc": position.signal_timestamp_utc,
            "fill_timestamp_utc": position.fill_timestamp_utc,
            "exit_timestamp_utc": exit_time,
            "entry_price": position.entry_price,
            "initial_stop": position.initial_stop,
            "initial_risk_price": position.initial_risk_price,
            "exit_price": str(exit_price),
            "exit_reason": reason,
            "realized_r": float(realized_r),
            "r_parity_valid": parity_valid,
            "strategy_config_sha256": self.strategy_hash,
            "timeframe": TIMEFRAME,
            "direction_policy": DIRECTION_POLICY,
            "atr_period": ATR_PERIOD,
            "supertrend_factor": SUPERTREND_FACTOR,
            "confirmation": CONFIRMATION,
            "macd_filter": MACD_FILTER,
            "primary_exit_policy": PRIMARY_EXIT_POLICY,
            "broker_order": False,
            "historical_backfill": False,
            "qualifying": True,
        }
        self.ledger.append(trade)
        shadow = {
            "trade_id": position.trade_id,
            "strategy_config_sha256": self.strategy_hash,
            "authority": SHADOW_5R_AUTHORITY,
            **{f"reached_{key.lower()}": value for key, value in position.shadow_reached.items()},
            "first_5r_timestamp": position.shadow_first_touch_utc.get("5R"),
            "primary_realized_r": float(realized_r),
        }
        self.shadow_closed.append(shadow)
        del self.active_positions[position.instrument]
        self._event(
            "PAPER_POSITION_CLOSED",
            trade_id=position.trade_id,
            instrument=position.instrument,
            exit_timestamp_utc=exit_time,
            qualifying=True,
        )
        return "CLOSED"

    @property
    def formal_trades(self) -> list[dict[str, Any]]:
        qualifying = [trade for trade in self.ledger if trade.get("qualifying")]
        return sorted(
            qualifying,
            key=lambda item: (
                item["exit_timestamp_utc"], item["instrument"], item["trade_id"]
            ),
        )[:PAPER30_TARGET]

    @property
    def paper30_target_reached(self) -> bool:
        return len(self.formal_trades) >= PAPER30_TARGET

    def metrics(self) -> dict[str, Any]:
        trades = self.formal_trades
        values = [float(trade["realized_r"]) for trade in trades]
        wins = [value for value in values if value > 0]
        losses = [value for value in values if value < 0]
        flats = len(values) - len(wins) - len(losses)
        gross_profit = sum(wins)
        gross_loss = -sum(losses)
        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        max_loss_streak = 0
        loss_streak = 0
        for value in values:
            equity += value
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
            if value < 0:
                loss_streak += 1
                max_loss_streak = max(max_loss_streak, loss_streak)
            else:
                loss_streak = 0
        shadow_by_id = {item["trade_id"]: item for item in self.shadow_closed}
        reached = {
            label: sum(
                bool(shadow_by_id.get(trade["trade_id"], {}).get(f"reached_{label.lower()}"))
                for trade in trades
            )
            for label in ("1R", "2R", "3R", "4R", "5R")
        }
        closed = len(values)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (
            math.inf if gross_profit > 0 else 0.0
        )
        paper30_pass = None
        if closed >= PAPER30_TARGET:
            paper30_pass = bool(
                sum(values) > 0
                and sum(values) / closed > 0
                and profit_factor >= 1.10
                and self.r_parity_failures == 0
            )
        return {
            "closed": closed,
            "wins": len(wins),
            "losses": len(losses),
            "flats": flats,
            "win_rate": len(wins) / closed if closed else 0.0,
            "average_win_r": sum(wins) / len(wins) if wins else 0.0,
            "average_loss_r": sum(losses) / len(losses) if losses else 0.0,
            "expectancy_r": sum(values) / closed if closed else 0.0,
            "profit_factor": profit_factor,
            "net_r": sum(values),
            "max_drawdown_r": max_drawdown,
            "max_loss_streak": max_loss_streak,
            "buy_count": closed,
            "instrument_count": len({trade["instrument"] for trade in trades}),
            "peak_active_paper_positions": self.peak_active_positions,
            "reached_1r_count": reached["1R"],
            "reached_2r_count": reached["2R"],
            "reached_3r_count": reached["3R"],
            "reached_4r_count": reached["4R"],
            "reached_5r_count": reached["5R"],
            "reached_5r_percent": reached["5R"] / closed if closed else 0.0,
            "paper30_target_reached": closed >= PAPER30_TARGET,
            "paper30_decision": "PASS" if paper30_pass else (
                "FAIL" if paper30_pass is False else "PENDING"
            ),
            "paper30_pass": paper30_pass,
        }


def sanitize_completed_m5(payload: Mapping[str, Any], instrument: str) -> list[Candle]:
    if str(payload.get("instrument", instrument)) != instrument:
        raise ValueError("INSTRUMENT_RESPONSE_MISMATCH")
    if str(payload.get("granularity", TIMEFRAME)) != TIMEFRAME:
        raise ValueError("GRANULARITY_RESPONSE_MISMATCH")
    result: list[Candle] = []
    for raw in payload.get("candles", []):
        if raw.get("complete") is not True:
            continue
        mid = raw.get("mid")
        if not isinstance(mid, Mapping):
            continue
        timestamp = _iso_utc(str(raw["time"]))
        open_price = _finite_decimal(mid["o"])
        high = _finite_decimal(mid["h"])
        low = _finite_decimal(mid["l"])
        close = _finite_decimal(mid["c"])
        if high < max(open_price, close) or low > min(open_price, close) or high < low:
            continue
        result.append(
            Candle(
                symbol=instrument,
                timeframe=TIMEFRAME,
                timestamp=timestamp,
                open=float(open_price),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(raw.get("volume", 0)),
                source="OANDA_PRACTICE_GET_ONLY",
            )
        )
    return sorted(result, key=lambda candle: candle.timestamp)


def latest_true_2_close_state(candles: Sequence[Candle]) -> dict[str, Any] | None:
    if len(candles) < ATR_PERIOD + 3:
        return None
    rows = supertrend(list(candles), ATR_PERIOD, SUPERTREND_FACTOR)
    confirmed: int | None = None
    candidate: int | None = None
    candidate_count = 0
    latest_event: dict[str, Any] | None = None
    for index, row in enumerate(rows):
        raw_direction = int(row["direction"])
        if raw_direction == candidate:
            candidate_count += 1
        else:
            candidate = raw_direction
            candidate_count = 1
        if candidate_count >= 2 and candidate != confirmed:
            confirmed = candidate
            latest_event = {
                "direction": "BUY" if confirmed > 0 else "SELL",
                "confirmation_timestamp_utc": _iso_utc(candles[index].timestamp),
                "support_band": row.get("lower_band") if confirmed > 0 else row.get("upper_band"),
            }
    latest = rows[-1]
    return {
        "confirmed_direction": "BUY" if (confirmed or 0) > 0 else "SELL",
        "latest_event": latest_event,
        "active_support": latest.get("lower_band"),
        "latest_timestamp_utc": _iso_utc(candles[-1].timestamp),
    }


def market_data_fresh(
    latest_completed_m5_utc: str | datetime,
    now_utc: str | datetime | None = None,
    freshness_seconds: int = FRESHNESS_SECONDS,
) -> bool:
    now = _parse_utc(now_utc or _utc_now())
    latest = _parse_utc(latest_completed_m5_utc)
    age = (now - latest).total_seconds()
    return 0 <= age <= freshness_seconds


def sanitize_pricing(payload: Mapping[str, Any]) -> dict[str, tuple[Decimal, Decimal, str]]:
    result: dict[str, tuple[Decimal, Decimal, str]] = {}
    for price in payload.get("prices", []):
        instrument = str(price.get("instrument", ""))
        bids = price.get("bids") or []
        asks = price.get("asks") or []
        if not instrument or not bids or not asks or "time" not in price:
            continue
        bid = _finite_decimal(bids[0]["price"])
        ask = _finite_decimal(asks[0]["price"])
        if ask < bid:
            continue
        result[instrument] = (bid, ask, _iso_utc(str(price["time"])))
    return result


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


@contextmanager
def _runtime_lock(path: Path, strategy_hash: str) -> Iterable[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b" ")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("PAPER30_RUNTIME_ALREADY_LOCKED") from exc
        yield
    finally:
        if os.name == "nt":
            import msvcrt

            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        handle.close()
        _atomic_json(
            path,
            {
                "schema": RUNTIME_ID,
                "locked": False,
                "lock_id": LOCK_ID,
                "lane": LANE,
                "strategy_config_sha256": strategy_hash,
                "worker_identity": WORKER_IDENTITY,
            },
        )


def _runtime_paths(root: Path) -> dict[str, Path]:
    return {
        "active": root / "AIOS_FOREX_PAPER30_ACTIVE.json",
        "ledger": root / "AIOS_FOREX_PAPER30_LEDGER.json",
        "events": root / "AIOS_FOREX_PAPER30_EVENTS.jsonl",
        "state": root / "AIOS_FOREX_PAPER30_STATE.json",
        "lock": root / "AIOS_FOREX_PAPER30_LOCK.json",
        "shadow": root / "AIOS_FOREX_PAPER30_5R_SHADOW.jsonl",
    }


def _persist(engine: FrozenCandidatePaper30, root: Path, runtime_status: str) -> None:
    paths = _runtime_paths(root)
    root.mkdir(parents=True, exist_ok=True)
    state = engine.state_payload()
    state["runtime_status"] = runtime_status
    _atomic_json(paths["state"], state)
    _atomic_json(
        paths["active"],
        {
            "schema": RUNTIME_ID,
            "strategy_config_sha256": engine.strategy_hash,
            "pending_entries": state["pending_entries"],
            "active_positions": state["active_positions"],
        },
    )
    _atomic_json(
        paths["ledger"],
        {
            "schema": RUNTIME_ID,
            "strategy_config_sha256": engine.strategy_hash,
            "trades": engine.ledger,
        },
    )
    paths["events"].write_text(
        "".join(json.dumps(item, sort_keys=True, allow_nan=False) + "\n" for item in engine.events),
        encoding="utf-8",
    )
    paths["shadow"].write_text(
        "".join(
            json.dumps(item, sort_keys=True, allow_nan=False) + "\n"
            for item in engine.shadow_closed
        ),
        encoding="utf-8",
    )


def _persist_runtime_status(
    engine: FrozenCandidatePaper30, root: Path, runtime_status: str
) -> None:
    """Persist a wait status without rewriting ledger, active, event, or shadow files."""
    state = engine.state_payload()
    state["runtime_status"] = runtime_status
    _atomic_json(_runtime_paths(root)["state"], state)


def _load_or_arm(root: Path, universe: Sequence[str], universe_hash: str) -> FrozenCandidatePaper30:
    state_path = _runtime_paths(root)["state"]
    if state_path.exists():
        return FrozenCandidatePaper30.from_payload(
            json.loads(state_path.read_text(encoding="utf-8")), universe, universe_hash
        )
    return FrozenCandidatePaper30(universe, universe_hash, _utc_now())


def _build_result(
    engine: FrozenCandidatePaper30,
    runtime_status: str,
    market_fresh: bool,
    network_calls: int,
    broker_calls: int,
    *,
    sentinel_get_success: bool,
    sentinel_market_data_fresh: bool,
    full_universe_candle_scan_performed: bool,
    network_data_available: bool,
    network_status: str,
    pre_qualifying_closed_trades: int,
    pre_ledger_snapshot: Sequence[Mapping[str, Any]],
    active_position_preserved: bool,
) -> dict[str, Any]:
    metrics = engine.metrics()
    serialized_metrics = json_safe_paper30_metrics(metrics)
    if metrics["paper30_target_reached"]:
        status = (
            "PAPER30_30_TRADES_COMPLETE_PASS"
            if metrics["paper30_pass"]
            else "PAPER30_30_TRADES_COMPLETE_FAIL"
        )
        next_decision = (
            "RUN_PAPER30_POSTMORTEM_AND_FORMAL_GATE"
            if metrics["paper30_pass"]
            else "PAPER30_EDGE_NOT_PROVEN"
        )
        next_packet_id = (
            "PKT-EAST-FOREX-PAPER30-POSTMORTEM-016" if metrics["paper30_pass"] else None
        )
    elif runtime_status == "READY_WAITING_FOR_FRESH_MARKET":
        status = "PAPER30_INTEGRATION_READY_MARKET_CLOSED"
        next_decision = "RERUN_WHEN_FRESH_M5_MARKET_DATA_EXISTS"
        next_packet_id = PACKET_ID
    elif runtime_status == "READY_WAITING_FOR_PRACTICE_NETWORK":
        status = "PAPER30_READY_WAITING_FOR_PRACTICE_NETWORK"
        next_decision = "RERUN_WHEN_PRACTICE_NETWORK_IS_AVAILABLE"
        next_packet_id = PACKET_ID
    else:
        status = "PAPER30_FORWARD_CAMPAIGN_RUNNING"
        next_decision = "CONTINUE_FROZEN_FORWARD_PAPER30"
        next_packet_id = PACKET_ID
    return {
        "schema": "AIOS_FOREX_PAPER30_FAST_NETWORK_GATE_V1",
        "packet_id": PACKET_ID,
        "lock_id": LOCK_ID,
        "worker_identity": WORKER_IDENTITY,
        "lane": LANE,
        "bootstrap_result": "PASS",
        "v2_holdout_blocks_paper30": False,
        "strategy_config": strategy_config(engine.universe_sha256),
        "paper30_strategy_config_sha256": engine.strategy_hash,
        "paper30_campaign_start_utc": engine.campaign_start_utc,
        "pair_universe_count": len(engine.universe),
        "paper30_runtime_status": runtime_status,
        "market_data_fresh": market_fresh,
        "practice_network_timeout_seconds": PRACTICE_NETWORK_TIMEOUT_SECONDS,
        "sentinel_instrument": SENTINEL_INSTRUMENT,
        "sentinel_get_success": sentinel_get_success,
        "sentinel_market_data_fresh": sentinel_market_data_fresh,
        "full_universe_candle_scan_performed": full_universe_candle_scan_performed,
        "network_data_available": network_data_available,
        "network_status": network_status,
        "pre_qualifying_closed_trades": pre_qualifying_closed_trades,
        "qualifying_closed_trades": metrics["closed"],
        "qualifying_trades_created_this_run": max(
            0, metrics["closed"] - pre_qualifying_closed_trades
        ),
        "remaining_to_30": max(0, PAPER30_TARGET - metrics["closed"]),
        "active_paper_positions": len(engine.active_positions),
        "ledger_preserved": list(engine.ledger[: len(pre_ledger_snapshot)])
        == list(pre_ledger_snapshot),
        "active_position_preserved": active_position_preserved,
        "historical_backfill_trade_count": engine.historical_backfill_trade_count,
        "r_parity_failures": engine.r_parity_failures,
        "shadow_5r_authority": SHADOW_5R_AUTHORITY,
        "paper30_metrics": serialized_metrics,
        "json_nonfinite_float_count": _nonfinite_float_count(serialized_metrics),
        "paper_only": True,
        "sell_enabled": False,
        "broker_writes": False,
        "practice_orders": False,
        "live_orders": False,
        "money_movement": False,
        "credentials_persisted": False,
        "network_calls": network_calls,
        "broker_calls": broker_calls,
        "next_decision": next_decision,
        "next_packet_id": next_packet_id,
        "status": status,
    }


def run_campaign_segment(
    client: OandaReadOnlyClient,
    *,
    cycles: int = 288,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    reviewer: str = "Human Owner Anthony",
    report_path: Path = DEFAULT_REPORT_PATH,
    sleep_seconds: float = 300.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], datetime] = _utc_now,
) -> dict[str, Any]:
    del reviewer  # Reviewer identity is intentionally not an execution authority.
    if client.environment != "practice":
        raise ValueError("PRACTICE_ENVIRONMENT_REQUIRED")
    if int(getattr(client, "timeout_seconds", PRACTICE_NETWORK_TIMEOUT_SECONDS)) != (
        PRACTICE_NETWORK_TIMEOUT_SECONDS
    ):
        raise ValueError("PRACTICE_NETWORK_TIMEOUT_MISMATCH")
    if cycles < 1:
        raise ValueError("CYCLES_MUST_BE_POSITIVE")
    universe, universe_hash = load_fixed_universe()
    engine = _load_or_arm(runtime_root, universe, universe_hash)
    pre_qualifying_closed_trades = len(engine.formal_trades)
    pre_ledger_snapshot = json.loads(json.dumps(engine.ledger))
    network_calls = 0
    broker_calls = 0
    runtime_status = "RUNNING"
    fresh = False
    sentinel_get_success = False
    sentinel_market_data_fresh = False
    full_universe_candle_scan_performed = False
    network_data_available = True
    network_status = "AVAILABLE"
    paths = _runtime_paths(runtime_root)
    with _runtime_lock(paths["lock"], engine.strategy_hash):
        try:
            network_calls += 1
            broker_calls += 1
            sentinel_payload = client.observation_candles(
                SENTINEL_INSTRUMENT,
                granularity=TIMEFRAME,
                count=5,
                price="M",
            )
            sentinel_get_success = True
            sentinel_candles = sanitize_completed_m5(
                sentinel_payload, SENTINEL_INSTRUMENT
            )
            sentinel_market_data_fresh = bool(sentinel_candles) and market_data_fresh(
                sentinel_candles[-1].timestamp, now_fn()
            )
        except OandaReadOnlyClientError as exc:
            runtime_status = "READY_WAITING_FOR_PRACTICE_NETWORK"
            network_data_available = False
            network_status = exc.public_reason
            _persist_runtime_status(engine, runtime_root, runtime_status)
            result = _build_result(
                engine,
                runtime_status,
                False,
                network_calls,
                broker_calls,
                sentinel_get_success=False,
                sentinel_market_data_fresh=False,
                full_universe_candle_scan_performed=False,
                network_data_available=False,
                network_status=network_status,
                pre_qualifying_closed_trades=pre_qualifying_closed_trades,
                pre_ledger_snapshot=pre_ledger_snapshot,
                active_position_preserved=True,
            )
            _atomic_json(report_path, result)
            return result

        if not sentinel_market_data_fresh:
            runtime_status = "READY_WAITING_FOR_FRESH_MARKET"
            _persist_runtime_status(engine, runtime_root, runtime_status)
            result = _build_result(
                engine,
                runtime_status,
                False,
                network_calls,
                broker_calls,
                sentinel_get_success=True,
                sentinel_market_data_fresh=False,
                full_universe_candle_scan_performed=False,
                network_data_available=True,
                network_status=network_status,
                pre_qualifying_closed_trades=pre_qualifying_closed_trades,
                pre_ledger_snapshot=pre_ledger_snapshot,
                active_position_preserved=True,
            )
            _atomic_json(report_path, result)
            return result

        try:
            network_calls += 1
            broker_calls += 1
            discovered = client.discover_instruments()
        except OandaReadOnlyClientError as exc:
            runtime_status = "READY_WAITING_FOR_PRACTICE_NETWORK"
            network_data_available = False
            network_status = exc.public_reason
            _persist_runtime_status(engine, runtime_root, runtime_status)
            result = _build_result(
                engine,
                runtime_status,
                True,
                network_calls,
                broker_calls,
                sentinel_get_success=True,
                sentinel_market_data_fresh=True,
                full_universe_candle_scan_performed=False,
                network_data_available=False,
                network_status=network_status,
                pre_qualifying_closed_trades=pre_qualifying_closed_trades,
                pre_ledger_snapshot=pre_ledger_snapshot,
                active_position_preserved=True,
            )
            _atomic_json(report_path, result)
            return result
        available = {
            str(item.get("name"))
            for item in discovered.get("instruments", [])
            if item.get("type", "CURRENCY") == "CURRENCY"
        }
        if not set(universe).issubset(available):
            raise ValueError("FIXED_UNIVERSE_NOT_AVAILABLE")

        for cycle_index in range(cycles):
            cycle_active_snapshot = {
                key: asdict(value) for key, value in engine.active_positions.items()
            }
            candle_sets: dict[str, list[Candle]] = {}
            latest_timestamps: list[str] = []
            try:
                for instrument in universe:
                    network_calls += 1
                    broker_calls += 1
                    payload = client.observation_candles(
                        instrument, granularity=TIMEFRAME, count=500, price="M"
                    )
                    candles = sanitize_completed_m5(payload, instrument)
                    candle_sets[instrument] = candles
                    if candles:
                        latest_timestamps.append(_iso_utc(candles[-1].timestamp))
                full_universe_candle_scan_performed = True
            except OandaReadOnlyClientError as exc:
                runtime_status = "READY_WAITING_FOR_PRACTICE_NETWORK"
                network_data_available = False
                network_status = exc.public_reason
                _persist_runtime_status(engine, runtime_root, runtime_status)
                result = _build_result(
                    engine,
                    runtime_status,
                    True,
                    network_calls,
                    broker_calls,
                    sentinel_get_success=True,
                    sentinel_market_data_fresh=True,
                    full_universe_candle_scan_performed=False,
                    network_data_available=False,
                    network_status=network_status,
                    pre_qualifying_closed_trades=pre_qualifying_closed_trades,
                    pre_ledger_snapshot=pre_ledger_snapshot,
                    active_position_preserved=(
                        cycle_active_snapshot
                        == {
                            key: asdict(value)
                            for key, value in engine.active_positions.items()
                        }
                    ),
                )
                _atomic_json(report_path, result)
                return result
            fresh = bool(latest_timestamps) and market_data_fresh(
                max(latest_timestamps), now_fn()
            )
            if not fresh:
                runtime_status = "READY_WAITING_FOR_FRESH_MARKET"
                _persist_runtime_status(engine, runtime_root, runtime_status)
                break

            try:
                network_calls += 1
                broker_calls += 1
                pricing = client.pricing(universe)
            except OandaReadOnlyClientError as exc:
                runtime_status = "READY_WAITING_FOR_PRACTICE_NETWORK"
                network_data_available = False
                network_status = exc.public_reason
                _persist_runtime_status(engine, runtime_root, runtime_status)
                result = _build_result(
                    engine,
                    runtime_status,
                    True,
                    network_calls,
                    broker_calls,
                    sentinel_get_success=True,
                    sentinel_market_data_fresh=True,
                    full_universe_candle_scan_performed=True,
                    network_data_available=False,
                    network_status=network_status,
                    pre_qualifying_closed_trades=pre_qualifying_closed_trades,
                    pre_ledger_snapshot=pre_ledger_snapshot,
                    active_position_preserved=(
                        cycle_active_snapshot
                        == {
                            key: asdict(value)
                            for key, value in engine.active_positions.items()
                        }
                    ),
                )
                _atomic_json(report_path, result)
                return result

            states: dict[str, dict[str, Any]] = {}
            for instrument, candles in candle_sets.items():
                state = latest_true_2_close_state(candles)
                if state is None:
                    continue
                states[instrument] = state
                event = state.get("latest_event")
                if (
                    event
                    and event["direction"] == "BUY"
                    and event["confirmation_timestamp_utc"] == state["latest_timestamp_utc"]
                    and event.get("support_band") is not None
                ):
                    engine.observe_signal(
                        instrument,
                        "BUY",
                        event["confirmation_timestamp_utc"],
                        event["support_band"],
                    )

            quotes = sanitize_pricing(pricing)
            for instrument, (bid, ask, quote_time) in quotes.items():
                state = states.get(instrument, {})
                latest_event = state.get("latest_event") or {}
                engine.apply_quote(
                    instrument,
                    bid,
                    ask,
                    quote_time,
                    active_stop_candidate=state.get("active_support"),
                    opposite_confirmed=(
                        latest_event.get("direction") == "SELL"
                        and latest_event.get("confirmation_timestamp_utc")
                        == state.get("latest_timestamp_utc")
                    ),
                )
            if engine.paper30_target_reached:
                runtime_status = "TARGET_REACHED"
                _persist(engine, runtime_root, runtime_status)
                break
            _persist(engine, runtime_root, runtime_status)
            if cycle_index + 1 < cycles:
                sleep_fn(sleep_seconds)

        result = _build_result(
            engine,
            runtime_status,
            fresh,
            network_calls,
            broker_calls,
            sentinel_get_success=sentinel_get_success,
            sentinel_market_data_fresh=sentinel_market_data_fresh,
            full_universe_candle_scan_performed=full_universe_candle_scan_performed,
            network_data_available=network_data_available,
            network_status=network_status,
            pre_qualifying_closed_trades=pre_qualifying_closed_trades,
            pre_ledger_snapshot=pre_ledger_snapshot,
            active_position_preserved=True,
        )
        _atomic_json(report_path, result)
        return result


__all__ = [
    "ATR_PERIOD",
    "CONFIRMATION",
    "DIRECTION_POLICY",
    "FrozenCandidatePaper30",
    "GLOBAL_PAPER_POSITION_CAP",
    "MACD_FILTER",
    "MAX_ACTIVE_POSITIONS_PER_INSTRUMENT",
    "PAPER_ONLY",
    "PRACTICE_NETWORK_TIMEOUT_SECONDS",
    "PRIMARY_EXIT_POLICY",
    "SELL_ENABLED",
    "SHADOW_5R_AUTHORITY",
    "SENTINEL_INSTRUMENT",
    "SUPERTREND_FACTOR",
    "TIMEFRAME",
    "load_fixed_universe",
    "json_safe_paper30_metrics",
    "market_data_fresh",
    "run_campaign_segment",
    "sanitize_completed_m5",
    "sanitize_pricing",
    "strategy_config",
    "strategy_config_sha256",
]
