# AIOS YubiKey and Passkey Authority Model V1

## Phase identity and purpose

This is Phase 9, **YubiKey and Passkey Authority Model**, of the Owner Cellular Voice Gateway program. It is a deterministic, declarative `PREPARE_BEHIND_GATE` contract. It grants no authority and activates no device, biometric, microphone, network, provider, runtime, trading, broker, order, money, credential, vault, or secret capability.

| Identity field | Value |
|---|---|
| phase | `9` |
| owner_authority | `PHYSICAL_DEVICE` |
| owner_bundle | `OWNER-BUNDLE-2-DEVICE-IDENTITY` |
| preparation_mode | `PREPARE_BEHIND_GATE` |
| protected_transition | `BLOCKED` |

## Closed record contract

The closed schema requires an opaque `record_id`, exact `phase`, bounded `state`, `authority_state: BLOCKED`, freshness data, action binding, sanitized provenance, and an integrity reference. Unknown, missing, stale, conflicting, replayed, revoked, or unverifiable input resolves to `BLOCKED`. Canonical comparison uses sorted-key compact UTF-8 JSON.

## Required safety behavior

- **Opaque factor references** is mandatory and fail closed.
- **No private keys** is mandatory and fail closed.
- **No secrets** is mandatory and fail closed.
- **No physical enrollment** is mandatory and fail closed.
- **Stale or revoked factor rejection** is mandatory and fail closed.
- **Cross-device binding** is mandatory and fail closed.
- **Factor authority remains blocked** is mandatory and fail closed.

- Evidence is purpose-bound, least-privilege, sanitized, and cannot become current owner authority.
- Every receiving boundary revalidates freshness, exact action and subject binding, revocation, integrity, policy, and current independent owner authority.

## Failure states and attacks

Ambiguous state, substituted transcripts, mismatched subjects, stale approvals, duplicate receipts, downgrade attempts, archive poisoning, confused-deputy requests, and integrity failures are rejected. Failures produce sanitized reason codes only. No raw voice, biometric material, credential material, private data, or secrets may be persisted or logged.

## Downstream handoff

Downstream phases may consume only this reviewed vocabulary and sanitized evidence. Completion does not grant an owner bundle, authorize a protected transition, or prove a runtime fact. Activation remains `BLOCKED`.

## Acceptance matrix

| Requirement | Evidence | Pass condition |
|---|---|---|
| Identity | Schema constants | Exact phase and gate metadata |
| Closed contract | JSON Schema | Unknown properties rejected |
| Safety requirements | Required safety behavior | Every listed control is explicit |
| Fail closed | Failure states | Unknown and invalid evidence blocks |
| Capability boundary | Purpose and owner gate | No operational capability exists |

## Owner gate

Design and negative-test preparation may complete autonomously behind the gate. Policy acceptance, enrollment, activation, deployment, external access, or any operational transition remains **BLOCKED** until separately authorized and revalidated. This phase does not grant or consume `OWNER-BUNDLE-2-DEVICE-IDENTITY`.
