# AIOS Trusted Command Terminal Model V1

## Phase identity and purpose

This is Phase 5, **Z Fold 6 Trusted Command Terminal Model**, of the Owner
Cellular Voice Gateway program. It defines a deterministic, declarative model
for a future trusted owner command terminal. The device is a trust signal, not
standalone authority. This design registers, enrolls, provisions, and activates
nothing.

| Identity field | Value |
|---|---|
| phase | `5` |
| owner_authority | `DEVICE` |
| owner_bundle | `OWNER-BUNDLE-2-DEVICE-IDENTITY` |
| preparation_mode | `PREPARE_BEHIND_GATE` |
| protected_transition | `BLOCKED` |

`DEVICE` is a design label and is not proof of owner authority. The canonical
manifest and Approval Broker remain unchanged and non-authoritative.

## Device record contract

The canonical machine-readable contract is
`schemas/orchestration/aios_trusted_command_terminal_model_v1.schema.json`. A
record contains exactly these required fields:

- `device_record_version`, `device_reference_id`, `device_class`, and
  `device_state`;
- `ownership_state`, `enrollment_state`, `attestation_state`, `integrity_state`,
  `os_security_state`, and `screen_lock_state`;
- `biometric_policy_state`, `passkey_readiness_state`, `revocation_state`,
  `recovery_state`, and `authority_state`; and
- `privacy_classification`, `provenance`, and `integrity_reference`.

The device reference is opaque and cannot encode a hardware or account
identifier. Deterministic comparison uses `(device_record_version,
device_reference_id, integrity_reference)`. Canonical serialization uses UTF-8
JSON, lexicographically sorted object keys, and no insignificant whitespace.
Integrity evidence detects alteration; it does not authenticate the owner,
establish freshness, or grant permission.

## Device data boundary

No real hardware identifiers or private authority material may enter this
model. Prohibited data includes IMEI, serial number, Android ID, advertising ID,
SIM/eSIM ID, MAC address, real phone number, device certificate or private key,
passkey credential material, YubiKey secrets, biometric templates, tokens,
passwords, and secrets. Producers use opaque references only and must reject,
redact, and quarantine prohibited values before persistence or transfer.

## Trust model

- Device possession alone is insufficient and grants no authority.
- An unlocked device alone is insufficient.
- Screen-lock success is insufficient.
- A biometric match alone is insufficient.
- An operating-system claim alone is insufficient.
- Attestation alone is evidence, not approval, and grants no authority.
- Later, current Human Owner authority remains mandatory.
- Every receiving boundary revalidates current authority, exact binding,
  freshness, integrity, revocation, and policy.

No evidence item in this model can independently authorize a protected action.

## Phase 3 threat binding

Phase 5 owns the mitigation design for every Phase 5-owned entry in the
canonical Phase 3 threat model:

| Threat ID | Phase 5 binding | Fail-closed evidence |
|---|---|---|
| `GW-T023` | Trusted-device compromise | Compromise, theft, invalid integrity, or revocation blocks use and requires independent recovery |

Phase 3 completion and Phase 5 evidence do not accept residual risk or activate
a mitigation runtime.

## Device states

The only device states are `UNREGISTERED`, `DESIGN_ONLY`,
`PENDING_OWNER_AUTHORITY`, `PENDING_ENROLLMENT`, `PENDING_ATTESTATION`,
`VERIFIED_NOT_ACTIVE`, `BLOCKED`, `REVOKED`, `LOST`, and `COMPROMISED`. Every
state is non-operational and fail closed. There is no `ACTIVE` or
`TRUSTED_FOR_EXECUTION` state. Unknown, missing, expired, conflicting, or
unverifiable state resolves to `BLOCKED`.

## Ownership and enrollment model

Any future enrollment requires current owner approval, the exact opaque device
reference, the exact enrollment action, an expiry, replay protection,
consume-once semantics where applicable, receiving-boundary verification, and
an independent recovery path. A missing, stale, replayed, consumed, mismatched,
or unverifiable approval blocks enrollment. Design validation, possession, and
attestation are evidence only.

## Revocation model

A lost device, stolen device, compromise suspicion, OS integrity failure,
attestation failure, lock-screen policy failure, or owner revocation immediately
sets `BLOCKED`, `REVOKED`, `LOST`, or `COMPROMISED`, invalidates prior evidence,
and denies all operational trust. Recovery requires an independent trusted
owner path, a fresh record and approval, replay checks, and receiving-boundary
revalidation. The affected device cannot approve its own recovery.

## GrapheneOS and Android boundary

GrapheneOS or Android security posture is evidence only. Phase 5 does not modify
operating-system settings, invoke ADB, enroll with MDM, use a provider or network
client, assume Pixel- or Z Fold-specific runtime APIs, deploy software, or add
runtime or remote-control capability.

## Biometric boundary

Biometrics may become future local-unlock evidence only. No biometric capture,
template, sample, or derived identity material is stored in the repository, and
a biometric match can never be sole Human Owner authority.

## Passkey and YubiKey boundary

Phase 5 models readiness and a sanitized handoff only. Actual passkey or YubiKey
authority and enrollment belong to Phase 9. Phase 5 contains no enrollment,
credential material, private key, secret, or factor association.

## Privacy model

Collect only opaque device references, bounded state classifications, sanitized
provenance, and integrity references needed for the declared design purpose.
Evidence is minimized, redacted, purpose-bound, and least-privilege. Unknown
privacy classification is quarantined. Logs, reports, exports, retention, and
deletion evidence remain sanitized and must never reconstruct device identity.

## Phase 5 handoff

Phase 6 may consume the reviewed non-operational device-state vocabulary,
fail-closed trust rules, and sanitized design evidence when designing voice
confidence. Phase 9 may consume the readiness state, revocation requirements,
and exact-binding requirements when designing passkey/YubiKey authority. Neither
phase may infer enrollment, owner identity, attestation validity, operational
trust, activation, runtime readiness, or permission from Phase 5 completion.

## Acceptance matrix

| Requirement | Evidence | Pass condition | Downstream consumer |
|---|---|---|---|
| Exact identity | Identity table and schema constants | Phase 5, DEVICE, bundle, mode, and blocked transition are exact | Program coordinator |
| Device contract | Schema and contract section | Required fields are closed and deterministic | Future device validator |
| Data boundary | Device data boundary | Only opaque references; prohibited data is rejected | Privacy review |
| Trust model | Trust model | No single device signal grants authority | Phases 6, 9, 11, and 13 |
| Threat binding | Threat table | Every Phase 5-owned threat is mapped | Phase 3 risk review |
| Device states | State section and schema | Every state fails closed; no active state exists | Future state machine |
| Enrollment | Enrollment section | Exact current, expiring, replay-safe approval is mandatory | Owner verification boundary |
| Revocation | Revocation section | Loss, theft, compromise, or policy failure immediately denies trust | Recovery designer |
| OS security | OS boundary | Posture remains evidence and no mutation capability exists | Future device adapter |
| Biometrics | Biometric boundary | Local evidence only; no templates or sole authority | Phase 9 |
| Passkey/YubiKey | Factor boundary | Readiness only; no enrollment or secret material | Phase 9 |
| Privacy | Privacy section | Minimized, opaque, sanitized evidence only | Privacy review |
| Handoff | Phase 5 handoff | Reviewed design grants no downstream authority | Phases 6 and 9 |
| Owner gate | Owner gate | Every real or operational action remains blocked | Human Owner and receiving boundary |

## Owner gate

Phase 5 design/preparation may complete autonomously behind the gate. Any real
device registration, enrollment, binding, attestation activation, certificate
provisioning, passkey/YubiKey association, biometric enrollment, or operational
trust activation remains **BLOCKED** until valid
`OWNER-BUNDLE-2-DEVICE-IDENTITY` authority is separately verified. Phase 5
cannot consume that authority or perform a protected transition.
