#!/usr/bin/env python3
"""Run the deterministic, offline AIOS engineering forecast."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.orchestration.aios_engineering_velocity_forecast_v1 import (  # noqa: E402
    build_forecast, collect_git_metadata, load_event_log, load_json, render_report, stable_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--project-input", required=True)
    parser.add_argument("--event-log")
    parser.add_argument("--github-pr-metadata")
    parser.add_argument("--codex-task-metadata")
    parser.add_argument("--calibration", default="automation/orchestration/baselines/AIOS_ENGINEERING_VELOCITY_CALIBRATION_V1.json")
    parser.add_argument("--as-of-utc", required=True)
    parser.add_argument("--state-output", required=True)
    parser.add_argument("--report-output", required=True)
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    resolve = lambda value: Path(value) if Path(value).is_absolute() else root / value
    project = load_json(resolve(args.project_input))
    events = load_event_log(resolve(args.event_log) if args.event_log else None)
    prs = load_json(resolve(args.github_pr_metadata)) if args.github_pr_metadata else []
    tasks = load_json(resolve(args.codex_task_metadata)) if args.codex_task_metadata else []
    calibration = load_json(resolve(args.calibration))
    for name, value in (("GitHub PR metadata", prs), ("Codex task metadata", tasks)):
        if not isinstance(value, list):
            parser.error(f"{name} must be a JSON array")
    state = build_forecast(project, events, git_metadata=collect_git_metadata(root), github_pr_metadata=prs, codex_task_metadata=tasks, calibration=calibration, as_of_utc=args.as_of_utc)
    state_path, report_path = resolve(args.state_output), resolve(args.report_output)
    state_path.parent.mkdir(parents=True, exist_ok=True); report_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(stable_json(state), encoding="utf-8")
    report_path.write_text(render_report(state), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
