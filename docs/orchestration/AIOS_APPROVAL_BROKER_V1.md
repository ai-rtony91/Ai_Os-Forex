# AIOS Approval Broker V1

## Purpose and authority boundary

`ApprovalBroker` is the canonical phase-facing approval-routing interface for the
seventeen-phase owner-authority workflow. It consolidates phase requirements,
binds externally supplied decisions to their receipts, projects one operator
queue, and reports whether bound phases are eligible to resume.

The broker is **not** the Human Owner and is **not** an approval authority. It
does not authenticate anyone, create approval records, inspect an approval
inbox, enroll devices, handle credentials, or execute protected actions. An
approval fails closed unless an external trusted verifier is injected and
accepts the complete decision record. Future approval-authority integration must
use this narrow verifier interface.

Unmerged pull-request components are architecture evidence only. They are not
automatically canonical, and this broker does not copy or depend on them.

## Phase directives

Phases 1, 12, and 13 return `CONTINUE_AUTONOMOUSLY` without a separate owner
checkpoint. Every owner-controlled phase returns `PREPARE_BEHIND_GATE` until a
trusted, correctly bound, unexpired decision is accepted. Only then may the
broker return `RESUME_AUTHORIZED`; the receiving component remains responsible
for its own execution gates and the broker executes nothing.

While the protected transition is blocked, declarative preparation may continue.
That can include documentation, schemas, tests, manifests, routing tables,
validation artifacts, and sanitized preparation receipts. No asynchronous
worker, scheduler, daemon, timer, polling loop, or background process is
introduced.

## Four V1 owner bundles

These are the only V1 operator checkpoints:

1. `OWNER-BUNDLE-1-POLICY`: phases 2, 3, 6, 7, 8, 10, and 11.
2. `OWNER-BUNDLE-2-DEVICE-IDENTITY`: phases 4, 5, and 9.
3. `OWNER-BUNDLE-3-RUNTIME-SECRETS`: phases 14, 15, and 16.
4. `OWNER-BUNDLE-4-LOCATION-PRIVACY`: phase 17.

The queue contains at most one item per bundle and is always ordered from bundle
1 through bundle 4. It contains sanitized operational metadata only. Tokens,
passwords, private keys, passkey or YubiKey material, phone numbers, exact
locations, account identifiers, raw approval payloads, and credential values do
not belong in the queue.

## Decision binding

A decision must provide a non-empty receipt ID, the exact bundle ID, the exact
ordered bundle phase set, `APPROVE` or `REJECT`, an authority-source identifier,
a timezone-aware issuance time, and an optional expiry time. Duplicate receipt
IDs, partial or cross-bundle phase sets, unknown decisions, expired approvals,
missing verifiers, verifier rejection, and verifier exceptions fail closed.

## Operator-facing projection example

```text
Pending approvals:
- Device / Identity Bundle
- Runtime / Secrets Bundle

Unblocked preparation:
- Continuing

Protected actions:
- Blocked until trusted owner approval
```

This projection is declarative state. It is not evidence that work is running in
the background.
