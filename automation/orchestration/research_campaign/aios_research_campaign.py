"""Pure, local-only contracts for the Forex-first research campaign.

It validates JSON-compatible campaign inputs, calculates evidence metrics,
and persists explicitly requested temporary checkpoints. It has no network,
broker, credential, scheduler, or runtime-launch path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from types import MappingProxyType
from typing import Any, Mapping, Sequence


REQUIRED_MARKET_LANES = frozenset(
    {"FOREX_EURUSD_PRIMARY", "CME_INDEX_FUTURES_COMPARISON"}
)
RESEARCH_STAGES = (
    "CHEAP_SCREEN",
    "COST",
    "WALK_FORWARD",
    "TRUE_OOS",
    "STRESS",
    "REPLICATION",
    "PAPER",
)
EVIDENCE_CATEGORY_WEIGHTS = {
    "data_quality": 10,
    "backtest_replay": 10,
    "cost_model": 10,
    "strategy_discovery": 10,
    "oos_validation": 15,
    "market_time_transfer": 10,
    "stress_resilience": 10,
    "paper_validation": 10,
    "execution_recovery": 5,
    "risk_controls": 5,
    "live_micro": 5,
}
ENGINEERING_EVIDENCE_CATEGORIES = frozenset(
    {
        "data_quality",
        "backtest_replay",
        "cost_model",
        "execution_recovery",
        "risk_controls",
    }
)
EDGE_EVIDENCE_CATEGORIES = frozenset(EVIDENCE_CATEGORY_WEIGHTS) - ENGINEERING_EVIDENCE_CATEGORIES
PROFITABILITY_READINESS_CATEGORIES = frozenset({"data_quality", "cost_model"})
ROUTING_CONTEXT_SCHEMA = "AIOS_RESEARCH_ROUTING_CONTEXT.v2"
MAX_JSON_INPUT_BYTES = 1024 * 1024
MAX_CATALOG_ENTRIES = 1000
MAX_EXPERIMENT_BUDGET = 1000
MAX_OUTCOMES = 1000
MAX_EVIDENCE_RECORDS = 1000
PAPER_GATE_INPUT_FIELDS = (
    "candidate_fingerprint",
    "evidence_version",
    "positive_oos_expectancy",
    "positive_stressed_expectancy",
    "profit_factor_after_costs",
    "max_drawdown_pct",
    "oos_trade_count",
    "walk_forward_stable",
    "replication_stable",
    "nearby_parameter_stable",
    "no_profit_concentration",
    "performance_evidence",
)
PERFORMANCE_FIELDS = frozenset({
    "source_id", "cost_model_id", "dataset_sha256", "currency", "initial_equity",
    "selection_frozen_at_utc", "oos_start_utc", "oos_end_utc", "trades",
})
PERFORMANCE_TRADE_FIELDS = frozenset({
    "trade_id", "closed_at_utc", "gross_pnl", "base_cost", "stress_cost",
})


class CampaignValidationError(ValueError):
    """Raised when a JSON campaign or experiment contract is unsafe or invalid."""


class CampaignCheckpointError(ValueError):
    """Raised when a persisted campaign checkpoint is unsafe or malformed."""


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CampaignValidationError(f"{field_name} must be a mapping")
    return value


def _require_nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CampaignValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_positive_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CampaignValidationError(f"{field_name} must be a positive integer")
    return value


def _require_utc_timestamp(value: Any, field_name: str) -> str:
    timestamp = _require_nonempty_string(value, field_name)
    candidate = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise CampaignCheckpointError(f"{field_name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise CampaignCheckpointError(f"{field_name} must be an explicit UTC timestamp")
    return parsed.astimezone(timezone.utc).isoformat(
        timespec="microseconds" if parsed.microsecond else "seconds"
    ).replace("+00:00", "Z")


def _utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _freeze_json_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Copy a JSON-compatible mapping so the campaign contract cannot be mutated."""

    try:
        copied = json.loads(
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        )
        return _freeze_json_value(copied)
    except (TypeError, ValueError, RecursionError) as error:
        raise CampaignValidationError("mapping must contain JSON-compatible values") from error


def _freeze_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json_value(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json_value(item) for item in value)
    return value


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_compatible(item) for item in value]
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            _json_compatible(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as error:
        raise CampaignValidationError("value must be JSON-compatible") from error


def _validate_json_input_size(value: Any, label: str) -> int:
    try:
        encoded = _canonical_json(value).encode("utf-8")
    except CampaignValidationError as error:
        raise CampaignValidationError(f"{label} must be valid JSON") from error
    if len(encoded) > MAX_JSON_INPUT_BYTES:
        raise CampaignValidationError(f"{label} exceeds 1 MiB")
    return len(encoded)


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def read_bounded_json_file(path: Path, label: str = "JSON input") -> Any:
    """Read at most 1 MiB from an opened regular file, never wait on a FIFO."""

    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0),
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise CampaignValidationError(f"{label} must be a regular file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None  # The context manager now owns the descriptor.
            raw = handle.read(MAX_JSON_INPUT_BYTES + 1)
        if len(raw) > MAX_JSON_INPUT_BYTES:
            raise CampaignValidationError(f"{label} exceeds 1 MiB")
        return json.loads(
            raw.decode("utf-8-sig"),
            parse_constant=_reject_nonstandard_json_constant,
        )
    except CampaignValidationError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise CampaignValidationError(f"{label} is unreadable or malformed") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


@dataclass(frozen=True)
class Experiment:
    """One bounded, evidence-producing research experiment."""

    experiment_id: str
    market_lane: str
    strategy_family: str
    instrument: str
    session_window: str
    stage: str
    data_capability: Mapping[str, Any]
    cost_scenario: str
    parameter_fingerprint: str
    expected_evidence_version: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Experiment":
        data = _require_mapping(payload, "experiment")
        stage = _require_nonempty_string(data.get("stage"), "stage")
        if stage not in RESEARCH_STAGES:
            raise CampaignValidationError(f"stage must be one of {RESEARCH_STAGES}")

        data_capability = _require_mapping(
            data.get("data_capability"), "data_capability"
        )
        if not data_capability:
            raise CampaignValidationError("data_capability must not be empty")
        if not isinstance(data_capability.get("pinned"), bool):
            raise CampaignValidationError("data_capability.pinned must be a boolean")
        market_lane = _require_nonempty_string(data.get("market_lane"), "market_lane")
        if market_lane not in REQUIRED_MARKET_LANES:
            raise CampaignValidationError("market_lane is not approved")
        if market_lane == "FOREX_EURUSD_PRIMARY":
            for field_name in (
                "source_id",
                "calendar_id",
                "cost_model_id",
            ):
                _require_nonempty_string(
                    data_capability.get(field_name), f"data_capability.{field_name}"
                )
            pip_value = data_capability.get("pip_value")
            if (
                not _is_number(pip_value)
                or not math.isfinite(pip_value)
                or pip_value <= 0
            ):
                raise CampaignValidationError(
                    "data_capability.pip_value must be a positive finite number"
                )
        if market_lane == "CME_INDEX_FUTURES_COMPARISON":
            for field_name in (
                "source_id",
                "contract_definition_id",
                "calendar_id",
                "cost_model_id",
            ):
                _require_nonempty_string(
                    data_capability.get(field_name), f"data_capability.{field_name}"
                )
            tick_value = data_capability.get("tick_value")
            if (
                not _is_number(tick_value)
                or not math.isfinite(tick_value)
                or tick_value <= 0
            ):
                raise CampaignValidationError(
                    "data_capability.tick_value must be a positive finite number"
                )

        return cls(
            experiment_id=_require_nonempty_string(
                data.get("experiment_id"), "experiment_id"
            ),
            market_lane=market_lane,
            strategy_family=_require_nonempty_string(
                data.get("strategy_family"), "strategy_family"
            ),
            instrument=_require_nonempty_string(data.get("instrument"), "instrument"),
            session_window=_require_nonempty_string(
                data.get("session_window"), "session_window"
            ),
            stage=stage,
            data_capability=_freeze_json_mapping(data_capability),
            cost_scenario=_require_nonempty_string(
                data.get("cost_scenario"), "cost_scenario"
            ),
            parameter_fingerprint=_require_nonempty_string(
                data.get("parameter_fingerprint"), "parameter_fingerprint"
            ),
            expected_evidence_version=_require_nonempty_string(
                data.get("expected_evidence_version"), "expected_evidence_version"
            ),
        )

    def to_dict(self, *, include_experiment_id: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "market_lane": self.market_lane,
            "strategy_family": self.strategy_family,
            "instrument": self.instrument,
            "session_window": self.session_window,
            "stage": self.stage,
            "data_capability": _json_compatible(self.data_capability),
            "cost_scenario": self.cost_scenario,
            "parameter_fingerprint": self.parameter_fingerprint,
            "expected_evidence_version": self.expected_evidence_version,
        }
        if include_experiment_id:
            payload["experiment_id"] = self.experiment_id
        return payload


def experiment_fingerprint(experiment: Experiment) -> str:
    """Return the stable identity of an experiment, excluding its display ID."""

    if not isinstance(experiment, Experiment):
        raise CampaignValidationError("experiment must be an Experiment")
    canonical = _canonical_json(experiment.to_dict(include_experiment_id=False))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalised_readiness(
    category_points: Mapping[str, int], categories: frozenset[str]
) -> int:
    available_points = sum(EVIDENCE_CATEGORY_WEIGHTS[category] for category in categories)
    earned_points = sum(category_points[category] for category in categories)
    return round((earned_points / available_points) * 100)


def score_evidence(spec: "CampaignSpec", evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Score only evidence records with complete, passing provenance.

    The returned readiness measures are explanatory evidence meters.  They are
    deliberately not a trading permission; the controller can at most return
    ``PAPER_ELIGIBLE`` after an independent edge-gate evaluation.
    """

    if not isinstance(spec, CampaignSpec):
        raise CampaignValidationError("spec must be a CampaignSpec")
    data = _require_mapping(evidence, "evidence")
    _validate_json_input_size(data, "evidence JSON")
    records = data.get("evidence", [])
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise CampaignValidationError("evidence.evidence must be a sequence")
    if len(records) > MAX_EVIDENCE_RECORDS:
        raise CampaignValidationError("evidence.evidence exceeds 1000 records")

    supported_categories: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        category = record.get("category")
        if not isinstance(category, str) or category not in EVIDENCE_CATEGORY_WEIGHTS:
            continue
        try:
            _require_nonempty_string(record.get("source_id"), "evidence.source_id")
            _require_nonempty_string(record.get("version"), "evidence.version")
        except CampaignValidationError:
            continue
        if record.get("status") == "PASS":
            supported_categories.add(category)

    category_points = {
        category: EVIDENCE_CATEGORY_WEIGHTS[category]
        if category in supported_categories
        else 0
        for category in EVIDENCE_CATEGORY_WEIGHTS
    }
    profitability_readiness = sum(
        category_points[category] for category in PROFITABILITY_READINESS_CATEGORIES
    )
    engineering_readiness = _normalised_readiness(
        category_points, ENGINEERING_EVIDENCE_CATEGORIES
    )
    edge_evidence = _normalised_readiness(category_points, EDGE_EVIDENCE_CATEGORIES)

    return {
        "category_points": category_points,
        "supported_categories": sorted(supported_categories),
        "total_points": sum(category_points.values()),
        "profitability_readiness": profitability_readiness,
        "engineering_readiness": engineering_readiness,
        "edge_evidence": edge_evidence,
        "live_readiness": min(engineering_readiness, edge_evidence),
        "live_authorization": False,
    }


def _is_number(value: Any) -> bool:
    try:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        return False


def _performance_receipt_shape(raw: Any) -> Mapping[str, Any]:
    """Reject unknown/private fields instead of carrying them into a checkpoint."""
    data = _require_mapping(raw, "performance_evidence")
    if set(data) != PERFORMANCE_FIELDS:
        raise CampaignValidationError("performance_evidence fields are invalid")
    for name in PERFORMANCE_FIELDS - {"trades"}:
        if isinstance(data[name], (Mapping, list, tuple)):
            raise CampaignValidationError("performance_evidence metadata must be scalar")
    trades = data["trades"]
    if not isinstance(trades, (list, tuple)) or not 1 <= len(trades) <= MAX_OUTCOMES:
        raise CampaignValidationError("performance_evidence requires 1..1000 trades")
    for trade in trades:
        record = _require_mapping(trade, "performance_evidence.trade")
        if set(record) != PERFORMANCE_TRADE_FIELDS or any(
            isinstance(value, (Mapping, list, tuple)) for value in record.values()
        ):
            raise CampaignValidationError("performance_evidence trade fields are invalid")
    return data


def _derive_performance_metrics(candidate: Experiment, raw: Any) -> dict[str, Any]:
    """Recalculate closed-trade OOS metrics; identifiers are bindings, not authentication."""

    data = _performance_receipt_shape(raw)
    for name in ("source_id", "cost_model_id"):
        if data.get(name) != candidate.data_capability[name]:
            raise CampaignValidationError(f"performance_evidence.{name} does not match candidate")
    digest = data.get("dataset_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise CampaignValidationError("performance_evidence.dataset_sha256 is invalid")
    _require_nonempty_string(data.get("currency"), "performance_evidence.currency")
    initial_equity = data.get("initial_equity")
    if not _is_number(initial_equity) or initial_equity <= 0:
        raise CampaignValidationError("performance_evidence.initial_equity is invalid")
    frozen, start, end = [
        _require_utc_timestamp(data.get(name), f"performance_evidence.{name}")
        for name in ("selection_frozen_at_utc", "oos_start_utc", "oos_end_utc")
    ]
    frozen_time, start_time, end_time = map(_utc_datetime, (frozen, start, end))
    if not frozen_time <= start_time < end_time:
        raise CampaignValidationError("performance_evidence OOS window overlaps selection")
    trades = data.get("trades")
    if not isinstance(trades, (list, tuple)) or not 1 <= len(trades) <= MAX_OUTCOMES:
        raise CampaignValidationError("performance_evidence requires 1..1000 trades")
    seen: set[str] = set()
    previous_close = start_time
    base_values: list[Decimal] = []
    stress_values: list[Decimal] = []
    for raw_trade in trades:
        trade = _require_mapping(raw_trade, "performance_evidence.trade")
        identity = _require_nonempty_string(trade.get("trade_id"), "trade_id")
        if identity in seen:
            raise CampaignValidationError("duplicate performance trade")
        seen.add(identity)
        closed = _require_utc_timestamp(trade.get("closed_at_utc"), "trade.closed_at_utc")
        closed_time = _utc_datetime(closed)
        if not start_time <= previous_close <= closed_time < end_time:
            raise CampaignValidationError("performance trade chronology is outside OOS")
        previous_close = closed_time
        values = [trade.get(name) for name in ("gross_pnl", "base_cost", "stress_cost")]
        if not all(_is_number(value) for value in values):
            raise CampaignValidationError("performance trade values must be finite numbers")
        gross, base_cost, stress_cost = [Decimal(str(value)) for value in values]
        if not 0 <= base_cost <= stress_cost:
            raise CampaignValidationError("performance stress costs cannot be below base costs")
        base_values.append(gross - base_cost)
        stress_values.append(gross - stress_cost)

    def summarize(values: Sequence[Decimal]) -> tuple[float, float | None, float]:
        total = sum(values, Decimal(0))
        profit = sum((value for value in values if value > 0), Decimal(0))
        loss = -sum((value for value in values if value < 0), Decimal(0))
        equity = peak = Decimal(str(initial_equity))
        drawdown = Decimal(0)
        for value in values:
            equity += value
            peak = max(peak, equity)
            drawdown = max(drawdown, (peak - equity) / peak * 100)
        return float(total / len(values)), float(profit / loss) if loss else None, float(drawdown)

    expectancy, factor, base_dd = summarize(base_values)
    stressed_expectancy, stressed_factor, stress_dd = summarize(stress_values)
    metrics = {
        "oos_expectancy": expectancy,
        "stressed_expectancy": stressed_expectancy,
        "profit_factor_after_costs": factor,
        "stressed_profit_factor_after_costs": stressed_factor,
        "max_drawdown_pct": max(base_dd, stress_dd),
        "oos_trade_count": len(trades),
    }
    if any(value is not None and not _is_number(value) for value in metrics.values()):
        raise CampaignValidationError("performance metrics overflowed")
    return metrics


def evaluate_edge_gate(spec: "CampaignSpec", evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Check candidate-bound claims and recalculate cost-adjusted OOS metrics.

    Source authenticity, open-position drawdown, independent test selection,
    and actual paper fills remain unverified. Eligibility only routes research.
    """

    if not isinstance(spec, CampaignSpec):
        raise CampaignValidationError("spec must be a CampaignSpec")
    data = _require_mapping(evidence, "edge evidence")
    try:
        _validate_json_input_size(data, "edge evidence JSON")
    except CampaignValidationError:
        invalid_reasons = ["edge_evidence_invalid_json"]
        for name in ("profit_factor_after_costs", "max_drawdown_pct"):
            if not _is_number(data.get(name)):
                invalid_reasons.append(name)
        return {
            "status": "REJECT", "paper_eligible": False, "reasons": invalid_reasons,
            "derived_metrics": {}, "source_authentication_verified": False,
            "paper_readiness_verified": False, "live_authorization": False,
        }
    reasons: list[str] = []
    candidate: Experiment | None = None
    metrics: dict[str, Any] = {}

    try:
        candidate_fingerprint = _require_nonempty_string(
            data.get("candidate_fingerprint"), "candidate_fingerprint"
        )
    except CampaignValidationError:
        candidate_fingerprint = None
        reasons.append("candidate_fingerprint")
    try:
        evidence_version = _require_nonempty_string(
            data.get("evidence_version"), "evidence_version"
        )
    except CampaignValidationError:
        evidence_version = None
        reasons.append("evidence_version")
    if candidate_fingerprint is not None:
        matching_candidates = [
            experiment
            for experiment in spec.catalog
            if experiment_fingerprint(experiment) == candidate_fingerprint
        ]
        if not matching_candidates:
            reasons.append("candidate_fingerprint")
        else:
            candidate = matching_candidates[0]
            if candidate.stage != "PAPER":
                reasons.append("candidate_stage")
            if evidence_version != candidate.expected_evidence_version:
                reasons.append("evidence_version")

    if data.get("performance_evidence") is None:
        reasons.append("performance_evidence_required")
    elif candidate is not None:
        try:
            metrics = _derive_performance_metrics(candidate, data["performance_evidence"])
        except (CampaignValidationError, CampaignCheckpointError):
            reasons.append("performance_evidence_invalid")
        else:
            if metrics["oos_expectancy"] <= 0:
                reasons.append("derived_oos_expectancy")
            if metrics["stressed_expectancy"] <= 0:
                reasons.append("derived_stressed_expectancy")
            # Null PF means no loss denominator; positive expectancy is still required.
            for name in ("profit_factor_after_costs", "stressed_profit_factor_after_costs"):
                if metrics[name] is not None and metrics[name] < 1.10:
                    reasons.append(f"derived_{name}")
            if metrics["max_drawdown_pct"] > 10:
                reasons.append("derived_max_drawdown_pct")
            if metrics["oos_trade_count"] < spec.edge_gates["min_oos_trade_count"]:
                reasons.append("derived_oos_trade_count")

    if data.get("positive_oos_expectancy") is not True:
        reasons.append("positive_oos_expectancy")
    if data.get("positive_stressed_expectancy") is not True:
        reasons.append("positive_stressed_expectancy")

    profit_factor = data.get("profit_factor_after_costs")
    if not _is_number(profit_factor) or profit_factor < 1.10:
        reasons.append("profit_factor_after_costs")

    drawdown = data.get("max_drawdown_pct")
    if not _is_number(drawdown) or drawdown < 0 or drawdown > 10:
        reasons.append("max_drawdown_pct")

    oos_trade_count = data.get("oos_trade_count")
    if (
        isinstance(oos_trade_count, bool)
        or not isinstance(oos_trade_count, int)
        or oos_trade_count < spec.edge_gates["min_oos_trade_count"]
    ):
        reasons.append("oos_trade_count")

    for field_name in (
        "walk_forward_stable",
        "replication_stable",
        "nearby_parameter_stable",
        "no_profit_concentration",
    ):
        if data.get(field_name) is not True:
            reasons.append(field_name)

    paper_eligible = not reasons
    return {
        "status": "PAPER_ELIGIBLE" if paper_eligible else "REJECT",
        "paper_eligible": paper_eligible,
        "reasons": reasons,
        "derived_metrics": metrics,
        "source_authentication_verified": False,
        "paper_readiness_verified": False,
        "live_authorization": False,
    }


@dataclass(frozen=True)
class CampaignSpec:
    """Validated immutable envelope for the finite approved research catalog."""

    campaign_id: str
    campaign_version: str
    market_lanes: tuple[str, ...]
    experiment_budget: int
    edge_gates: Mapping[str, Any]
    freshness: Mapping[str, Any]
    experiment_catalog: tuple[Experiment, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CampaignSpec":
        data = _require_mapping(payload, "campaign")
        lanes_value = data.get("market_lanes")
        if isinstance(lanes_value, (str, bytes)) or not isinstance(lanes_value, Sequence):
            raise CampaignValidationError("market_lanes must be a sequence")
        lanes = tuple(
            _require_nonempty_string(lane, "market_lanes item") for lane in lanes_value
        )
        if len(lanes) != len(REQUIRED_MARKET_LANES) or set(lanes) != REQUIRED_MARKET_LANES:
            raise CampaignValidationError(
                "market_lanes must contain exactly FOREX_EURUSD_PRIMARY and "
                "CME_INDEX_FUTURES_COMPARISON"
            )

        edge_gates = _require_mapping(data.get("edge_gates"), "edge_gates")
        _require_positive_integer(edge_gates.get("min_oos_trade_count"), "edge_gates")

        freshness = _require_mapping(data.get("freshness"), "freshness")
        _require_positive_integer(
            freshness.get("progress_max_age_seconds"), "freshness"
        )

        has_catalog = "experiment_catalog" in data
        has_legacy_catalog = "experiments" in data
        if has_catalog and has_legacy_catalog:
            raise CampaignValidationError(
                "provide only one of experiment_catalog or experiments"
            )
        raw_catalog = data.get(
            "experiment_catalog" if has_catalog else "experiments", []
        )
        if isinstance(raw_catalog, (str, bytes)) or not isinstance(raw_catalog, Sequence):
            raise CampaignValidationError("experiment_catalog must be a sequence")
        if len(raw_catalog) > MAX_CATALOG_ENTRIES:
            raise CampaignValidationError("experiment_catalog exceeds 1000 entries")
        experiment_budget = _require_positive_integer(
            data.get("experiment_budget"), "experiment_budget"
        )
        if experiment_budget > MAX_EXPERIMENT_BUDGET:
            raise CampaignValidationError("experiment_budget exceeds 1000")
        catalog = tuple(Experiment.from_dict(item) for item in raw_catalog)

        return cls(
            campaign_id=_require_nonempty_string(data.get("campaign_id"), "campaign_id"),
            campaign_version=_require_nonempty_string(
                data.get("campaign_version"), "campaign_version"
            ),
            market_lanes=lanes,
            experiment_budget=experiment_budget,
            edge_gates=_freeze_json_mapping(edge_gates),
            freshness=_freeze_json_mapping(freshness),
            experiment_catalog=catalog,
        )

    @property
    def catalog(self) -> tuple[Experiment, ...]:
        """Alias for the finite catalog used by the deterministic router."""

        return self.experiment_catalog

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical JSON campaign envelope used for replay."""

        return {
            "campaign_id": self.campaign_id,
            "campaign_version": self.campaign_version,
            "market_lanes": list(self.market_lanes),
            "experiment_budget": self.experiment_budget,
            "edge_gates": _json_compatible(self.edge_gates),
            "freshness": _json_compatible(self.freshness),
            "experiment_catalog": [item.to_dict() for item in self.catalog],
        }


@dataclass(frozen=True)
class ExperimentOutcome:
    """Normalized result from a single finished campaign experiment."""

    experiment_fingerprint: str
    stage: str
    status: str
    reason: str
    evidence_version: str
    completed_at_utc: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentOutcome":
        data = _require_mapping(payload, "experiment outcome")
        stage = _require_nonempty_string(data.get("stage"), "outcome.stage")
        if stage not in RESEARCH_STAGES:
            raise CampaignValidationError("outcome.stage is unsupported")
        status = _require_nonempty_string(data.get("status"), "outcome.status")
        if status not in {"ADVANCE", "REJECT", "BLOCKED"}:
            raise CampaignValidationError("outcome.status is unsupported")
        return cls(
            experiment_fingerprint=_require_nonempty_string(
                data.get("experiment_fingerprint"), "outcome.experiment_fingerprint"
            ),
            stage=stage,
            status=status,
            reason=_require_nonempty_string(data.get("reason"), "outcome.reason"),
            evidence_version=_require_nonempty_string(
                data.get("evidence_version"), "outcome.evidence_version"
            ),
            completed_at_utc=_require_utc_timestamp(
                data.get("completed_at_utc"), "outcome.completed_at_utc"
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "experiment_fingerprint": self.experiment_fingerprint,
            "stage": self.stage,
            "status": self.status,
            "reason": self.reason,
            "evidence_version": self.evidence_version,
            "completed_at_utc": self.completed_at_utc,
        }


@dataclass(frozen=True)
class CampaignDecision:
    """A safe controller decision, never a live-trading authorization."""

    status: str
    reason: str
    next_experiment: Experiment | None = None
    sos_wake_required: bool = False
    paper_edge_gate: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "next_experiment": (
                self.next_experiment.to_dict() if self.next_experiment is not None else None
            ),
            "sos_wake_required": self.sos_wake_required,
            "paper_edge_gate": (
                _json_compatible(self.paper_edge_gate)
                if self.paper_edge_gate is not None
                else None
            ),
            "live_authorization": False,
        }


def _validate_checkpoint_decision(value: Any) -> None:
    decision = _require_mapping(value, "checkpoint last_decision")
    if "next_experiment" not in decision:
        raise CampaignCheckpointError("checkpoint last_decision.next_experiment is required")
    if decision.get("live_authorization") is not False:
        raise CampaignCheckpointError("checkpoint last_decision.live_authorization must be false")
    status = _require_nonempty_string(decision.get("status"), "checkpoint last_decision.status")
    if status not in {"ADVANCE", "REJECT", "BLOCKED", "NO_EDGE_IN_SCOPE", "BUDGET_EXHAUSTED", "RESEARCH_COMPLETE"}:
        raise CampaignCheckpointError("checkpoint last_decision.status is unsupported")
    _require_nonempty_string(decision.get("reason"), "checkpoint last_decision.reason")
    sos_wake_required = decision.get("sos_wake_required")
    if not isinstance(sos_wake_required, bool):
        raise CampaignCheckpointError(
            "checkpoint last_decision.sos_wake_required must be a boolean"
        )
    if "paper_edge_gate" not in decision:
        raise CampaignCheckpointError("checkpoint last_decision.paper_edge_gate is required")
    paper_edge_gate = decision.get("paper_edge_gate")
    if paper_edge_gate is not None:
        if not isinstance(paper_edge_gate, Mapping):
            raise CampaignCheckpointError("checkpoint paper_edge_gate must be a mapping or null")
        gate_status = paper_edge_gate.get("status")
        if gate_status not in {"REJECT", "PAPER_ELIGIBLE"}:
            raise CampaignCheckpointError("checkpoint paper_edge_gate.status is unsupported")
        if paper_edge_gate.get("paper_eligible") is not (gate_status == "PAPER_ELIGIBLE"):
            raise CampaignCheckpointError("checkpoint paper_edge_gate status is inconsistent")
        if paper_edge_gate.get("live_authorization") is not False:
            raise CampaignCheckpointError("checkpoint paper_edge_gate.live_authorization must be false")
        gate_reasons = paper_edge_gate.get("reasons")
        if not isinstance(gate_reasons, list) or any(
            not isinstance(reason, str) or not reason for reason in gate_reasons
        ):
            raise CampaignCheckpointError("checkpoint paper_edge_gate.reasons must be a string list")
    next_experiment = decision.get("next_experiment")
    if status in {"ADVANCE", "REJECT"}:
        if not isinstance(next_experiment, Mapping):
            raise CampaignCheckpointError(
                "checkpoint last_decision.next_experiment is required"
            )
        try:
            Experiment.from_dict(next_experiment)
        except CampaignValidationError as error:
            raise CampaignCheckpointError(
                "checkpoint last_decision.next_experiment is invalid"
            ) from error
    elif next_experiment is not None:
        raise CampaignCheckpointError(
            "checkpoint last_decision.next_experiment must be null"
        )
    if sos_wake_required is not (status == "BLOCKED"):
        raise CampaignCheckpointError(
            "checkpoint last_decision.sos_wake_required is inconsistent"
        )


LANE_PRIORITY = {
    "FOREX_EURUSD_PRIMARY": 0,
    "CME_INDEX_FUTURES_COMPARISON": 1,
}
STRATEGY_FAMILY_PRIORITY = {
    "MOMENTUM": 0,
    "MEAN_REVERSION": 1,
    "BREAKOUT": 2,
}


def _candidate_sort_key(experiment: Experiment) -> tuple[int, int, int, str]:
    return (
        LANE_PRIORITY.get(experiment.market_lane, len(LANE_PRIORITY)),
        STRATEGY_FAMILY_PRIORITY.get(
            experiment.strategy_family, len(STRATEGY_FAMILY_PRIORITY)
        ),
        RESEARCH_STAGES.index(experiment.stage),
        experiment.experiment_id,
    )


def _lineage_key(experiment: Experiment) -> tuple[str, str, str, str, str, str, str, str]:
    return (
        experiment.market_lane,
        experiment.strategy_family,
        experiment.instrument,
        experiment.session_window,
        _canonical_json(experiment.data_capability),
        experiment.cost_scenario,
        experiment.parameter_fingerprint,
        experiment.expected_evidence_version,
    )


def _blocked(reason: str) -> CampaignDecision:
    return CampaignDecision(status="BLOCKED", reason=reason, sos_wake_required=True)


def _find_next_eligible_experiment(
    spec: CampaignSpec, outcomes_by_fingerprint: Mapping[str, ExperimentOutcome]
) -> Experiment | None:
    for candidate in sorted(spec.catalog, key=_candidate_sort_key):
        candidate_fingerprint = experiment_fingerprint(candidate)
        if candidate_fingerprint in outcomes_by_fingerprint:
            continue
        stage_index = RESEARCH_STAGES.index(candidate.stage)
        if stage_index == 0:
            return candidate

        predecessor_stage = RESEARCH_STAGES[stage_index - 1]
        predecessor_fingerprints = {
            experiment_fingerprint(experiment)
            for experiment in spec.catalog
            if _lineage_key(experiment) == _lineage_key(candidate)
            and experiment.stage == predecessor_stage
        }
        if any(
            outcomes_by_fingerprint[fingerprint].status == "ADVANCE"
            for fingerprint in predecessor_fingerprints
            if fingerprint in outcomes_by_fingerprint
        ):
            return candidate
    return None


def run_campaign_cycle(
    spec: CampaignSpec,
    outcomes: Sequence[ExperimentOutcome],
    now_utc: str,
    paper_evidence: Mapping[str, Any] | None = None,
) -> CampaignDecision:
    """Select the next safe finite-catalog experiment without side effects.

    ``ADVANCE`` means only that the next research experiment is selected.  It
    does not run it, create a job, or grant paper/live trading authority.
    """

    if not isinstance(spec, CampaignSpec):
        raise CampaignValidationError("spec must be a CampaignSpec")
    normalized_now = _require_utc_timestamp(now_utc, "now_utc")
    if isinstance(outcomes, (str, bytes)) or not isinstance(outcomes, Sequence):
        raise CampaignValidationError("outcomes must be a sequence")
    if len(outcomes) > MAX_OUTCOMES:
        raise CampaignValidationError("outcomes exceeds 1000 entries")
    if len(outcomes) > spec.experiment_budget:
        return _blocked("OUTCOME_HISTORY_EXCEEDS_APPROVED_BUDGET")
    if isinstance(paper_evidence, Mapping):
        _validate_json_input_size(paper_evidence, "paper evidence JSON")
        evidence_records = paper_evidence.get("evidence", [])
        if isinstance(evidence_records, Sequence) and not isinstance(
            evidence_records, (str, bytes)
        ) and len(evidence_records) > MAX_EVIDENCE_RECORDS:
            raise CampaignValidationError("paper evidence exceeds 1000 evidence records")

    candidates_by_fingerprint: dict[str, list[Experiment]] = {}
    for candidate in spec.catalog:
        candidates_by_fingerprint.setdefault(experiment_fingerprint(candidate), []).append(
            candidate
        )

    outcomes_by_fingerprint: dict[str, ExperimentOutcome] = {}
    for outcome in outcomes:
        if not isinstance(outcome, ExperimentOutcome):
            raise CampaignValidationError("outcomes must contain ExperimentOutcome values")
        normalized_outcome = ExperimentOutcome.from_dict(outcome.to_dict())
        if _utc_datetime(normalized_outcome.completed_at_utc) > _utc_datetime(normalized_now):
            return _blocked("OUTCOME_COMPLETED_IN_FUTURE")
        outcome = normalized_outcome
        if outcome.experiment_fingerprint in outcomes_by_fingerprint:
            return _blocked("DUPLICATE_OUTCOME_FINGERPRINT")
        matching_candidates = candidates_by_fingerprint.get(outcome.experiment_fingerprint)
        if not matching_candidates:
            return _blocked("OUTCOME_EXPERIMENT_NOT_IN_CATALOG")
        if any(
            outcome.stage != candidate.stage
            or outcome.evidence_version != candidate.expected_evidence_version
            for candidate in matching_candidates
        ):
            return _blocked("OUTCOME_CONTRACT_MISMATCH")
        outcomes_by_fingerprint[outcome.experiment_fingerprint] = outcome

    for outcome in outcomes_by_fingerprint.values():
        candidate = candidates_by_fingerprint[outcome.experiment_fingerprint][0]
        stage_index = RESEARCH_STAGES.index(candidate.stage)
        if stage_index == 0:
            continue
        predecessor_stage = RESEARCH_STAGES[stage_index - 1]
        predecessor_fingerprints = {
            experiment_fingerprint(experiment)
            for experiment in spec.catalog
            if _lineage_key(experiment) == _lineage_key(candidate)
            and experiment.stage == predecessor_stage
        }
        if not any(
            outcomes_by_fingerprint[fingerprint].status == "ADVANCE"
            for fingerprint in predecessor_fingerprints
            if fingerprint in outcomes_by_fingerprint
        ):
            return _blocked("OUTCOME_STAGE_SEQUENCE_INVALID")
        if not any(
            _utc_datetime(outcomes_by_fingerprint[fingerprint].completed_at_utc)
            <= _utc_datetime(outcome.completed_at_utc)
            for fingerprint in predecessor_fingerprints
            if fingerprint in outcomes_by_fingerprint
            and outcomes_by_fingerprint[fingerprint].status == "ADVANCE"
        ):
            return _blocked("OUTCOME_STAGE_CHRONOLOGY_INVALID")

    for outcome in outcomes_by_fingerprint.values():
        if outcome.status == "BLOCKED":
            return _blocked(outcome.reason)

    next_experiment = _find_next_eligible_experiment(spec, outcomes_by_fingerprint)
    duplicate_completed = any(
        len(candidates) > 1 and fingerprint in outcomes_by_fingerprint
        for fingerprint, candidates in candidates_by_fingerprint.items()
    )
    if next_experiment is None:
        latest_by_lineage: dict[tuple[str, ...], ExperimentOutcome] = {}
        for fingerprint, outcome in outcomes_by_fingerprint.items():
            lineage = _lineage_key(candidates_by_fingerprint[fingerprint][0])
            previous = latest_by_lineage.get(lineage)
            if previous is None or RESEARCH_STAGES.index(outcome.stage) > RESEARCH_STAGES.index(previous.stage):
                latest_by_lineage[lineage] = outcome
        catalog_lineages = {_lineage_key(candidate) for candidate in spec.catalog}
        if latest_by_lineage and set(latest_by_lineage) != catalog_lineages:
            return CampaignDecision(
                status="BUDGET_EXHAUSTED", reason="CAMPAIGN_VALIDATION_SCOPE_INCOMPLETE"
            )
        if any(
            outcome.status == "ADVANCE" and outcome.stage != "PAPER"
            for outcome in latest_by_lineage.values()
        ):
            return CampaignDecision(
                status="BUDGET_EXHAUSTED", reason="CAMPAIGN_VALIDATION_SCOPE_INCOMPLETE"
            )
        if any(outcome.stage == "PAPER" and outcome.status == "ADVANCE" for outcome in latest_by_lineage.values()):
            return CampaignDecision(
                status="RESEARCH_COMPLETE", reason="CAMPAIGN_RESEARCH_RESULTS_REQUIRE_REVIEW"
            )
        if latest_by_lineage and set(latest_by_lineage) == catalog_lineages:
            return CampaignDecision(
                status="NO_EDGE_IN_SCOPE", reason="CAMPAIGN_VIABLE_CATALOG_EXHAUSTED"
            )
        return _blocked("campaign_active_but_no_next_experiment")
    if len(outcomes_by_fingerprint) >= spec.experiment_budget:
        return CampaignDecision(
            status="BUDGET_EXHAUSTED", reason="CAMPAIGN_APPROVED_BUDGET_EXHAUSTED"
        )
    if next_experiment.data_capability.get("pinned") is not True:
        if next_experiment.market_lane == "FOREX_EURUSD_PRIMARY":
            return _blocked("FOREX_DATA_CAPABILITY_MISSING")
        if next_experiment.market_lane == "CME_INDEX_FUTURES_COMPARISON":
            return _blocked("FUTURES_DATA_CAPABILITY_MISSING")
        return _blocked("DATA_CAPABILITY_MISSING")
    paper_edge_gate = None
    if next_experiment.stage == "PAPER":
        if isinstance(paper_evidence, Mapping):
            try:
                paper_edge_gate = evaluate_edge_gate(spec, paper_evidence)
                if paper_evidence.get("candidate_fingerprint") != experiment_fingerprint(next_experiment):
                    paper_edge_gate = {
                        "status": "REJECT",
                        "paper_eligible": False,
                        "reasons": ["selected_candidate_mismatch"],
                        "live_authorization": False,
                    }
            except CampaignValidationError:
                paper_edge_gate = {
                    "status": "REJECT",
                    "paper_eligible": False,
                    "reasons": ["paper_evidence_invalid"],
                    "live_authorization": False,
                }
        else:
            paper_edge_gate = {
                "status": "REJECT",
                "paper_eligible": False,
                "reasons": ["paper_evidence_required"],
                "live_authorization": False,
            }
        if paper_edge_gate["status"] != "PAPER_ELIGIBLE":
            return CampaignDecision(
                status="REJECT",
                reason="PAPER_EDGE_GATE_REJECTED",
                next_experiment=next_experiment,
                sos_wake_required=False,
                paper_edge_gate=paper_edge_gate,
            )
    if duplicate_completed:
        return CampaignDecision(
            status="REJECT",
            reason="DUPLICATE_EXPERIMENT_FINGERPRINT",
            next_experiment=next_experiment,
            sos_wake_required=False,
            paper_edge_gate=paper_edge_gate,
        )
    return CampaignDecision(
        status="ADVANCE",
        reason="NEXT_EXPERIMENT_SELECTED",
        next_experiment=next_experiment,
        sos_wake_required=False,
        paper_edge_gate=paper_edge_gate,
    )


_CHECKPOINT_FIELDS = frozenset(
    {
        "campaign_id",
        "campaign_version",
        "last_completed_fingerprint",
        "completed_fingerprints",
        "last_progress_utc",
        "progress_max_age_seconds",
        "last_decision",
        "outcomes",
        "routing_context",
    }
)


def _safe_paper_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only gate inputs and scorecard provenance in a replay context."""

    if not isinstance(value, Mapping):
        raise CampaignCheckpointError("paper evidence must be a mapping")
    try:
        _validate_json_input_size(value, "paper evidence JSON")
    except CampaignValidationError as error:
        raise CampaignCheckpointError(str(error)) from error

    safe = {
        field_name: _json_compatible(value[field_name])
        for field_name in PAPER_GATE_INPUT_FIELDS
        if field_name in value
    }
    if "performance_evidence" in safe:
        try:
            _performance_receipt_shape(safe["performance_evidence"])
        except CampaignValidationError as error:
            raise CampaignCheckpointError(str(error)) from error
    records = value.get("evidence")
    if records is not None:
        if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
            raise CampaignCheckpointError("paper evidence.evidence must be a sequence")
        if len(records) > MAX_EVIDENCE_RECORDS:
            raise CampaignCheckpointError("paper evidence exceeds 1000 evidence records")
        safe["evidence"] = [
            {
                field_name: _json_compatible(record[field_name])
                for field_name in ("category", "source_id", "version", "status")
                if field_name in record
            }
            for record in records
            if isinstance(record, Mapping)
        ]
    return safe


def _build_routing_context(
    spec: CampaignSpec, paper_evidence: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    if not isinstance(spec, CampaignSpec):
        raise CampaignCheckpointError("routing context requires a CampaignSpec")
    route_inputs: dict[str, Any] = {}
    if paper_evidence is not None:
        route_inputs["paper_evidence"] = _safe_paper_evidence(paper_evidence)
    return {
        "schema": ROUTING_CONTEXT_SCHEMA,
        "campaign_spec": spec.to_dict(),
        "route_inputs": route_inputs,
    }


def _routing_context_parts(
    value: Any, campaign_id: str, campaign_version: str
) -> tuple[CampaignSpec, Mapping[str, Any] | None]:
    try:
        context = _require_mapping(value, "checkpoint routing_context")
        if set(context) != {"schema", "campaign_spec", "route_inputs"}:
            raise CampaignCheckpointError("checkpoint routing_context fields are invalid")
        if context.get("schema") != ROUTING_CONTEXT_SCHEMA:
            raise CampaignCheckpointError("checkpoint routing_context schema is unsupported")
        route_inputs = context.get("route_inputs")
        if not isinstance(route_inputs, Mapping) or set(route_inputs) - {"paper_evidence"}:
            raise CampaignCheckpointError("checkpoint routing_context.route_inputs are invalid")
        paper_evidence = route_inputs.get("paper_evidence")
        if paper_evidence is not None:
            paper_evidence = _require_mapping(
                paper_evidence, "checkpoint routing_context.paper_evidence"
            )
            normalized_evidence = _safe_paper_evidence(paper_evidence)
            if _canonical_json(normalized_evidence) != _canonical_json(paper_evidence):
                raise CampaignCheckpointError(
                    "checkpoint routing_context.paper_evidence is not canonical"
                )
        raw_spec = _require_mapping(
            context.get("campaign_spec"), "checkpoint routing_context.campaign_spec"
        )
        spec = CampaignSpec.from_dict(raw_spec)
        if _canonical_json(spec.to_dict()) != _canonical_json(raw_spec):
            raise CampaignCheckpointError(
                "checkpoint routing_context campaign spec is not canonical"
            )
        if (spec.campaign_id, spec.campaign_version) != (campaign_id, campaign_version):
            raise CampaignCheckpointError(
                "checkpoint routing_context campaign identity/version does not match checkpoint"
            )
        return spec, paper_evidence
    except CampaignCheckpointError:
        raise
    except (CampaignValidationError, TypeError, ValueError) as error:
        raise CampaignCheckpointError("checkpoint routing_context is invalid") from error


def _checkpoint_payload_without_digest(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(checkpoint, Mapping):
        raise CampaignCheckpointError("checkpoint must be a mapping")
    if "digest" in checkpoint:
        raise CampaignCheckpointError("checkpoint input must not contain a digest")
    missing = _CHECKPOINT_FIELDS - set(checkpoint)
    if missing:
        raise CampaignCheckpointError(
            f"checkpoint is missing required fields: {', '.join(sorted(missing))}"
        )
    try:
        canonical_payload = _canonical_json(dict(checkpoint))
    except (CampaignValidationError, TypeError, ValueError, RecursionError) as error:
        raise CampaignCheckpointError("checkpoint is not JSON-compatible") from error
    if len(canonical_payload.encode("utf-8")) > MAX_JSON_INPUT_BYTES:
        raise CampaignCheckpointError("checkpoint exceeds 1 MiB")
    try:
        payload = json.loads(canonical_payload)
    except (TypeError, ValueError, RecursionError) as error:
        raise CampaignCheckpointError("checkpoint is not JSON-compatible") from error

    for field_name in ("campaign_id", "campaign_version"):
        if not isinstance(payload.get(field_name), str) or not payload[field_name].strip():
            raise CampaignCheckpointError(f"checkpoint {field_name} must be a non-empty string")
    try:
        payload["last_progress_utc"] = _require_utc_timestamp(
            payload.get("last_progress_utc"), "checkpoint last_progress_utc"
        )
        _require_positive_integer(
            payload.get("progress_max_age_seconds"), "checkpoint progress_max_age_seconds"
        )
    except CampaignValidationError as error:
        raise CampaignCheckpointError(str(error)) from error
    last_fingerprint = payload.get("last_completed_fingerprint")
    if last_fingerprint is not None and (
        not isinstance(last_fingerprint, str) or not last_fingerprint
    ):
        raise CampaignCheckpointError(
            "checkpoint last_completed_fingerprint must be a string or null"
        )
    completed_fingerprints = payload.get("completed_fingerprints")
    if isinstance(completed_fingerprints, (str, bytes)) or not isinstance(
        completed_fingerprints, list
    ):
        raise CampaignCheckpointError("checkpoint completed_fingerprints must be a list")
    if any(not isinstance(item, str) or not item for item in completed_fingerprints):
        raise CampaignCheckpointError("checkpoint completed_fingerprints contains an invalid value")
    if len(completed_fingerprints) != len(set(completed_fingerprints)):
        raise CampaignCheckpointError("checkpoint completed_fingerprints contains duplicates")
    if last_fingerprint != (completed_fingerprints[-1] if completed_fingerprints else None):
        raise CampaignCheckpointError(
            "checkpoint last_completed_fingerprint does not match completed history"
        )
    try:
        _validate_checkpoint_decision(payload.get("last_decision"))
    except CampaignValidationError as error:
        raise CampaignCheckpointError("checkpoint last_decision is invalid") from error
    raw_outcomes = payload.get("outcomes")
    if isinstance(raw_outcomes, (str, bytes)) or not isinstance(raw_outcomes, list):
        raise CampaignCheckpointError("checkpoint outcomes must be a list")
    if len(raw_outcomes) > MAX_OUTCOMES:
        raise CampaignCheckpointError("checkpoint outcomes exceed 1000 entries")
    try:
        parsed_outcomes = [ExperimentOutcome.from_dict(item) for item in raw_outcomes]
    except (CampaignValidationError, TypeError, ValueError) as error:
        raise CampaignCheckpointError("checkpoint outcomes are invalid") from error
    if [outcome.experiment_fingerprint for outcome in parsed_outcomes] != completed_fingerprints:
        raise CampaignCheckpointError(
            "checkpoint completed_fingerprints does not match outcomes"
        )
    payload["outcomes"] = [outcome.to_dict() for outcome in parsed_outcomes]
    if parsed_outcomes:
        newest_completion = max(
            (outcome.completed_at_utc for outcome in parsed_outcomes),
            key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        )
        if payload["last_progress_utc"] != newest_completion:
            raise CampaignCheckpointError(
                "checkpoint last_progress_utc must match the newest completed outcome"
            )

    spec, paper_evidence = _routing_context_parts(
        payload["routing_context"], payload["campaign_id"], payload["campaign_version"]
    )
    if payload["progress_max_age_seconds"] != spec.freshness["progress_max_age_seconds"]:
        raise CampaignCheckpointError(
            "checkpoint progress_max_age_seconds must match campaign routing context"
        )
    expected_decision = run_campaign_cycle(
        spec, parsed_outcomes, payload["last_progress_utc"], paper_evidence
    )
    if _canonical_json(expected_decision.to_dict()) != _canonical_json(payload["last_decision"]):
        raise CampaignCheckpointError(
            "checkpoint last_decision does not match deterministic campaign routing replay"
        )
    payload["routing_context"] = _build_routing_context(spec, paper_evidence)
    return payload


def validate_checkpoint_payload(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical digest-free checkpoint data, or fail closed.

    Both checkpoint readers use this digest, decision, and history contract.
    The caller's mapping is never modified.
    """

    if not isinstance(checkpoint, Mapping):
        raise CampaignCheckpointError("checkpoint must be a mapping")
    try:
        checkpoint_size = len(_canonical_json(checkpoint).encode("utf-8"))
    except CampaignValidationError as error:
        raise CampaignCheckpointError("checkpoint is not JSON-compatible") from error
    if checkpoint_size > MAX_JSON_INPUT_BYTES:
        raise CampaignCheckpointError("checkpoint exceeds 1 MiB")
    stored_digest = checkpoint.get("digest")
    if not isinstance(stored_digest, str) or len(stored_digest) != 64:
        raise CampaignCheckpointError("checkpoint digest is missing or invalid")
    raw_payload = {key: value for key, value in checkpoint.items() if key != "digest"}
    try:
        expected_digest = hashlib.sha256(
            _canonical_json(raw_payload).encode("utf-8")
        ).hexdigest()
    except CampaignValidationError as error:
        raise CampaignCheckpointError("checkpoint is not JSON-compatible") from error
    if stored_digest != expected_digest:
        raise CampaignCheckpointError("checkpoint digest verification failed")
    return _checkpoint_payload_without_digest(raw_payload)


def build_checkpoint(
    spec: CampaignSpec,
    outcomes: Sequence[ExperimentOutcome],
    decision: CampaignDecision,
    now_utc: str,
    previous_checkpoint: Mapping[str, Any] | None = None,
    paper_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a replay-verified checkpoint without refreshing unchanged work."""

    if not isinstance(spec, CampaignSpec) or not isinstance(decision, CampaignDecision):
        raise CampaignCheckpointError("checkpoint requires campaign spec and decision")
    if isinstance(outcomes, (str, bytes)) or not isinstance(outcomes, Sequence):
        raise CampaignCheckpointError("checkpoint outcomes must be a sequence")
    if len(outcomes) > MAX_OUTCOMES:
        raise CampaignCheckpointError("checkpoint outcomes exceed 1000 entries")
    if any(not isinstance(outcome, ExperimentOutcome) for outcome in outcomes):
        raise CampaignCheckpointError("checkpoint outcomes must contain ExperimentOutcome values")
    try:
        history = [ExperimentOutcome.from_dict(outcome.to_dict()).to_dict() for outcome in outcomes]
    except (CampaignValidationError, TypeError, ValueError) as error:
        raise CampaignCheckpointError("checkpoint outcomes are invalid") from error
    previous: dict[str, Any] | None = None
    routing_context = _build_routing_context(spec, paper_evidence)
    if previous_checkpoint is not None:
        if not isinstance(previous_checkpoint, Mapping):
            raise CampaignCheckpointError("checkpoint previous state must be a mapping")
        previous_input = dict(previous_checkpoint)
        raw_previous_outcomes = previous_input.get("outcomes")
        if isinstance(raw_previous_outcomes, list):
            previous_input["outcomes"] = [
                item.to_dict() if isinstance(item, ExperimentOutcome) else item
                for item in raw_previous_outcomes
            ]
        previous = (
            validate_checkpoint_payload(previous_input)
            if "digest" in previous_input
            else _checkpoint_payload_without_digest(previous_input)
        )
        if (previous["campaign_id"], previous["campaign_version"]) != (
            spec.campaign_id, spec.campaign_version
        ):
            raise CampaignCheckpointError("checkpoint campaign identity/version does not match spec")
        previous_spec, _ = _routing_context_parts(
            previous["routing_context"], previous["campaign_id"], previous["campaign_version"]
        )
        if _canonical_json(previous_spec.to_dict()) != _canonical_json(spec.to_dict()):
            raise CampaignCheckpointError("checkpoint campaign routing context does not match spec")
        if not history:
            history = previous["outcomes"]
        elif history[: len(previous["outcomes"])] != previous["outcomes"]:
            raise CampaignCheckpointError(
                "checkpoint outcomes must preserve the persisted completed history"
            )

    if previous is not None and history == previous["outcomes"]:
        last_progress = previous["last_progress_utc"]
    elif history:
        last_progress = max(
            (item["completed_at_utc"] for item in history),
            key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        )
    else:
        last_progress = _require_utc_timestamp(now_utc, "checkpoint now_utc")

    parsed_history = [ExperimentOutcome.from_dict(item) for item in history]
    expected_decision = run_campaign_cycle(
        spec, parsed_history, now_utc, paper_evidence
    )
    if _canonical_json(expected_decision.to_dict()) != _canonical_json(decision.to_dict()):
        raise CampaignCheckpointError(
            "checkpoint decision does not match deterministic campaign routing replay"
        )
    fingerprints = [item["experiment_fingerprint"] for item in history]
    return _checkpoint_payload_without_digest({
        "campaign_id": spec.campaign_id,
        "campaign_version": spec.campaign_version,
        "last_completed_fingerprint": fingerprints[-1] if fingerprints else None,
        "completed_fingerprints": fingerprints,
        "last_progress_utc": last_progress,
        "progress_max_age_seconds": spec.freshness["progress_max_age_seconds"],
        "last_decision": decision.to_dict(),
        "outcomes": history,
        "routing_context": routing_context,
    })


def validate_checkpoint_root(root: Path) -> Path:
    """Resolve a checkpoint root and require a safe descendant of the OS temp dir."""

    try:
        sandbox_root = Path(root).resolve()
        temporary_root = Path(tempfile.gettempdir()).resolve()
        repository_root = Path(__file__).resolve().parents[3]
        current_root = Path.cwd().resolve()
    except (TypeError, OSError) as error:
        raise CampaignCheckpointError("checkpoint root is invalid") from error

    if sandbox_root == temporary_root:
        raise CampaignCheckpointError("checkpoint root must be below the temporary directory")
    if temporary_root not in sandbox_root.parents:
        raise CampaignCheckpointError("checkpoint root must be below the temporary directory")
    if sandbox_root == repository_root or repository_root in sandbox_root.parents:
        raise CampaignCheckpointError("checkpoint root must not be inside the repository")
    if sandbox_root == current_root:
        raise CampaignCheckpointError("checkpoint root must not equal the current directory")
    if sandbox_root.exists() and not sandbox_root.is_dir():
        raise CampaignCheckpointError("checkpoint root must be a directory")
    return sandbox_root


_UNSPECIFIED_REVISION = object()


def write_checkpoint(
    root: Path, checkpoint: Mapping[str, Any], *,
    expected_digest: str | None | object = _UNSPECIFIED_REVISION,
) -> Path:
    """Persist append-only history with an exclusive writer and revision check.

    Explicit ``None`` requires an absent checkpoint. A digest requires the
    exact loaded revision; omitted revision still protects completed history.
    A held writer lock fails closed without waiting or guessing lock expiry.
    """

    sandbox_root = validate_checkpoint_root(root)
    payload = _checkpoint_payload_without_digest(checkpoint)
    target_path = sandbox_root / "campaign_checkpoint.json"
    if target_path.is_symlink():
        raise CampaignCheckpointError("checkpoint path must not be a symlink")
    try:
        sandbox_root.mkdir(parents=True, exist_ok=True)
        target = target_path.resolve()
    except OSError as error:
        raise CampaignCheckpointError("checkpoint root cannot be prepared") from error
    if target.parent != sandbox_root or target.name != "campaign_checkpoint.json":
        raise CampaignCheckpointError("checkpoint path escapes the sandbox root")

    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    serialized = _canonical_json({**payload, "digest": digest}) + "\n"
    if len(serialized.encode("utf-8")) > MAX_JSON_INPUT_BYTES:
        raise CampaignCheckpointError("serialized checkpoint exceeds 1 MiB")
    temporary_path: Path | None = None
    lock_path = sandbox_root / ".campaign_checkpoint.lock"
    lock_descriptor: int | None = None
    try:
        try:
            lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise CampaignCheckpointError("checkpoint writer is already active or requires recovery") from error
        if target_path.is_symlink():
            raise CampaignCheckpointError("checkpoint path must not be a symlink")
        existing = None
        if target.exists():
            try:
                existing_input = read_bounded_json_file(target, "existing checkpoint")
            except CampaignValidationError as error:
                raise CampaignCheckpointError(str(error)) from error
            try:
                existing = validate_checkpoint_payload(existing_input)
            except CampaignCheckpointError as error:
                raise CampaignCheckpointError("existing checkpoint is unreadable or malformed") from error
        current_digest = (
            hashlib.sha256(_canonical_json(existing).encode("utf-8")).hexdigest()
            if existing is not None else None
        )
        if expected_digest is not _UNSPECIFIED_REVISION and expected_digest != current_digest:
            raise CampaignCheckpointError("checkpoint revision changed since it was read")
        if existing is not None:
            if (existing["campaign_id"], existing["campaign_version"], existing["routing_context"]["campaign_spec"]) != (
                payload["campaign_id"], payload["campaign_version"], payload["routing_context"]["campaign_spec"]
            ):
                raise CampaignCheckpointError("checkpoint campaign context cannot be replaced")
            prior_history = existing["outcomes"]
            if payload["outcomes"][:len(prior_history)] != prior_history:
                raise CampaignCheckpointError("checkpoint history must preserve all completed outcomes")
            if not prior_history and not payload["outcomes"] and payload["last_progress_utc"] != existing["last_progress_utc"]:
                raise CampaignCheckpointError("checkpoint unchanged history cannot refresh progress")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".campaign_checkpoint.", suffix=".tmp", dir=sandbox_root
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
    except OSError as error:
        raise CampaignCheckpointError("checkpoint atomic write failed") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
        if lock_descriptor is not None:
            os.close(lock_descriptor)
            lock_path.unlink()
    return target


def load_checkpoint(path: Path, spec: CampaignSpec) -> dict[str, Any]:
    """Load a matching, digest-verified checkpoint or fail closed."""

    if not isinstance(spec, CampaignSpec):
        raise CampaignCheckpointError("checkpoint requires a CampaignSpec")
    try:
        raw_payload = read_bounded_json_file(path, "checkpoint")
    except CampaignValidationError as error:
        raise CampaignCheckpointError(str(error)) from error
    if not isinstance(raw_payload, dict):
        raise CampaignCheckpointError("checkpoint must be a JSON object")
    payload = validate_checkpoint_payload(raw_payload)
    if (
        payload["campaign_id"] != spec.campaign_id
        or payload["campaign_version"] != spec.campaign_version
    ):
        raise CampaignCheckpointError("checkpoint campaign identity/version does not match spec")
    try:
        outcomes = [ExperimentOutcome.from_dict(item) for item in payload["outcomes"]]
    except CampaignValidationError as error:
        raise CampaignCheckpointError("checkpoint outcomes are invalid") from error
    # Bind the returned normalized state to its canonical digest. The original
    # on-disk digest was already verified before any UTC normalization.
    canonical_digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {**payload, "outcomes": outcomes, "digest": canonical_digest}
