# AIOS Forex Broker-Paper Adapter Implementation Packet V1

## Status

Status: HUMAN_OWNER_APPROVAL_REQUIRED_IMPLEMENTATION_PACKET

Packet ID: PKT-AIOS-BROKER-PAPER-ADAPTER-IMPLEMENTATION-V1

Packet Name: Broker-Paper Adapter Implementation

Zone: FOREX_BROKER_PAPER_IMPLEMENTATION

Lane: broker-paper-adapter-implementation

Human Owner: Anthony Meza

## Identity Chain

- Mission ID: MISSION-AIOS-001
- Mission Name: AIOS Governed Self-Building Operating System
- Program ID: PRG-FOREX-001
- Program Name: AIOS Forex Supervised Operational Validation Program V1
- Epic ID: EPC-FOREX-004
- Epic Name: Production Transition
- Bucket ID: BKT-FOREX-008
- Bucket Name: Production Review
- Packet ID: PKT-AIOS-BROKER-PAPER-ADAPTER-IMPLEMENTATION-V1
- Packet Name: Broker-Paper Adapter Implementation

## Objective

Implement the minimum controlled broker-paper adapter that advances the approved paper-only plan into a paper/demo execution path with deterministic receipts, fail-closed boundaries, and no live authorization.

This packet bridges approved planning evidence into the first controlled broker-paper implementation surface. It does not authorize live execution.

## Scope

- Create the broker-paper adapter core that consumes approved paper/demo execution requests.
- Normalize BUY, SHORT, and LONG intent paths without changing strategy logic.
- Require explicit paper/demo environment verification before any broker-facing write path can be used.
- Emit deterministic evidence for intent, submission, acknowledgement, rejection/error, and final state.
- Keep live execution blocked.
- Keep broker writes paper/demo only and fail closed on any live boundary.
- Add tests for receipts, rejection behavior, and sandbox verification.

## Non-scope

- Live execution.
- Live credentials.
- Live account IDs.
- Live order routing.
- Strategy changes.
- Risk-limit changes.
- 30-trade campaign execution.
- Market-open campaign execution.
- Webhooks.
- Scheduler or daemon registration.
- Commit, push, PR, or merge authority.
- Claims of broker connectivity before the paper/demo implementation exists and is validated.

## Existing Interfaces

The implementation must reuse the following existing interfaces instead of creating a parallel safety stack:

- `automation/forex_engine/broker_paper_adapter_stub_contract.py`
- `automation/forex_engine/broker_paper_dryrun_intent_ledger.py`
- `automation/forex_engine/broker_paper_dryrun_risk_governor.py`
- `automation/forex_engine/broker_paper_dryrun_replay_harness.py`
- `automation/forex_engine/broker_paper_dryrun_replay_evidence_gate.py`
- `automation/forex_engine/broker_paper_adapter_plan_approval_gate.py`
- `automation/forex_engine/broker_paper_sandbox_readiness.py`
- `automation/forex_engine/schema_contracts.py`
- `automation/forex_engine/next_action_engine.py`
- `automation/forex_engine/long_only_supervisor_broker_proof_adapter_v1.py`
- `automation/forex_engine/oanda_long_only_broker_proof_intake_v1.py`

The approved plan gate proves the source evidence is ready and the approval artifact is plan-only.

The next-action engine already routes paper-only work toward `FOREX-LONG-RUN-PAPER-SUPERVISOR` and `RUN_PAPER_LONG_FORM_VALIDATION_CYCLE`, which is the next milestone after this adapter implementation is validated.

## Proposed Adapter Contract

The implementation surface should stay small and deterministic.

Proposed module path:

- `automation/forex_engine/broker_paper_adapter.py`

Proposed demo runner:

- `automation/forex_engine/run_broker_paper_adapter_demo.py`

Proposed test surface:

- `tests/forex_engine/test_broker_paper_adapter.py`
- `tests/forex_engine/test_broker_paper_adapter_receipts.py`
- `tests/forex_engine/test_broker_paper_adapter_sandbox_verification.py`

Proposed contract functions:

- `build_broker_paper_adapter_contract()`
- `evaluate_broker_paper_adapter()`
- `summarize_broker_paper_adapter()`
- `broker_paper_adapter_boundary_summary()`
- `classify_broker_paper_adapter()`

Proposed contract inputs:

- Approved plan evidence classified as `ADAPTER_PLAN_APPROVAL_READY`.
- A paper/demo execution request with normalized side, quantity, stop-loss, take-profit, and max-loss fields.
- A paper/demo environment verification record that proves the adapter is not pointed at a live endpoint.
- A human approval checkpoint record for the paper/demo execution phase.

Proposed contract outputs:

- `paper_only`
- `live_execution_allowed`
- `paper_broker_writes_allowed`
- `live_broker_writes_allowed`
- `submission_state`
- `acknowledgement_state`
- `rejection_state`
- `error_state`
- `final_state`
- `intent_receipt`
- `submission_receipt`
- `acknowledgement_receipt`
- `rejection_receipt`
- `error_receipt`
- `final_receipt`
- `evidence_bundle`

Supported order directions:

- `BUY`
- `SHORT`
- `LONG`

The `LONG` path must be normalized by the adapter but remain fail closed until the separate LONG validation milestone is satisfied.

## Safety Controls

- Paper/demo broker writes are allowed only when the adapter is in paper/demo mode, the approval gate is ready, the paper verification record is present, and no live boundary is detected.
- Live execution remains blocked in every code path.
- Any live credential, live account ID, live endpoint, live order flag, or live execution flag must force fail-closed behavior.
- Any missing receipt segment must fail closed and produce a terminal error state.
- Any acknowledgement that does not match the submitted intent must fail closed.
- Any broker response that cannot be sanitized must fail closed.
- Any network or broker path outside the approved paper/demo boundary must fail closed.

## Paper-Only Boundary

This packet allows paper/demo-only broker interaction in the future implementation, but it never allows live execution.

Boundary rules:

- `paper_only: true`
- `live_execution_allowed: false`
- `live_broker_writes_allowed: false`
- `live_orders_allowed: false`
- `live_trade_ready: false`
- `real_order_ready: false`
- `credentials_used_for_live: false`
- `broker_sdk_allowed_for_live: false`

Paper/demo broker writes are only valid for a paper/demo endpoint that has been explicitly verified and approved.

## Evidence / Receipt Contract

The adapter must emit a deterministic receipt chain with these stages:

- Intent receipt.
- Submission receipt.
- Acknowledgement receipt.
- Rejection receipt, when the broker or paper environment rejects the request.
- Error receipt, when the adapter fails closed.
- Final state receipt.

Receipt requirements:

- Every stage must be timestamped in UTC.
- Every stage must carry a stable intent identifier.
- Every stage must carry the same sanitized symbol, side, quantity, and request fingerprint.
- Every stage must exclude secrets, raw authorization headers, live account IDs, raw broker payloads, and live-only identifiers.
- Every stage must preserve the paper/demo boundary in the evidence payload.
- The final state must record whether the order was accepted, rejected, errored, or completed in paper/demo mode.

Evidence bundle requirements:

- The evidence bundle must prove intent -> submission -> acknowledgement/rejection/error -> final state.
- The evidence bundle must be reproducible in tests.
- The evidence bundle must be readable without any live execution claim.

## Failure / Rollback Behavior

- If plan approval is missing, return a blocked result and do not submit anything.
- If paper/demo verification is missing, return a blocked result and do not submit anything.
- If the adapter sees a live boundary, disable the path immediately and return a fail-closed result.
- If submission is attempted and acknowledgement is missing, record an error receipt and stop.
- If acknowledgement conflicts with the submitted intent, disable the adapter and stop further broker-facing writes.
- If any paper/demo receipt is incomplete or sanitized evidence cannot be built, stop and require operator review.

Rollback does not mean reverse a live action. Live actions are not part of this packet.

## Required Tests

The implementation must be covered by tests that prove:

- The packet doc matches this contract.
- The adapter refuses to operate without the approved plan gate.
- The adapter refuses to operate without paper/demo verification.
- The adapter keeps live execution blocked in every state.
- The adapter emits intent, submission, acknowledgement, rejection/error, and final-state receipts.
- The adapter fails closed on receipt mismatch.
- The adapter supports BUY, SHORT, and LONG normalization without changing strategy logic.
- The adapter does not weaken the existing dry-run evidence chain.
- The adapter remains compatible with the approved plan gate and the sandbox readiness chain.

## Acceptance Criteria

- This packet exists and is readable at the canonical docs path.
- The packet names the existing approval and evidence interfaces that must be reused.
- The packet defines a minimum implementation surface.
- The packet defines paper/demo-only boundaries and explicit fail-closed behavior.
- The packet defines the receipt chain from intent through final state.
- The packet defines the tests required before any paper broker connection is exercised.
- The packet keeps live execution blocked.
- The packet does not change strategy rules or risk limits.
- The packet does not claim broker connectivity.

## Human Owner Approval Checkpoint

Human Owner approval is required before any APPLY work that creates the adapter module, runner, or tests.

Human Owner approval is also required before:

- any paper/demo broker connection is exercised.
- any market-open paper execution is attempted.
- any campaign run is started.
- any LONG validation packet is promoted after adapter implementation.

This packet does not authorize live execution.

## Implementation Sequence

1. Add the paper/demo adapter contract and receipt schema.
2. Add the paper/demo verification step and fail-closed boundary checks.
3. Add the paper/demo submission, acknowledgement, rejection, error, and final-state receipt flow.
4. Add deterministic tests for the adapter and receipts.
5. Validate the adapter against the approved plan gate and the existing dry-run evidence chain.
6. Promote the result to the long-form paper validation cycle.
7. Continue to integrated BUY/SHORT/LONG paper execution only after LONG validation passes.
8. Continue to market-open controlled paper execution only after integrated paper execution is proven.
9. Continue to the 30-trade paper campaign only after market-open paper execution is proven.
10. Continue to reconciliation, performance evidence, live-readiness audit, and governed live execution only after the prior gates pass.

## Post-Implementation Validation Gate

The next milestone after this packet is the long-form paper validation cycle:

- `FOREX-LONG-RUN-PAPER-SUPERVISOR`
- `RUN_PAPER_LONG_FORM_VALIDATION_CYCLE`

This validation comes after the adapter implementation is complete and verified. It does not authorize live execution.

## Explicit Live-Execution Statement

Approval of this packet does not authorize live execution.

Approval of this packet does not authorize live credentials.

Approval of this packet does not authorize live broker writes.

Approval of this packet does not authorize live order submission.

Approval of this packet does not authorize the 30-trade campaign.

Approval of this packet does not authorize governed live execution.
