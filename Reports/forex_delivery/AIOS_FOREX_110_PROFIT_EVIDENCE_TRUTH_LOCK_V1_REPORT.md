# AIOS Forex 110 Profit Evidence Truth Lock V1

Packet ID: `PKT-FOREX-110-PROFIT-EVIDENCE-TRUTH-LOCK-V1`
Profit proof status: `BLOCKED`
Truth lock status: `BLOCKED`
Unverified diagnostic persistent profitability status: `PERSISTENT_PROFITABILITY_BLOCKED`
Unverified diagnostic ledger status: `PROFIT_PROOF_LEDGER_BLOCKED_MISSING_EVIDENCE`
Top candidate: `NONE`
Unverified diagnostic top candidate classification: `NONE`

## Owner Answer
Profit proof is blocked: independent candidate and source verification is unavailable. Summary metrics are diagnostic only. No execution or money authority is approved.

## Permission Locks
- next_demo_trade_allowed: `false`
- broker_action_allowed: `false`
- real_money_allowed: `false`
- compounding_allowed: `false`
- bank_movement_allowed: `false`
- live_trading_allowed: `false`
- credential_access_allowed: `false`
- order_submission_allowed: `false`
- owner_approval_created: `false`

## Blockers
- after-cost profitability evidence is missing
- no promotable strategy is selected
- next demo trade remains locked
- broker action remains locked
- real money remains locked
- compounding remains locked
- bank movement remains locked
- NO_INDEPENDENT_VERIFIER_CONNECTED

## Next Safe Action
Obtain independent candidate/source/custody verification through the existing admitted evidence owner. Preserve economic blockers; labels and summary metrics are insufficient. Do not execute research, access proof data, or trade without separate admission.

## 42-trade claim investigation ? 2026-10-12

Disposition: **REJECTED_SYNTHETIC_FIXTURE / NOT PROVEN**. Candidate: `c2-eur-buy-stronger-review-ready`; verified qualifying trades: **0**.

The original saved `walkforward_result` and every OOS segment result exactly equal the default input produced by `build_default_c2_harness_input`. Six lists of seven hard-coded outcomes total 42. Arithmetic: gross profit 13.09, gross loss 1.91, net 11.18, mean 0.26619048 and profit factor 6.85340314. The four OOS lists contain another 24 synthetic outcomes. This reproduces fixture arithmetic, not a market strategy.

`walkforward_validation_harness._window_candidates` supplies fixed EURUSD buy entry 1.1, stop 1.09, target 1.12, spread 0.0001 and the same 2026-01-01 timestamp. `strategy_evaluation_harness` passes these into `paper_session_sample_generator`, which constructs an exit to produce the supplied P/L and overwrites realized P/L with that value. No original market data, actual fill schedule, spread/fee/slippage/financing deductions, frozen C2 parameters or independent replay are bound to this claim. The period generator previously hard-coded `after_costs=True`. The reported mean comes from dollar P/L, not R: first window mean USD0.27857143 versus R0.00278548 with average dollar risk 100.00851429. The original 0.22 drawdown is a within-window dollar diagnostic, not independently verified percentage risk.

The source's empty period table resulted from computing `periods` without passing it as `profitable_periods` into the Markdown formatter. Filling that table would only publish more fixture summaries, so source export is blocked instead.

Repository search covered candidate ID, exact reported numbers, implementation paths and history. Runtime metadata inspection covered 14,758 text files under `.aios/runtime`, one under `data/forex_engine` and two under the report archive. No matching candidate/strategy/session receipt was found. Raw partitions, protected holdout/untouched/credential/secret paths and files over 16 MiB were excluded; the large files were H1 histories and a replay cache. This is a bounded absence finding, not a claim about every backup or differently labelled record. Original committed artifacts and hashes remain referenced by `claim_audit` at base commit `6c937257d954a1f12e96e012e8d3f7f79594e75b`.

Existing accepted engineering evidence and the current truth-lock source-authentication guard were reused. No market experiment or research worker was repeated or started. Existing local authenticity repair/test/fixture files were copied into a clean main-based worktree; the dirty authoritative checkout was preserved.

The correction closes numeric-to-real harness promotion, historical period-source export and summary-only source collection. Diagnostics remain available. Cost verification is UNVERIFIED, and interrupted profitable windows are no longer called a consecutive run.

Remaining candidate requirements:
- Freeze the exact C2 strategy/parameters and bind it to admitted, licensed source data, costs and risk rules.
- Supply chronological candidate-specific trade receipts with entry/exit/fill times, prices/units, gross P/L, spread/fees/slippage/financing, dollar risk and net R. Retain losses and unknown outcomes; reconcile full equity drawdown.
- Bind untouched independent confirmation/replay, selection history and accepted canonical receipts to the same candidate/input/code hashes. There is no independent verifier connected to these summary interfaces.
- Meet the existing gate being used. The summary ledger requires at least 30 trades, sufficient-depth evidence, positive expectancy, PF >=1.25, drawdown <=0.05, <=3 consecutive losses, >=3 regimes, WF/OOS/cost-sensitivity/reconciliation/risk evidence. Those thresholds alone do not authenticate proof.
- The factory development lane separately requires >=200 genuine after-cost trades and >=30 shared weeks with its retained WARM/cost/risk rules. Its PAPER handoff requires >=30 actual confirmation trades and >=30 PAPER trades for each selected side, PF >=1.10, positive after-cost expectancy, drawdown <=10%, distinct input sets and operational PAPER/recovery evidence. Use its existing independent receipt/journal/global-ledger bindings and separate owner admission.

The accepted P1 simulated trade is `sprint_4_intraday_trend_follow_v1`, not C2. It is excluded. PAPER qualification and LIVE/order authority remain closed.

## Offline validation

14 affected proof/intake/autopilot/dashboard modules: 124 tests passed. The reused harness regressions failed 10/10 before the repair and passed afterward; historical period-source and summary-collector export cases each failed 2/2 before repair and passed afterward. Interrupted-period/cost diagnostics reproduced baseline streak=5/after_costs=true and corrected streak=3/after_costs=false. Five source-generation tests already failed on the unchanged snapshot because the guarded truth lock selected NONE; their expectations now retain that fail-closed behavior. Syntax, configured Ruff 0.17.0 rules F821/F822/F823 and diff checks passed. This is scoped engineering validation, not a full-suite or profitable-edge claim.

Independent review also reproduced historical proof labels escaping through three report formatters and a stale dashboard completion cache. Three report regressions and one cache-agreement regression failed before correction and passed afterward. Report formatters now render authentication as unverified with closed permissions, and existing dashboard state/report, document mirror and completion index now show BLOCKED. No dashboard UI or runtime behavior was changed.

Final review also caught a supplied PROVEN OOS status still printable by the harness report, and static review-ready wording in a blocked completion index. Both now render unverified/blocked; their red regressions were observed and the final 14-module suite passed 124 tests. A temporary edit script initially failed under Windows default text encoding; explicit UTF-8 corrected it before the final verification.

## Authentic-source milestone preflight - 2026-10-12T18:53:58Z

The authoritative remaining-task board (same existing identity, version 20) still records 107 criteria: 65 completed and 42 blocked. These 42 blockers are distinct from C2's 42 synthetic outcomes. No economic, source-admission, PAPER or LIVE criterion is closed by this follow-up.

Current main at preflight: `27f8e43e4555afa8b7410b1d1bf666cb2a0b0809`. The dirty laptop checkout and all completed experiments remain preserved. Existing `factory_connection.py`, `PinnedS6Evaluator`, supported-entry code, Optuna bridge, global budget owner and PAPER handoff are reused. The prior recommendation to build a new research runner was too broad: the existing runner connection already exists; authentic acquisition/custody/provider evidence and current admission are the immediate gap.

Native metadata fingerprints freshly match the accepted source-lineage evidence:

| Existing artifact | SHA-256 |
| --- | --- |
| EUR/USD M5 corpus manifest | `1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b` |
| Acquisition checkpoint | `ce5adbde8bc4e317e00d3b9221e3ba6f816dd1f22be1cb6082f01cc254db92a1` |
| Development-only manifest | `ab40a9fc6c2abb1c9dfe1065afb072b8483d00ada693a708d0ea92c6aa901313` |
| Current registered S6 request | `50940fd5d31bb9571f6ea69f2a8f9d41d34e3ef8e0f3f5278524ee80ba9c7ca6` |

Source metadata locations are `C:/Dev/Ai.Os/.aios/runtime/forex_m5_immutable_corpus_v2/{manifest.json,acquisition_checkpoint.json}`. The development manifest is the existing `successor-pending/research_binding_s6/tests/data_owner_v1_20261001/development_slice_2024_2025_FINAL/DEVELOPMENT_ONLY_MANIFEST.json` under `C:/AIOS_Backups/factory-loop-run4-20261006`. Accepted prior verification covers 24 EUR/USD M5 partitions and 149,453 records for 2024-2025. Their native byte lineage does not authenticate the original provider event or applicable licence. No raw prices or protected holdout were opened in this follow-up.

The broader development manifest records 408 partitions across 17 instruments and 2,532,363 records; it preserves 3,527 unexpected gaps and labels value/financing contracts incomplete. Those broader metadata claims must not be silently credited to the smaller EUR/USD scope. The prepared EUR/USD jobs reset features at gaps and prohibit planned paths crossing quarantined intervals.

OANDA support review was freshly checked: only the existing acknowledgment and review-pending message were returned, with no new permission or acquisition answer. The public [August 2026 API agreement](https://legal.oanda.com/oc/api_license_agreement_oc/en) describes internal-use terms, but public text alone does not establish this custodian's agreement, effective entitlement or historical acquisition. The official [instrument API specification](https://github.com/oanda/v20-openapi/blob/master/yaml/separate/v20_instrument.yaml) supports midpoint/bid/ask candles, UTC timestamps, smoothing control and RequestID; technical support is not authentication of these retained files. No email was sent, credential read or provider API called.

The existing S6 request remains `pending_review`, `approved_by_human=false`; there is no signature field. This is unsigned preparation, not an admitted research session. The actual process observation found no research worker (only the read-only inspection process matched its own search terms).

### Existing bounded catalog retained, not executed

Use the frozen three `S6_FXH02_*` jobs already prepared for EUR/USD M5 development `[2024-01-01, 2026-01-01)`. Their original parameter and catalog bindings remain authoritative; do not regenerate them from this prose. Each reserves two configurations and six physical calls: total six configurations and eighteen calls. The jobs use completed-close breakout signals from a lagged 12-bar range, 12-bar compression, 288-bar reference, 20-bar ATR, next-bar-open entry, six-bar maximum holding and one-ATR stop. Retain the exact frozen variants and all 126 quarantined intervals. Untouched confirmation is separate, follows development, and was not accessed.

Declared research cost scenarios (commission USD per million per side / slippage pips per side): BASE `35 / 0.1`, STRESSED `52.5 / 0.5`, SEVERE_BUT_PLAUSIBLE `70 / 1.0`. These assumptions are not verified current broker charges. The existing bid/ask replay must include spread without double-counting it. Retain fixed risk, rejection rules, search history and finite global reservations. The current request's allocation is a preparation record, not a fresh reconciliation of spent/reserved global totals.

Retained development gates: at least 200 actual trades, positive results at all fixed cost levels, stressed PF >=1.10, drawdown <=10%, zero unknown outcomes, at least three positive blocks, surviving removal of November, the largest block and the top five trades, and beating the opposite control. Retain all additional current warm/shared-week, provenance, risk and statistical requirements. Passing development diagnostics would still require untouched independent confirmation, source-bound trade receipts and separate PAPER qualification.

No new trials, receipts, research calls, PAPER trades or orders were produced. The next executable research action waits for independently accepted acquisition/custody and applicable provider permission (or a distinctly licensed successor), then the existing HUMAN_ONLY admission and current input/history/budget/resource checks. Original H1 mapping remains a separate P06-11 requirement; it is not an added per-shard HTTP-receipt requirement for this EUR/USD source. C2 remains quarantined with zero verified trades; P1's different-strategy trade remains excluded.

### Confirmed projection defect

Three static window summaries still advertised a review-ready command center, review-ready candidate and proven profit when the actual saved proof chain was blocked. The correction derives these summaries from their respective source statuses and candidate presence. It does not change proof criteria or execution authority. Existing state and window-map exports are refreshed; focused regression and native verification results are recorded below after execution.

Follow-up verification: three new cases failed on the uncorrected static summaries; the ready-state control already passed. After the correction, Windows Python 3.12 ran the complete affected dashboard-closure test module: **9 passed**. Configured Ruff 0.17.0 F821/F822/F823 and `git diff --check` passed. These are focused engineering checks, not a full-suite or economic verification claim. The scratch interpreter had no pytest; the existing installed Windows test environment was reused without installing tools.

Independent review required clearer candidate wording and a nested cache comparison. The additional wording regression failed before correction; comparing the original main cache to the corrected producer also failed as expected. Both corrections passed the final nine-test Windows run (0.23 seconds). All six changed artifacts were reviewed; no remaining scoped code-review issues were reported. Canonical JSON ordering was retained to keep the cache diff limited to its three corrected strings.

### Existing native individual-trade contract

Read-only independent inspection verified `successor-pending/research_binding_s6/research_consumer.py` against its unchanged current request pin: `bfd6ca07ad5068a2a2ca76489808711b708bf2c1856c660fa396aa71a8145108`. The existing S6 path already emits trade rows. No new runner, receipt format or market replay was created.

Rows retain `pair`, `event_id`, `direction`, `signal`, `entry_time`, `entry_price`, `entry_spread`, `stop_price`, `exit_time`, `exit_price`, `exit_reason`, `exit_phase`, `intrabar_time_unknown`, `exit_spread`, `units`, `planned_risk_usd`, `reserved_notional_usd`, `bid_ask_pnl_before_extra_costs_usd`, `slippage_usd`, `commission_usd`, `net_usd`, `net_r`, `account_currency`, `quote_to_account_conversion`, `price_path`, `financing` and `cost_label`. The frozen parent spec/result supplies candidate/strategy parameters, `spec_sha256`, `source_sha256` and shard row-consumption bindings. Keep every row bound to that parent and scenario; an `event_id` alone is not guaranteed to identify a unique trade.

The existing saved artifacts are `RESULT.json`, `RECEIPT.json`, six `CANDIDATE_`/`CONTROL_` cost-scenario artifacts, canonical core acceptance and the `ACCEPTED_MARKET_UNIT` journal, plus the `AIOS_OPTUNA_S6_RECEIPT_V1` envelope. New actual receipt locations remain absent because this catalog has not been admitted or executed.

Native `trade_path()` derives slippage-adjusted executable prices, units and dollar risk. `net_usd` equals direction times exit-minus-entry price times units, minus commission; equivalently, executable bid/ask P/L before extra costs minus slippage and commission. `net_r` divides that net by planned dollar risk. Spread is embedded in bid/ask prices; it is not another dollar subtraction. Financing is excluded by a no-rollover boundary. An intrabar stop uses an explicit unknown tick time and bar-end convention; these are modeled fills, not observed tick executions.

Reuse native `metrics(trades, equity)`, `full_path_drawdown_bound(trades, equity)` and `analyze_supported_entry_catalog_v1(jobs, results)` for saved-result consistency. The latter recomputes and hash-compares each candidate/control arm without extra market calls. It remains same-engine consistency, not an independent second financial engine. Qualification still requires independently reconstructing costs, P/L, risk, chronology and ambiguity from admitted data and those receipts, preserving losses and all search exposure. No independent profitable-edge claim is made here.
