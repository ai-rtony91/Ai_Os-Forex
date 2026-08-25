# AIOS Forex Owner Risk Authority V1

## Authority and scope

Human Owner Anthony approved this policy in packet
`PKT-EAST-FOREX-OWNER-RISK-AUTHORITY-020` for continued PAPER, demo, and
live-readiness development.

This policy is risk authority only. It does not authorize live execution,
broker connectivity, order submission, credentials, account identifiers, or
money movement. Stricter authority in `AGENTS.md` and `RISK_POLICY.md` remains
in force.

## Approved controls

| Control | Value | Source |
|---|---:|---|
| `MAX_RISK_PER_TRADE_PERCENT` | `1.0` percent of account equity | `PREEXISTING_PROVEN_AUTHORITY` |
| `MAX_DAILY_LOSS_PERCENT` | `2.0` percent of account equity | `HUMAN_OWNER_APPROVAL_PACKET_020` |
| `MAX_OPEN_RISK_PERCENT` | `1.0` percent of account equity | `HUMAN_OWNER_APPROVAL_PACKET_020` |
| `MAX_OPEN_TRADES` | `1` | `PREEXISTING_PROVEN_AUTHORITY` |
| `MAX_DRAWDOWN_PERCENT` | `5.0` percent | `PREEXISTING_PROVEN_AUTHORITY` |
| `MAX_PAIR_EXPOSURE_POLICY` | `RISK_DERIVED_FROM_1_PERCENT_ACCOUNT_EQUITY_AND_INITIAL_STOP_DISTANCE` | `HUMAN_OWNER_APPROVAL_PACKET_020` |
| `MAX_SPREAD_PIPS` | `3.0` pips | `HUMAN_OWNER_APPROVAL_PACKET_020` |

## Interpretation

The daily-loss budget is the applicable account-equity baseline multiplied by
`0.02`. Once cumulative realized loss plus applicable protected loss reaches or
exceeds the budget, new entries are blocked until the authoritative next
trading-day boundary. This document does not create an automatic reset path.

Total simultaneous initial risk is limited to account equity multiplied by
`0.01`. Because only one open trade is permitted, an active position also
blocks a second entry independently of the aggregate risk calculation.

Pair exposure is risk-derived. The maximum permissible position is calculated
from the 1 percent risk budget and the actual initial stop distance. No fixed
quote-currency notional may override or bypass that risk limit. Invalid or
non-positive stop distance fails closed. Any stricter existing risk constraint
continues to apply.

Spread is normalized to pips before comparison. The standard Forex convention
used for the supported symbol forms is a pip size of `0.01` when the quote
currency is JPY and `0.0001` otherwise. Thus 3 pips corresponds to `0.03` for a
JPY-quoted pair and `0.0003` for a typical non-JPY pair. One universal raw
price-distance threshold is prohibited.

## Kill-switch procedural authority

`KILL_SWITCH_CREDENTIAL_REVOKE_PATH` is
`GOVERNED_OPERATOR_BROKER_TOKEN_REVOCATION_PROCEDURE`.

This is a procedure, not a repository credential path:

1. Stop or disable AIOS Forex execution authority.
2. Revoke or disable the applicable broker credential through the authorized
   broker credential-management mechanism.
3. Terminate any owner-started broker-connected process.
4. Verify AIOS no longer has broker connectivity.
5. Record sanitized evidence only.

`KILL_SWITCH_NOTIFICATION_PATH` is
`SANITIZED_LOCAL_AIOS_HUMAN_OWNER_ALERT`.

The local alert records event type, timestamp, triggered risk control,
sanitized reason, runtime state, `entries_blocked=true`, and
`human_review_required=true`. It excludes secret material, account identifiers,
authorization values, and private broker payloads. No external notification
provider is authorized.

## Safety state

- `PAPER_ONLY=true`
- `LIVE_ENABLED=false`
- `BROKER_WRITES=false`
- `PRACTICE_ORDERS=false`
- `LIVE_ORDERS=false`
- `MONEY_MOVEMENT=false`

