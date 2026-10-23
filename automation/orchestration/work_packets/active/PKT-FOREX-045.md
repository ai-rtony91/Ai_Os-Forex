CODEX-ONLY PROMPT
AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

# PKT-FOREX-045 — Dukascopy Paired-Tick MID Successor Preregistration Stage 0

IDENTITY MARKER: PKT_FOREX_045_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_PREREGISTRATION_STAGE0
SUPERVISOR IDENTITY: Codex East
PACKET ID: PKT-FOREX-045
PACKET NAME: Dukascopy Paired-Tick MID Successor Preregistration Stage 0
MODE: APPLY — LOCAL PREREGISTRATION ONLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_83
LANE: FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_PREREGISTRATION_STAGE0
WORKTREE: C:\Dev\Ai.Os
BRANCH: main, observed and preserved during preflight
LOCK ID: LOCK_EAST_FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_PREREGISTRATION_STAGE0_OCC83
APPROVAL AUTHORITY: Anthony, Human Owner, explicit PKT-FOREX-045 assignment

MISSION ID: MISSION-AIOS-001
MISSION NAME: AIOS Governed Self-Building Operating System
PROGRAM ID: PRG-FOREX-001
PROGRAM NAME: AIOS Forex Supervised Operational Validation Program V1
EPIC ID: EPC-FOREX-002
EPIC NAME: Strategy Intelligence V1
BUCKET ID: BKT-FOREX-003
BUCKET NAME: Strategy Validation V1

## Parent evidence and mission

PKT-FOREX-044 remains blocked historical evidence. Its frozen provider-native MID OHLC contract could not be met by Dukascopy's separate minute BID/ASK candle extrema without invalid reconstruction. The parent outcome is `MATERIAL_DATA_SEMANTICS_CHANGE`, not a successful PKT-044 result.

This packet prepares a separately identified and unscored successor using only same-record Dukascopy ticks. It freezes the source semantics, validates saved local tick evidence, produces deterministic preregistration receipts, checks duplicate identities against read-only research memory, and leaves the next acquisition/certification/scoring phase at an owner approval boundary.

## Allowed paths

- `automation/orchestration/work_packets/active/PKT-FOREX-045.md`
- `automation/forex_engine/edge_research/dukascopy_bi5.py`
- `automation/forex_engine/edge_research/dukascopy_acquisition.py`
- `automation/forex_engine/edge_research/research.py`
- `automation/forex_engine/edge_research/batch.py`
- `automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py`
- `automation/forex_engine/forex_control_baseline_rsi_filter_comparison_stage1_v1.py`
- `scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py`
- focused existing tests directly covering those files, plus focused PKT-FOREX-045 preregistration/source-semantics/factory-handoff tests
- `.aios/staging/PKT_FOREX_045/`
- `automation/orchestration/locks/FILE_LOCK_REGISTRY.json`, only for the exact OCC83 claim/release lifecycle

## Forbidden paths and actions

All other paths are read-only, including PKT-FOREX-044 history, canonical research ledger, canonical fingerprint index, OANDA data, partial Dukascopy raw data, validation/holdout evidence, AWS credential files, broker state, and the T9 backup.

Do not make AWS LIST, GET, HEAD, sync, or other paid requests. Do not acquire or normalize a corpus; score or reproduce a strategy; publish research-memory events; access validation/holdout outcomes; access broker, PAPER, LIVE, credentials, orders, or money; or commit, push, merge, reset, stash, clean, delete, or rename unrelated work.

## Frozen successor contract

- Parent packet: `PKT-FOREX-044`; parent outcome: `MATERIAL_DATA_SEMANTICS_CHANGE`.
- Provider/source type: `DUKASCOPY` / `PAIRED_TICK`.
- Per same-record source tick: `MID_t = (BID_t + ASK_t) / 2`.
- Completed UTC M5 MID OHLC: first, maximum, minimum, and last valid `MID_t` in the exact interval.
- Execution prices: observed source-backed BID/ASK, side-correct for entries, exits, stops, trailing stops, direction changes, maximum holds, and rollover exits.
- Prohibited: nearest-neighbor pairing, candle-level BID/ASK extrema averaging, interpolation, forward/back fill, future data, mixed providers, midpoint as an executable fill.
- Target universe: the existing certified 58-pair metadata set, still unproven for complete tick coverage.
- Development interval: `2024-01-01T00:00:00Z` inclusive through `2025-04-01T00:00:00Z` exclusive.
- Configuration A: `DUKASCOPY_TICK_MID_COST_CERTIFIED_SUPERTREND_BASELINE`.
- Configuration B: `DUKASCOPY_TICK_MID_COST_CERTIFIED_SUPERTREND_BASELINE_PLUS_RSI14_70_30`.
- A/B difference: only the existing RSI(14) long-at-most-70 / short-at-least-30 filter. Supertrend ATR(3), multiplier 2.0, two completed confirmations, entry, stop, exit, cost, and exposure rules remain fixed.
- Evidence status: `NO_OUTCOME_ACCESS`, `NO_SCORING`, `NO_RESEARCH_MEMORY_PUBLICATION`.

## Required gate order

`STRATEGY_SPECIFICATION -> REQUIRED_DATA_SEMANTICS -> SOURCE_CAPABILITY -> SAVED_LOCAL_TICK_PROBE -> SEMANTICS_GATE -> EXACT_TICK_INVENTORY -> CURRENT_PRICING_AND_COST_GATE -> OWNER_ACQUISITION_AUTHORITY -> BULK_ACQUISITION -> NORMALIZATION -> CORPUS_CERTIFICATION -> SCORING`.

The local source-semantics gate can prove only same-record paired-tick compatibility. It must explicitly remain blocked for full 58-pair coverage, current cost, acquisition, certification, and scoring until a later approved packet verifies them.

## Validator chain

1. Verify current branch, dirty-state overlap, goal preservation, packet/worker/lane/lock identity, and no active conflicting worker.
2. Run official OCC83 collision preview, then claim only this packet's allowed paths.
3. Verify PKT-044 parent evidence, canonical ledger and index hashes, 1,294 lower bound, and no active AWS process/request.
4. Test same-record tick pairing, causal midpoint formula, M5 first/max/min/last aggregation, no look-ahead, no cross-bar leakage, malformed/missing side rejection, and deterministic local proof.
5. Test source semantic ordering: unsupported BID/ASK candles fail paired-tick requirements; full cost/acquisition cannot pass without a later full source gate; changed data semantics produce new fingerprints; preregistration cannot score.
6. Test explicit packet/specification identities, read-only duplicate prevention, factory handoff, old-PKT044 corpus fallback rejection, and old scorer rejection for a successor contract.
7. Generate two byte-identical preregistration receipts under `.aios/staging/PKT_FOREX_045/preregistration_occ83_20260907/`.
8. Verify canonical ledger/index bytes and trial lower bound unchanged; verify no AWS request, protected-data access, outcome access, or memory publication.
9. Run scoped diff check, release only OCC83, and verify registry integrity with no active OCC83 lock.

## Stop point

Stop after deterministic local preregistration and its tests pass. Do not inventory remote objects, price AWS, acquire ticks, construct a corpus, certify data, score A/B, reproduce, publish to canonical research memory, or open protected evidence. Return one complete later approval request for exact tick inventory/current pricing/cost gate/acquisition/certification/A-B only after this packet's evidence is complete.

## Execution state

- Status: `PREREGISTRATION_COMPLETE_AWAITING_ACQUISITION_AUTHORITY`.
- PKT-044: `PRESERVED_BLOCKED_HISTORICAL_EVIDENCE`.
- New scored trials: `0`.
- Canonical research memory mutation: `0`.
- AWS requests: `0`.
- Validation/holdout rows opened: `0`.
- Broker/PAPER/LIVE activity: `0`.
- Commit: `NOT_PERFORMED`.
- Push: `NOT_PERFORMED`.

## OCC83 completion checkpoint — 2026-09-07

- Fresh preflight observed `C:\Dev\Ai.Os`, branch `main`, HEAD `b86c65140ed03d53d6c8d6c3618e50da0502f51b`, and unrelated dirty work. PKT-FOREX-045 did not exist; EAST_OCC_83, its lane, and its lock were not already owned. Official collision preview returned zero collisions, zero policy blocks, and zero review items before OCC83 claimed exactly the approved 14 paths.
- PKT-FOREX-044 is preserved as the historical `MATERIAL_DATA_SEMANTICS_CHANGE` blocker. It was not reopened, altered, rescored, or relabeled as successful.
- The reusable controlled-challenger path now accepts an explicit governed experiment identity. PKT-045 cannot default to PKT-044, cannot fall back to the old OANDA corpus, and the old PKT-044 executor rejects any successor packet before it can open prices or score.
- The local source-semantics proof passed using only the saved `AUDCAD/2024/00/02_ticks.bi5` probe: 100,705 same-record bid/ask ticks, 288 deterministic completed M5 bars, and paired-tick midpoint aggregation. No candle-extrema averaging, nearest-neighbor pairing, interpolation, forward fill, or future observation is permitted.
- New identities are frozen: `EXP_FOREX_045_DUKASCOPY_PAIRED_TICK_MID_AB_V1`; A fingerprint `38decce38c56603269789a55b19e1b2d3a1b96369d077ee655aa88f13461b7b7`; B fingerprint `3385ec5c0f24b4eaedce17367f40a7e37be4255afb5e1594bda7ca8685f7d327`. A and B differ only in the RSI filter.
- The expected tick plan has 58 target pairs, 456 calendar dates, and 26,448 expected daily tick keys. It is `EXPECTED_KEYS_ONLY_NO_AWS_REQUESTS`, not a source-coverage claim. Full tick coverage, current pricing, cost gate, acquisition, certification, and scoring remain blocked.
- Local factory handoff performed a read-only duplicate search. No equivalent canonical fingerprint was found; both cards are `PREPARED_UNREGISTERED`. No canonical registration was attempted.
- Real delivery command: `python scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py preregister-pkt045 --output-root .aios/staging/PKT_FOREX_045/preregistration_occ83_20260907 --approve-pkt045-preregistration`. The two scientific receipts match: `75b7c661ab197e5da531f0cbfedd43584176d514e67eef01ad0495f24f67dd0f`. Summary receipt SHA-256: `74c13bfbe3e13c326093e0bb8e750773ee70989a72654c24a24c238bb356de12`. Status command reports `PASS_PREACQUISITION_ONLY`, `AWAITING_ACQUISITION_AUTHORITY`, and zero executable market trials.
- Focused regression: `142 passed, 0 failed, 0 skipped`; one existing pytest configuration warning about disabled cache configuration. Receipt: `.aios/staging/PKT_FOREX_045/tests_occ83_20260907/focused_regression_final.xml`.
- Canonical memory remains unchanged: ledger 271 records, SHA-256 `a347e88dc71db5a84cd6b8247dec075f42cb864fbd02bb02da7b5661cd22213b`; fingerprint index 117 entries, SHA-256 `067c7102298bb3b57f08242ae3cfd6ac552425891adbe9c51e73bff01d777d59`; scored-attempt lower bound `1,294`. No unscored proposal or scored outcome was published.
- No AWS process or request, acquisition, corpus normalization, A/B score, reproduction, validation/holdout access, protected price access, broker activity, credential write, commit, or push occurred in this packet.

## Complete next approval request

`I approve PKT-FOREX-045 Stage 1 using EAST_OCC_84 in lane FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_ACQUISITION_CERTIFICATION_STAGE1 with lock LOCK_EAST_FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_ACQUISITION_CERTIFICATION_STAGE1_OCC84 to verify the exact 58-pair Dukascopy tick-object inventory and current first-party AWS pricing, enforce the remaining cumulative USD 0.77082012039 ceiling after prior estimated spend USD 0.22917987961, acquire only if source-semantics, inventory, and cost gates pass, certify the corpus before running only the two frozen PKT-045 A/B configurations, reproduce and publish only if valid, with no validation/holdout access, PAPER/LIVE activity, credential persistence, commit, push, or merge.`

## Final report

Use the mandatory Owner View plus APPLY completion/failure report. Include the distinct packet/specification/fingerprint identities; semantic gate and local tick proof; deterministic receipt hashes; exact test counts; unchanged canonical memory/trial lower bound; no AWS/acquisition/scoring/protected-data activity; full next approval request; scope-limited diff; lock release; and no-commit/no-push result.

---

# Stage 1 authority — Acquisition, Certification and Controlled A/B Research

IDENTITY MARKER: `PKT_FOREX_045_DUKASCOPY_PAIRED_TICK_MID_STAGE1`

- Supervisor: `Codex East`
- Approval authority: `Anthony, Human Owner`
- Mode/zone: `APPLY` / `EAST`
- Worker: `EAST_OCC_84`
- Lane: `FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_ACQUISITION_CERTIFICATION_STAGE1`
- Lock: `LOCK_EAST_FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_ACQUISITION_CERTIFICATION_STAGE1_OCC84`
- Branch/worktree: resolve and preserve the observed branch in `C:\Dev\Ai.Os`; no branch or worktree mutation.

Stage 1 preserves every Stage 0 receipt, the parent PKT-044 `MATERIAL_DATA_SEMANTICS_CHANGE` conclusion, the two frozen PKT-045 fingerprints, and the exact paired-tick-MID semantics.  It may perform only the owner-authorized controlled chain: local implementation/tests; bounded tick inventory and first-party pricing; a cumulative cost gate; raw tick acquisition only if every gate passes; corpus/certification; then exactly the two frozen A/B configurations, one deterministic reproduction, checked publication, and closed-loop handoff.

The Stage 1 output root is `.aios/staging/PKT_FOREX_045/stage1_occ84/`.  Raw objects are limited to `raw_ticks/`, normalized data to `corpus_m5/`, and operational/checkpoint evidence to the named Stage 1 subdirectories.  Existing Stage 0 outputs are immutable.

AWS source scope is fixed to the direct executable `C:\Users\mylab\AppData\Local\Programs\Amazon\AWSCLIV2\aws.exe`, profile `AIOS-FOREX`, bucket `cfg-public-proper-wallaby`, region `eu-west-1`, Requester Pays, and same-record Dukascopy paired-tick objects only.  No AWS action is allowed before local tests pass.  Inventory/pricing must use at most USD 0.02 in additional conservative request cost.  The total lifetime ceiling remains USD 1.00, with reported prior spend USD 0.22917987961; no bulk GET may start unless the reconciled cumulative cost gate passes.

Required gates, in order:

1. packet/path/branch/ownership validation and OCC84 claim;
2. Stage 0 receipt, fingerprint, memory, and local source-semantics validation;
3. focused paired-tick, inventory, cost, resume, and partial-state tests;
4. exact bounded 58-pair tick inventory and first-party pricing verification;
5. conservative cumulative cost and resource gates;
6. raw receipt/hash checks; full 58-pair corpus certification twice; and only then the frozen A/B run, reproduction, publication, and handoff.

Stop before the next chargeable request if projected total cost exceeds USD 1.00; also stop for a collision, unsupported source coverage, source semantics failure, protected-data requirement, missing executable path, unlisted write, resource ceiling, or platform denial.  A failed data/cost gate must preserve all evidence and return one consolidated blocker; it must not change pairs, dates, rules, fingerprints, or historical research.

## OCC84 Stage 1 start checkpoint — 2026-09-07

- Read-only preflight preserved the current native goal (`blocked`), repository root `C:\Dev\Ai.Os`, branch `main`, HEAD `b86c65140ed03d53d6c8d6c3618e50da0502f51b`, and unrelated dirty work. No branch, checkout, reset, stash, merge, commit, or cleanup was performed.
- The Stage 0 scientific receipt `PREREGISTRATION_RECEIPT_RUN1.json` and run 2 both match `75b7c661ab197e5da531f0cbfedd43584176d514e67eef01ad0495f24f67dd0f`. Full frozen fingerprints remain `38decce38c56603269789a55b19e1b2d3a1b96369d077ee655aa88f13461b7b7` and `3385ec5c0f24b4eaedce17367f40a7e37be4255afb5e1594bda7ca8685f7d327`.
- Canonical research memory preflight is unchanged: ledger 271 records / `a347e88dc71db5a84cd6b8247dec075f42cb864fbd02bb02da7b5661cd22213b`; fingerprint index 117 entries / `067c7102298bb3b57f08242ae3cfd6ac552425891adbe9c51e73bff01d777d59`; lower-bound trial count 1,294.
- Official collision preview returned `READY_TO_CLAIM` with zero collisions, policy blocks, and review items. OCC84 then claimed exactly the Stage 1 allowed paths. No AWS request, data acquisition, corpus construction, score, reproduction, publication, protected-data read, or broker activity has occurred in Stage 1 at this checkpoint.

## OCC84 bounded inventory and cost checkpoint — 2026-09-08

- The Stage 0 semantic receipt and full fingerprints were revalidated before any remote request. The paired-tick source-semantics gate remained `PASS`.
- A bounded, checkpointed Requester Pays listing completed all 870 exact pair/month prefixes for the frozen 58-pair, 456-calendar-day development interval. It made 870 `ListObjectsV2` requests and no `GetObject`, `HeadObject`, raw acquisition, corpus, scoring, reproduction, publication, validation/holdout, or broker request.
- The exact paired-tick listing selected 21,171 source objects totaling 6,446,848,763 bytes. It retained 5,277 absent calendar-day keys as source availability evidence; their executability remains a later certification question and they were not filled or hidden.
- Current first-party AWS pricing was recorded without assuming a free allowance. Including the prior spend estimate USD 0.22917987961, the 870 inventory lists, all 21,171 planned object GETs, 6,446,848,763 planned download bytes, and USD 0.01 uncertainty reserve, the deterministic conservative project estimate is USD 0.83221466828. This is below the owner hard limit of USD 1.00.
- Inventory evidence: `.aios/staging/PKT_FOREX_045/stage1_occ84/inventory/PKT045_PAIRED_TICK_OBJECT_INVENTORY.json` SHA-256 `20794241f3ea3aa90ec2b5f83f732a66145082270ee47cbd056cbd736fa934ad`. Cost gate evidence: `.aios/staging/PKT_FOREX_045/stage1_occ84/pricing/PKT045_DUKASCOPY_TICK_COST_GATE.json` SHA-256 `df43a3420d69faec938344a4a3f90ae27bd2574ff7075a9342d4b444cbf7787d`.
- Status after this checkpoint: `AWAITING_ACQUISITION_AND_CERTIFICATION`. OCC84 remains the only active writer for the approved Stage 1 paths.

## OCC84 acquisition feasibility checkpoint — 2026-09-08

- The sealed Stage 1 contract was revalidated after a code-identity update without overwriting earlier contract receipts; the stable versioned contract is retained under `stage1_occ84/receipts/`.
- AWS STS was revalidated with the approved executable/profile. One bounded real Requester Pays GET probe succeeded, followed by one controlled resumable acquisition process. It produced 9 complete, receipted raw tick objects totaling 2,558,942 bytes; 8 GET requests were made in the full process (the first probe object was reused), with no retries or conflicts.
- Measured throughput was approximately two objects per minute. With 21,162 inventoried objects still unreceipted, completion would exceed the packet's six-hour foreground execution ceiling by a wide margin. The process was interrupted cleanly between objects; no second downloader was started. The durable checkpoint remains `RUNNING` with `SAFE_RESUME_ACTION=VALIDATE_RECEIPTS_THEN_CONTINUE_ONLY_UNRECEIPTED_INVENTORIED_KEYS` and preserves all 9 receipts.
- No normalization, corpus certification, strategy scoring, reproduction, research-memory publication, validation/holdout access, broker activity, or Git operation occurred. The cumulative conservative project estimate remains USD 0.83221466828, below the USD 1.00 cost ceiling, but the measured foreground resource limit is now the active blocker.
- OCC84 was released through the official lifecycle at 2026-09-08T06:54:42Z; the lock registry reports no active OCC84 ownership. Resume requires a new approved Stage 1 worker/lock lifecycle and must not duplicate the 9 completed objects.
