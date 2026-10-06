# BKT-FOREX-010: OANDA Practice 21-Series Dataset Evidence, Validation, Provenance, and Freeze

## Identity

- Mission: `MISSION-AIOS-001` — AIOS Governed Self-Building Operating System
- Program: `PRG-FOREX-001` — AIOS Forex Supervised Operational Validation Program V1
- Epic: `EPC-FOREX-006` — Governed Forex Historical Dataset Validation and Immutable Freezing
- Bucket: `BKT-FOREX-010`
- Human Owner: Anthony
- Status: Defined

## Purpose

Own the bounded evidence contract for validating and freezing the existing OANDA Practice 21-series historical dataset.

## Owned Packet

- `PKT-FOREX-011` — Historical Dataset Verifier and Freezer V1

## Allowed Capability Scope

- Read-only terminal-manifest and checkpoint reconciliation.
- Batch-file, candle-schema, timestamp, continuity, duplicate, overlap, gap, and boundary validation.
- SHA-256, candle-count, series-inventory, and provenance evidence.
- Explicit validation and freeze receipts.
- Atomic copy-once promotion after matching verifier PASS evidence.
- Idempotent verification of an identical existing frozen dataset.
- Synthetic fixtures and offline tests.

## Exclusions

This Bucket grants no candle collection, source mutation, M5 corpus substitution, strategy research, paper activity, live activity, external requests, credential access, dashboard changes, deployment, broker mutation, monetary action, staging, commit, push, PR, or merge authority.

## Validation Requirements

- Exactly 21 expected series, 21 complete, zero partial, zero missing, and zero invalid.
- Zero duplicate timestamps, uncontrolled overlaps, and unexplained internal gaps.
- Exact scope fingerprint and requested half-open date interval.
- Complete checkpoint, batch-ledger, manifest, file-hash, candle-count, and provenance reconciliation.
- Source-state and dataset hashes plus canonical inventories and receipts.
- No source artifact mutation.

## Reproducibility Commands

Future full-dataset verification, under a separate approved runtime boundary:

```powershell
python scripts/forex_delivery/run_forex_historical_dataset_verifier_freezer_v1.py verify --source-root .aios/runtime/forex_scalping_history_human_inbox_v1 --expected-scope-fingerprint e7ea1cf452a0cbafc9e2071c250c81b6cef242f800e2a2d0e694bcabfbade680 --expected-start-utc 2024-01-01T00:00:00Z --expected-end-utc 2026-08-30T00:00:00Z --expected-instruments EUR_USD GBP_USD USD_JPY --expected-granularities M1 M2 M4 S10 S15 S30 S5 --source-head b86c65140ed03d53d6c8d6c3618e50da0502f51b --validation-receipt .aios/runtime/forex_historical_dataset_freezes_v1/pending/AIOS_FOREX_HISTORICAL_DATASET_VALIDATION_RECEIPT.json --output-format both
```

Future freeze, only after that verification returns PASS and a separate write boundary is approved:

```powershell
python scripts/forex_delivery/run_forex_historical_dataset_verifier_freezer_v1.py freeze --source-root .aios/runtime/forex_scalping_history_human_inbox_v1 --validation-receipt .aios/runtime/forex_historical_dataset_freezes_v1/pending/AIOS_FOREX_HISTORICAL_DATASET_VALIDATION_RECEIPT.json --freeze-root .aios/runtime/forex_historical_dataset_freezes_v1 --expected-scope-fingerprint e7ea1cf452a0cbafc9e2071c250c81b6cef242f800e2a2d0e694bcabfbade680 --expected-start-utc 2024-01-01T00:00:00Z --expected-end-utc 2026-08-30T00:00:00Z --source-head b86c65140ed03d53d6c8d6c3618e50da0502f51b --output-format both
```

## Stop Point

Stop at tested capability implementation. Verification and freezing of the real dataset require a separate Human Owner-approved runtime packet.
