CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

CONTRACT TITLE
AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1

IDENTITY MARKER
AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1

SUPERVISOR IDENTITY
ChatGPT planning supervisor

WORKER IDENTITY
Codex

MODE
APPLY

ZONE
Trading Lab / Forex

LANE
Forex Owner Safety Evidence Intake Verification Prep

WORKTREE
C:\Dev\Ai.Os

BRANCH
codex/forex-edge-autopilot-20261008

MISSION / PROGRAM / EPIC / BUCKET / PACKET IDENTITY
Mission ID: MISSION-AIOS-FOREX-FINISH-LINE-V1
Mission Name: Governed Forex Finish Line
Program ID: PROGRAM-FOREX-PROFIT-AUTONOMY-V1
Program Name: Forex Profit Autonomy System
Epic ID: EPC-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-001
Epic Name: Owner Safety Evidence Intake And Verification Prep
Bucket ID: BKT-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-001
Bucket Name: Owner Safety Evidence Intake Template And Classifier
Packet ID: PKT-FOREX-OWNER-SAFETY-EVIDENCE-INTAKE-VERIFICATION-PREP-V1
Packet Name: Build Owner Safety Evidence Intake Verification Prep V1

APPROVAL AUTHORITY
Human Owner approval is required before APPLY execution, commit, push, PR creation, broker/API use, credential use, live trading authorization, scheduler activation, daemon activation, webhook activation, dashboard mutation, or order execution.
A later Human Owner message that explicitly approves commit is required before commit.
A later Human Owner message that explicitly approves push is required before push.

PREFLIGHT
cd C:\Dev\Ai.Os
git status --short --branch
git branch --show-current
git log -1 --oneline

ALLOWED PATHS
Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json
Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json
Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md
Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md
automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py
scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py
tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py

FORBIDDEN PATHS
AGENTS.md
README.md
WHITEPAPER.md
RISK_POLICY.md
.env
secrets
credential files
broker account identifiers
broker modules outside allowed files
scheduler files
daemon files
webhook files
dashboard mutation files
unrelated docs
unrelated tests
any path outside C:\Dev\Ai.Os

RULES
Do not read .env.
Do not use credentials.
Do not use broker API.
Do not authorize live trading.
Do not place trades.
Do not start schedulers, daemons, loops, webhooks, or background workers.
Do not create PR.
Do not commit.
Do not push.

MISSION
Prepare next owner-facing packet handoff after local, sanitized evidence intake classification.
Do not claim verified evidence unless explicit verification exists.
Do not infer evidence from report text.

VALIDATOR CHAIN
python -m py_compile automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py
python -m pytest tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py -q
python scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py --write-template --write-state --write-report --input-template-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json --template-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json --state-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json --report-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md --next-packet-output-path Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md
python -m json.tool Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json
python -m json.tool Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json
python automation/validators/aios_governance_validator.py --input Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md
git diff --check -- automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py scripts/forex_delivery/run_forex_owner_safety_evidence_intake_verification_prep_v1.py tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_TEMPLATE_V1.json Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md
git status --short --branch

SAFE NEXT ACTION
Owner must refresh stale evidence entries with current sanitized artifacts. Then route to later verification packet only when explicit verification mechanism is available.

STOP POINT
Stop after validators and final report.
Do not commit.
Do not push.
Do not create PR.

FINAL REPORT FORMAT
CURRENT_BRANCH:codex/forex-edge-autopilot-20261008
CURRENT_HEAD:4fdf3061
MISSING_CONTROLS:none
PRESENT_UNVERIFIED_CONTROLS:
STALE_CONTROLS:kill_switch_state, daily_stop_state, max_loss_state, monitoring_ready
INVALID_CONTROLS:
OWNER_EVIDENCE_COMPLETION_PERCENT:0.0
NEXT_RESULT_STATUS:OWNER_SAFETY_EVIDENCE_INTAKE_REVIEW
VERIFICATION_CLAIMED:False
BROKER_API_USED:False
CREDENTIALS_USED:False
ORDER_EXECUTION:False
LIVE_TRADING_AUTHORIZED:False
