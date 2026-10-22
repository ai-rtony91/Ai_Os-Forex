# AIOS Owner Authority Workflow V1

## Purpose

This is **Part B** of the post-A/B/C/D 17-phase gateway program.

Its job is to remove repeated operator stop/go loops. AIOS should prepare as much engineering work as possible and collect only the actions that cannot be delegated to software. Owner work is consolidated into a small number of authority bundles.

This document is subordinate to `AGENTS.md`. It does not grant authority, alter protected-action policy, or bypass any existing approval gate.

## Operating rule

The workflow uses **PREPARE_BEHIND_GATE**:

1. AIOS may inspect, design, implement, test, document, and prepare evidence for a phase when those actions are permitted by existing repository policy.
2. When a phase reaches a non-delegable action, AIOS records that action in the appropriate owner bundle instead of repeatedly interrupting the owner.
3. AIOS may continue preparing downstream work that does not cross the protected boundary.
4. A protected transition stays blocked until a trusted owner-approval receipt is supplied through an existing approved authority path.
5. After the receipt is validated upstream, AIOS may resume the corresponding work automatically.

The canonical phase-facing interface is `ApprovalBroker`, documented in
`AIOS_APPROVAL_BROKER_V1.md`. The broker is non-authoritative: it does **not**
validate owner identity or create approval receipts. It accepts a decision only
through an injected trusted-verifier interface, then reports resume eligibility
without executing the protected transition.

## Maximum owner interaction target

The 17 phases are consolidated into **four planned owner sessions maximum**:

| Bundle | Phases | Owner purpose |
|---|---:|---|
| `OWNER-BUNDLE-1-POLICY` | 2, 3, 6, 7, 8, 10, 11 | Privacy, residual risk, confidence, fallback, liveness, memory, and risk-threshold policy |
| `OWNER-BUNDLE-2-DEVICE-IDENTITY` | 4, 5, 9 | Phone/provider control, trusted-device enrollment, YubiKey/passkey possession |
| `OWNER-BUNDLE-3-RUNTIME-SECRETS` | 14, 15, 16 | Runtime activation, The_Lab authority boundary, protected vault/session configuration |
| `OWNER-BUNDLE-4-LOCATION-PRIVACY` | 17 | Explicit location/privacy consent |

Phases 1, 12, and 13 require no separate owner checkpoint under this V1 plan.

Four is a consolidation target, not permission to suppress a genuinely non-delegable action discovered later. Any newly discovered protected action must remain blocked unless existing authority already covers it.

## Safety boundaries

This milestone performs no:

- passkey or YubiKey enrollment;
- secret or credential storage;
- phone-provider mutation;
- voice call or SMS operation;
- runtime deployment;
- broker or trading operation;
- location access;
- automatic approval;
- automatic merge authority.

The manifest stores only descriptions of owner actions. Secret values, recovery codes, private keys, access tokens, and passkey material must never be written into the repository.

## Canonical broker integration

Part A remains the engineering/autonomy lane. Existing callers may continue to
use compatibility projections, while new phase-facing work calls:

- `ApprovalBroker.classify_phase()`
- `ApprovalBroker.prepare_phase()`
- `ApprovalBroker.build_queue()`

The broker delegates phase classification, four-bundle queue consolidation, and
trusted-decision binding. It is a sidecar authority check around the existing
A/B/C/D task lifecycle, not a replacement controller, approval authority, or
second governance head. The manifest remains the sole phase-to-bundle mapping.

The four bundles above are the only V1 operator checkpoints. Phases 1, 12, and
13 continue without a checkpoint. Protected actions remain blocked until
trusted verification succeeds, but documentation, schemas, tests, manifests,
routing tables, validation artifacts, and sanitized preparation receipts may
continue declaratively.

No asynchronous worker, daemon, scheduler, network poller, timer, or background
loop is introduced. Secret values and physical enrollment data never belong in
the broker queue. Future approval-authority integrations must implement the
narrow trusted-verifier interface. Components found only in unmerged pull
requests are not automatically canonical.

## Deletion/consolidation rule

No existing file should be deleted merely because Part B exists. Delete or supersede an artifact only after repository evidence proves it is a duplicate of this workflow and the deletion is within an approved change scope.
