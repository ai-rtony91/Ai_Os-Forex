"""Deterministic, offline engineering-velocity forecast for AIOS."""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "AIOS_ENGINEERING_VELOCITY_FORECAST.v1"
EVENT_SCHEMA = "AIOS_ENGINEERING_VELOCITY_EVENT.v1"
EVENT_TYPES = {
    "TASK_STARTED", "TASK_COMPLETED", "TASK_BLOCKED", "COMMIT_CREATED", "PR_CREATED",
    "PR_MERGED", "PR_CLOSED_UNMERGED", "VALIDATION_PASSED", "VALIDATION_FAILED",
    "BLOCKER_DISCOVERED", "BLOCKER_CLOSED", "RUNTIME_MILESTONE_VERIFIED",
    "EXTERNAL_GATE_OPENED", "EXTERNAL_GATE_CLOSED",
}
SENSITIVE_KEY = re.compile(r"(?:secret|password|passwd|credential|api[_-]?key|access[_-]?token|account[_-]?id)", re.I)
SENSITIVE_VALUE = re.compile(r"(?:sk-[A-Za-z0-9]{12,}|-----BEGIN [A-Z ]+PRIVATE KEY-----)")


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"malformed timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _sanitize(value: Any, path: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if SENSITIVE_KEY.search(str(key)):
                raise ValueError(f"private or secret-like metadata rejected at {path}.{key}")
            _sanitize(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _sanitize(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite numeric value at {path}")
    elif isinstance(value, str) and SENSITIVE_VALUE.search(value):
        raise ValueError(f"secret-like value rejected at {path}")


def percentile(values: Sequence[float], percent: float) -> float | None:
    """Linear-interpolated percentile, stable across supported Python versions."""
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * percent / 100.0
    lower, upper = math.floor(position), math.ceil(position)
    result = ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(result, 3)


def robust_statistics(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {key: None for key in ("median", "p25", "p75", "p90", "minimum", "maximum", "median_absolute_deviation")} | {"sample_count": 0, "outlier_count": 0}
    ordered = sorted(_finite_number(value, "sample") for value in values)
    median = float(statistics.median(ordered))
    mad = float(statistics.median(abs(value - median) for value in ordered))
    outliers = sum(abs(value - median) > 3 * mad for value in ordered) if mad else 0
    return {
        "sample_count": len(ordered), "median": round(median, 3), "p25": percentile(ordered, 25),
        "p75": percentile(ordered, 75), "p90": percentile(ordered, 90),
        "minimum": round(min(ordered), 3), "maximum": round(max(ordered), 3),
        "median_absolute_deviation": round(mad, 3), "outlier_count": outliers,
    }


def pert_expected(optimistic: float, most_likely: float, pessimistic: float) -> float:
    values = [_finite_number(value, "PERT estimate") for value in (optimistic, most_likely, pessimistic)]
    if any(value < 0 for value in values) or not values[0] <= values[1] <= values[2]:
        raise ValueError("PERT estimates must be non-negative and ordered")
    return round((values[0] + 4 * values[1] + values[2]) / 6, 3)


def load_json(path: str | Path) -> Any:
    value = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON number: {value}")))
    _sanitize(value)
    return value


def load_event_log(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None or not Path(path).is_file():
        return []
    events: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON number: {value}")))
        if not isinstance(event, dict):
            raise ValueError(f"event line {line_number} must be an object")
        _sanitize(event)
        normalized = normalize_event(event, line_number)
        identity = str(normalized["event_id"])
        canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        if identity in seen and seen[identity] != canonical:
            raise ValueError(f"conflicting duplicate event: {identity}")
        if identity not in seen:
            seen[identity] = canonical
            events.append(normalized)
    return events


def normalize_event(event: Mapping[str, Any], line_number: int = 0) -> dict[str, Any]:
    value = dict(event)
    # Legacy task receipts are normalized without inventing additional events.
    if "event_type" not in value:
        if value.get("final_status") == "COMPLETE":
            value["event_type"] = "TASK_COMPLETED"
            value["timestamp_utc"] = value.get("completed_utc")
            value["task_id"] = value.get("packet_id")
        elif value.get("final_status") == "BLOCKED":
            value["event_type"] = "TASK_BLOCKED"
            value["timestamp_utc"] = value.get("completed_utc")
    event_type = str(value.get("event_type") or "")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported event type: {event_type}")
    timestamp = value.get("timestamp_utc") or value.get("observed_utc")
    parsed = parse_timestamp(timestamp)
    value["timestamp_utc"] = parsed.isoformat().replace("+00:00", "Z")
    if "elapsed_seconds" in value:
        elapsed = _finite_number(value["elapsed_seconds"], "elapsed_seconds")
        if elapsed < 0:
            raise ValueError("elapsed_seconds cannot be negative")
    identity_parts = [event_type, str(value.get("task_id") or value.get("packet_id") or value.get("pr_number") or value.get("blocker_id") or ""), value["timestamp_utc"]]
    value["event_id"] = str(value.get("event_id") or "|".join(identity_parts) or f"line-{line_number}")
    return value


def completion_credit(item: Mapping[str, Any]) -> bool:
    """Credit only merged and validated work when repository validation is required."""
    state = str(item.get("state") or item.get("status") or "").upper()
    merged = item.get("merged") is True or state == "MERGED" or bool(item.get("merged_at") or item.get("merged_timestamp"))
    validated = item.get("validated") is True or str(item.get("validation_status") or item.get("check_status") or "").upper() in {"PASS", "PASSED", "SUCCESS"}
    return merged and validated


def _cycle_and_path(dependencies: Sequence[Mapping[str, Any]]) -> list[str]:
    graph: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = set()
    for edge in dependencies:
        upstream, downstream = str(edge.get("upstream") or ""), str(edge.get("downstream") or "")
        if not upstream or not downstream:
            raise ValueError("dependency edges require upstream and downstream")
        graph[upstream].append(downstream); nodes.update((upstream, downstream))
    visiting: set[str] = set(); visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting: raise ValueError("dependency cycle detected")
        if node in visited: return
        visiting.add(node)
        for child in sorted(graph[node]): visit(child)
        visiting.remove(node); visited.add(node)
    for node in sorted(nodes): visit(node)
    # Deterministic longest path; status filtering remains an input responsibility.
    memo: dict[str, list[str]] = {}
    def longest(node: str) -> list[str]:
        if node not in memo:
            choices = [longest(child) for child in sorted(graph[node])]
            memo[node] = [node] + (max(choices, key=lambda p: (len(p), tuple(reversed(p)))) if choices else [])
        return memo[node]
    return max((longest(node) for node in sorted(nodes)), key=lambda p: (len(p), tuple(reversed(p))), default=[])


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def collect_git_metadata(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    head, branch = _git(root, "rev-parse", "HEAD"), _git(root, "branch", "--show-current")
    records = []
    raw = _git(root, "log", "--format=%H%x1f%aI%x1f%cI%x1f%s", "--no-merges", "-100")
    for row in raw.splitlines() if raw else []:
        sha, authored, committed, subject = row.split("\x1f", 3)
        match = re.search(r"\(#(\d+)\)", subject)
        records.append({"commit_sha": sha, "author_timestamp": authored, "commit_timestamp": committed, "subject": subject, "referenced_pr_number": int(match.group(1)) if match else None})
    fingerprint = hashlib.sha256((head + "\n" + branch).encode()).hexdigest()
    return {"head": head, "branch": branch, "repository_fingerprint": fingerprint, "commits": records}


def _task_samples(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    samples = []
    starts: dict[str, datetime] = {}
    for event in events:
        task_id = str(event.get("task_id") or event.get("packet_id") or "")
        if event["event_type"] == "TASK_STARTED" and task_id: starts[task_id] = parse_timestamp(event["timestamp_utc"])
        if event["event_type"] == "TASK_COMPLETED":
            seconds = event.get("elapsed_seconds")
            if seconds is None and task_id in starts: seconds = (parse_timestamp(event["timestamp_utc"]) - starts[task_id]).total_seconds()
            if seconds is not None and _finite_number(seconds, "elapsed_seconds") >= 1:
                samples.append({"minutes": round(float(seconds) / 60, 3), "lane": event.get("lane"), "subsystem": event.get("subsystem"), "program": event.get("program"), "task_id": task_id})
    return samples


def _codex_task_samples(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize measured Codex delivery receipts without estimating missing time."""
    samples: list[dict[str, Any]] = []
    for item in items:
        task_id = str(item.get("task_id") or item.get("packet_id") or "")
        seconds = item.get("elapsed_seconds")
        if seconds is None and item.get("started_utc") and item.get("completed_utc"):
            seconds = (parse_timestamp(item["completed_utc"]) - parse_timestamp(item["started_utc"])).total_seconds()
        if seconds is not None:
            elapsed = _finite_number(seconds, "elapsed_seconds")
            if elapsed < 0:
                raise ValueError("elapsed_seconds cannot be negative")
            if elapsed >= 1:
                samples.append({
                    "minutes": round(elapsed / 60, 3), "lane": item.get("lane"),
                    "subsystem": item.get("subsystem"), "program": item.get("program"),
                    "task_id": task_id,
                })
    return samples


def build_forecast(project: Mapping[str, Any], events: Sequence[Mapping[str, Any]] = (), *, git_metadata: Mapping[str, Any] | None = None, github_pr_metadata: Sequence[Mapping[str, Any]] = (), codex_task_metadata: Sequence[Mapping[str, Any]] = (), calibration: Mapping[str, Any] | None = None, as_of_utc: str) -> dict[str, Any]:
    _sanitize(project); _sanitize(github_pr_metadata); _sanitize(codex_task_metadata)
    as_of = parse_timestamp(as_of_utc)
    dependencies = project.get("dependencies") or []
    critical_path = _cycle_and_path(dependencies)
    all_events = list(events)
    event_samples = _task_samples(all_events)
    codex_samples = _codex_task_samples(codex_task_metadata)
    samples = event_samples + codex_samples
    lane = project.get("lane"); subsystem = project.get("subsystem"); program = project.get("hierarchy", {}).get("program") if isinstance(project.get("hierarchy"), Mapping) else None
    candidates = [sample for sample in samples if lane and sample.get("lane") == lane]
    source = "LANE_MEASURED_HISTORY"
    if len(candidates) < 5:
        candidates = [sample for sample in samples if subsystem and sample.get("subsystem") == subsystem]; source = "SUBSYSTEM_MEASURED_HISTORY"
    if len(candidates) < 5:
        candidates = [sample for sample in samples if program and sample.get("program") == program]; source = "PROGRAM_MEASURED_HISTORY"
    if len(candidates) < 5:
        candidates = samples; source = "REPOSITORY_MEASURED_HISTORY"
    owner_used = len(candidates) < 5
    calibration = calibration or {"typical_task_duration_minutes": 20, "provenance": "HUMAN_OWNER_REPORTED", "confidence": "LOW", "minimum_measured_samples_to_override": 5}
    stats = robust_statistics([sample["minutes"] for sample in candidates])
    if owner_used:
        duration = _finite_number(calibration.get("typical_task_duration_minutes", 20), "calibration duration"); source = "HUMAN_OWNER_REPORTED"
    else: duration = float(stats["median"])
    work = list(project.get("remaining_work") or [])
    remaining = {key: 0 for key in ("repository_fixable", "owner_action", "external_evidence", "broker_runtime", "observation_time", "unknown")}
    for item in work:
        category = str(item.get("category") or "unknown")
        remaining[category if category in remaining else "unknown"] += 1
    task_count = sum(1 for item in work if str(item.get("category") or "unknown") == "repository_fixable")
    baseline = project.get("pert_task_minutes")
    if owner_used and isinstance(baseline, Mapping):
        low = _finite_number(baseline["optimistic"], "optimistic") * task_count
        best = pert_expected(baseline["optimistic"], baseline["most_likely"], baseline["pessimistic"]) * task_count
        high = _finite_number(baseline["pessimistic"], "pessimistic") * task_count; source = "REPOSITORY_PERT_BASELINE"; owner_used = False
    else:
        low = (float(stats["p25"]) if not owner_used else duration * .75) * task_count
        best = duration * task_count
        high = (float(stats["p90"]) if not owner_used else duration * 1.5) * task_count
    unknown_external = any(item.get("wait_minutes") is None for item in work if str(item.get("category")) in {"external_evidence", "broker_runtime", "observation_time", "owner_action"})
    enumerated = isinstance(project.get("remaining_work"), list)
    insufficient = not enumerated or (not samples and not calibration and not baseline)
    exact_dates_allowed = enumerated and not unknown_external and not remaining["unknown"]
    calendar = {"low": "UNKNOWN", "best": "UNKNOWN", "high": "UNKNOWN"}
    if exact_dates_allowed:
        waits = sum(float(item.get("wait_minutes", 0)) for item in work if item.get("category") != "repository_fixable")
        calendar = {key: (as_of + timedelta(minutes=value + waits)).isoformat().replace("+00:00", "Z") for key, value in (("low", low), ("best", best), ("high", high))}
    counts = Counter(event["event_type"] for event in all_events)
    active_days = len({event["timestamp_utc"][:10] for event in all_events}) or 1
    prs = [dict(item) for item in github_pr_metadata]
    credited = sum(completion_credit(item) for item in prs)
    pr_leads = [
        (parse_timestamp(merged) - parse_timestamp(created)).total_seconds() / 60
        for item in prs
        if (merged := item.get("merged_at") or item.get("merged_timestamp"))
        and (created := item.get("created_at") or item.get("created_timestamp"))
    ]
    score = min(85, 15 + min(len(samples), 10) * 5 + (10 if enumerated else 0) + (10 if dependencies else 0) + (10 if prs else 0))
    warnings = []
    if owner_used: score -= 15; warnings.append("Owner-reported calibration used because fewer than five measured task samples exist.")
    if not prs: score -= 10; warnings.append("Local GitHub PR metadata was not supplied.")
    if unknown_external: score -= 20; warnings.append("An external wait is unconstrained; calendar completion is UNKNOWN.")
    if stats["sample_count"] and stats["median_absolute_deviation"] and stats["median_absolute_deviation"] > stats["median"] * .5: score -= 15; warnings.append("Measured task duration has high variance.")
    stale = bool(all_events) and max(parse_timestamp(event["timestamp_utc"]) for event in all_events) < as_of - timedelta(days=30)
    if stale: score -= 10; warnings.append("Measured event metadata is stale.")
    score = max(0, min(100, score))
    label = "INSUFFICIENT_DATA" if insufficient or not all_events else ("LOW" if score < 50 else "MODERATE" if score < 75 else "HIGH")
    git_metadata = dict(git_metadata or {})
    return {
        "schema": SCHEMA, "generated_at_utc": as_of.isoformat().replace("+00:00", "Z"),
        "repository_fingerprint": git_metadata.get("repository_fingerprint", "UNAVAILABLE"), "branch": git_metadata.get("branch", "UNKNOWN"), "HEAD": git_metadata.get("head", "UNKNOWN"),
        "forecast_target": project.get("forecast_target", "UNKNOWN"), "hierarchy": dict(project.get("hierarchy") or {}),
        "data_sources_used": sorted(["EVENT_LOG"] + (["GIT_COMMIT_METADATA"] if git_metadata else []) + (["GITHUB_PR_METADATA"] if prs else []) + (["CODEX_TASK_METADATA"] if codex_task_metadata else []) + [source]),
        "data_sources_missing": [name for name, present in (("GITHUB_PR_METADATA", bool(prs)), ("CODEX_TASK_METADATA", bool(codex_task_metadata)), ("MEASURED_TASK_DURATION", bool(samples))) if not present],
        "event_counts": {key: counts.get(key, 0) for key in sorted(EVENT_TYPES)}, "valid_sample_counts": {"task_duration": len(samples), "selected_task_duration": stats["sample_count"], "merged_pr_lead_time": len(pr_leads)},
        "excluded_event_counts": {"zero_or_subsecond_task_duration": sum(event["event_type"] == "TASK_COMPLETED" and float(event.get("elapsed_seconds", 1)) < 1 for event in all_events) + sum(item.get("elapsed_seconds") is not None and float(item["elapsed_seconds"]) < 1 for item in codex_task_metadata)}, "exclusion_reasons": ["Subsecond durations are automation receipts, not engineering-duration evidence."] if (all_events or codex_task_metadata) and not samples else [],
        "observed_velocity": {"task_duration_minutes": stats, "selected_duration_source": source, "merged_pr_lead_time_minutes": robust_statistics(pr_leads), "tasks_completed_per_active_day": round(counts["TASK_COMPLETED"] / active_days, 3), "PRs_merged_per_active_day": round(counts["PR_MERGED"] / active_days, 3), "blocker_discovery_rate": round(counts["BLOCKER_DISCOVERED"] / active_days, 3), "blocker_closure_rate": round(counts["BLOCKER_CLOSED"] / max(1, counts["BLOCKER_DISCOVERED"]), 3), "validation_failure_rate": round(counts["VALIDATION_FAILED"] / max(1, counts["VALIDATION_FAILED"] + counts["VALIDATION_PASSED"]), 3), "rework_rate": round(sum(1 for item in prs if item.get("rework") is True) / max(1, len(prs)), 3)},
        "completion_credit": {"merged_and_validated": credited, "unverified_uncredited": len(prs) - credited},
        "remaining_work": remaining, "critical_path": critical_path, "highest_blocker": critical_path[0] if critical_path else None,
        "low_estimate": {"active_engineering_minutes": round(low, 2)}, "best_estimate": {"active_engineering_minutes": round(best, 2)}, "high_estimate": {"active_engineering_minutes": round(high, 2)},
        "estimated_tasks_remaining": task_count if enumerated else "UNKNOWN", "estimated_active_engineering_minutes": {"low": round(low, 2), "best": round(best, 2), "high": round(high, 2)}, "estimated_calendar_completion_range": calendar,
        "confidence_score": score, "confidence_label": label, "assumptions": [f"Task-duration source: {source}.", "External waiting is excluded from active engineering time."], "warnings": warnings,
        "evidence_provenance": {"owner_calibration": dict(calibration), "measured_task_ids": sorted(sample["task_id"] for sample in samples), "open_or_unmerged_work": "UNVERIFIED_UNCREDITED"},
        "first_withdrawable_dollar_status": "DISTINCT_MILESTONE_NOT_INFERRED", "next_safe_action": project.get("next_safe_action") or "Record measured task start and completion events.",
        "protected_actions": {key: False for key in ("network", "broker", "order", "scheduler", "daemon", "webhook", "push", "merge")},
    }


def stable_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def render_report(state: Mapping[str, Any]) -> str:
    velocity = state["observed_velocity"]; duration = velocity["task_duration_minutes"]
    return f"""# AIOS Engineering Velocity Forecast V1

## What is being forecast?
{state['forecast_target']}

## What is complete?
{state['completion_credit']['merged_and_validated']} locally supplied items have merged and validated evidence.

## What remains?
{state['remaining_work']}

## What data was measured?
{state['valid_sample_counts']} Event counts: {state['event_counts']}.

## What data is missing?
{', '.join(state['data_sources_missing']) or 'None identified.'}

## Current productivity rate
Median task minutes: {duration['median']}; tasks per active day: {velocity['tasks_completed_per_active_day']}; PRs merged per active day: {velocity['PRs_merged_per_active_day']}.

## Expected Codex tasks
{state['estimated_tasks_remaining']}

## Expected active development time
{state['estimated_active_engineering_minutes']} minutes. External wait is excluded.

## Calendar completion range
{state['estimated_calendar_completion_range']}

## Confidence
{state['confidence_score']}/100 ({state['confidence_label']}).

## Critical-path blocker
Path: {state['critical_path']}. Highest blocker: {state['highest_blocker']}.

## External rather than engineering delays
Owner action, external evidence, broker runtime, and observation time: {state['remaining_work']}.

## Evidence that would improve the next forecast
Add measured task durations, sanitized merged-PR/check metadata, complete dependencies, and bounded external waits.

## First Withdrawable Dollar
{state['first_withdrawable_dollar_status']}; it is distinct from repository completion, demo readiness, live approval, profitable-trade evidence, and withdrawal proof.
"""
