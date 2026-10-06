CODEX-ONLY PROMPT
AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

# PKT-FOREX-044 — Control Baseline RSI Filter Comparison Stage 1

IDENTITY MARKER: PKT_FOREX_044_CONTROL_BASELINE_RSI_FILTER_COMPARISON_STAGE1
SUPERVISOR IDENTITY: Codex East
PACKET ID: PKT-FOREX-044
PACKET NAME: Control Baseline RSI Filter Comparison Stage 1
MODE: APPLY — DEVELOPMENT-ONLY STAGE 1
ZONE: EAST
WORKER IDENTITY: EAST_OCC_82
LANE: FOREX_CONTROL_BASELINE_RSI_FILTER_COMPARISON_STAGE1
WORKTREE: C:\Dev\Ai.Os
BRANCH: main, observed and preserved during preflight
LOCK ID: LOCK_EAST_FOREX_CONTROL_BASELINE_RSI_FILTER_COMPARISON_STAGE1_OCC82
APPROVAL AUTHORITY: Anthony, Human Owner, explicit PKT-FOREX-044 authorization

MISSION ID: MISSION-AIOS-001
MISSION NAME: AIOS Governed Self-Building Operating System
PROGRAM ID: PRG-FOREX-001
PROGRAM NAME: AIOS Forex Supervised Operational Validation Program V1
EPIC ID: EPC-FOREX-002
EPIC NAME: Strategy Intelligence V1
BUCKET ID: BKT-FOREX-003
BUCKET NAME: Strategy Validation V1

## Mission

Repair the existing RSI calculation against a fixed Wilder reference, then run one bounded development-only comparison between an existing Supertrend baseline and that identical baseline with one RSI filter. Determine whether the added rule improves after-cost results on matched opportunities. Do not alter PKT-FOREX-043, broaden the search, or open validation, holdout, or PAPER evidence.

## Allowed paths

- `automation/orchestration/work_packets/active/PKT-FOREX-044.md`
- `automation/forex_engine/forex_control_baseline_rsi_filter_comparison_stage1_v1.py`
- `automation/forex_engine/forex_scalping_techniques_v1.py`
- `scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py`
- `tests/forex_engine/test_forex_control_baseline_rsi_filter_comparison_stage1_v1.py`
- `tests/forex_engine/test_forex_scalping_techniques_v1.py`
- `.aios/staging/PKT_FOREX_044/`
- `.aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl`
- `.aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_FINGERPRINT_INDEX_V1.json`
- `automation/orchestration/locks/FILE_LOCK_REGISTRY.json`, only for the exact OCC82 claim/release lifecycle

## Forbidden paths and actions

All other paths are read-only. Do not modify PKT-FOREX-043 or prior scientific evidence. Do not open validation or holdout outcomes. Do not run PAPER, Practice, LIVE, broker, credential, order, or money operations. Do not use network access. Do not add another indicator framework, parameter sweep, or strategy combination. Do not switch branches, reset, stash, clean unrelated work, stage, commit, push, merge, create a PR, deploy, or install packages.

## Frozen scientific contract

- Data: certified native M5 corpus `AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2`, aggregate SHA-256 `44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a`, 58 eligible pairs.
- Development boundary: `2024-01-01T00:00:00Z` inclusive through `2025-04-01T00:00:00Z` exclusive.
- Indicator reference: RSI(14), Wilder initial average gain/loss over the first 14 completed close-to-close changes, then Wilder recursion. No earlier RSI value is valid.
- Baseline: existing Supertrend direction with ATR period 3 and multiplier 2.
- Candidate: identical baseline plus RSI(14) filter; permit long only when RSI is at most 70 and short only when RSI is at least 30.
- Timing: completed candles only; indicators use information available at the signal close; entry occurs on the next M5 candle using side-correct ask for long and bid for short.
- Costs: observed entry/exit bid-ask spread plus fixed per-side slippage stress of `0.1`, `0.5`, and `1.0` pip. Gross is diagnostic only.
- Risk and exit: identical between arms; freeze exact rules in source and receipts before scoring.
- Accounting: record the common opportunity set, selected opportunities, skipped opportunities, executed trades, and results per executed trade and across the common opportunity set.
- Trial budget: exactly 2 outcome-touched configurations. Expected scored-attempt lower bound after canonical registration: 1,294.
- Promotion screen: candidate must have positive BASE and STRESSED net expectancy, BASE profit factor at least 1.10, at least 200 trades, adequate direction/instrument/currency/regime breadth, no material concentration failure, stable period slices, and a positive paired improvement whose uncertainty excludes zero under the preregistered resampling rule. Otherwise retire it without opening later evidence.
- Evidence status: development-only exploratory evidence. It cannot independently confirm an edge.

## Validator chain

1. Verify branch, dirty-state overlap, packet identity, corpus and metadata hashes, canonical memory hashes, and the exact OCC82 lock.
2. Test RSI initialization, Wilder recursion, flat/gain/loss edge cases, completed-candle timing, and future-data invariance against independent examples.
3. Test signal/entry timing, side-correct prices, pip metadata, observed spreads, slippage, matched opportunities, skipped/executed accounting, exits, exposure, and deterministic output with synthetic fixtures.
4. Run the focused PKT-FOREX-044 and RSI tests, then the applicable PKT-FOREX-039 through PKT-FOREX-043 regression chain without weakening or skipping failures.
5. Run two isolated deterministic development screens and require byte-identical artifacts.
6. Register exactly two scored attempts and their fingerprints through append-only research memory; rerun registration to prove idempotency.
7. Verify prior ledger prefix and fingerprints, PKT-039 corrected history, canonical hashes, artifact hashes, scoped diff, and `git diff --check`.
8. Release only OCC82 and verify lock-registry integrity and zero active OCC82 lock.

## Stop point

Stop after the two frozen development configurations are scored once, results and rejection reasons are recorded, deterministic reproduction and relevant regressions pass, exactly two attempts are registered without changing prior history, and OCC82 is released. Do not open validation, holdout, or PAPER evidence. If the candidate survives, return one exact separate approval request for pre-holdout validation. If it fails, preserve the rejection and return one evidence-based next action without expanding this search.

## Final report

Use the mandatory Owner View and APPLY completion or failure report. Include exact rules, calculation proof, corpus identity, costs, common/selected/skipped/executed counts, both arms' results, uncertainty, gate decisions, trial ledger change, deterministic hashes, tests, files changed, lock status, no-commit/no-push, and one safe next action. Do not claim an edge from development-only evidence.

## Execution state

- Status: `MEMORY_REPAIR_COMPLETE_AWAITING_EXECUTION_RULE_FREEZE_NO_SCORING`.
- Verified edge: `FALSE`.
- Validation rows opened: `0`.
- Holdout rows opened: `0`.
- PAPER rows opened: `0`.
- Commit: `NOT_PERFORMED`.
- Push: `NOT_PERFORMED`.

## OCC82 checkpoint — 2026-09-07

- Owner approval received for the original ten-path boundary. Official claim preview returned the exact OCC82 identity with zero collisions, blocks, or review items. Claim succeeded at `2026-09-07T04:35:46.3386317Z` after sandbox filesystem escalation for the official tool's atomic write. No scope was expanded.
- RSI repaired: first value is at index 14 after 14 changes; every following delta is incorporated; flat values return neutral 50; invalid periods and nonfinite closes fail. Historical strategy artifacts are not regenerated.
- RSI focused tests: `21 passed`. Independent arithmetic examples include a period-3 seed and two recursions, a fixed period-14 reference vector, flat/up/down inputs, warm-up, period one, invalid values, and future-data invariance.
- Final scoped regression: `91 passed, 2 failed, 0 skipped, 0 deselected`. Both failures are new synthetic tests proving pre-existing count-pin defects. Report: `.aios/staging/PKT_FOREX_044/tests_occ82_20260907/regression_final.xml`.
- Earlier sandbox run: `78 passed, 14 failed`; protected receipt access caused 13 failures and a Windows long-path fixture issue caused one. Receipt reads were rerun with filesystem approval; the new fixture uses Windows extended path syntax. The following run had `91 passed, 1 failed`; the final run added the second count-pin reproduction. Earlier XML reports are preserved.
- Pytest's cache plugin was disabled intentionally; its existing `cache_dir` configuration produces one warning. Bytecode writes were disabled. Test temporary roots and XML files stayed within the new PKT-044 staging folder.
- Blocker 1: `forex_edge_discovery_tournament_stage1_v1.py:254-256` requires the current global scored count to equal 1292 even after trusted-prefix and append-chain validation passes. The copied ledger with two valid synthetic scored entries has count 1294 and fails `GLOBAL_TRIAL_MEMORY_PRE_SCORE_MISMATCH`.
- Blocker 2: `forex_factor_common_component_momentum_stage0_v1.py:367-368` rejects an idempotent repeat of the completed 36-proposal registration after later scores, with `SCORED_ATTEMPT_LOWER_BOUND_CHANGED`. Its post-registration check also pins 1292. The historical registration tests hard-code current totals.
- Synthetic copies preserve all 263 current historical ledger records and all 115 index entries. Two artificial candidate records are added only to test copies; neither is an experiment or canonical scored attempt.
- Full PKT-038 through PKT-043 chain and actual comparison/reproduction remain pending. Existing Stage-0 runner tests also write into PKT-038/043 staging, which is outside the current PKT-044 output boundary.
- No comparison engine or runner was created. No market, validation, holdout, or PAPER rows were read. Canonical trial increment: `0`; lower bound: `1292`; proposed count: `561`.
- Canonical ledger SHA-256 unchanged: `5101414160c7d803a820786d69818dc575bed549205ef5661a7fb54958248d20`.
- Canonical index SHA-256 unchanged: `6df7c2a7a1b1b301a3f43179542b228eda20492a5094cc486a2ba0195776f078`.
- RSI source SHA-256: before `aecda6b3f0cf8c62b59eb5f7198465d3c6c492fa8b79e2a908dcfd829fe40e88`; after `ac1cd1223eefd426bb0dc5086dc21db2a09f947faba8b73472302a009157ca1c`.
- RSI test SHA-256: before `fceaf74d68be16dbca4a70401b5903b51ca70f963e1fa09c4fab15463f240d42`; after `f087449808e19ec54f1e9dd5a4d273e1ec831ea4bfea13db8783e704d5af5d26`.
- Baseline readback correction: the existing control carries a trailing Supertrend stop forward after each completed candle. The earlier commentary describing a static stop was incorrect and is withdrawn. Exact execution adaptation, holding and rollover rules still require source-level freeze before any scoring; no result exists under either description.
- OCC82: terminal release requested after this checkpoint; registry is authoritative for release confirmation.

## Concrete scope amendment requested — not authorized or executed

Historical request below retained. Anthony approved the bounded memory-repair and evidence-handoff amendment on 2026-09-07. The amendment execution below supersedes this section's pending-authority label, not the frozen scientific specifications.

Keep PKT-FOREX-044, EAST_OCC_82, the same lane and canonical lock ID, the two-configuration budget, and all existing restrictions. Add only these five paths for memory compatibility and necessary tests:

- `automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py`
- `automation/forex_engine/forex_factor_common_component_momentum_stage0_v1.py`
- `tests/forex_engine/test_forex_edge_discovery_tournament_stage1_v1.py`
- `tests/forex_engine/test_forex_edge_validation_pipeline_v1.py`
- `tests/forex_engine/test_forex_factor_common_component_momentum_stage0_v1.py`

Allow new test-only subfolders beneath `.aios/staging/PKT_FOREX_038/` and `.aios/staging/PKT_FOREX_043/` for their existing runner regressions. Preserve all existing files in those roots.

Required repair: distinguish immutable experiment snapshots from current cumulative research memory. Preserve exact trusted historical records, corrected results, candidate identities, and fingerprints. Accept validated later scored records; test subsequent additions beyond 1294, and reject tampering, deletion, reordering, broken chains, duplicate IDs, and identity conflicts. Keep PKT-043's frozen 36 scientific specifications and 18 baselines unchanged. Its repeated registration must preserve the current cumulative count rather than reset it or require the old value. Snapshot tests must use trusted snapshots; current-memory tests must verify append-only invariants. Update source/test hash expectations only for reviewed approved edits and retain trusted artifact hashes.

After approval: re-preview the expanded claim, claim exact OCC82, repair and pass both new failure reproductions plus the complete relevant chain, then resume the already approved two-variant comparison. Release OCC82 at the approved terminal stop or a verified blocker. No additional scoring budget, dataset, network, broker, holdout, or PAPER authority is requested.

## Approved evidence-handoff amendment — 2026-09-07

Status: IN_PROGRESS_NO_MARKET_SCORING. Existing identity/hierarchy retained. Official OCC82 claim at 2026-09-07T05:09:42.8284548Z; zero collisions, policy blocks, or review items. Observed main at b86c65140ed03d53d6c8d6c3618e50da0502f51b; unrelated dirty work preserved. No Python research process found; existing Codex sessions untouched.

This phase authorizes the five memory-repair paths above, plus the existing packet, comparison module/runner/test paths, and `automation/forex_engine/forex_edge_validation_pipeline_v1.py`. New test-only subfolders under PKT_FOREX_038/043 and new synthetic/replay subfolders under PKT_FOREX_044 are allowed. Registry writes are OCC82 lifecycle only. Canonical ledger/index, RSI source/test, all prior scientific artifacts, all other paths, and all raw market data are read-only. No market scoring, canonical registration, validation/holdout access, network, broker, PAPER, Git mutation, deletion, or new controller is authorized in this phase.

Implement current-memory compatibility first; then checked summaries, failure review, memory lookup, bounded evidence-linked proposals, and AWAITING_APPROVAL through existing interfaces. Test valid later scores/proposals, tampering, deletion/reorder, chains/duplicates/identity conflicts, idempotency and partial-state detection. Test cost failure, invalid calculation, inadequate sample, duplicate proposal, missing evidence, near-miss/promotion blocking, contaminated evidence, deterministic routing, recovery and limits. Replay only approved completed PKT042 summaries twice; no event journal or market reads. Full relevant synthetic regression remains required; no skipped/xfail valid failures.

Limits: one worker; zero market trials/spending; 60 minutes per command, 4 GiB process memory, 1 GiB new outputs. One checked transient retry only. Checkpoint and stop at a real blocker. Output root for this execution: `.aios/staging/PKT_FOREX_044/amendment_occ82_20260907/`. Preserve existing files. Source/test hashes may change only for reviewed edits; trusted artifact hashes remain fixed.

Stop after tested compatibility and checked-summary handoff, or a genuine blocker; release OCC82 and verify registry. No scoring follows automatically: exact execution adaptation, holding/rollover rules and original comparison remain pending. Report latest Owner View, exact tests, unchanged memory, zero market reads/trials, evidence paths, resources, and one next action. Do not mark the existing trading-edge goal complete.

## Amendment checkpoint and narrow blocker — 2026-09-07

- Original two synthetic failures reproduced (`before.xml`), then both passed (`repaired_two.xml`). Broader memory regression: 153 passed. Handoff regression: 169 passed. Final regression with the real publisher regression added: **169 passed, 1 failed, 0 skipped, 0 deselected** (`final_regression.xml`). One existing pytest warning: cache_dir option with cache plugin disabled. No valid failure hidden or excluded. Scope was the full selected PKT038/039/040/041/043, PKT044, RSI and indicator regression chain; not unrelated broker/PAPER suites.
- Repaired current count checks while preserving exact historical snapshot checks and trusted corrected prefix/index. Factor registration now validates trusted history and preserves the incoming scored total. Invalid fractional/boolean/negative ledger counters fail. Tests cover 7 later scores and 19 later proposals beyond the two immediate synthetic additions, identity conflicts, partial memory pairs, history damage and idempotency. Historical replay tests now use trusted snapshot inputs, not a reconstructed mutable current index.
- Added a checked-record contract and causal context-join validator in the existing validation module; added the approved PKT044 summary adapter/comparison helper and no-market runner. The runner cannot execute the RSI experiment. It uses existing fingerprint rules, protected memory validation, tournament taxonomy/successor production and factor cards. No separate controller, ledger or approval database was created.
- The summary handoff checks all 72 corrected cells, preserves missing fields explicitly, retains attribution where recorded, distinguishes invalid/no-execution/insufficient evidence/cost destruction, and stops at AWAITING_APPROVAL. Historical taxonomy retained: 30 COST_DESTROYED_EDGE, 30 DEAD, 12 NO_EXECUTION. No inference that whole families are dead. Pooled pip summaries are explicitly not cash/portfolio returns. All 36 successor factor fingerprints already exist; replay registers no new proposal. Synthetic positive cases cannot promote or access data.
- Two real-interface summary replays saved in `replay1/` and `replay2/` under this amendment output root. Both handoff files: 2,238,930 bytes; SHA-256 `2d50a7a2896a99b7be50834e4f66f00dd2199c80bfae25ae4bb69b211b4595dd`. Repeating replay1 returned its existing identical receipt without rewriting it. Partial output is preserved and rejected; recovery uses a fresh output folder and trusted inputs. No canonical shared-write recovery was implemented or claimed.
- Resource evidence before this checkpoint: amendment staging 54 files / 6,131,073 bytes; final synthetic chain 3.63 seconds. No background jobs; no spending. Memory ceiling was not independently sampled; fixed summary input sizes were bounded at 8 MiB each and output limit enforced. The 60-minute/4-GiB limits remain operating limits, not tested scheduler enforcement.
- New genuine blocker: `scripts/forex_delivery/run_forex_factor_common_component_momentum_stage0_v1.py:82-83` still demands a staged count of 1292 before checking whether staged/current bytes are identical. The final failing test calls its real `promote_memory` using copied paths and two valid later scores (1294); it raises STAGED_MEMORY_INVALID. The same wrapper also pins the initial 227-record state for changes and writes ledger/index sequentially. It is outside the approved amendment, was not edited, and must not be used against canonical memory until separately repaired and tested. No canonical publisher call occurred.
- Exact next amendment required: add only `scripts/forex_delivery/run_forex_factor_common_component_momentum_stage0_v1.py` to the existing OCC82 scope for trusted-history validation, lawful-growth/idempotent publishing checks, and fail-closed partial-update handling. Use already approved tests and copy-only output roots; canonical memory remains read-only. Preserve frozen historical artifacts; do not promote staging or score markets. Re-run the final failing test and full chain, release OCC82, and stop for execution-rule/scoring scope review.
- Factory status: PARTIAL, not operational/certified. Implemented/tested first checked-summary connection only. Full reusable market runner, full numeric context producer, automatic canonical memory transaction/recovery, fresh-data acquisition/access, and complete promotion/PAPER path remain unimplemented or unproven here. Near-miss labels alone do not authorize promotion. No new edge evidence exists.
- Current goal preserved without recreation, replacement, or completion. Canonical trials added 0; lower bound 1292; canonical proposals 561. Ledger/index hashes unchanged at `5101414160c7d803a820786d69818dc575bed549205ef5661a7fb54958248d20` / `6df7c2a7a1b1b301a3f43179542b228eda20492a5094cc486a2ba0195776f078`. Both PKT042 trusted manifest hashes unchanged at `9df195ac79f68671b99e54293874974b88fb3574cb681e1c58f7822358c3b191`; RSI source/test unchanged. PKT043 scientific cards/baselines unchanged. Old holdout guard read as metadata only: SPENT_CONTAMINATED, access_count 2. No market/validation/holdout outcomes, broker, credential, PAPER, Git publishing or destructive actions.

Reviewed source/test hashes for resume:

| Path | SHA-256 |
| --- | --- |
| automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py | 75583fd5181cdd5de34d9d9eca13f11c1edcb1141381c96f1fe9bb04f92d4658 |
| automation/forex_engine/forex_factor_common_component_momentum_stage0_v1.py | 92f712e5d719383b96b888363a7c361cb6a71d75db8404009301443174db7665 |
| automation/forex_engine/forex_edge_validation_pipeline_v1.py | eb1f2b2094d563442111b032002231e89f71f60e20d98da52184dabac4165465 |
| automation/forex_engine/forex_control_baseline_rsi_filter_comparison_stage1_v1.py | 85e9071d84af1b3bf4d507fcaa12071a43d7203878300fcc1f793763f14d8fd5 |
| scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py | 9aea1e118a92889ab4df401fc2dbe70580d55c597a60fdbaab707f97de3b128d |
| tests/forex_engine/test_forex_edge_discovery_tournament_stage1_v1.py | 19c1052bb3713217fe9d0c4490bec0d2e9ff656a63f250ccfde1868bde4c43f2 |
| tests/forex_engine/test_forex_edge_validation_pipeline_v1.py | add4758f76743a1fcf6569b996fe708c2e03a171e25ae89b10585da3d4a677aa |
| tests/forex_engine/test_forex_factor_common_component_momentum_stage0_v1.py | eaaf5bb2f7a1feeec6733ad0985c3dc15facdd2f5e083c314bfe84130bd20804 |
| tests/forex_engine/test_forex_control_baseline_rsi_filter_comparison_stage1_v1.py | 7ae6bf808a78462142f19f01fd31e6b69d3f7b822c76a0a9f29a948a1d044f94 |

Official OCC82 release required at this checkpoint; registry readback is authoritative. Unrelated dirty work remains untouched. No commit/push.

## Approved publisher amendment — 2026-09-07

Anthony explicitly approved adding only `scripts/forex_delivery/run_forex_factor_common_component_momentum_stage0_v1.py` to the preceding 14-path scope. Existing tests/output roots and OCC82 identity/lifecycle remain unchanged. Fresh preview returned the exact lock, 15 paths, zero collisions/blocks/review items; claim succeeded. Repository remains main at b86c65140ed03d53d6c8d6c3618e50da0502f51b. No Python research process found. Canonical memory remains read-only; publishing tests redirect both destinations into isolated copies. No market scoring or scope expansion.

Publisher before SHA-256: `7802cd79e6d18d0b41c686e181927a894092b0ddda719b9758bb0e2af1f56391`. Ledger/index baseline hashes remain those above. Repair must verify exact frozen registration against trusted history rather than pin future counts, reject unapproved staged changes, preserve prior entries, and detect partial publication. Save trusted before/target identities in new test-only publication evidence directories; never automatically overwrite damaged canonical state. Stop after validation and release OCC82. Original strategy execution-rule freeze remains a later boundary.

## Publisher repair completion — 2026-09-07

- Approved publisher repair is complete. All previously reproduced memory compatibility failures pass. Final relevant regression: **177 passed, 0 failed, 0 skipped, 0 deselected**, 4.57 seconds, one existing cache_dir warning because pytest's cache plugin is disabled. Receipt: `.aios/staging/PKT_FOREX_044/amendment_occ82_20260907/publisher_final_regression.xml`. The intermediate publisher test exposed index-sort differences during an identical-file no-op; fixed by preserving valid identical bytes after trusted-history validation, not rewriting them to sort later additions. Intermediate reports retained.
- Publisher no longer pins the current global count or current history length. It reconstructs the exact allowed 36-card registration from trusted history and accepts only that result, or a validated identical-file no-op. Scores cannot be added through this Stage-0 publisher. Historical entries, candidate definitions, dispositions, and earlier research stay protected. Test copies verify first registration after 0 or 7 later scores, repeated registration after growth, arbitrary score/tamper/deletion rejection, and no extra publication on repeat.
- Changed publication takes an exclusive nonblocking ledger lock and rechecks both current files before writing. It saves and flushes before-ledger/index copies plus before/target hashes in a new `memory_publication_` directory under the supplied staged source. Both destination files are NOT claimed jointly atomic. An injected failure between writes preserves recovery evidence, raises a recovery-required error, and a repeat rejects the inconsistent pair without overwriting it. A concurrent-writer test leaves both copies unchanged. Recovery is explicit from checked saved before/target evidence; no automatic rollback or blind retry is authorized.
- Files changed in this follow-up: the newly authorized publisher, existing PKT044 comparison test, this packet, OCC82 registry lifecycle, and new approved test outputs. No other source/test edits. Publisher final SHA-256 `45791aeaab2fb23c1146316e6f1dc55106b13a72cad50873b59ccae71f969265`; comparison-test final SHA-256 `8235095d8f28a614318c97dd1efff790ddb3607f67c8b9e42ac8e6babf085593`. These supersede their earlier checkpoint hashes; other source/test hashes remain unchanged.
- Canonical ledger/index hashes still `5101414160c7d803a820786d69818dc575bed549205ef5661a7fb54958248d20` / `6df7c2a7a1b1b301a3f43179542b228eda20492a5094cc486a2ba0195776f078`. New canonical trials/proposals 0; scored lower bound 1292. No canonical publishing, price reads, validation/holdout outcomes, broker/credentials, PAPER, commit/push, or destructive actions. Existing goal unchanged. Branch/HEAD unchanged; unrelated dirty work preserved.
- Output measurement after final tests: amendment root 113 files / 8,214,524 bytes, including preceding amendment evidence; below the approved storage limit. Bytecode/cache disabled, test temp fixtures confined to approved roots. No background jobs or spending. Scoped diff whitespace check passed; tests imported/executed the changed code.
- Current stop: memory/publisher amendment complete, factory still PARTIAL. PKT044 market comparison is not implemented/scored; exact execution adaptation, holding/rollover rules and scoring authority review remain pending. Do not label repair or synthetic handoff as a verified edge or factory completion. Release only OCC82 using the official tool and verify zero active locks. No additional file amendment is needed for this repair.

## Approved build-and-launch amendment — 2026-09-07

Anthony explicitly approved completing execution rules, building/testing the connected workflow, and launching one foreground A/B development batch. This supersedes prior repair-only/no-scoring stop points, not historical evidence. Identity, hierarchy, branch and lock remain unchanged. OCC82 fresh official preview: zero collisions, blocks or review items; 26 paths. Claim created 2026-09-07T05:56:25.0805229Z, expires 2026-09-07T11:56:25.0805229Z. Native goal remains blocked; no native resume control is exposed. Continue this approved turn without replacing or marking that goal resumed/complete.

Exact allowed paths (all other writes forbidden):

- `automation/orchestration/work_packets/active/PKT-FOREX-044.md`
- `automation/forex_engine/forex_scalping_techniques_v1.py`
- `automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py`
- `automation/forex_engine/forex_factor_common_component_momentum_stage0_v1.py`
- `automation/forex_engine/forex_edge_validation_pipeline_v1.py`
- `automation/forex_engine/forex_control_baseline_rsi_filter_comparison_stage1_v1.py`
- `automation/forex_engine/forex_high_throughput_edge_factory_v1.py`
- `automation/forex_engine/forex_edge_existence_controller_v1.py`
- `scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py`
- `scripts/forex_delivery/run_forex_factor_common_component_momentum_stage0_v1.py`
- `scripts/forex_delivery/run_forex_high_throughput_edge_factory_v1.py`
- `tests/forex_engine/test_forex_scalping_techniques_v1.py`
- `tests/forex_engine/test_forex_edge_discovery_tournament_stage1_v1.py`
- `tests/forex_engine/test_forex_factor_common_component_momentum_stage0_v1.py`
- `tests/forex_engine/test_forex_edge_validation_pipeline_v1.py`
- `tests/forex_engine/test_forex_control_baseline_rsi_filter_comparison_stage1_v1.py`
- `tests/forex_engine/test_forex_high_throughput_edge_factory_v1.py`
- `tests/forex_engine/test_forex_edge_existence_controller_v1.py`
- `automation/forex_engine/edge_research/`
- `tests/forex_engine/edge_research/`
- `.aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl`
- `.aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_FINGERPRINT_INDEX_V1.json`
- `.aios/staging/PKT_FOREX_044/`
- `.aios/staging/PKT_FOREX_038/`
- `.aios/staging/PKT_FOREX_043/`
- `automation/orchestration/locks/FILE_LOCK_REGISTRY.json`

Memory writes only through the checked publisher; registry only official OCC82 lifecycle. Preserve all previous outputs; use new run/test directories. Existing 177-pass receipt and canonical ledger/index hashes verified unchanged before edits. One worker and scoring process; two new economic specifications maximum, one numerical reproduction, at most three new unscored proposals, six hours foreground, 4 GiB memory, stricter existing 1 GiB output limit. No spending, background service, broker/credentials/trading, protected validation/holdout outcomes, Git mutation or cleanup.

Ordered execution checklist (unchecked items are not ready):

- [x] Read current checkpoint, goal, authority/maps, branch/HEAD/worktrees, dirty state, processes, ownership and resources; preserve unrelated work.
- [x] Preview exact paths and claim OCC82 with zero conflicts.
- [ ] Remove metadata-only caller's access to the price-bearing replay cache; verify trusted PKT042 metadata receipt instead.
- [ ] Freeze complete two-arm rules, dataset/metadata identities, execution ordering, DST-aware no-financing schedule, risk, opportunity accounting, attribution, selector, budgets and fingerprints before outcomes.
- [ ] Implement actual checked development reader -> shared features -> separate A/B simulation -> checked results/uncertainty/attribution -> post-mortem -> memory lookup/duplicate check -> bounded next action through existing ownership.
- [ ] Prove indicator/timing/cost/stop/gap/rollover/boundary/portfolio correctness with independent synthetic examples and future-data invariance.
- [ ] Prove memory growth, partial publication, recovery, duplicate completion, permission/resource stops and two synthetic cycles; pass applicable regression without hiding failures.
- [ ] Launch explicit foreground market mode; durably record first outcome access, exactly A/B; preserve progress and protected-period exclusion evidence.
- [ ] Independently reproduce numerical results in a separate new folder and compare scientific artifacts.
- [ ] Automatically complete checked post-mortem, attribution, duplicate check and next-action selection; publish authorized memory once.
- [ ] Verify actual status/resume interfaces, terminal budget stop and all launch acceptance items; release only OCC82 and verify registry.

Stop only at a genuine ownership/authority/data/calculation/resource/platform block or after the complete approved batch. A helper or test report is not the launch milestone. If blocked, preserve valid progress and record exact remaining acceptance items. No factory or independently validated edge claim without evidence.

## Build-and-launch checkpoint — FACTORY_LAUNCH_BLOCKED — 2026-09-07

Actual native goal remains blocked and unchanged. Branch/HEAD unchanged. Built scoped implementation, but did NOT launch or certify the factory. No executable scientific freeze or passing-test launch receipt was produced. The current helpers remain work in progress, not approved market evidence.

Implemented within approved paths:

- Replaced price-bearing replay-cache metadata reads in the tournament and factory with the exact trusted PKT042 metadata-only receipt. Verified 58 instruments, including exceptional pip sizes. Development manifest preflight found 870 shards, no missing files or size mismatches; 5,364,708 declared rows / 191,801,734 compressed bytes. This was metadata/stat-only, not scoring.
- Added shared completed-M5 feature snapshots reusing Supertrend/ATR, repaired RSI and EMA. Includes candle structure, MACD, Bollinger context, causal confirmed pivots, session/spread and explicitly labelled activity. ADX startup and unobserved quote path/traded volume remain unavailable, not fabricated.
- Added proposed fixed A/B execution adaptation, stop/gap/trailing timing, 16:30 New York exit / 16:00–17:15 no-entry with tested US DST transitions, midnight development-end handling, cost ceiling, side-correct costs and separate portfolio lifecycles. Gross is a midpoint shadow path; do not call its difference an exact same-time spread measurement.
- Connected explicit controller -> factory -> batch -> calculation -> checked handoff interfaces. Kept the existing default summary CLI no-market. Added run-batch/status/resume/review parsing. CLI --help succeeds; real market run/status/resume were NOT executed.
- Reused the existing publisher transaction kernel; saved before/target pairs for explicit recovery. Added bounded A/B publication preparation and idempotency checks. Synthetic test exposed an orphan ledger/index case; it now fails instead of silently filling the gap. Canonical publisher was NOT called.
- Added 31 synthetic tests. They cover reference arithmetic, initialization/timing/future invariance, stop/gap/calendar behavior, cash conversion, independent A/B position selection, checked small-sample handoff, duplicate publication, actual batch-function execution on synthetic inputs, completed-run resume and artifact tampering. This is NOT the full requested interruption/resource/permission suite; finish those remaining checks after resolving the blocker.

Final applicable regression: **228 passed, 2 failed, 0 skipped, 0 deselected**, 7.30 seconds. One existing cache_dir warning with the cache plugin disabled. XML: `.aios/staging/PKT_FOREX_044/amendment_occ82_20260907/launch_regression1.xml`, SHA-256 `ef6fea1c78f6d479351f002b2df9124f05d184371909881cb15c774804c2251c`. Earlier 177-pass receipt remains intact. The first execution-fixture failure was an incomplete synthetic second trade; fixture now includes its stop. No failure was hidden or excluded.

**Verified authority blocker:** `automation/forex_engine/forex_edge_discovery_tournament_stage0_v1.py:497`, `research_memory`, raises `PKT037_SOURCE_CHANGED`. Its `PRIOR_SOURCE_HASHES` binds the current factory source, runner and test to old PKT037 hashes. All three current files are legitimately changed under this amendment. The two failing tests are `test_memory_preserves_pkt037_and_adds_zero_scored_trials` and `test_build_and_runner_are_deterministic_and_isolated`. The Stage-0 module and its test are outside this approved write boundary and were not edited. Its runner was inspected: no independent source-hash pin or required wrapper edit was found.

**Protected-access exception discovered in the same Stage-0 dependency:** `information_provenance` rehashes `.aios/runtime/forex_feature_edge_research_v2/currency_factor_table.json`, whose declared data extends to 2026-08-28, and parses the old `AIOS_FOREX_EDGE_RESEARCH_V1_STATE.json` / `AIOS_FOREX_FEATURE_EDGE_RESEARCH_V2_STATE.json` reports containing validation/holdout summaries. The broad regression ran that existing path before this defect was identified. No raw validation/holdout shards were parsed, and these old outcomes were not used to choose new parameters, but strict zero protected-data access cannot be claimed. Do not rerun this path unchanged. Replace it with trusted metadata-only provenance evidence, preserving the spent/contaminated classification; add tests denying price-bearing caches and outcome-report access. Hashing protected price-bearing files is still access.

One consolidated required scope addition, not yet approved:

- `automation/forex_engine/forex_edge_discovery_tournament_stage0_v1.py`
- `tests/forex_engine/test_forex_edge_discovery_tournament_stage0_v1.py`

Purpose: separate trusted historical source/snapshot verification from approved current implementation versions, and repair metadata-only provenance access. Preserve original hashes, historical packets/artifacts, legacy trial accounting and all outcomes; do not merely replace old source hashes or remove integrity checks. No changes to PKT037/038 packets, old scientific artifacts, or the Stage-0 runner are requested. Continue the already approved PKT044 build/test/launch only after these repairs and all remaining launch checks pass; do not request the same existing scoring budget again.

Canonical ledger/index still match `5101414160c7d803a820786d69818dc575bed549205ef5661a7fb54958248d20` / `6df7c2a7a1b1b301a3f43179542b228eda20492a5094cc486a2ba0195776f078`. New scored configurations 0; lower bound 1292; new proposals 0; cumulative proposed count 561. No A/B results, independent reproduction, canonical publication, broker/credentials/orders, commit/push or destructive action. Existing 36 factor proposals and 18 baselines unchanged.

Files changed this execution: this packet; tournament Stage1 source; existing factory and controller sources; comparison, factor-publisher and factory runners; validation-pipeline and factory tests; four new `edge_research` helpers (`features.py`, `execution.py`, `research.py`, `batch.py`); three new tests (`test_features.py`, `test_execution.py`, `test_batch.py`); approved new test/checkpoint outputs; OCC82 registry lifecycle. Other previously dirty files remain unrelated and preserved. Existing RSI/factor/validation/comparison calculations outside these listed edits were not changed.

Key current hashes: tournament source `37cf2662b8a169fa7a8a13647d1c19e39ebe16261cea3d26161ee1c986fc39c5`; factory `11a66f2a3512b38ab3095aa25b46ba9fe5cc53155fd4fcd9411eedcebc85065c`; controller `e0f4caa4b8e7178e3987d3bdee770adf8b17ee99ec602de031b8cae7672909da`; comparison runner `2436380b94160c6c48a116253928a773c716c0d9e93f796866c7cb39266d56ec`; publisher `48a8c4a8eec5994c4349dccc8839d3e0ea5feda6936e5493f6b228582fc17b5c`; batch helper `540b7b8ae412d6a40ccdf17e222b8a879017f3b238b275f2fb97e0a1e3bd8c8b`. Updated tournament source pin in the authorized validation test only after review; trusted historical artifact pins remain unchanged.

Resume evidence: `.aios/staging/PKT_FOREX_044/amendment_occ82_20260907/launch_blocker_checkpoint.json`. Measured amendment folder before this checkpoint: 135 files / 9,001,543 bytes, including earlier work. No background process launched; no Python process remained at final inspection. Full peak memory was not sampled by the regression command; no market resource-use claim is made. Whitespace check passed. A read-only attempt to inspect the lock validator under `locks/` found no file; its actual location is `validators/`, to be used for final integrity readback.

Official OCC82 release preview returned READY_TO_RELEASE with one exact match and no review items. Release follows this checkpoint; final lock registry/readback is authoritative. Stop now for the two-path owner amendment, not at a claimed launch milestone.

## Approved two-file continuation — 2026-09-07

Anthony approved adding only tournament Stage0 source and its test to the existing 26-path build-and-launch boundary. Official OCC82 preview returned 28 paths, zero collisions, policy blocks or review items; claim succeeded at 06:48:00Z. Same branch/HEAD, worker, lane, hierarchy, two-configuration budget, development-only boundary and safety limits apply. No Python research process or competing active lock was found. The coordination skill marker is absent; no secondary board was initialized. Resume existing helpers; do not duplicate the job. Existing native goal remains blocked with no exposed native resume control.

The prior checkpoint remains immutable at SHA-256 `1c0d1b453f73ab89db8896008d82e86155e75a04d1c56c86427745cb304f01f5`. Its access incident is preserved: `information_provenance` hashed the named later-period derived cache, then parsed both named historical outcome reports during `test_information_provenance_is_truthful_and_zero_row`. The failing build test stops in research_memory before provenance; logs do not establish any additional exact access count. Cache prices were not parsed by that function; report validation/holdout summary objects were read and included in its return. No new A/B parameter choice or score followed. Independent claims on these reused/contaminated periods remain blocked. This is not a zero-protected-access job; subsequent clean runs must be reported separately.

Repair uses the saved incident and holdout access guard only, retains historical hash declarations without reopening their protected targets, and validates current source against the previously reviewed checkpoint versions. Missing metadata and unexplained source changes fail closed. Original historical completion/source identities remain protected. Remaining launch checklist above is still binding. Prior foreground build claim consumed 2,377 seconds; budget must carry that usage forward, not restart. Prior 1-GiB output ceiling remains stricter than the later 4-GiB allowance. Stop after the actual approved batch or a genuine blocker, not after this repair.

## Reviewed executable version and prelaunch gate — 2026-09-07

The two original failures now pass. Full applicable regression after the repair: 237 passed; after recovery/resource/boundary additions: 244 passed; after exercising the actual publisher wrapper on isolated trusted copies: **245 passed, 0 failed, 0 skipped, 0 deselected**, 7.79 seconds. The same pre-open audit hook denied protected caches and the named validation/holdout reports across each full run. Only the existing disabled-cache config warning remains. Earlier receipts are preserved. Current proof: `launch_preflight_regression3.xml` and `launch_test_receipt.json` under the amendment root. The latter records every executable source hash before real outcomes. Changes after that identity must fail launch/resume. Canonical ledger/index remain at their prior hashes and lower bound 1292 before launch.

Reviewed current Stage0 source separates historical identities from explicit reviewed PKT044 identities; trusted PKT037 completion still matches its original hash. Source tamper, missing provenance and protected content denial are tested. Current provenance checks read only the hash-pinned original incident checkpoint and metadata-only holdout guard. The old access incident is not removed or made independent by this repair.

Execution freeze uses `research.specifications`: exact 58-pair A/B, ATR3 multiplier2, existing tested Supertrend initialization/rounding and two-close confirmation, Wilder RSI14 only in B, contiguous next-open entry, confirmation-band stop, monotonic close-updated trailing, gap-stop before scheduled/opposite exits before intrabar stop, no take-profit, at most 288 bars, fixed 16:30 New York pre-financing exit and 16:00–17:15 no-entry window with DST, fixed 23:55Z last-development exit and last-ten-minute no-entry. Unresolved open-position gaps or missing conversion quotes invalidate the batch. No outcome-dependent exclusion or calendar rewrite is permitted. Gross uses an explicitly separate midpoint shadow path; it is not an exact spread decomposition. Slippage scenarios, current-open BASE cost ceiling, USD conversions, separate capital-limited portfolios and all risk limits remain as approved. Additional context does not affect A/B decisions.

The original 05:56:25Z claim's six-hour ceiling is enforced as an absolute 11:56:25Z deadline, conservatively counting owner-wait time too. Resume cannot reset it. Storage checks count the entire PKT044 staging root, including earlier outputs. Prelaunch free resources: 14,490,376 KiB RAM and 1,382,622,244,864 disk bytes. RAM cap 4 GiB; output cap 1 GiB. No new background process or spending.

The tested real publisher wrapper adds exactly two OUTCOME_EXAMINED events on copies, preserves the original bytes as a prefix, and returns unchanged on repeat. Tests cover interrupted two-run resume, no repeated trial, missing permission, memory/time/storage stops, blocked blind retries, immutable artifact tampering and prior partial ledger/index failure handling. The actual factory/controller interfaces remain in the execution path. Synthetic replay is not counted as a real launch. Promotion checks lacking required independent/statistical inputs remain explicitly unevaluated and cannot PASS. The next step is the approved foreground batch, not a new strategy search.

## Actual launch attempt — verified data blocker — 2026-09-07

FACTORY_LAUNCH_BLOCKED. The actual `run-batch` CLI routed through controller -> factory -> batch at 06:58:25Z. Contract saved before outcomes: `.aios/staging/PKT_FOREX_044/first_launch_occ82_20260907/contract.json`, SHA-256 `b215c8dfb6eb030cda3dcd025661e95070d7313bb7943fe36dcfeb16caadc7ab`. Full launch command is recorded in `invalid_test.json`. The tested source identity and all A/B rules were unchanged during launch.

The checked publisher durably added exactly two OUTCOME_EXAMINED events before feature/strategy evaluation. The first pair, AUD_CAD, loaded 92,958 development rows from 15 hash-verified permitted monthly shards. Processing then raised `UNRESOLVED_OPEN_POSITION_PRICE_GAP` in the midpoint shadow diagnostic. Process exit 1; elapsed batch time 3.109 seconds; zero complete pairs, zero complete scientific results, no run2 reproduction. The progress field completed=1/total=2 denotes RUN_START number, NOT a completed pair or configuration. Observed working-memory sample was 32,342,016 bytes before calculation; it is not a measured full-process peak.

One timestamp-only gap inspection and one bounded exact-failure diagnosis used the same authorized AUD_CAD development reader. No new configuration, profitability comparison, or full batch retry occurred. Failure: LONG event at 2024-09-02T14:50:00Z, entry 14:55Z; midpoint path crosses from 17:35Z to 17:45Z, missing the 17:40Z M5 interval. September shard: `partitions/AUD_CAD/2024-09.jsonl.gz`, SHA-256 `843065819ee88bf9f40f5e4c7f82874d35a79555e42f00229a347a6c34958265`, 6,075 records. Certification identity passes but does not prove continuous executable coverage. No protected-period shards or caches were opened in this continuation. Prior incident remains explicitly preserved above.

Invalid evidence/post-mortem: `first_launch_occ82_20260907/invalid_test.json`, SHA-256 `2445b09d5daaba75b82ac1262c1797e090648d54a04adb745c245731b9537957`. Both candidates are incomplete INVALID_TEST, not economically rejected. A/B net results, original opportunity totals, executed totals, matched delta and attribution are unknown, not zero. No conclusion about RSI or Supertrend profitability follows. The existing checked transport currently requires integer opportunity/trade counts, so this invalid run cannot be represented there honestly using unknown counts. The saved invalid report does not falsely claim a complete automatic checked-result handoff. Selected next action: REPAIR_MEASUREMENT; descendants and promotion blocked; no new proposals registered.

Authorized recovery used the existing checked publisher to append two INVALID_TEST dispositions with zero extra scored increments; receipt `invalid_publication.json`. Total ledger records 267; scored-attempt lower bound 1294; proposals 561; fingerprint entries 117. The original 263-record ledger bytes remain an exact prefix and the original 115 index entries remain unchanged and in the same order. Final ledger SHA-256 `822e9a2717add13cf8fcdd2e44b681f12bc1b973af42c80dfa7515ba5c72f46e`; index SHA-256 `067c7102298bb3b57f08242ae3cfd6ac552425891adbe9c51e73bff01d777d59`. Before/target recovery copies and intent receipts are preserved in the batch's publication directories. The original 36 factor proposals and 18 baselines remain unchanged. No additional score is justified by a retry, correction, or reproduction of these same specifications.

Post-publication regression exposed one real no-op defect: factor registration sorted later fingerprint entries even when adding nothing. Fixed only that branch in the already-authorized factor module: completed registration preserves existing entry order; historical first-registration sorting stays unchanged. Final factor source SHA-256 `bd48e5930fa466cb4a041b7191061a957e63f7d0d8f0c46e0172f83bcc8d1460`. No canonical memory write followed this repair. The publisher wrapper test now uses immutable trusted pre-launch fixtures instead of assuming current research memory lacks PKT044. It also verifies INVALID_TEST repeat publication is idempotent on copies. Final regression: **245 passed, 0 failed, 0 skipped, 0 deselected**, 7.96 seconds. Receipt `amendment_occ82_20260907/post_launch_memory_final.xml`, SHA-256 `95d1933c895952b28ee98d0ff1598fdbe572f586f5c7a39887b6444bab6e7f85`. Intermediate 244-pass/1-fail receipt remains preserved. No valid failure excluded.

Actual status command succeeds without price access. Actual resume command rejects the diagnosed BLOCKED checkpoint with `BLOCKED_BATCH_REQUIRES_DIAGNOSIS_NOT_BLIND_RETRY` before outcomes; this was a refusal check, not a market retry. Do not overwrite this run or its freeze. Commands (under Python bytecode-disabled environment):

`python -B scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py status --output-root .aios/staging/PKT_FOREX_044/first_launch_occ82_20260907`

`python -B scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py resume --output-root .aios/staging/PKT_FOREX_044/first_launch_occ82_20260907 --approve-pkt044-launch`

The second command is NOT a recommended next action; it correctly refuses. No numerical reproduction receipt exists. Launch acceptance is incomplete: full A/B processing, reproduction, automatic attribution/post-mortem/next-proposal handoff and successful batch termination are blocked. Synthetic PASS cannot substitute. Goal remains native blocked, unchanged and not achieved. No Python process remained at inspection; no detached process, spending, broker/credential/order/PAPER/LIVE access, commit or push. Observed PKT044 staging total 6,752,608 bytes before this final packet update. Original resource budget was not reset.

Files changed in this continuation: this packet; tournament Stage0 source/test; factor Stage0 source (no-op repair only); edge_research execution/research/batch helpers and execution/batch tests; authorized new receipts/test outputs; the two canonical memory files through the publisher; OCC82 registry lifecycle. Existing other dirty changes are preserved. No frozen dataset, historical scientific artifact, or strategy rule was edited after scoring.

## One requested measurement-availability amendment

Owner decision required because outcome access has occurred and the saved contract makes a missing diagnostic path fatal. Do not silently loosen it. Proposed correction: missing midpoint-only diagnostic paths produce explicitly unavailable gross metrics and coverage counts, never invented prices, zero returns, dropped opportunities, or gross-based PASS; executable net-path gaps remain fatal. Invalid checked records must support unknown counts without pretending no trades occurred. Keep every A/B trading rule, signal, stop, cost, risk, pair and date fixed. Preserve the invalid attempt and its two trial identities. A corrected run requires a separately saved measurement-version contract and tested correction/resume path; never overwrite the original run or count a correction as a new economic strategy. Remaining original time/storage budget still applies; if exhausted, stop without launching.

Exact requested write boundary is a subset of the existing approval: this PKT044 packet; `automation/forex_engine/edge_research/`; `tests/forex_engine/edge_research/`; `automation/forex_engine/forex_edge_validation_pipeline_v1.py`; `tests/forex_engine/test_forex_edge_validation_pipeline_v1.py`; `automation/forex_engine/forex_control_baseline_rsi_filter_comparison_stage1_v1.py`; `tests/forex_engine/test_forex_control_baseline_rsi_filter_comparison_stage1_v1.py`; `scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py`; `scripts/forex_delivery/run_forex_factor_common_component_momentum_stage0_v1.py`; the existing canonical ledger/index through that checked publisher only; new outputs under PKT_FOREX_044 and new test-only subfolders under PKT_FOREX_038/043; registry for the same OCC82 lifecycle only. All other paths read-only; no dataset edit/acquisition, protected evidence, new economic configurations or trading. First test unknown-count transport, unavailable diagnostics, strict executable-path rejection, unchanged opportunity population, correction lineage, idempotent publication and actual recovery commands, then full regression. Any same-specification continuation must retain the original two-score budget and complete at most the single authorized reproduction. Stop at successful bounded batch or a specific unresolved executable-data/resource block. Release OCC82 in either case.

Approval sentence: I approve the PKT-FOREX-044 measurement-availability amendment exactly as recorded here, using EAST_OCC_82 and LOCK_EAST_FOREX_CONTROL_BASELINE_RSI_FILTER_COMPARISON_STAGE1_OCC82, preserving the invalid attempt, unchanged trading rules and original remaining budgets, with no new strategy specifications, fabricated data, protected-data access or trading.

## Measurement-availability amendment approved and resumed — 2026-09-07

Anthony explicitly approved the preceding exact amendment. Current observed branch/HEAD unchanged; no Python worker, zero active locks before claim. Official preview and claim used the exact same OCC82 identity, 15 recorded paths, zero collisions/policy blocks/review items. Native goal remains blocked without exposed resume control; no goal replacement. Optional coordination board absent; no second board or worker created. This amendment changes measurement availability only: unknown midpoint diagnostics cannot erase opportunities or become zero returns, and missing executable paths remain fatal. Preserve original contract/invalid evidence by their pinned hashes; corrective events refer to the original trial and add zero economic specifications. New output directories only. Original 11:56:25Z deadline and 1-GiB total output ceiling remain, not reset. Required chain: synthetic missing-diagnostic versus executable-gap tests; unknown invalid counts; checked invalid handoff; immutable parent/correction lineage; publisher idempotency and recovery; full regression; explicit corrective batch; reproduction if valid; checked publication/review; release OCC82 at success or genuine blocker. No protected data, broker, credentials, orders or Git publishing.

Pre-outcome correction review: 253 passed, zero failed/skipped/deselected, 8.62 seconds in `amendment_occ82_20260907/measurement_regression2.xml` (SHA-256 `05863249d5a715519998e567fa791dbef3d5b1a00adca22b0f60f6ab9eb818da`). `measurement_test_receipt.json` records the reviewed executable hashes and unchanged original ledger/index/contract/invalid hashes. Actual publisher tests on copies prove zero-count corrective outcome/invalid events, original prefix preservation, unchanged index and repeat idempotency. The actual factory invalid branch produces checked unknown-count records, blocks descendants and selects REPAIR_MEASUREMENT. Missing midpoint diagnostics remain null; no whole-population gross estimate is reported from only the available subset. Net executable gaps remain fatal; unrelated calculation errors are not swallowed. Economic cards must exactly equal the trusted original contract.

Corrective launch command: `python -B scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py correct-batch --output-root .aios/staging/PKT_FOREX_044/measurement_r1_occ82_20260907 --approve-pkt044-launch --test-receipt .aios/staging/PKT_FOREX_044/amendment_occ82_20260907/measurement_test_receipt.json`. Run with bytecode disabled, packet-scoped TEMP/TMP and the same pre-open protected-content denial hook as regression. New output path verified absent; OCC82 is the only active lock with no collision. This is the authorized measurement correction, not a third economic specification or a reset of original budgets.

## Corrective execution stopped on an executable-data gap — 2026-09-07

FACTORY_LAUNCH_BLOCKED. Actual correction contract SHA-256 `14342fe487d7b70e2b7b387a697f08a74327c4ba91487f03b739af04e1fa8aeb`; both cards exactly match the original frozen A/B contract. The authorized AUD_CAD midpoint-only missing diagnostic no longer stops execution or causes price invention. Eight pairs completed opportunity preparation: AUD_CAD, AUD_CHF, AUD_HKD, AUD_JPY, AUD_NZD, AUD_SGD, AUD_USD, CAD_CHF; accumulated 38,333 original opportunities before the ninth pair failed. This is NOT eight completed portfolio evaluations or 38,333 executed trades.

CAD_HKD raises `UNRESOLVED_OPEN_POSITION_PRICE_GAP` with `midpoint=false`. Saved entry is 2024-05-20T09:25:00-04:00 (13:25Z); last available candle 10:20-04:00 (14:20Z), next candle 13:20-04:00 (17:20Z). The required M5 grid between these observations has 35 absent intervals, 14:25Z through 17:15Z inclusive. The checked reader appends all validated development records and does not silently filter dates or prices. No additional raw-price diagnosis or data rewrite followed this failure. Whether another authoritative local source can supply the missing observations is not established. Filling/interpolating prices, ignoring the gap, removing the trade/pair/date or changing risk rules is not authorized.

Process exited 1 after 39.344 batch seconds; no numerical reproduction started because run1 was incomplete. Last sampled working-memory high-water 695,599,104 bytes, not a continuously measured process peak. Original absolute deadline and output cap unchanged. Current accessible PKT044 output scan: 5,166,704 bytes before terminal receipt; no cleanup/deletion command performed. No Python process remained at inspection. No valid A/B net result, matched delta, portfolio return, concentration result or gross estimate exists; all remain unknown. This is invalid evidence, not rejection of either indicator's economics.

The actual exception path now automatically saved checked INVALID records, unknown counts, specific failure details, research-memory lookup, post-mortem, blocked descendants, zero proposals and selected REPAIR_MEASUREMENT / AWAITING_APPROVAL. Evidence: `measurement_r1_occ82_20260907/invalid_test.json`, SHA-256 `86c7930eb438d8bd94b6d5119b4e81cc2d29d1e75dd69c978aeb99d441aaf0a4`; publication receipt SHA-256 `1483d2040e33ed6b08b7e6f1aefc916aa8700bc8b458b3ad13a1892eef4d00dd`. This proves the invalid-run handoff, not a successful research launch or a profitable edge.

Publisher appended two corrective OUTCOME_EXAMINED events and two corrective INVALID_TEST events, each `scored_trial_increment=0`, linked to original trial and invalid events. Ledger 271 records; lower bound **1294 unchanged**; unscored proposals 561 unchanged; index 117 entries unchanged, including PKT043's 36 entries. Original 267-record ledger bytes remain exact prefix SHA-256 `822e9a2717add13cf8fcdd2e44b681f12bc1b973af42c80dfa7515ba5c72f46e`; final ledger SHA-256 `a347e88dc71db5a84cd6b8247dec075f42cb864fbd02bb02da7b5661cd22213b`; index retains `067c7102298bb3b57f08242ae3cfd6ac552425891adbe9c51e73bff01d777d59`. Original first-launch contract and invalid report retain their pinned hashes. Reviewed executable code is unchanged since the correction freeze. No registration or correction resets trial history.

Post-publication full regression: **253 passed, zero failed/skipped/deselected**, 7.31 seconds; only the disabled-cache configuration warning. Receipt `amendment_occ82_20260907/measurement_post_run_regression.xml`, SHA-256 `082906b458f352904b65cf7e6b576e7f23520fb4d9d3c351647e6361aff95a70`. Tests include actual isolated correction publisher idempotency, invalid handoff, strict executable-gap failure and synthetic blocked resume. Current actual `status --output-root .aios/staging/PKT_FOREX_044/measurement_r1_occ82_20260907` succeeds. Actual resume refusal check could not complete: sandbox denied stat of the trusted PKT042 metadata receipt, then platform review rejected escalation because resume could access protected metadata or continue execution. That decision was not bypassed or retried indirectly. Do not claim the actual corrective resume command was verified. No market retry occurred.

Protected-access statement: the earlier later-period-cache hashing and validation/holdout-summary incident remains preserved above. Subsequent correction/regression used the development-only reader and pre-open denial hook; no new protected outcome access was observed. Trusted instrument metadata is distinct from market outcomes; the denied resume metadata access is separately recorded. No claim that the entire job had zero protected access. Goal remains native BLOCKED and unchanged; no exposed native resume control. No broker, credentials, orders, paper/live, money, commit or push.

Changed this measurement continuation: execution/research/batch helpers; their execution/batch tests; validation unknown-count check; comparison CLI corrective mode; existing checked publisher corrective lineage; this packet; approved test/run outputs; ledger via publisher; OCC82 lifecycle. Index bytes did not change. Other existing dirty work preserved. The previous two-file provenance repair was not repeated.

## One next approval request: development-data availability audit only

Purpose: identify all development timestamp gaps once, including CAD_HKD's 35 missing intervals, and establish whether existing authoritative local evidence can repair them without fabrication or changing the experiment. This is not permission to ignore gaps or rerun scoring. Retain PKT044 / EAST_OCC_82 / existing lane and exact OCC82 lock, fresh collision preview required. Allowed writes only this packet, new files beneath `.aios/staging/PKT_FOREX_044/development_gap_audit/`, and the official OCC82 registry lifecycle. All source, tests, datasets and canonical research memory remain read-only. Reads: approved metadata and only the 58-pair development shards from 2024-01-01 inclusive to 2025-04-01 exclusive under `.aios/runtime/forex_m5_immutable_corpus_v2/`; examine timestamp/completeness coverage, not returns or strategy outcomes. Any other local source must first be identified by metadata and its access authority checked; no external acquisition, protected-period data or prices may be opened. Do not bypass a platform denial.

Audit validation: verify shard identities from the existing trusted manifest, chronology, duplicate timestamps and per-pair gap counts; distinguish declared calendar closures from unexplained gaps without using later returns. Retain unavailable fields and source limitations. One bounded pass, one worker, no strategy evaluation, no market-trial or proposal increments, no edits to data or historical evidence. Original resource limits/deadline remain binding; if exhausted request new bounded resource authority rather than reset them. Save a checked gap inventory and one smallest evidence-backed data-repair request (or state that no authorized repair is available), then stop and release OCC82. Do not launch a replacement job or produce several alternative strategy changes.

Approval sentence: I approve the PKT-FOREX-044 development-data availability audit exactly as recorded here, using EAST_OCC_82 and LOCK_EAST_FOREX_CONTROL_BASELINE_RSI_FILTER_COMPARISON_STAGE1_OCC82, with writes only to PKT-FOREX-044.md, new development_gap_audit outputs and its lock lifecycle; preserve all research history and remaining budgets, with no strategy scoring, dataset changes, external acquisition, protected-data access or trading.

## Full 58-pair development availability audit — 2026-09-07

The approved audit completed across all 58 pairs using only the frozen M5 development corpus, its trusted manifest, the 2024-01-01 inclusive through 2025-04-01 exclusive interval, and the frozen potential-executable clock. No signals, outcomes, or protected validation/holdout data were read. No strategy scoring occurred. Existing audit outputs are under `.aios/staging/PKT_FOREX_044/development_gap_audit/`; the primary matrix is `availability_matrix.json` with code SHA-256 `5dff01803ea1c28eb4602ddaefe22de057716b61bb4a3fc05fe3f8f25c103dac`, trusted manifest SHA-256 `1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b`, and elapsed scan time 67.422 seconds.

Owner summary: **58/58 audited; 0 PASS_COMPLETE; 0 PASS_OPTIONAL_DIAGNOSTIC_GAPS_ONLY; 58 BLOCK_EXECUTABLE_GAP; 0 BLOCK_DATA_INTEGRITY.** Observed rows total 5,364,708. The 24/7 reference grid contains 7,617,024 five-minute slots; 2,252,316 slots are absent, of which 8,589 occur during a potentially executable clock and 2,243,727 occur when the frozen contract has no active path. Duplicate rows, out-of-order rows and malformed rows are all zero. Bid/ask price fields are present on observed rows; no optional-midpoint-only classification was found. These calendar gaps are retained as diagnostics, but the executable gaps block the frozen 58-pair experiment.

Known failures were confirmed in the larger gap family: AUD/CAD has the exact executable 2024-09-02T17:40:00Z gap; CAD/HKD has 35 executable missing bars from 2024-05-20T14:25:00Z through 17:15:00Z. They are not isolated: every pair has at least one executable-clock gap under the frozen contract. The matrix retains all ranges, first/last observations, expected/observed counts, duplicate/order/malformed counts, bid/ask/midpoint row defects, executable versus no-active-path counts, largest gap, and block decision. No pair was removed.

Local recovery search is complete for the approved repository-local sources and found **103 missing executable timestamps, all `NOT_FOUND_LOCALLY`**. No authoritative local copy, certified replacement, or unambiguous alternate source was found. `local_recovery_results.json` records zero complete bid/ask subinterval repairs, 103 missing/partial candidates, no data changes and no protected access. The audit did not copy, merge, certify or mutate any source. Therefore the evidence-based decision is **EXPERIMENT_NOT_EXECUTABLE_ON_CURRENT_CORPUS**, not RERUN_READY. A new authority decision is required: replace/certify the development corpus, preregister a different clean period/universe, or stop PKT-044. Excluding pairs or changing dates is not authorized.

Validation: canonical ledger/index hashes remain unchanged from the corrective checkpoint; the scored-attempt lower bound remains **1,294**; both prior INVALID_TEST attempts and all four linked correction events remain; no strategy specifications or proposals were added; no protected data or market outcomes were accessed. The earlier protected-access incident remains preserved and is not relabeled. The audit itself is not a strategy result.

The exact next approval request is one bounded data decision: `I approve a PKT-FOREX-044 development-corpus replacement/certification step limited to the 103 NOT_FOUND_LOCALLY executable timestamps listed in development_gap_audit/local_recovery_results.json, with immutable source identity, bid/ask validation, chronology/gap checks, no protected-period access, no external acquisition unless separately named, no scoring until certification, and the same 58-pair rules and remaining budgets.` Until that is approved and completed, corrective A/B scoring remains blocked.

## Development-corpus repair attempt — source-certified failure — 2026-09-07

Anthony approved the bounded repair and runtime read-only access to the original OANDA Practice GET-only source. Fresh OCC82 preflight had zero collisions and the exact packet/lane identity. The original immutable corpus was not modified. The repair version is `.aios/staging/PKT_FOREX_044/development_corpus_repair/repair_r1_occ82_20260907/`.

The 103 prior local records were gap-range representatives, not the full repair set. The completed audit expands them to **5,050 executable ranges, 14,634 exact pair/timestamp requirements, and 3,780 unique UTC timestamps**. The audit-reported 8,589 executable missing-bar count is retained as the original matrix measure; the expanded range representation is the exact acquisition key set. No request was broadened beyond an audited executable range.

The same source was queried with M5, `price=MBA`, completed candles, and five-minute context around each exact range. Final source dispositions cover all 14,634 unique requirements:

- **9,397 AUTHORITATIVE_CANDLE_RECOVERED** with complete bid/ask MBA rows;
- **5,237 AUTHORITATIVE_NO_OBSERVATION_EXISTS**;
- **0 unresolved ambiguous requirements** after retrying the 14 initial HTTP timeouts at 60 seconds;
- **0 remaining source errors**.

The 5,237 no-observation results are genuine source responses, not missing local bytes that can be repaired. No candle was fabricated, interpolated, forward-filled, reconstructed from midpoint, or inferred from another pair. No alternate provider was merged. The recovered rows passed complete-candle and bid/ask presence checks. The source response and retry receipts preserve request identity, returned timestamps, raw response fields and disposition.

Repair manifest: `repair_overlay_manifest.json`, overlay SHA-256 `883e841fcac18746dc1c60fbf7b0fa2d30bd3f01de09c66c3b6b04cc4d52a4a2`, manifest SHA-256 `056CFEE80F019CDC72BFD5F01464FCB1670E838CBCBA8EAB9B986A1098B9ACA1`. Composite certification receipt: `composite_certification.json`, SHA-256 `640C5817A7DDC94F61D8F36E4C6D3E76DF0D69BC6FB6CDE2E586BB238958B62B`; deterministic certification reproduction matched twice with composite identity hash `14460f2fd3bed17e23a7fd44c452a0148c96010dc95d1e599540fa393d5bd489`, receipt SHA-256 `A7CBE337BF3E1416C5B22D0303A843FBDBE0E69DCDCE34876D9C01B050517EFB`. The overlay is retained as immutable evidence but is **not certified for PKT-044 scoring**.

`EXECUTABLE_DATA_CERTIFICATION = FAIL`: 5,237 required executable observations have authoritative no-observation responses. Composite scoring is forbidden. No corrected A/B run, reproduction, publication, post-mortem or new proposal was started. Trial lower bound remains 1,294; canonical ledger/index and prior invalid/correction events are unchanged. No protected validation/holdout data was accessed. No broker account, orders, PAPER/LIVE activity, commit or push occurred.

The evidence-based next state is **EXPERIMENT_NOT_EXECUTABLE_ON_CURRENT_CORPUS**. The frozen experiment cannot be made valid by merging this overlay alone. One new authority decision is required: approve a new certified development corpus/source with observations for the 5,237 no-observation requirements, preregister a different clean period/universe, or stop PKT-044. Do not exclude pairs, change dates, or score partial data.

## Development availability audit approved — 2026-09-07

Anthony approved the complete 58-pair audit, not scoring or dataset repair. Preflight: C:\Dev\Ai.Os, main, HEAD b86c65140ed03d53d6c8d6c3618e50da0502f51b; origin unchanged; unrelated dirty backlog preserved. No Python process or active lock before claim. Canonical worker inbox has only completed historical items; profile registry is not active file ownership. Official OCC82 preview and claim returned zero collisions, policy blocks and review items for exactly three paths: this packet, new development_gap_audit outputs, and registry lifecycle. Skill coordination marker absent; no secondary board created. Native goal remains blocked and unchanged. Audit-only outputs do not amend strategy rules. Original 11:56:25Z deadline and 1-GiB total output budget remain binding.

Method frozen before audit: inspect only manifest-selected development shards (2024-01-01 inclusive through 2025-04-01 exclusive), verify compressed identity, count chronology/structural defects, then discard prices. No signals, indicators, returns, stops or portfolio simulation. Save only timestamps, counts and defect labels. Full 24/7 M5 grid count is separate from the frozen executable clock. Potential executable paths use the existing New York/DST no-entry and 16:30 financing-exit functions, 288-bar limit, final-development exit, and at least four prior completed contiguous candles (ATR3 plus two-bar confirmation). Potential positions are not removed using observed winning/losing outcomes. Absent entry prices may matter but cannot create an invented position. Gaps after the last possible scheduled close are calendar/no-active-path gaps, not optional midpoint diagnostics. Missing midpoint OHLC needed by Supertrend is required signal data, not an optional diagnostic. No all-missing row is classified as midpoint-only. AUD_CAD may be executable-risk under this price-blind test even though its earlier observed failure was only diagnostic.

## Dukascopy BI5 acquisition continuation — 2026-09-07

The approved coherent-source continuation is in progress under the existing OCC82 lock. The existing goal was preserved. The original OANDA corpus, its repair overlay, the two INVALID_TEST attempts, the trial ledger and fingerprint index remain untouched. No strategy score, validation/holdout read, broker action, credential write, commit or push occurred in this continuation.

The saved probe was verified and corrected probe artifacts were retained where older zero-based month labels were misleading. Real Dukascopy samples prove that the documented daily tick BI5 representation is LZMA-compressed, big-endian, and uses 20-byte tick records. A single real AUDCAD day independently reproduced every one of its 288 source-native M5 bid/ask OHLC bars from the tick stream against the corresponding daily minute-candle BI5 objects. The minute-candle binary layout is therefore probe-validated for PKT-044; it is not represented as vendor-documented serialization.

The minimum decoder and acquisition adapter are limited to the approved `edge_research` source/test roots. They preserve bid and ask independently, reject corrupt/truncated payloads and invalid records, never interpolate or substitute sides, and checkpoint raw source objects with hashes. Focused adapter/decoder validation passed: **46 passed, 0 failed, 0 skipped**; the only warning was the existing disabled-cache pytest configuration warning.

The complete bounded object inventory is `dukascopy_inventory_occ82_20260907/OBJECT_INVENTORY_V2.json`, SHA-256 `c53c54f118376b99d1deb3cf6e9a71468a8d8d9e4ff161fbc0b4cca87d1a41b2`: 58 pairs, 456 calendar dates, 25,335 BID and 25,335 ASK planned daily minute-candle objects (50,670 total, 445,584,394 listed bytes). It also records 2,226 missing planned keys / 1,113 no-object pair-days in eight source prefixes. These are preserved for later frozen execution-availability certification; they are not filled, treated as price data, or used to choose an outcome.

Current first-party AWS S3 pricing evidence and the Requester Pays terms were checked before bulk transfer. The verified cumulative cost gate is `PKT044_DUKASCOPY_COST_GATE_VERIFIED_V3.json`, SHA-256 `710ae6e32295a9a65ab0f3899774e24a74206aa62242c78b2036e1ad63b8f01e`. It includes conservative prior activity, 50,670 future GETs, one reserved HEAD per planned object, grouped listing, transfer at USD 0.09 per decimal GB, and safety margin. The conservative total is **USD 0.29091277866**, below the owner’s cumulative USD 1.00 limit. Six-month grouping reduces planned acquisition chunks to 174 without expanding any object scope.

The first constrained acquisition checkpoint completed through the tested adapter: one AUDCAD January-2024 source chunk, 62 planned source objects, no price normalization or scoring. All remaining transfers remain bounded by the frozen inventory and the verified cost gate. The next step is resumable grouped acquisition, followed by source-native normalization and 58-pair executable-path certification. Certification failure remains a hard stop before the frozen A/B run.

## Dukascopy source-semantics gate — stopped before corpus construction — 2026-09-07

The verified AWS executable and the existing `AIOS-FOREX` profile were used without exposing or persisting credentials. Source decoding and Requester Pays transfer mechanics passed the focused offline regression: **46 passed, 0 failed, 0 skipped** (one existing disabled-cache configuration warning). The revised cumulative gate is `PKT044_DUKASCOPY_COST_GATE_VERIFIED_V4.json`, SHA-256 `8e030cdf50325239b26a353e4523eccec3ffd11c62c52ed1fd4293f9c181fb08`, with a conservative whole-job estimate of USD `0.290990101`, including the extra early monthly sync reserve.

After gated foreground acquisition began, a repository-contract check found a source-semantics precondition that was not satisfied by the originally limited BID/ASK probe: the frozen PKT044 signal and stop-formation code require **source-native midpoint OHLC**, not merely bid/ask execution prices. `features.validate_bar` requires `bid`, `ask`, and `mid`; `features.snapshots` forms Supertrend and RSI from the `mid` OHLC. The complete constrained inventory has zero source midpoint objects, including zero `MID` keys among non-target/unexpected keys. Neither the frozen contract nor the approved source-replacement authority permits calculating midpoint OHLC from bid/ask. Doing so would alter source semantics and the frozen strategy rather than repair data.

This is a data-semantics blocker, not a finding about RSI, Supertrend, or profitability. The checked record is `dukascopy_acquisition_occ82_20260907/PKT044_DUKASCOPY_FROZEN_STRATEGY_SEMANTICS_GATE_V2.json`, SHA-256 `3f22ffebb6af411ce80cb7b5d599e602dd49de205d3fd170de1ada306c0f6496`; V2 supersedes a spelling-only V1 receipt and preserves its evidence. It records `FAIL_FOR_FROZEN_PKT044_SIGNAL_SEMANTICS`, `EXECUTABLE_DATA_CERTIFICATION=NOT_RUN_PRECONDITION_FAILED`, `CORPUS_NORMALIZATION=NOT_RUN`, `AB_SCORING=NOT_STARTED`, and `REPRODUCTION=NOT_STARTED`.

The source process was stopped after this verified precondition failure to prevent avoidable further Requester Pays transfer. It left **58 durable chunk receipts**, **16,546 raw objects** / **142,110,823 bytes**, and no `.part` files. **364 complete raw objects** from the interrupted current chunk have no durable chunk receipt; they are retained untouched as `PRESERVED_NOT_ELIGIBLE_FOR_CORPUS_UNTIL_CHECKPOINTED`, not normalized or used. No object was deleted, overwritten, retried, or silently accepted. The receipt’s conservative spent-to-date estimate, including safety margin, is USD `0.22917987961`, below the owner’s USD 1.00 limit; exact AWS billing remains external/delayed.

Canonical research memory is still unchanged: ledger 271 records, SHA-256 `a347e88dc71db5a84cd6b8247dec075f42cb864fbd02bb02da7b5661cd22213b`; fingerprint index 117 entries, SHA-256 `067c7102298bb3b57f08242ae3cfd6ac552425891adbe9c51e73bff01d777d59`; scored-attempt lower bound remains **1,294**. The two prior INVALID_TEST attempts and all correction/source history remain preserved. No new price normalization, corpus, executable certification, A/B outcome access, reproduction, publication, post-mortem, proposal, validation/holdout read, broker operation, credential write, commit, or push occurred.

The exact next owner decision is: `I approve one of the following mutually exclusive PKT-FOREX-044 paths: (A) replace the development source with one that provides source-native midpoint OHLC matching the frozen signal contract, or (B) create a separately preregistered bid/ask-only strategy specification with new fingerprint, trial accounting and scoring authority; do not derive midpoint from Dukascopy BID/ASK or alter the frozen PKT-044 A/B rules.` Until one path is chosen under new authority, preserve the partial raw Dukascopy evidence and do not resume acquisition, normalize it, certify it, or score PKT-044.

Reproducible audit code, self-check fixtures, one machine-readable full matrix, gap ranges, provenance/access evidence and compact owner summary will live only in the approved new output root. No production source or test changes. Stop after all 58 are audited and one evidence-supported next action is selected; no scoring restart under this audit. Any denied source remains unavailable and cannot support a local-recovery claim.

## No-AWS source-semantics amendment — 2026-09-07

Anthony confirmed that the previously active AWS PID 39420 had ended before this amendment started. Fresh OCC82 preview returned `READY_TO_CLAIM` with zero collisions, zero policy blocks, and zero review items. OCC82 then claimed only this packet, `dukascopy_bi5.py`, `dukascopy_acquisition.py`, their two focused tests, `.aios/staging/PKT_FOREX_044`, and its own registry lifecycle. This amendment made no AWS call, performed no paid request, did not acquire or normalize market data, and did not score a strategy.

### Frozen PKT-044 MID requirement audit

The frozen implementation requires `bid`, `ask`, and `mid` OHLC in `features.validate_bar`. `features.snapshots` forms the M5 candle stream for ATR(3), Supertrend, RSI(14), EMA/MACD/Bollinger/momentum context, signals, and band values from `mid` OHLC. The Supertrend bands are therefore `REQUIRED_FOR_STRATEGY_SEMANTICS` and, through the initial/trailing stop values consumed by `execution.py`, indirectly `REQUIRED_FOR_EXECUTION`. Actual entry and liquidation quotes remain observed ask/bid. The midpoint shadow path is `REQUIRED_FOR_DIAGNOSTICS_ONLY` and remains explicitly non-equivalent to a spread-cost estimate. Activity data is not a frozen A/B input.

The old OANDA reader requested `granularity=M5`, `price=MBA`, and `smooth=false`, which returned separate `mid`, `bid`, and `ask` components. The repository does not contain an authoritative definition of how OANDA formed its `mid` candle extrema. It is therefore recorded as `OANDA_MID_CONSTRUCTION=UNKNOWN`, not assumed to be either a synchronized bid/ask midpoint or an independent provider calculation.

The saved Dukascopy minute BI5 objects are separate BID or ASK one-minute OHLC records. They cannot establish that their side opens, highs, lows, or closes occurred at the same underlying observations, so candle-level averaging is forbidden. The saved Dukascopy daily tick BI5 probe instead carries bid and ask in the same source record with one timestamp. A causal `MID_t=(BID_t+ASK_t)/2`, followed by M5 aggregation, is mathematically valid only for that quote-level tick representation. It is not a provider-native MID series and it is not the frozen PKT-044 specification.

### Scientific decision and prepared successor

The classification is **B — MATERIAL_DATA_SEMANTICS_CHANGE**. The frozen PKT-044 A/B remains blocked: the complete Dukascopy minute inventory has zero source-native MID objects, while the frozen signal and stop contract requires native MID OHLC. No OANDA-to-Dukascopy indicator/signal equivalence claim is possible from the current evidence because the OANDA MID construction is unproven and the retained Dukascopy tick probe does not provide full 58-pair coverage.

Prepared but not registered, acquired, or scored: `PROPOSED_DUKASCOPY_TICK_MID_SUCCESSOR`. Its required data definition is `PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION`: form the midpoint only from each same-record bid/ask tick, aggregate those midpoint observations within completed UTC M5 buckets, retain empty buckets as unavailable, and preserve observed bid/ask for execution. It must receive a new preregistration, new fingerprint, separate trial accounting, a full tick-source capability/cost gate, and new scoring authority. It cannot inherit PKT-044's frozen native-MID identity or use the partially acquired BID/ASK-minute corpus as a substitute.

### Implemented pre-acquisition source-semantics gate

`dukascopy_acquisition.py` now checks required pair coverage, price sides, MID semantics, timestamp granularity, candle construction, execution-price coverage, and activity semantics before a cost gate can be built. Cost estimation and acquisition both reject a failed or unpreregistered semantics result. A BID/ASK-only source cannot claim native MID. A quote-level paired-tick midpoint is tracked separately and requires a new fingerprint plus preregistration before it can become acquisition-eligible.

`dukascopy_bi5.py` now contains only a pure successor-preparation normalizer for paired ticks. It calculates the midpoint for each source tick before M5 OHLC aggregation and never averages side-candle extrema, carries forward a quote, invents an empty bucket, or changes the frozen strategy.

Focused offline validation used saved local probes and synthetic fixtures only: **56 passed, 0 failed, 0 skipped**. The sole warning is the existing pytest `cache_dir` configuration warning. Tests cover frozen native-MID rejection before cost calculation, missing pair/side/execution evidence, the unpreregistered tick-MID successor, deterministic paired-tick MID aggregation, causal behavior, no empty-bucket creation, and no candle-level MID claim. Test temporary output is limited to `.aios/staging/PKT_FOREX_044/source_semantics_occ82_20260907/`.

Research memory remains outside this amendment. No strategy identity, score, proposal, validation/holdout artifact, or broker action was created. The prior OANDA and Dukascopy records, including the two INVALID_TEST attempts, remain preserved. The next allowed action is a single owner decision: either formally retire PKT-044 in favor of a separately preregistered Dukascopy paired-tick-MID successor, or authorize a documented source that can demonstrate the frozen native-MID semantics for all 58 pairs. Do not resume AWS acquisition under the current frozen contract.
