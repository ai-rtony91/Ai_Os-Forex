# AIOS Forex Effectiveness Isolated Recovery V1

Status: CONTROL_REMAINS_BEST_AVAILABLE
Mode: PAPER research only; no campaign launch or production configuration change.

## State authority

The isolated review found a live runtime, not a stopped runtime:

- autostart `READY`: `2026-08-18T10:26:49.534938Z`
- runtime PID: `5992`
- runtime lock heartbeat: `2026-08-18T13:54:30.093813Z`
- latest provenance cycle: `44`
- latest provenance completion: `2026-08-18T13:54:31.134945Z`
- latest campaign summary: `WAITING_FOR_NEXT_RUN`
- active session: `ACTIVE`, BUY, 100 units

The canonical campaign summary and active session conflict. Provenance and the
runtime lock establish that the runtime is active; the campaign summary's
`active_position: null` is stale or incomplete evidence. This packet did not
close, reconcile, or overwrite that owner evidence.

## Observed control funnel

Across 44 persisted runtime cycles:

| Measure | Count |
|---|---:|
| `NO_SIGNAL` | 38 |
| `WAIT_FOR_DATA` | 2 |
| `PAPER_SESSION_OPEN` | 1 |
| `PAPER_SESSION_HELD` | 3 |
| signal accepted | 2 |
| paper eligible | 1 |
| closed qualifying trades | 0 |

Observed rejection records were: volatility 38, pullback 29, trend 6,
duplicate-position guard 3, and data unavailable 2. The leading measured
opportunity blockers are volatility, pullback confirmation, and trend
alignment. This is descriptive evidence only; it is not a promotion result.

## Research boundary

The available sanitized history artifact contains 50 M5 candles and the
existing replay ledger contains no trade records. It is insufficient for the
required 5,000–10,000-candle train/validation/test study. No repeated broker
download or Practice request was made, and no candidate was selected.

Therefore no entry or exit change is proven, no false-negative recovery is
claimed, and no production parameter was changed. The existing control remains
the best available candidate pending an owner-local, GET-only research dataset.

## Timer implementation

`Watch-AiOsForexP1CycleTelemetryV1.ps1` now remains active until Ctrl+C,
refreshes every second, and reads persisted timestamps on every refresh:

- `RUNTIME AGE`: latest applicable autostart `READY.observed_at_utc`;
- `CAMPAIGN AGE`: campaign `started_utc`;
- `CYCLE AGE`: latest provenance `cycle_completed_utc`;
- `NEXT CHECK IN`: latest provenance `next_check_at_utc`.

The monitor also reads the active session and ledger, clears the prior display,
and never writes runtime files, starts processes, calls the network, or changes
the scheduler. Missing or invalid timestamps render as `UNKNOWN`.

Safety: broker write false; Practice order false; live false; money movement
false.
