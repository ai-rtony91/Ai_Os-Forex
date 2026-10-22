# AIOS Owner Cellular Voice Gateway Program Charter V1

## Purpose

The Owner Cellular Voice Gateway program defines a governed future path for
carrying trusted Human Owner commands across a cellular voice channel to the
AIOS receiving boundary. This Phase 1 charter establishes the architecture,
authority, safety, dependency, and acceptance contract only. It does not build,
activate, or deploy the gateway.

## Scope

The eventual gateway may translate a command that entered through a separately
verified trusted command-entry boundary into a bounded request for AIOS. Each
later phase must preserve the command's provenance, apply its own verification
and policy gates, and stop at every protected transition until the applicable
owner authority is verified. This charter is the common contract used to design
those later phases; it is not a runtime component or an authority source.

## Non-goals and safety exclusions

Phase 1 does not implement or activate any of the following:

- phone-number provisioning, SMS/MMS, cellular-provider integration, carrier
  APIs, call initiation, or inbound call handling;
- microphone capture, speech recognition, speaker recognition, biometric
  enrollment, liveness verification, or replay-protection runtime;
- device enrollment, Z Fold trust activation, passkeys, or YubiKey enrollment;
- credentials, secrets, vault access, or protected session configuration;
- location collection, location storage, or a location capability;
- a runtime execution bridge, The_Lab execution, or deployment; or
- trading, broker access, orders, or money movement.

Those capabilities belong to later, separately governed work. Phase 1 also does
not create an owner decision, approval receipt, background worker, network
connection, external-system mutation, or automatic approval.

## Trust boundary

- **Human Owner:** the only final authority for protected owner decisions.
- **Trusted command-entry boundary:** a future boundary that must prove command
  origin and integrity under later-phase controls before AIOS may trust input.
  This charter does not designate any phone, device, identity, or provider as
  trusted.
- **Approval Broker:** the canonical non-authoritative router. It may classify
  phases and bind a decision accepted by an injected trusted verifier, but it
  cannot authenticate the owner, create approval authority, or execute a
  protected transition.
- **AIOS receiving boundary:** the future fail-closed contract endpoint that may
  accept a verified, policy-compliant command envelope. Receipt of an envelope
  does not itself authorize execution.
- **External systems:** carriers, devices, identity providers, vaults, runtime
  hosts, location services, and other external components are untrusted until a
  later phase separately verifies them under its applicable authority gate.

## Authority model

Phase 1 has `owner_authority = NONE` and can establish this declarative contract
without an owner checkpoint. That classification grants no authority to any
later phase or protected transition. The Approval Broker remains
non-authoritative. Protected transitions remain blocked until a trusted decision
for the existing owner bundle is supplied and all receiving-component gates also
pass.

Phases 1, 12, and 13 may continue autonomously without a separate owner
checkpoint. Phases 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15, 16, and 17 are
owner-gated at their protected transitions. Permitted declarative preparation
may continue behind those gates, but preparation is not authorization.

## Canonical 17-phase dependency map

The ordered program phases are:

1. Owner Cellular Voice Gateway Program Charter
2. Full Conversation Context Archive Design
3. Gateway Threat Model
4. Phone Number Routing Model
5. Z Fold 6 Trusted Command Terminal Model
6. Voice Recognition Confidence Model
7. Sick-Day and Voice Fallback Model
8. Anti-Replay and Time-Bound Liveness Model
9. YubiKey and Passkey Authority Model
10. Governance Memory Model
11. Risk-Scored Command Gating Model
12. Command Intent Parser Contract
13. AIOS Gateway Router Contract
14. Runtime Bridge Architecture
15. The_Lab Execution Routing
16. Vault, Secrets, and Session Protection
17. Location Vault and Privacy Broker

The sequence is a dependency and authority map, not permission to activate one
phase merely because an earlier document exists. Each downstream phase must
prove its own entry criteria and preserve all applicable gates.

## Four owner bundles

The canonical V1 owner checkpoints remain exactly:

| Bundle | Phases |
|---|---:|
| `OWNER-BUNDLE-1-POLICY` | 2, 3, 6, 7, 8, 10, 11 |
| `OWNER-BUNDLE-2-DEVICE-IDENTITY` | 4, 5, 9 |
| `OWNER-BUNDLE-3-RUNTIME-SECRETS` | 14, 15, 16 |
| `OWNER-BUNDLE-4-LOCATION-PRIVACY` | 17 |

## Phase handoff contract

Before Phase 2 or any later implementation relies on Phase 1, validation must
prove that:

1. the charter matches the canonical manifest's exact 17 phase identities,
   autonomous set, owner-gated set, and four bundle assignments;
2. the Human Owner, command-entry, Approval Broker, AIOS receiving, and external
   system trust boundaries are explicit;
3. the Approval Broker is described only as a non-authoritative router;
4. all listed runtime, identity, communication, secret, location, deployment,
   trading, broker, order, and money-movement capabilities remain excluded;
5. no downstream authority or implementation is implied; and
6. the acceptance matrix passes through automated tests and review.

A downstream phase consumes this charter only as an architectural constraint.
It must use the canonical manifest for phase and bundle data and must obtain its
own approval and validation evidence where required.

## Acceptance matrix

| Requirement | Evidence | Pass condition | Downstream consumer |
|---|---|---|---|
| Purpose and bounded scope | Purpose, Scope, and Non-goals sections | Charter is contract-only and claims no gateway implementation | All phases |
| Trust boundary | Trust boundary section | All five boundary roles are explicit and external systems default to untrusted | Phases 2-17 |
| Authority model | Authority model section and canonical manifest | Phase 1 is `NONE`; protected phases and broker remain gated/non-authoritative | Approval Broker and phases 2-17 |
| Ordered dependencies | Canonical 17-phase dependency map | Names and order exactly match the manifest | Phase planners and routers |
| Autonomous routing | Authority model | Exact set is 1, 12, and 13 | Approval Broker |
| Owner-gated routing | Authority model | Exact set is 2-11 and 14-17, excluding autonomous phases | Approval Broker and receiving components |
| Owner consolidation | Four owner bundles table | Exact four IDs and phase sets match the manifest | Owner queue projection |
| Safety exclusions | Non-goals and safety exclusions | Every prohibited capability is expressly excluded from Phase 1 | All implementation phases |
| Handoff | Phase handoff contract | Entry evidence and downstream obligations are explicit | Phases 2-17 |
| Fail closed | Fail-closed rule | Undefined authority or boundary cannot be inferred | Every component |

## Fail-closed rule

Any undefined, inconsistent, missing, or unverifiable authority, dependency,
trust boundary, owner decision, or protected transition remains **BLOCKED**. No
worker or component may infer permission from silence, phase order, preparation
work, a validator result, or Approval Broker output.
