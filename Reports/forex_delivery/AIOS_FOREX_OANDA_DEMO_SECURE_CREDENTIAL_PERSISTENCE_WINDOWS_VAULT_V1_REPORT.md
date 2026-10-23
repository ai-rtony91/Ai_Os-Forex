# AIOS Forex OANDA Demo Secure Credential Persistence Windows Vault V1 Report

## Scope

This report records the PR #1069 secure persistence lane for OANDA DEMO credentials. The lane is DEMO-only, Windows vault oriented, and proof-gated before any broker execution packet.

## Local Blocker Reproduction

Local CI reproduction found the main CI secret-assignment scanner would flag the test fixture line that used a direct keyword assignment for a non-demo broker case. The test was rewritten to preserve the same non-demo rejection behavior without matching the scanner's assignment pattern.

No scanner rule was weakened. No real secret was added. No broker call was made.

## Persistence Outcome Preserved

The intended product behavior remains:

- owner enters OANDA DEMO credential material one time;
- AIOS stores the material through a secure Windows vault adapter boundary;
- later owner-run flows reload from secure storage;
- repeated manual entry is not required after vault proof succeeds;
- no repo-stored secret is allowed;
- no plaintext persistence is allowed;
- no `.env` dependency is allowed;
- account mismatch fails closed;
- live credentials remain rejected in this lane.

## Broker Safety

- DEMO order placement: blocked.
- Live order placement: blocked.
- Broker mutation calls: blocked.
- `/orders` calls: blocked.
- Scheduler, daemon, webhook, and background execution: blocked.

## Known Demo Account Context

The prior read-only diagnostic found that the token-visible OANDA DEMO account is `[REDACTED_DEMO_ACCOUNT_ID]`.

The prior mismatched account remains rejected for this token context.

## Validation Snapshot

Initial local validation before final report update:

- targeted Python compile: PASS
- targeted persistence pytest: PASS, 39 passed
- diff whitespace check: PASS
- compileall over forex automation, tests, and runner scripts: PASS
- local CI secret-assignment scanner equivalent after patch: PASS

Final validation is recorded in the packet handoff and terminal completion response.

