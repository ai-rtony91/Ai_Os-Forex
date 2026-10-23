# EPC-FOREX-006: Governed Forex Historical Dataset Validation and Immutable Freezing

## Identity

- Mission: `MISSION-AIOS-001` — AIOS Governed Self-Building Operating System
- Program: `PRG-FOREX-001` — AIOS Forex Supervised Operational Validation Program V1
- Epic: `EPC-FOREX-006`
- Human Owner: Anthony
- Status: Defined

## Purpose

Provide a governed capability to certify the integrity, coverage, provenance, and reproducibility of a bounded historical Forex dataset and to preserve a verified copy-once snapshot for later chronological research.

## Owned Bucket

- `BKT-FOREX-010` — OANDA Practice 21-Series Dataset Evidence, Validation, Provenance, and Freeze

## Packet Inventory

- `PKT-FOREX-011` — Historical Dataset Verifier and Freezer V1

## Scope

This Epic owns offline manifest, checkpoint, batch, candle, timestamp, hash, gap, coverage, provenance, receipt, and frozen-copy validation for the existing 21-series collection.

It does not own historical acquisition, M5 corpus acquisition, strategy research, dashboard work, deployment, credentials, account access, orders, broker mutation, or money movement.

## Acceptance Criteria

- The verifier is deterministic and read-only by default.
- A freeze requires matching PASS evidence from the same source state.
- Source artifacts are never mutated.
- Frozen content is atomically promoted and collision-safe.
- Focused synthetic tests and relevant regressions pass.
- Real-dataset execution requires a separate governed boundary.

## Stop Point

This Epic defines capability ownership only. It grants no runtime execution, staging, commit, push, PR, merge, trading, or external-service authority.
