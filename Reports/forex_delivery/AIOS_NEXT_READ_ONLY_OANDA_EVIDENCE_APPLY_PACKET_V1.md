CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

MODE: APPLY
ZONE: LOCAL_REPOSITORY
WORKER IDENTITY: EAST_OCC_02
LANE: FOREX_READ_ONLY_EVIDENCE_RECONCILIATION
WORKTREE: /workspace/Ai_Os
BRANCH: Resolve during preflight; do not assume.

MISSION ID: AIOS-FIRST-LIVE-TRADE-READINESS
MISSION NAME: First Repository-Approved Live Trade Readiness
PROGRAM ID: AIOS-FOREX
PROGRAM NAME: AIOS Forex
EPIC ID: OPERATOR-VALIDATION-CLOSURE
EPIC NAME: Operator Validation Closure
BUCKET ID: READ-ONLY-OANDA-EVIDENCE
BUCKET NAME: Read-Only OANDA Evidence Approval And Reconciliation
PACKET ID: AIOS-READ-ONLY-OANDA-EVIDENCE-APPLY-V1
PACKET NAME: Generate and validate sanitized read-only OANDA evidence approval

SUPERVISOR IDENTITY: Codex East Worksite Supervisor

OBJECTIVE
Generate and validate sanitized read-only OANDA evidence approval and reconciliation artifacts without broker writes, order placement, credential persistence, live execution, push, merge, deploy, or runtime mutation.

ALLOWED PATHS
- src/forex_delivery/read_only_live_data_bridge.py
- src/forex_delivery/read_only_evidence_approval.py
- scripts/forex_delivery/run_read_only_live_data_bridge.py
- scripts/forex_delivery/run_read_only_evidence_approval.py
- tests/forex_delivery/test_read_only_live_data_bridge.py
- tests/forex_delivery/test_read_only_evidence_approval.py
- Reports/forex_delivery/

FORBIDDEN PATHS
- .env
- credentials
- secrets
- OANDA/
- broker credential stores
- live order placement paths
- deployment paths
- scheduled tasks
- startup persistence
- apps/dashboard/assets/
- RISK_POLICY.md
- AGENTS.md
- README.md

APPROVAL AUTHORITY
Human Owner Anthony authorizes bounded repository APPLY for sanitized read-only evidence code/tests/reports only. No authority is granted for live trading, demo orders, credentials, broker writes, push, merge, deployment, or money movement.

PREFLIGHT
Run:
- pwd
- git status --short --branch
- git branch --show-current
- git remote -v
- rg -n "read_only_live_data_bridge|read_only_evidence_approval|OANDA_READ_ONLY_SANITIZED|live_micro_trade_arming_gate" src scripts tests docs Reports -S
Stop if dirty files are unrelated or outside the allowed paths.

REQUIRED WORK
1. Read `AGENTS.md`, `RISK_POLICY.md`, `docs/forex_delivery/AIOS_FOREX_READ_ONLY_EVIDENCE_APPROVAL_AND_RECONCILIATION_V1.md`, and related read-only bridge tests.
2. Verify the read-only bridge never reads `.env`, never persists secrets/account identifiers, never writes broker payloads, never places orders, and never calls broker write endpoints.
3. Generate or refresh only sanitized read-only evidence and approval/reconciliation report artifacts under `Reports/forex_delivery/`.
4. Preserve all live execution blocks and keep `live_execution_allowed` false.
5. Add or repair focused tests for sanitizer behavior, freshness, open-position reconciliation, daily P/L availability, margin/risk availability, and no-secret/no-account-output behavior.
6. Do not connect credentials, call OANDA, place orders, enter demo orders, or mutate broker state.

VALIDATOR CHAIN
- python -m pytest -q tests/forex_delivery/test_read_only_live_data_bridge.py tests/forex_delivery/test_read_only_evidence_approval.py
- python -m py_compile src/forex_delivery/read_only_live_data_bridge.py src/forex_delivery/read_only_evidence_approval.py scripts/forex_delivery/run_read_only_live_data_bridge.py scripts/forex_delivery/run_read_only_evidence_approval.py
- git diff --check
- git status --short --branch
If PowerShell exists, run repository-required PowerShell parser checks for changed `.ps1` files. If unavailable, report as PLATFORM_BLOCKED.

STOP POINT
Stop after sanitized read-only evidence and tests are complete. Do not commit, push, merge, deploy, connect broker credentials, place orders, or arm live trading unless separately instructed by Anthony in a new packet.

FINAL REPORT FORMAT
WHAT HAPPENED:
IS IT SAFE:
WHAT DO I DO NEXT:
HOW CLOSE ARE WE:
WHICH MODE SHOULD I USE:

SUMMARY:
FILES CHANGED:
VALIDATION:
PLATFORM-BLOCKED TESTS:
FOREX BLOCKERS REDUCED:
FOREX BLOCKERS REMAINING:
COMMIT STATUS:
PUSH STATUS:
STATUS:
