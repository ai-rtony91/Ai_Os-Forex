# AIOS Location Vault and Privacy Broker V1

## Phase identity and purpose

This document defines Phase 17, **Location Vault and Privacy Broker**, of the
Owner Cellular Voice Gateway program. It is a declarative privacy boundary for
future location-derived evidence. It neither collects location nor grants
consent, owner authority, or operational permission.

| Identity field | Value |
|---|---|
| phase | `17` |
| owner_authority | `PRIVACY_CONSENT` |
| owner_bundle | `OWNER-BUNDLE-4-LOCATION-PRIVACY` |
| preparation_mode | `PREPARE_BEHIND_GATE` |
| protected_transition | `BLOCKED` |

The canonical owner manifest and Approval Broker remain unchanged. Broker and
validation results are evidence only; neither can create or consume privacy
consent.

## Closed privacy record contract

The machine-readable contract is
`schemas/orchestration/aios_location_vault_and_privacy_broker_v1.schema.json`.
It contains exactly four closed records:

- an opaque record identity and purpose binding;
- a current-consent reference containing state, exact scope, issue time, expiry,
  revocation state, action binding, and sanitized provenance;
- minimized location evidence containing only an opaque evidence reference,
  permitted granularity class, privacy classification, sanitization state, and
  integrity reference; and
- a retention record containing retention class, expiry, deletion state, and an
  opaque deletion-evidence reference when deletion is evidenced.

Unknown properties are rejected. Identifiers are opaque and must not encode or
permit reconstruction of a real place, person, device, provider account, or
secret. Canonical serialization uses UTF-8 JSON with sorted keys and no
insignificant whitespace.

## Data minimization and prohibited data

This phase stores no actual coordinates, latitude/longitude pair, altitude,
address, postal code, geofence geometry, place name, home/work label, location
history, travel path, wireless scan, cell identifier, device identifier, or raw
provider response. It collects no precise location. Only opaque, purpose-bound
references and bounded classifications are permitted.

A producer must reject and quarantine evidence that contains precise or
reconstructable location, unknown fields, free-form location text, or
cross-purpose metadata. Hashing raw location is not sufficient minimization: a
digest that can be correlated or enumerated remains prohibited.

## Consent model

Consent is external Human Owner authority and is never inferred from location
evidence, prior use, device possession, route success, validation, or historical
approval. A receiving boundary must verify all of the following atomically:

1. consent state is `CURRENT_EXTERNAL_CONSENT_EVIDENCE`;
2. the trusted external consent reference is current and independently verified;
3. scope and purpose exactly match the requested action;
4. subject, action, and evidence bindings match;
5. issue and expiry times are valid under a known trusted clock;
6. consent has not been revoked or consumed where consume-once policy applies;
7. privacy classification and sanitization are permitted; and
8. current owner authority is independently revalidated.

Missing, stale, expired, revoked, mismatched, replayed, unverifiable, or unknown
consent fails closed as `BLOCKED`. Consent may be revoked at any time. Historic
consent and historic location can never become current authority. Consent for
one purpose cannot be reused for another purpose; there is no cross-purpose reuse.

## Evidence and authority boundary

Location evidence is contextual evidence only. It cannot independently identify
the owner, approve an action, satisfy a device or factor gate, reduce command
risk, or grant execution authority. Integrity evidence detects mutation but
does not prove consent, freshness, identity, or authorization. Every receiving
boundary repeats current consent and authority validation rather than trusting
an upstream `PASS` value.

## Retention, deletion, and reconstruction boundary

Retention is purpose-limited and time-bounded. On consent revocation, purpose
completion, classification failure, or retention expiry, the evidence becomes
unavailable for use or export and enters `DELETION_REQUIRED`, `DELETED`, or
`QUARANTINED`. Deletion evidence is an opaque sanitized reference, not retained
location content. Unknown retention or deletion state is quarantined and cannot
be promoted.

Sanitized records must not be joinable with logs, timestamps, provider data,
device data, archives, or other references to reconstruct a real location.
Exports are denied by default and require separate current authority and the
same exact purpose and privacy checks.

## Capability boundary

Phase 17 adds no GPS or sensor access, Android or GrapheneOS permission
mutation, geofencing, background collection, provider/location API, network
client, external vault access, credential access, daemon, scheduler, deployment,
or runtime activation. It also adds no trading, broker, order, or money-moving
capability. There is no local runtime component because the current repository
architecture requires only the declarative model at this preparation stage.

## Phase 3 threat bindings

| Threat ID | Phase 17 mitigation | Fail-closed result |
|---|---|---|
| `GW-T026` | Minimized classified records, exact-purpose access, and sanitized evidence | Unknown or excessive privacy data is quarantined |
| `GW-T027` | No precise/reconstructable location and current explicit consent gate | Missing consent or location leakage blocks use |
| `GW-T028` | Allowlisted sanitized evidence and no raw location logging | Classification failure blocks logging and export |
| `GW-T029` | Export denied by default with current exact-purpose authority | Missing export authority blocks export |
| `GW-T038` | Retention expiry, revocation, deletion state, and deletion evidence | Expired or unverifiable deletion state is quarantined |

Threat-model coverage is design evidence only. It does not accept residual risk
or activate a mitigation runtime.

## Upstream dependencies and downstream handoff

Phase 17 consumes only reviewed, sanitized, non-authoritative design vocabulary
from Phase 2 privacy/retention, Phase 3 threats, Phase 10 governance memory,
Phase 13 receiving-boundary routing, and Phase 16 opaque-reference/session
protection. It does not infer that any upstream phase is activated.

A future receiving component may consume the closed schema and threat bindings
only after revalidating current consent, current owner authority, exact purpose,
freshness, revocation, retention, privacy classification, and integrity. Phase
17 completion grants no downstream authority.

## Acceptance matrix

| Requirement | Evidence | Pass condition | Consumer |
|---|---|---|---|
| Exact identity | Identity table and schema metadata | Phase, authority, bundle, mode, and blocked transition match | Program coordinator |
| Closed record | Schema | Exact fields; unknown properties rejected | Future validator |
| Minimization | Data boundary and schema | Opaque references and classifications only | Privacy review |
| Consent | Consent model | Current exact-purpose external consent required | Receiving boundary |
| Revocation/expiry | Consent and retention records | Stale, revoked, and expired states block | Privacy broker design |
| Non-authority | Evidence boundary | Location never grants owner authority | Command gate |
| Retention/deletion | Retention model | Expiry and deletion evidence are explicit | Records review |
| Threat coverage | Threat table | All Phase 17-owned threats bound exactly | Phase 3 review |
| No capability | Capability boundary | No collection, provider, permission, vault, or runtime integration | Security review |
| Owner gate | Owner gate | Consent and activation remain blocked | Human Owner |

## Owner gate

Safe design and negative-test preparation may complete behind the gate. Actual
privacy consent, location collection, permission changes, provider access,
external vault access, deployment, and operational activation remain
**BLOCKED** until valid `OWNER-BUNDLE-4-LOCATION-PRIVACY` authority is separately
provided and independently revalidated. Phase 17 does not grant or consume that
bundle.
