# AIOS Phone Number Routing Model V1

## Phase identity and purpose

This is Phase 4, **Phone Number Routing Model**, of the Owner Cellular Voice
Gateway program. It defines a deterministic, declarative contract for a future
owner-controlled phone-number/provider route into AIOS. It provisions nothing,
contacts no provider, and activates no telephony capability.

| Identity field | Value |
|---|---|
| phase | `4` |
| owner_authority | `PHONE_NUMBER` |
| owner_bundle | `OWNER-BUNDLE-2-DEVICE-IDENTITY` |
| preparation_mode | `PREPARE_BEHIND_GATE` |
| protected_transition | `BLOCKED` |

`PHONE_NUMBER` is the routing model's authority label, not proof of authority
and not a change to the canonical owner-authority manifest. The manifest and
Approval Broker remain unchanged and non-authoritative. Phase 4 design and
preparation may complete autonomously behind the gate; operational use cannot.

## Routing record contract

The canonical machine-readable contract is
`schemas/orchestration/aios_phone_number_routing_model_v1.schema.json`. A record
contains exactly these required fields:

- `route_version`, `route_id`, `route_state`, `provider_class`,
  `number_reference_id`, and `number_classification`;
- `inbound_policy`, `outbound_policy`, `source_binding_policy`,
  `forwarding_policy`, `failover_policy`, and `recovery_policy`;
- `change_control_state`, `verification_state`, `authority_state`, and
  `privacy_classification`; and
- `provenance` and `integrity_reference`.

Identifiers are opaque, non-sensitive references. Deterministic comparison uses
the tuple `(route_version, route_id, number_reference_id, integrity_reference)`.
Canonical serialization uses UTF-8 JSON, lexicographically sorted object keys,
and no insignificant whitespace. Integrity evidence detects record alteration;
it does not prove source identity, freshness, owner authority, or permission.

## Phone-number data boundary

No real phone number may appear in docs, tests, fixtures, reports, logs, or
examples. A real owner number, production E.164 value, carrier account ID,
SIM/eSIM identifier, provider credential, token, password, or secret is
prohibited. Producers must use opaque references and reject, redact, and
quarantine prohibited values before persistence or downstream transfer.

## Source trust model

- Caller ID is untrusted.
- ANI/CLI metadata is untrusted.
- Carrier metadata is untrusted.
- Provider transport is untrusted.
- Possession or control of a number does not authenticate the Human Owner and
  does not equal owner authority.
- Successful routing does not authorize a protected action.
- Later independently verified identity and device factors remain mandatory.
- Every receiving boundary revalidates identity, route binding, freshness,
  integrity, authority, and policy; transport assertions never bypass a gate.

## Phase 3 threat binding

Phase 4 owns mitigations for every Phase 4-owned entry in the canonical Phase 3
threat model:

| Threat ID | Phase 4 binding | Fail-closed evidence |
|---|---|---|
| `GW-T001` | Caller/source spoofing | Untrusted source metadata and independent factor binding |
| `GW-T002` | SIM swap or number takeover | Immediate block, revocation, and independent recovery |
| `GW-T003` | Provider-account compromise | Provider anomaly blocks the route |
| `GW-T004` | Provider infrastructure compromise | Transport is untrusted and cannot confer authority |
| `GW-T031` | Denial of service | Failure cannot trigger an identity or policy downgrade |
| `GW-T039` | Compromised external dependency | Provider isolation and receiving-boundary revalidation |

Phase 3 completion supplies design constraints only. These bindings do not mark
residual risk accepted and do not activate a mitigation runtime.

## Provider abstraction

Provider classes are abstract: `CELLULAR_CARRIER`, `HOSTED_TELEPHONY`,
`ENTERPRISE_TELEPHONY`, or fail-closed `UNKNOWN`. This design contains no vendor
configuration, provider SDK, network client, account access, endpoint, or
credential. A class is descriptive and cannot make transport trusted.

## Route states

The only route states are `UNCONFIGURED`, `DESIGN_ONLY`,
`PENDING_OWNER_AUTHORITY`, `PENDING_PROVIDER_VERIFICATION`,
`VERIFIED_NOT_ACTIVE`, `BLOCKED`, and `REVOKED`. Every state is non-operational.
There is no `ACTIVE` state. Unknown, missing, conflicting, expired, or
unverifiable state resolves to `BLOCKED`, never to a permissive state.

## Change control

A future route change requires the exact route identity, current trusted Human
Owner approval, exact action binding, expiry, replay protection, consume-once
semantics where applicable, and receiving-boundary revalidation. Approval for
one route, action, provider class, or time window cannot be transferred. A
missing, expired, replayed, consumed, mismatched, or unverifiable decision blocks
the change. A validator result and successful transport are evidence only.

## SIM-swap and takeover response

A carrier ownership change, port event, SIM/eSIM change, number takeover,
provider-account anomaly, or route mismatch immediately moves the affected route
to `BLOCKED` or `REVOKED`. Processing stops, existing verification is invalidated,
and sanitized evidence is retained. Recovery requires an independent trusted
owner path, a newly bound route record, current approval, fresh verification,
replay checks, and receiving-boundary revalidation. Carrier or number possession
alone cannot recover the route.

## Failover model

Failover may select only another separately defined and verified design record.
It must never weaken identity, freshness, authority, integrity, source binding,
privacy, or verification requirements. There is no automatic fallback to an
unknown provider, unverified number reference, stale approval, weaker factor, or
permissive route state. If equivalent controls are unavailable, failover blocks.

## Privacy model

Collect only opaque route identity, bounded classifications, policy state, and
sanitized provenance needed for a declared purpose. Redact transport metadata
at ingestion; never retain raw dialing data or provider-private identifiers.
Logs and reports use route IDs and state labels only. Access is least-privilege
and purpose-bound; exports are minimized, schema-validated, integrity-checked,
and sanitized. Unknown privacy classification is quarantined. Retention and
deletion follow approved policy, and deletion evidence remains sanitized.

## Phase 4 handoff

Phase 5 and later phases may consume only the reviewed design, validated schema,
enumerated non-operational states, abstract provider classes, threat bindings,
privacy rules, and sanitized validation evidence. They may not infer provider
availability, phone-number control, owner identity, device trust, approval,
route activation, or runtime readiness. Phase 4 completion does not authorize
device enrollment, provider activation, deployment, or any protected action.

## Acceptance matrix

| Requirement | Evidence | Pass condition | Downstream consumer |
|---|---|---|---|
| Exact identity | Phase identity table and schema constants | Phase 4, bundle, mode, and blocked transition are exact | Program coordinator |
| Routing contract | Schema and routing contract section | All required fields are closed and deterministic | Future route validator |
| Data boundary | Phone-number data boundary | Only opaque references; prohibited data is rejected | Future provider adapter |
| Source trust | Source trust model | Transport metadata and number possession confer no trust | Phases 5, 9, 11, and 13 |
| Threat binding | Threat table | Every Phase 4-owned threat ID is mapped | Phase 3 risk review |
| Route states | State section and schema | All states are non-operational and no active state exists | Future route state machine |
| Change control | Change control section | Current exact, expiring, replay-safe approval is mandatory | Approval boundary |
| Takeover response | SIM-swap response section | Anomaly blocks/revokes and requires independent recovery | Recovery designer |
| Failover | Failover section | Failover never downgrades a security requirement | Future routing layer |
| Privacy | Privacy section and schema | Minimized, redacted, purpose-bound metadata only | Privacy review |
| Handoff | Phase 4 handoff | Design evidence grants no activation or enrollment | Phase 5 and later phases |
| Owner gate | Owner gate section | Operational actions remain blocked | Human Owner and Approval Broker |

## Owner gate

Phase 4 design/preparation may complete autonomously behind the gate. Any action
that provisions, binds, verifies, activates, forwards, ports, modifies, or
operationalizes a real phone/provider route remains **BLOCKED** until valid
`OWNER-BUNDLE-2-DEVICE-IDENTITY` authority is separately verified. Phase 4
itself cannot consume that authority or perform the protected transition.
