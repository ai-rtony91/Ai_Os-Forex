# AIOS Engineering Velocity Forecast V1

This is the canonical repository-local measured-velocity provider for the existing work countdown. It does not replace or duplicate countdown packet enumeration. The countdown accepts its state through the optional `engineering_velocity_forecast` argument while preserving existing callers.

The provider reads sanitized local event, Git, PR, task, dependency, blocker, runtime-milestone, test, and external-gate metadata. It makes no network or broker calls. Completion credit requires merged and validated evidence; open, closed-unmerged, and merged-unvalidated work remains `UNVERIFIED_UNCREDITED`.

## Calibration and fallbacks

The owner-reported 20-minute task duration is low-confidence calibration, not telemetry. Five valid measured durations replace it. Selection order is lane, subsystem, program, repository, owner calibration, then a repository PERT baseline. Outputs disclose the selected source, assumptions, exclusions, outliers, and missing evidence.

## Time boundaries

Active engineering time is separate from review/merge latency, calendar time, owner action, external evidence, broker runtime, and observation time. An unconstrained external wait makes calendar completion `UNKNOWN`. First Withdrawable Dollar remains distinct from repository completion, demo readiness, live-trade approval, profitable-trade evidence, and withdrawable-dollar proof.

## Offline CLI

```text
python scripts/run_aios_engineering_velocity_forecast_v1.py --repo-root . --project-input Reports/orchestration/AIOS_ENGINEERING_VELOCITY_FORECAST_INPUT_V1.example.json --event-log Reports/orchestration/AIOS_ENGINEERING_VELOCITY_EVENT_LOG_V1.jsonl --github-pr-metadata Reports/orchestration/AIOS_GITHUB_PR_DELIVERY_METADATA_V1.json --codex-task-metadata Reports/orchestration/AIOS_CODEX_TASK_DELIVERY_METADATA_V1.json --as-of-utc 2026-08-06T12:00:00Z --state-output Reports/orchestration/AIOS_ENGINEERING_VELOCITY_FORECAST_V1_STATE.json --report-output Reports/orchestration/AIOS_ENGINEERING_VELOCITY_FORECAST_V1_REPORT.md
```

The Git collector uses only fixed read-only `git rev-parse`, `git branch --show-current`, and `git log` commands. Identical inputs, repository HEAD, and as-of timestamp produce byte-stable JSON.

## Local delivery backfill

The checked-in Codex and GitHub delivery metadata backfills contain only facts available from local Git history: delivery/merge timestamps, PR numbers parsed from commit subjects, commit SHAs, and titles. They deliberately record task duration and GitHub check validation as unavailable rather than estimating either value. Consequently, merged work remains uncredited until sanitized check evidence is supplied, and local delivery cadence is not misrepresented as active Codex engineering time.
