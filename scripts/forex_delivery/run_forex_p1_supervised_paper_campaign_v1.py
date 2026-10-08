#!/usr/bin/env python3
"""Operator-started entry point for the bounded P1 paper campaign."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_p1_supervised_paper_campaign_v1 import (
    CampaignPaths,
    run_campaign,
)
from automation.forex_engine.forex_p1_practice_paper_campaign_runtime_v1 import (
    M5RuntimePaths,
    SIGNAL_SOURCES,
    SPRINT_4_SIGNAL_SOURCE,
    SUPERTREND_SIGNAL_SOURCE,
    completed_paper_records,
    resolve_m5_runtime_paths,
    resolve_signal_source,
)
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient
from automation.forex_engine.strategies import SUPERTREND_PULLBACK_V1
from scripts.forex_delivery.run_forex_p1_supertrend_paper_campaign_v1 import (
    campaign_paths as supertrend_campaign_paths,
)

REPORTS = ROOT / "Reports" / "forex_delivery"
SUPERVISED_PRACTICE_SESSION_PATH = (
    ROOT / ".aios/runtime/forex_p1_supervised_paper_sessions/active.json"
)
SUPER_TREND_PRACTICE_SESSION_PATH = (
    ROOT / ".aios/runtime/forex_p1_supertrend_paper_sessions/active.json"
)
SUPER_TREND_PRACTICE_SESSION_LOCK_PATH = (
    Path(SUPER_TREND_PRACTICE_SESSION_PATH).with_name(
        f"{SUPER_TREND_PRACTICE_SESSION_PATH.name}.runtime.lock"
    )
)


def _runtime_environment_value(name: str) -> str:
    return os.environ.get(name, "")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run up to 30 sequential PAPER/DEMO evidence captures."
    )
    result.add_argument("--owner-local-runtime", action="store_true")
    result.add_argument("--cycles", type=int, default=30)
    result.add_argument("--reviewer", default="Human Owner Anthony")
    result.add_argument("--maximum-session-loss", type=float)
    result.add_argument(
        "--signal-source", choices=SIGNAL_SOURCES, default=SPRINT_4_SIGNAL_SOURCE
    )
    result.add_argument(
        "--supertrend-paper-demo-only",
        action="store_true",
        help="Required with --signal-source supertrend; grants no order authority.",
    )
    result.add_argument(
        "--output-root",
        type=Path,
        default=REPORTS,
        help=(
            "Evidence output directory; manual runs retain Reports/forex_delivery "
            "by default."
        ),
    )
    result.add_argument(
        "--external-m5-runtime-root",
        type=Path,
        help="Use the single allowlisted external M5 PAPER runtime root.",
    )
    result.add_argument("--kill-switch-file", type=Path, default=ROOT / ".aios/runtime/forex/kill_switch.active")
    result.add_argument("--risk-halt-file", type=Path, default=ROOT / ".aios/runtime/forex/risk_halt.active")
    result.add_argument("--cancel-file", type=Path, default=ROOT / ".aios/runtime/forex/cancel_campaign.active")
    return result


def campaign_paths_for_signal_source(
    signal_source: str, output_root: Path = REPORTS
) -> CampaignPaths:
    if signal_source == SUPERTREND_SIGNAL_SOURCE:
        return supertrend_campaign_paths(output_root)
    return CampaignPaths(
        candidate=output_root / ".p1_campaign_candidate.tmp",
        ledger=output_root / "AIOS_FOREX_P1_30_TRADE_CAMPAIGN_V1_LEDGER.json",
        replay_state=output_root / "AIOS_FOREX_P1_30_TRADE_CAMPAIGN_V1_REPLAY_STATE.json",
        replay_report=output_root / "AIOS_FOREX_P1_30_TRADE_CAMPAIGN_V1_REPLAY_REPORT.md",
        event_log=output_root / "AIOS_FOREX_P1_30_TRADE_CAMPAIGN_V1_EVENTS.jsonl",
        campaign_state=output_root / "AIOS_FOREX_P1_30_TRADE_CAMPAIGN_V1_STATE.json",
        campaign_report=output_root / "AIOS_FOREX_P1_30_TRADE_CAMPAIGN_V1_REPORT.md",
    )


def runtime_paths_for_signal_source(
    signal_source: str,
    *,
    checkout_root: Path = ROOT,
    external_m5_runtime_root: Path | None = None,
) -> tuple[Path, Path | None, M5RuntimePaths | None]:
    if signal_source == SUPERTREND_SIGNAL_SOURCE:
        paths = resolve_m5_runtime_paths(
            checkout_root=checkout_root,
            external_runtime_root=external_m5_runtime_root,
        )
        return paths.active_session, paths.lock, paths
    if external_m5_runtime_root is not None:
        raise ValueError("external_m5_runtime_root_requires_supertrend")
    return checkout_root / SUPERVISED_PRACTICE_SESSION_PATH.relative_to(ROOT), None, None


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        selected_signal_source = resolve_signal_source(
            args.signal_source,
            supertrend_paper_demo_only=args.supertrend_paper_demo_only,
        )
        runtime_path, runtime_lock_path, runtime_paths = runtime_paths_for_signal_source(
            selected_signal_source,
            external_m5_runtime_root=args.external_m5_runtime_root,
        )
        if args.external_m5_runtime_root is not None and args.output_root != REPORTS:
            raise ValueError("external_m5_runtime_root_requires_default_output_root")
    except ValueError as exc:
        print(str(exc))
        return 2
    if runtime_paths is not None and runtime_paths.mode == "APPROVED_EXTERNAL":
        print(f"RUNTIME_ROOT_MODE: {runtime_paths.mode}")
    if not args.owner_local_runtime:
        print("RUNTIME_CREDENTIAL_OR_PRACTICE_DATA_REQUIRED")
        return 2
    token = _runtime_environment_value("OANDA_API_TOKEN") or _runtime_environment_value(
        "OANDA_DEMO_ACCESS_TOKEN"
    )
    account = _runtime_environment_value("OANDA_ACCOUNT_ID") or _runtime_environment_value(
        "OANDA_DEMO_ACCOUNT_ID"
    )
    if not token or not account:
        print("RUNTIME_CREDENTIAL_OR_PRACTICE_DATA_REQUIRED")
        return 2
    client = OandaReadOnlyClient(
        api_token=token, account_id=account, environment="practice"
    )
    paths = campaign_paths_for_signal_source(
        selected_signal_source,
        runtime_paths.root if runtime_paths and runtime_paths.mode == "APPROVED_EXTERNAL" else args.output_root,
    )
    candidates = completed_paper_records(
        client,
        cycles=args.cycles,
        reviewer_identity=args.reviewer,
        runtime_path=runtime_path,
        runtime_lock_path=runtime_lock_path,
        sleep=time.sleep,
        owner_cancelled=args.cancel_file.exists,
        kill_switch_active=args.kill_switch_file.exists,
        risk_halt_active=args.risk_halt_file.exists,
        signal_source=selected_signal_source,
        supertrend_paper_demo_only=args.supertrend_paper_demo_only,
    )
    state = run_campaign(
        candidates, paths, repository_root=ROOT, output=sys.stdout,
        kill_switch_active=args.kill_switch_file.exists(),
        risk_halt_active=args.risk_halt_file.exists(),
        maximum_session_loss=args.maximum_session_loss,
        active_session_path=(
            runtime_path if selected_signal_source == SUPERTREND_SIGNAL_SOURCE else None
        ),
        qualifying_strategy_name=(
            SUPERTREND_PULLBACK_V1
            if selected_signal_source == SUPERTREND_SIGNAL_SOURCE
            else None
        ),
    )
    print(f"CAMPAIGN_STOP_REASON: {state['stop_reason']}")
    return 0 if state["stop_reason"] in {
        "TARGET_REACHED", "OWNER_SESSION_CYCLE_LIMIT"
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
