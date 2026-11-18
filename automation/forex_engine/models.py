"""Data models for the AI_OS Forex Engine v1 paper-only scaffold."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngineMode:
    PAPER_ONLY = "PAPER_ONLY"


class Direction:
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus:
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    BLOCKED = "BLOCKED"


class TradeOutcome:
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    OPEN = "OPEN"


@dataclass
class Candle:
    symbol: str
    timeframe: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


@dataclass
class RegimeAssessment:
    symbol: str
    timeframe: str
    trend_state: str
    volatility_state: str
    candle_count: int
    lookback: int
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalCandidate:
    symbol: str
    timeframe: str
    direction: Optional[str]
    entry_price: float
    stop_loss: float
    take_profit: float
    strategy_name: str
    regime_trend: str
    regime_volatility: str
    confidence_hint: int
    reasons: List[str] = field(default_factory=list)
    blocked_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalRuleResult:
    symbol: str
    timeframe: str
    mode: str
    regime: RegimeAssessment
    candidates: List[SignalCandidate] = field(default_factory=list)
    accepted_count: int = 0
    blocked_count: int = 0
    summary_note: str = ""


class SetupGrade:
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class ConfidenceBand:
    HIGH_QUALITY = "HIGH_QUALITY"
    TRADE_CANDIDATE = "TRADE_CANDIDATE"
    WATCHLIST = "WATCHLIST"
    BLOCKED = "BLOCKED"


@dataclass
class ConfidenceComponent:
    name: str
    score_delta: int
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SetupQualityAssessment:
    mode: str
    symbol: str
    timeframe: str
    direction: str
    score: int
    grade: str
    band: str
    allowed: bool
    reduced_risk: bool
    blocked_reason: Optional[str]
    components: List[ConfidenceComponent] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class StrategyStatus:
    RESEARCH_CANDIDATE = "RESEARCH_CANDIDATE"
    WATCHLIST = "WATCHLIST"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class OptimizationCandidate:
    name: str
    reason: str
    priority: str
    suggested_direction: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyScoreComponent:
    name: str
    score_delta: int
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyScorecard:
    mode: str
    strategy_name: str
    symbol: str
    timeframe: str
    score: float
    status: str
    rank: int
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    profit_factor: Optional[float]
    net_pnl_usd: float
    max_drawdown_usd: float
    max_drawdown_pct: float
    starting_balance_usd: float
    ending_balance_usd: float
    components: List[StrategyScoreComponent] = field(default_factory=list)
    optimization_candidates: List[OptimizationCandidate] = field(default_factory=list)
    summary_note: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyComparisonResult:
    mode: str
    compared_at: str
    strategy_count: int
    scorecards: List[StrategyScorecard] = field(default_factory=list)
    top_strategy: Optional[str] = None
    rejected_count: int = 0
    watchlist_count: int = 0
    research_candidate_count: int = 0
    insufficient_data_count: int = 0
    summary_note: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class WalkForwardStatus:
    PASSED = "PASSED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class WalkForwardSplit:
    mode: str
    symbol: str
    timeframe: str
    train_ratio: float
    test_ratio: float
    train_count: int
    test_count: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WalkForwardWindowResult:
    mode: str
    symbol: str
    timeframe: str
    window_name: str
    candles_processed: int
    trades: int
    net_pnl_usd: float
    win_rate_pct: float
    profit_factor: Optional[float]
    max_drawdown_usd: float
    max_drawdown_pct: float
    status: str
    summary_note: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WalkForwardResult:
    mode: str
    symbol: str
    timeframe: str
    strategy_name: str
    split: WalkForwardSplit
    train_result: WalkForwardWindowResult
    test_result: WalkForwardWindowResult
    degradation_pct: Optional[float]
    status: str
    recommendations: List[str] = field(default_factory=list)
    summary_note: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class PaperOperatorStatus:
    READY_FOR_PAPER_RESEARCH = "READY_FOR_PAPER_RESEARCH"
    PAUSED_FOR_INSUFFICIENT_DATA = "PAUSED_FOR_INSUFFICIENT_DATA"
    PAUSED_FOR_RISK_LIMIT = "PAUSED_FOR_RISK_LIMIT"
    PAUSED_FOR_LOSS_STREAK = "PAUSED_FOR_LOSS_STREAK"
    WATCHLIST = "WATCHLIST"
    BLOCKED = "BLOCKED"


class RiskPosture:
    CONSERVATIVE = "CONSERVATIVE"
    NORMAL = "NORMAL"
    AGGRESSIVE_RESEARCH_ONLY = "AGGRESSIVE_RESEARCH_ONLY"
    PAUSED = "PAUSED"


class AlertState:
    PAPER_ONLY_BOUNDARY_OK = "PAPER_ONLY_BOUNDARY_OK"
    INSUFFICIENT_DATA_ALERT = "INSUFFICIENT_DATA_ALERT"
    PROFIT_MILESTONE_ALERT = "PROFIT_MILESTONE_ALERT"
    LOSS_STREAK_ALERT = "LOSS_STREAK_ALERT"
    DAILY_DRAWDOWN_ALERT = "DAILY_DRAWDOWN_ALERT"
    WEEKLY_DRAWDOWN_ALERT = "WEEKLY_DRAWDOWN_ALERT"
    VALIDATION_HEALTH_ALERT = "VALIDATION_HEALTH_ALERT"
    NO_ALERTS = "NO_ALERTS"


class PauseReason:
    NONE = "NONE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DAILY_DRAWDOWN_LIMIT = "DAILY_DRAWDOWN_LIMIT"
    WEEKLY_DRAWDOWN_LIMIT = "WEEKLY_DRAWDOWN_LIMIT"
    LOSS_STREAK = "LOSS_STREAK"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


@dataclass
class OperatorAlert:
    name: str
    active: bool
    severity: str
    reason: str
    recommended_action: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DailyOperatorReport:
    mode: str
    report_date: str
    starting_balance_usd: float
    current_balance_usd: float
    net_pnl_usd: float
    risk_posture: str
    operator_status: str
    pause_reason: str
    alerts: List[OperatorAlert] = field(default_factory=list)
    summary: str = ""
    next_safe_action: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SupervisorSummary:
    mode: str
    status: str
    risk_posture: str
    active_alert_count: int
    paper_only_boundary_ok: bool
    research_ready: bool
    promotion_ready: bool
    summary: str
    next_safe_action: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class BrokerSandboxMode:
    SANDBOX_MODEL_ONLY = "SANDBOX_MODEL_ONLY"
    PAPER_ONLY_COMPATIBLE = "PAPER_ONLY_COMPATIBLE"
    LIVE_BLOCKED = "LIVE_BLOCKED"


class SandboxOrderSide:
    BUY = "BUY"
    SELL = "SELL"


class SandboxOrderType:
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class SandboxOrderStatus:
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    LIVE_BLOCKED = "LIVE_BLOCKED"


class SandboxRejectReason:
    NONE = "NONE"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    INVALID_SIDE = "INVALID_SIDE"
    INVALID_ORDER_TYPE = "INVALID_ORDER_TYPE"
    INVALID_UNITS = "INVALID_UNITS"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_MODE = "INVALID_MODE"
    LIVE_TRADING_BLOCKED = "LIVE_TRADING_BLOCKED"
    CREDENTIALS_NOT_ALLOWED = "CREDENTIALS_NOT_ALLOWED"
    NETWORK_NOT_ALLOWED = "NETWORK_NOT_ALLOWED"
    RISK_BLOCKED = "RISK_BLOCKED"


class BrokerReadinessStatus:
    MODEL_READY = "MODEL_READY"
    NOT_LIVE_READY = "NOT_LIVE_READY"
    BLOCKED_FOR_LIVE = "BLOCKED_FOR_LIVE"
    REQUIRES_SEPARATE_AUTHORIZATION = "REQUIRES_SEPARATE_AUTHORIZATION"


@dataclass
class SandboxOrderRequest:
    mode: str
    symbol: str
    side: str
    order_type: str
    units: float
    requested_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    client_order_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SandboxOrderResponse:
    mode: str
    client_order_id: str
    sandbox_order_id: str
    symbol: str
    side: str
    order_type: str
    requested_units: float
    filled_units: float
    requested_price: Optional[float]
    fill_price: Optional[float]
    status: str
    reject_reason: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SandboxAccountState:
    mode: str
    starting_balance_usd: float
    current_balance_usd: float
    open_order_count: int = 0
    filled_order_count: int = 0
    rejected_order_count: int = 0
    live_trading_enabled: bool = False
    credentials_loaded: bool = False
    network_enabled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerReadinessCheck:
    mode: str
    status: str
    checks: List[str] = field(default_factory=list)
    blocked_reasons: List[str] = field(default_factory=list)
    next_safe_action: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class RiskAction:
    CONTINUE = "CONTINUE"
    REDUCE_RISK = "REDUCE_RISK"
    BLOCK_ORDER = "BLOCK_ORDER"
    PAUSE_TRADING = "PAUSE_TRADING"
    KILL_SWITCH = "KILL_SWITCH"


class KillSwitchState:
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    RESET_REQUIRED = "RESET_REQUIRED"


class RiskBreachType:
    NONE = "NONE"
    DAILY_DRAWDOWN = "DAILY_DRAWDOWN"
    WEEKLY_DRAWDOWN = "WEEKLY_DRAWDOWN"
    LOSS_STREAK = "LOSS_STREAK"
    MAX_OPEN_TRADES = "MAX_OPEN_TRADES"
    ORDER_RISK_TOO_HIGH = "ORDER_RISK_TOO_HIGH"
    EXPOSURE_TOO_HIGH = "EXPOSURE_TOO_HIGH"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    NON_PAPER_MODE = "NON_PAPER_MODE"


@dataclass
class RiskManagementScenario:
    name: str
    mode: str
    starting_balance_usd: float
    current_balance_usd: float
    current_daily_pnl_usd: float
    weekly_drawdown_pct: float
    consecutive_losses: int
    open_trade_count: int
    proposed_order_risk_usd: float
    validation_passed: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskDecisionReport:
    mode: str
    scenario_name: str
    risk_action: str
    kill_switch_state: str
    breaches: List[str] = field(default_factory=list)
    allowed: bool = False
    risk_posture: str = ""
    recommended_position_risk_pct: float = 0.0
    recommended_action: str = ""
    reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KillSwitchReport:
    mode: str
    state: str
    triggered_by: List[str] = field(default_factory=list)
    reset_required: bool = False
    reason: str = ""
    next_safe_action: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class OptimizationStatus:
    BEST_CANDIDATE = "BEST_CANDIDATE"
    WATCHLIST = "WATCHLIST"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    OVERFIT_RISK = "OVERFIT_RISK"


class OverfittingRisk:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


@dataclass
class ParameterSet:
    name: str
    strategy_name: str
    confidence_threshold: int
    reward_risk_min: float
    volatility_filter: bool
    regime_filter: bool
    max_open_trades: int
    risk_per_trade_pct: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParameterOptimizationScore:
    mode: str
    parameter_set_name: str
    score: float
    status: str
    overfitting_risk: str
    sample_size: int
    net_pnl_usd: float
    win_rate_pct: float
    profit_factor: Optional[float]
    max_drawdown_pct: float
    components: List[StrategyScoreComponent] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParameterOptimizationResult:
    mode: str
    tested_count: int
    scores: List[ParameterOptimizationScore] = field(default_factory=list)
    best_parameter_set: Optional[str] = None
    overfitting_risk: str = OverfittingRisk.UNKNOWN
    status: str = OptimizationStatus.INSUFFICIENT_DATA
    summary_note: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class PortfolioMode:
    PORTFOLIO_MODEL_ONLY = "PORTFOLIO_MODEL_ONLY"
    PAPER_ONLY_COMPATIBLE = "PAPER_ONLY_COMPATIBLE"
    LIVE_BLOCKED = "LIVE_BLOCKED"


class AllocationMethod:
    EQUAL_WEIGHT = "EQUAL_WEIGHT"
    RISK_CAPPED = "RISK_CAPPED"
    CONFIDENCE_WEIGHTED_PLACEHOLDER = "CONFIDENCE_WEIGHTED_PLACEHOLDER"


class ConcentrationStatus:
    OK = "OK"
    CAUTION = "CAUTION"
    TOO_CONCENTRATED = "TOO_CONCENTRATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PortfolioOptimizationStatus:
    MODEL_READY = "MODEL_READY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    WATCHLIST = "WATCHLIST"
    REJECTED = "REJECTED"


@dataclass
class PortfolioAllocation:
    symbol: str
    allocation_usd: float
    allocation_pct: float
    risk_cap_usd: float
    confidence_score: Optional[float]
    status: str
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioRiskSummary:
    mode: str
    symbol_count: int
    max_symbol_allocation_pct: float
    max_symbol_allocation_usd: float
    xauusd_allocation_pct: float
    total_allocated_pct: float
    concentration_status: str
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioOptimizationResult:
    mode: str
    allocation_method: str
    starting_capital_usd: float
    allocated_capital_usd: float
    unallocated_capital_usd: float
    allocations: List[PortfolioAllocation] = field(default_factory=list)
    concentration_status: str = ConcentrationStatus.INSUFFICIENT_DATA
    optimization_status: str = PortfolioOptimizationStatus.INSUFFICIENT_DATA
    risk_posture: str = RiskPosture.CONSERVATIVE
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    summary_note: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class HistoricalDataReadinessStatus:
    READY_FOR_LOCAL_IMPORT = "READY_FOR_LOCAL_IMPORT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_DATASET = "INVALID_DATASET"
    NEEDS_CLEANING = "NEEDS_CLEANING"


class DatasetIssueSeverity:
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class DatasetIssue:
    code: str
    severity: str
    message: str
    row_number: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetQualityScore:
    mode: str
    score: int
    status: str
    issues: List[DatasetIssue] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetManifest:
    mode: str
    dataset_name: str
    source_type: str
    path: str
    row_count: int
    symbols: List[str] = field(default_factory=list)
    timeframes: List[str] = field(default_factory=list)
    first_timestamp: Optional[str] = None
    last_timestamp: Optional[str] = None
    schema_fields: List[str] = field(default_factory=list)
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HistoricalDatasetSummary:
    mode: str
    manifest: DatasetManifest
    quality_score: DatasetQualityScore
    readiness_status: str
    valid_row_count: int
    invalid_row_count: int
    duplicate_count: int
    missing_field_count: int
    symbol_count: int
    timeframe_count: int
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class LargeDatasetBacktestStatus:
    READY_FOR_LOCAL_BACKTEST = "READY_FOR_LOCAL_BACKTEST"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_DATASET = "INVALID_DATASET"
    BACKTEST_COMPLETED = "BACKTEST_COMPLETED"
    BACKTEST_SKIPPED = "BACKTEST_SKIPPED"
    NEEDS_CLEANING = "NEEDS_CLEANING"


@dataclass(frozen=True)
class CandleGroupKey:
    symbol: str
    timeframe: str


@dataclass
class CandleGroupSummary:
    mode: str
    symbol: str
    timeframe: str
    candle_count: int
    first_timestamp: str
    last_timestamp: str
    status: str
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LargeDatasetBacktestGroupResult:
    mode: str
    symbol: str
    timeframe: str
    candle_count: int
    backtest_status: str
    trades_opened: int
    trades_closed: int
    net_pnl_usd: float
    win_rate_pct: float
    profit_factor: Optional[float]
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LargeDatasetBacktestReport:
    mode: str
    dataset_name: str
    readiness_status: str
    adapter_status: str
    group_count: int
    total_candles: int
    groups: List[CandleGroupSummary] = field(default_factory=list)
    group_results: List[LargeDatasetBacktestGroupResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    summary_note: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestConfig:
    symbol: str
    timeframe: str
    starting_balance_usd: float
    max_candles: Optional[int] = None
    strategy_name: str = "sprint_3_demo_strategy"
    mode: str = EngineMode.PAPER_ONLY
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestTradeResult:
    trade_id: str
    symbol: str
    timeframe: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    opened_at: str
    closed_at: str
    outcome: str
    pnl_usd: float
    confidence_score: int
    close_reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestResult:
    mode: str
    symbol: str
    timeframe: str
    strategy_name: str
    candles_processed: int
    signals_generated: int
    signals_accepted: int
    signals_blocked: int
    trades_opened: int
    trades_closed: int
    starting_balance_usd: float
    ending_balance_usd: float
    net_pnl_usd: float
    win_rate_pct: float
    profit_factor: Optional[float]
    max_drawdown_usd: float
    max_drawdown_pct: float
    results: List[BacktestTradeResult] = field(default_factory=list)
    summary_note: str = ""


@dataclass
class ForexSignal:
    symbol: str
    timeframe: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    timestamp: str
    strategy_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfidenceAssessment:
    score: int
    reasons: List[str] = field(default_factory=list)
    allowed: bool = False
    blocked_reason: Optional[str] = None


@dataclass
class RiskDecision:
    allowed: bool
    risk_amount_usd: float
    max_daily_loss_usd: float
    open_trade_count: int
    max_open_trades: int
    consecutive_losses: int
    blocked_reason: Optional[str] = None


@dataclass
class PaperTrade:
    trade_id: str
    mode: str
    symbol: str
    timeframe: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_units: float
    risk_amount_usd: float
    confidence_score: int
    status: str = TradeStatus.OPEN
    opened_at: str = field(default_factory=utc_now_iso)
    closed_at: Optional[str] = None
    exit_price: Optional[float] = None
    outcome: str = TradeOutcome.OPEN
    pnl_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JournalEvent:
    event_type: str
    timestamp: str
    mode: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceSummary:
    starting_balance_usd: float
    current_balance_usd: float
    total_trades: int
    open_trades: int
    closed_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate_pct: float
    gross_profit_usd: float
    gross_loss_usd: float
    net_pnl_usd: float
    profit_factor: Optional[float]
    max_drawdown_usd: float
    max_drawdown_pct: float
    consecutive_losses: int
    consistency_note: str
