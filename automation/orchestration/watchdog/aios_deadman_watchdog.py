#!/usr/bin/env python3
"""AI_OS Tier 0 DEAD-MAN WATCHDOG (DISABLED-BY-DEFAULT, DRY_RUN-only).

Purpose
-------
This closes the scariest audit finding: if the unattended loop dies, nothing
fires and the operator is never woken. This watchdog DETECTS staleness of the
runtime heartbeat and, fail-closed, classifies a missing/stale heartbeat as
BLOCKED (the loop is presumed dead).

Safety posture (Tier 0 gate)
----------------------------
This module is intentionally quiet-by-default. It does NOT send any live
notification, does NOT register any scheduler, and does NOT start any loop.
In DRY_RUN (the default) it only writes/prints an SOS alert record describing
what it WOULD escalate. Even with --apply, live delivery is NOT armed: it will
only write the alert file and print LIVE_DELIVERY_NOT_ARMED.

Severity model
--------------
BLOCKED is the only SOS-worthy state (matches services/python_supervisor/
notifier.py). A healthy fresh heartbeat is OK and never escalates.

Cross-platform
--------------
Pure Python 3 standard library only. No PowerShell, no Windows-only paths.
Exit code: 0 if healthy, 2 if BLOCKED (so an external scheduler could later
act on it).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

if __package__ in {None, ""}:  # Preserve the existing direct-script entry point.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from automation.orchestration.research_campaign.aios_research_campaign import (
    CampaignCheckpointError,
    CampaignValidationError,
    read_bounded_json_file,
    validate_checkpoint_payload,
)

# Capabilities this Tier 0 module is intentionally NOT permitted to perform.
# Consistent with other AIOS modules that gate live actions behind explicit
# arming. None of these are wired in this version.
BLOCKED_CAPABILITIES = [
    "live_send",              # no notification is delivered anywhere
    "scheduler_registration",  # no cron/systemd/Task Scheduler entry is created
    "loop_start",             # no background loop is started
]

# BLOCKED is the only SOS-worthy / wake-worthy state (quiet-by-default).
SOS_WAKE_STATUSES = {"BLOCKED"}

# Default staleness threshold: 10 minutes.
DEFAULT_THRESHOLD_SECONDS = 600
DEFAULT_CAMPAIGN_PROGRESS_THRESHOLD_SECONDS = 600

# Heartbeat path is relative to repo root by default.
DEFAULT_HEARTBEAT_REL = "telemetry/runtime/runtime_heartbeat.json"
DEFAULT_MARKER_REL = "control/cycle/last_marker.json"
ALERT_OUTPUT_REL = "telemetry/watchdog/DEADMAN_ALERT_LATEST.json"

# Timestamp field names we will try, in order, when reading a heartbeat/marker.
TIMESTAMP_FIELDS = (
    "heartbeatAt",
    "last_beat",
    "timestamp",
    "generated_at",
    "updated_at",
    "markedAt",
    "markAt",
    "ts",
)


def repo_root() -> Path:
    """Repo root: this file lives at automation/orchestration/watchdog/."""
    return Path(__file__).resolve().parents[3]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(raw: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime.

    Returns None on any failure (fail-closed; caller treats None as unknown).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Normalize a trailing 'Z' to an explicit UTC offset for fromisoformat.
    candidate = text
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(candidate)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        # Assume UTC for naive timestamps (conservative).
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_campaign_utc_timestamp(raw: Any) -> Optional[datetime]:
    """Parse a checkpoint timestamp only when it explicitly identifies UTC."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(timezone.utc)


def read_json(path: Path) -> Optional[dict[str, Any]]:
    """Read JSON, tolerating BOM. Returns None on any IO/parse failure."""
    try:
        data = read_bounded_json_file(path, "watchdog JSON")
    except CampaignValidationError:
        return None
    except Exception:  # pragma: no cover - defensive: never crash the watchdog
        return None
    if not isinstance(data, dict):
        return None
    return data


def extract_timestamp(data: dict[str, Any]) -> tuple[Optional[datetime], Optional[str]]:
    """Return (parsed_dt, raw_value_used) from the first usable timestamp field."""
    for field in TIMESTAMP_FIELDS:
        if field in data:
            parsed = parse_timestamp(data[field])
            if parsed is not None:
                return parsed, str(data[field])
    return None, None


def _campaign_health_result(
    status: str,
    reason: str,
    progress_threshold_seconds: int,
    last_progress: Optional[str] = None,
    staleness_seconds: Optional[float] = None,
) -> dict[str, Any]:
    sos_wake_required = status in SOS_WAKE_STATUSES
    return {
        "status": status,
        "reason": reason,
        "last_progress_utc": last_progress,
        "staleness_seconds": (
            round(staleness_seconds, 3) if staleness_seconds is not None else None
        ),
        "progress_threshold_seconds": progress_threshold_seconds,
        "sos_wake_required": sos_wake_required,
        "wake_class": "SOS" if sos_wake_required else "NO_WAKE",
        "live_delivery_armed": False,
    }


def evaluate_campaign_health(
    campaign_state: Mapping[str, Any],
    now: datetime,
    progress_threshold_seconds: int,
) -> dict[str, Any]:
    """Evaluate an optional campaign checkpoint without starting or repairing it.

    This function is intentionally observational.  A malformed or stale active
    checkpoint is BLOCKED. Valid terminal research decisions are informational;
    a future progress timestamp is always suspect, including at termination.
    """

    if (
        isinstance(progress_threshold_seconds, bool)
        or not isinstance(progress_threshold_seconds, int)
        or progress_threshold_seconds <= 0
    ):
        return _campaign_health_result(
            "BLOCKED", "campaign_progress_threshold_invalid", 0
        )
    if not isinstance(campaign_state, Mapping):
        return _campaign_health_result(
            "BLOCKED", "campaign_state_unreadable_or_malformed", progress_threshold_seconds
        )
    try:
        campaign_state = validate_checkpoint_payload(campaign_state)
    except CampaignCheckpointError as error:
        detail = str(error)
        reason = "campaign_checkpoint_malformed"
        if "digest" in detail:
            reason = "campaign_checkpoint_digest_invalid"
        elif "last_progress_utc" in detail:
            reason = "campaign_progress_missing_or_unparseable"
        elif "completed_fingerprints contains duplicates" in detail:
            reason = "campaign_completed_fingerprints_duplicate"
        elif "outcomes" in detail:
            reason = "campaign_outcomes_malformed"
        elif "last_decision" in detail:
            reason = "campaign_decision_missing_or_malformed"
        return _campaign_health_result(
            "BLOCKED", reason, progress_threshold_seconds
        )

    progress_threshold_seconds = min(
        progress_threshold_seconds, campaign_state["progress_max_age_seconds"]
    )
    raw_progress = campaign_state.get("last_progress_utc")
    parsed_progress = parse_campaign_utc_timestamp(raw_progress)
    if parsed_progress is None:
        return _campaign_health_result(
            "BLOCKED",
            "campaign_progress_missing_or_unparseable",
            progress_threshold_seconds,
        )
    staleness_seconds = (now - parsed_progress).total_seconds()
    if staleness_seconds < 0:
        return _campaign_health_result(
            "BLOCKED",
            "campaign_progress_future_timestamp",
            progress_threshold_seconds,
            str(raw_progress),
            staleness_seconds,
        )
    decision = campaign_state["last_decision"]
    decision_status = decision["status"]
    terminal_reasons = {
        "NO_EDGE_IN_SCOPE": "campaign_catalog_exhausted",
        "BUDGET_EXHAUSTED": "campaign_approved_scope_exhausted",
        "RESEARCH_COMPLETE": "campaign_research_results_require_review",
    }
    if decision_status in terminal_reasons:
        return _campaign_health_result(
            decision_status, terminal_reasons[decision_status], progress_threshold_seconds
        )
    if decision_status == "BLOCKED":
        return _campaign_health_result(
            "BLOCKED", "campaign_decision_blocked", progress_threshold_seconds
        )
    if decision_status not in {"ADVANCE", "REJECT"}:
        return _campaign_health_result(
            "BLOCKED", "campaign_decision_status_unknown", progress_threshold_seconds
        )
    if not campaign_state["completed_fingerprints"]:
        return _campaign_health_result(
            "BLOCKED", "campaign_active_empty_history", progress_threshold_seconds
        )
    if not isinstance(decision.get("next_experiment"), Mapping):
        return _campaign_health_result(
            "BLOCKED", "campaign_active_empty_queue", progress_threshold_seconds
        )

    if staleness_seconds > progress_threshold_seconds:
        return _campaign_health_result(
            "BLOCKED",
            "campaign_progress_stale",
            progress_threshold_seconds,
            str(raw_progress),
            staleness_seconds,
        )
    return _campaign_health_result(
        "OK",
        "campaign_progress_fresh",
        progress_threshold_seconds,
        str(raw_progress),
        staleness_seconds,
    )


def evaluate(
    heartbeat_path: Path,
    threshold_seconds: int,
    now: datetime,
    campaign_state_path: Optional[Path] = None,
    campaign_progress_threshold_seconds: Optional[int] = None,
) -> dict[str, Any]:
    """Evaluate heartbeat staleness. Fail-closed: any read/parse failure -> BLOCKED."""
    reason: str
    last_heartbeat: Optional[str] = None
    staleness_seconds: Optional[float] = None

    if not heartbeat_path.exists():
        status = "BLOCKED"
        reason = "heartbeat_file_missing"
    else:
        data = read_json(heartbeat_path)
        if data is None:
            status = "BLOCKED"
            reason = "heartbeat_unreadable_or_malformed"
        else:
            parsed, raw = extract_timestamp(data)
            if parsed is None:
                status = "BLOCKED"
                reason = "heartbeat_timestamp_missing_or_unparseable"
            else:
                last_heartbeat = raw
                staleness_seconds = (now - parsed).total_seconds()
                if staleness_seconds > threshold_seconds:
                    status = "BLOCKED"
                    reason = "heartbeat_stale"
                elif staleness_seconds < 0:
                    # Future timestamp: treat as suspect but not dead -> still OK,
                    # but flag the reason so the operator can investigate.
                    status = "OK"
                    reason = "heartbeat_fresh_future_timestamp"
                else:
                    status = "OK"
                    reason = "heartbeat_fresh"

    sos_wake_required = status in SOS_WAKE_STATUSES

    recommended_action = (
        "Wake operator: runtime loop presumed DEAD. Inspect the unattended "
        "loop/supervisor, confirm the runtime heartbeat writer is alive, and "
        "restart the loop if needed."
        if status == "BLOCKED"
        else "No action. Runtime heartbeat is fresh within threshold."
    )

    alert = {
        "schema": "AIOS_DEADMAN_ALERT.v1",
        "detected_at": fmt_utc(now),
        "heartbeat_path": str(heartbeat_path),
        "last_heartbeat": last_heartbeat,
        "staleness_seconds": (
            round(staleness_seconds, 3) if staleness_seconds is not None else None
        ),
        "threshold_seconds": threshold_seconds,
        "status": status,
        "severity": status,  # BLOCKED is the SOS-worthy severity
        "reason": reason,
        "sos_wake_required": sos_wake_required,
        "wake_class": "SOS" if sos_wake_required else "NO_WAKE",
        "recommended_action": recommended_action,
        "mode": "DRY_RUN",
        "blocked_capabilities": list(BLOCKED_CAPABILITIES),
        "live_delivery_armed": False,
    }
    if campaign_state_path is not None:
        campaign_threshold = (
            DEFAULT_CAMPAIGN_PROGRESS_THRESHOLD_SECONDS
            if campaign_progress_threshold_seconds is None
            else campaign_progress_threshold_seconds
        )
        if not campaign_state_path.exists():
            campaign_health = _campaign_health_result(
                "BLOCKED", "campaign_state_file_missing", campaign_threshold
            )
        else:
            campaign_state = read_json(campaign_state_path)
            campaign_health = (
                evaluate_campaign_health(campaign_state, now, campaign_threshold)
                if campaign_state is not None
                else _campaign_health_result(
                    "BLOCKED",
                    "campaign_state_unreadable_or_malformed",
                    campaign_threshold,
                )
            )
        alert["campaign_health"] = campaign_health
        if campaign_health["status"] == "BLOCKED":
            alert.update(
                {
                    "status": "BLOCKED",
                    "severity": "BLOCKED",
                    "reason": f"campaign_health:{campaign_health['reason']}",
                    "sos_wake_required": True,
                    "wake_class": "SOS",
                    "recommended_action": (
                        "Wake operator: campaign health is BLOCKED. Inspect the "
                        "checkpoint and research controller; do not restart or "
                        "repair it automatically."
                    ),
                }
            )
    return alert


def write_alert(alert_path: Path, alert: dict[str, Any]) -> bool:
    """Write the alert JSON. Returns True on success, False on failure (never raises)."""
    try:
        alert_path.parent.mkdir(parents=True, exist_ok=True)
        alert_path.write_text(
            json.dumps(alert, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return True
    except OSError:
        return False
    except Exception:  # pragma: no cover - defensive
        return False


def print_summary(alert: dict[str, Any], alert_path: Path, wrote: bool, apply: bool) -> None:
    print("AIOS_DEADMAN_WATCHDOG")
    print(f"MODE={alert['mode']}")
    print(f"STATUS={alert['status']}")
    print(f"SEVERITY={alert['severity']}")
    print(f"REASON={alert['reason']}")
    print(f"HEARTBEAT_PATH={alert['heartbeat_path']}")
    print(f"LAST_HEARTBEAT={alert['last_heartbeat']}")
    print(f"STALENESS_SECONDS={alert['staleness_seconds']}")
    print(f"THRESHOLD_SECONDS={alert['threshold_seconds']}")
    print(f"SOS_WAKE_REQUIRED={str(alert['sos_wake_required']).lower()}")
    print(f"WAKE_CLASS={alert['wake_class']}")
    print(f"RECOMMENDED_ACTION={alert['recommended_action']}")
    print(f"ALERT_FILE={alert_path}")
    print(f"ALERT_FILE_WRITTEN={'yes' if wrote else 'no'}")
    print(f"BLOCKED_CAPABILITIES={','.join(alert['blocked_capabilities'])}")
    campaign_health = alert.get("campaign_health")
    if isinstance(campaign_health, dict):
        print(f"CAMPAIGN_STATUS={campaign_health['status']}")
        print(f"CAMPAIGN_REASON={campaign_health['reason']}")
        print(
            "CAMPAIGN_SOS_WAKE_REQUIRED="
            f"{str(campaign_health['sos_wake_required']).lower()}"
        )
    print("LIVE_DELIVERY_ARMED=false")
    if apply:
        print("LIVE_DELIVERY_NOT_ARMED: wire an SOS channel first")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "AI_OS Tier 0 dead-man watchdog (DRY_RUN by default). Detects a "
            "missing/stale runtime heartbeat and classifies it BLOCKED. Does "
            "NOT send notifications, register schedulers, or start loops."
        )
    )
    parser.add_argument(
        "--threshold-seconds",
        type=int,
        default=DEFAULT_THRESHOLD_SECONDS,
        help=f"Staleness threshold in seconds (default {DEFAULT_THRESHOLD_SECONDS}).",
    )
    parser.add_argument(
        "--heartbeat-path",
        default=None,
        help=(
            "Path to the runtime heartbeat JSON. Default: "
            f"<repo_root>/{DEFAULT_HEARTBEAT_REL}"
        ),
    )
    parser.add_argument(
        "--alert-path",
        default=None,
        help=(
            "Where to write the DRY_RUN alert JSON. Default: "
            f"<repo_root>/{ALERT_OUTPUT_REL}"
        ),
    )
    parser.add_argument(
        "--campaign-state-path",
        default=None,
        help=(
            "Optional campaign checkpoint JSON to inspect. Without this flag, "
            "the watchdog retains heartbeat-only behavior."
        ),
    )
    parser.add_argument(
        "--campaign-progress-threshold-seconds",
        type=int,
        default=DEFAULT_CAMPAIGN_PROGRESS_THRESHOLD_SECONDS,
        help=(
            "Max age for active campaign progress before BLOCKED "
            f"(default {DEFAULT_CAMPAIGN_PROGRESS_THRESHOLD_SECONDS})."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "RESERVED for future live delivery. In this version it still only "
            "writes the alert file and prints LIVE_DELIVERY_NOT_ARMED. It does "
            "NOT send anything."
        ),
    )
    args = parser.parse_args(argv)

    root = repo_root()

    if args.heartbeat_path:
        heartbeat_path = Path(args.heartbeat_path).expanduser()
        if not heartbeat_path.is_absolute():
            heartbeat_path = (root / heartbeat_path).resolve()
    else:
        heartbeat_path = root / DEFAULT_HEARTBEAT_REL

    if args.alert_path:
        alert_path = Path(args.alert_path).expanduser()
        if not alert_path.is_absolute():
            alert_path = (root / alert_path).resolve()
    else:
        alert_path = root / ALERT_OUTPUT_REL

    campaign_state_path: Optional[Path] = None
    if args.campaign_state_path:
        campaign_state_path = Path(args.campaign_state_path).expanduser()
        if not campaign_state_path.is_absolute():
            campaign_state_path = (root / campaign_state_path).resolve()

    threshold = args.threshold_seconds if args.threshold_seconds > 0 else DEFAULT_THRESHOLD_SECONDS
    campaign_threshold = (
        args.campaign_progress_threshold_seconds
        if args.campaign_progress_threshold_seconds > 0
        else DEFAULT_CAMPAIGN_PROGRESS_THRESHOLD_SECONDS
    )

    try:
        alert = evaluate(
            heartbeat_path,
            threshold,
            utc_now(),
            campaign_state_path=campaign_state_path,
            campaign_progress_threshold_seconds=campaign_threshold,
        )
    except Exception as exc:  # pragma: no cover - last-resort fail-closed
        # The watchdog itself must never crash. Any unexpected error is treated
        # as BLOCKED (presume dead).
        alert = {
            "schema": "AIOS_DEADMAN_ALERT.v1",
            "detected_at": fmt_utc(utc_now()),
            "heartbeat_path": str(heartbeat_path),
            "last_heartbeat": None,
            "staleness_seconds": None,
            "threshold_seconds": threshold,
            "status": "BLOCKED",
            "severity": "BLOCKED",
            "reason": f"watchdog_internal_error:{type(exc).__name__}",
            "sos_wake_required": True,
            "wake_class": "SOS",
            "recommended_action": (
                "Wake operator: watchdog hit an internal error and is "
                "fail-closing to BLOCKED. Inspect the watchdog and runtime."
            ),
            "mode": "DRY_RUN",
            "blocked_capabilities": list(BLOCKED_CAPABILITIES),
            "live_delivery_armed": False,
        }

    wrote = write_alert(alert_path, alert)
    print_summary(alert, alert_path, wrote, args.apply)

    return 2 if alert["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
