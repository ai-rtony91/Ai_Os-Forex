# AI_OS Tier 0 — Dead-Man Watchdog

`aios_deadman_watchdog.py` is a cross-platform (pure Python 3 stdlib) dead-man
watchdog. It closes the scariest audit finding: **if the unattended loop dies,
nothing fires and the operator is never woken.**

## What it does

- Reads the runtime heartbeat (`telemetry/runtime/runtime_heartbeat.json`) emitted
  by `automation/orchestration/Invoke-AiOsNightCycle.ps1` and parses its
  timestamp (`heartbeatAt` / `last_beat` / etc.).
- Computes staleness against a threshold (default **600s / 10 min**).
- If the heartbeat is **missing, unreadable, or older than the threshold**, it
  classifies the situation as `BLOCKED` — the loop is presumed **dead** — and
  produces an SOS alert record (`detected_at`, `last_heartbeat`,
  `staleness_seconds`, `threshold_seconds`, `severity=BLOCKED`,
  `recommended_action`).
- **Fail-closed:** any failure to read the heartbeat is treated as `BLOCKED`
  (presumed dead), never as OK. The watchdog itself never crashes — all file IO
  is wrapped, and an internal error fail-closes to `BLOCKED`.
- **Exit code:** `0` if healthy, `2` if `BLOCKED`, so an external scheduler
  could later act on it.

Severity model matches `services/python_supervisor/notifier.py`: **`BLOCKED`
is the only SOS-worthy / wake-worthy state** (quiet-by-default).

## Safety posture — intentionally NOT armed (Tier 0 gate)

This module is **DISABLED-BY-DEFAULT and DRY_RUN by default**. It does **not**:

- send any live notification (`live_send`)
- register any scheduler / cron / systemd / Task Scheduler entry (`scheduler_registration`)
- start any background loop (`loop_start`)

These appear in the script's `BLOCKED_CAPABILITIES` list. In DRY_RUN it only
writes the alert to `telemetry/watchdog/DEADMAN_ALERT_LATEST.json` and prints a
clear summary — it delivers the alert nowhere.

The `--apply` flag is **reserved for future live delivery**. In this version,
even with `--apply`, it still only writes the alert file and prints
`LIVE_DELIVERY_NOT_ARMED: wire an SOS channel first`. **It does not send.**
Wiring an actual SOS channel + scheduler registration is a deliberate later tier.

## Runtime heartbeat contract

The night-cycle loop writes `telemetry/runtime/runtime_heartbeat.json` with:

- `heartbeatAt`
- `last_beat`
- `cycle_id`
- `phase_name`
- `pid`
- `mode`
- `effective_apply`
- `observe_only`
- `updated_at_utc`

The heartbeat is local runtime evidence only. It is written with temp-file then
rename behavior using a collision-safe GUID suffix. It is not approval evidence
and does not authorize APPLY, restart, commit, push, merge, live sends, scheduler
registration, broker access, or live trading.

## Optional research-campaign health

Pass `--campaign-state-path` to inspect one local research campaign checkpoint
in addition to the heartbeat. Without that flag, the JSON alert and exit behavior
remain heartbeat-only.

The optional checkpoint must carry a valid SHA-256 digest. For an active campaign,
the watchdog reports `BLOCKED` (and therefore an SOS-worthy wake) for a missing or
malformed file, invalid digest, an empty next-experiment queue, a duplicated last
completed fingerprint, or progress older than
`--campaign-progress-threshold-seconds` (default 600 seconds). The top-level
alert becomes `BLOCKED` when campaign health is blocked.

`NO_EDGE_IN_SCOPE` means the finite approved research catalog produced no edge in
scope. It is informational (`NO_WAKE`), not a system fault. As everywhere else in
this watchdog, **only `BLOCKED` wakes**.

Campaign inspection is detect-only: it never re-runs an experiment, modifies the
checkpoint, starts a worker, registers a scheduler, restarts a process, or sends a
notification.

## Research-controller fixture proof

The local research runner and watchdog share a canonical checkpoint contract.
The fixture proof runs one `APPLY` controller cycle into a pytest temporary
directory, then asks the watchdog to validate that checkpoint:

```bash
python -m pytest \
  tests/orchestration/test_aios_research_campaign.py \
  tests/orchestration/test_aios_research_campaign_runner.py \
  tests/orchestration/test_aios_deadman_watchdog_campaign_health.py \
  tests/orchestration/test_aios_research_campaign_end_to_end.py -q
```

This is a one-shot local contract test. It starts no scheduler, service, daemon,
worker, market-data connection, broker session, or order path. A candidate-bound
`PAPER` gate can select a catalog research stage; it does not launch paper
orders or establish paper readiness. Readiness still requires independently
verifiable cost-adjusted out-of-sample results and paper-trading execution
evidence. The fixture proof establishes neither a profitability edge nor
trading readiness.

The gate validates candidate/version bindings and recalculates OOS expectancy,
profit factor, trade count and closed-trade drawdown after both base and stress
costs from bounded trade receipts. It rejects duplicate trades, invalid cost
ordering, out-of-window receipts and selection/OOS overlap. It does not
authenticate source bytes, verify independent test selection, measure open
positions, or establish real paper fills. Optional `evidence` records contribute only to the
descriptive scorecard; their source identifiers are labels, not verified
artifacts. `PAPER_ELIGIBLE` therefore means only that the local controller
accepted bound records and reviewed claims for research-stage selection. It is not a claim that a
profitability edge has been proven or that paper trading is ready.

Checkpoint writes preserve completed history and use an exclusive writer lock
and loaded-revision check. Concurrent writers fail closed; an old caller cannot
erase newer results. APPLY refuses future checkpoints and stale active state
before writing. The watchdog checks future progress before informational
terminal states: `NO_EDGE_IN_SCOPE`, `BUDGET_EXHAUSTED`, `RESEARCH_COMPLETE`.
The last two mean exhausted approved work or completed research requiring
review; neither proves profitability or authorizes paper/live execution.

## Restart boundary

The watchdog remains detect-only. It does not restart the night cycle. Any future
restart supervisor must be manually launched, default to DRY_RUN, require an
explicit arming flag for actual restart, honor `control/self_continuation/STOP`,
and preserve the existing approval gates inside the night cycle.

No scheduler, service, startup task, cron, systemd unit, Task Scheduler entry, or
live notification channel is registered by this watchdog.

## How to run (DRY_RUN)

```bash
# Default: read the real runtime heartbeat, 600s threshold.
python3 automation/orchestration/watchdog/aios_deadman_watchdog.py

# Custom threshold (e.g. 5 minutes).
python3 automation/orchestration/watchdog/aios_deadman_watchdog.py --threshold-seconds 300

# Point at a specific heartbeat file.
python3 automation/orchestration/watchdog/aios_deadman_watchdog.py \
  --heartbeat-path /path/to/runtime_heartbeat.json

# Add an optional local research checkpoint (still detect-only).
python3 automation/orchestration/watchdog/aios_deadman_watchdog.py \
  --campaign-state-path /path/to/campaign_checkpoint.json \
  --campaign-progress-threshold-seconds 300

# Reserved flag: still DRY_RUN-only, prints LIVE_DELIVERY_NOT_ARMED.
python3 automation/orchestration/watchdog/aios_deadman_watchdog.py --apply
```

Arguments:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--threshold-seconds` | `600` | Max heartbeat age before `BLOCKED`. |
| `--heartbeat-path` | `telemetry/runtime/runtime_heartbeat.json` | Heartbeat file to check (relative paths resolve to repo root). |
| `--alert-path` | `telemetry/watchdog/DEADMAN_ALERT_LATEST.json` | Where the DRY_RUN alert JSON is written. |
| `--campaign-state-path` | unset | Optional local campaign checkpoint; enables campaign-health inspection. |
| `--campaign-progress-threshold-seconds` | `600` | Max active-campaign progress age before campaign health is `BLOCKED`. |
| `--apply` | off | Reserved; live delivery is NOT armed in this version. |

## Output

The alert JSON (`AIOS_DEADMAN_ALERT.v1`) is written to
`telemetry/watchdog/DEADMAN_ALERT_LATEST.json`. It is local runtime evidence,
not source authority.
