CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN: HUMAN_OWNER_REVIEW_REQUIRED_BEFORE_EXECUTION
AI_OS BOOTSTRAP REQUIRED: READ_AND_OBEY_CURRENT_REPOSITORY_AGENTS_MD_BEFORE_EXECUTION
IDENTITY MARKER: AIOS_COMPOUND_WORK_BRAID_CONTINUATION_V1
SUPERVISOR IDENTITY: HUMAN OWNER ANTHONY
PACKET ID: PACKET-CABLE-1896B284C185
MODE: APPLY
ZONE: CODEX_CLOUD_LOCAL_REPOSITORY
WORKER IDENTITY: CODEX_CLOUD_ENGINEERING_WORKER_01
LANE: AIOS_ORCHESTRATION_COMPOUND_WORK_BRAID
WORKTREE: /workspace/Ai_Os
BRANCH: work
MISSION ID: MISSION-AIOS-CLOSING-THE-LOOP-V1
MISSION NAME: AI_OS Closing the Loop
PROGRAM ID: PROGRAM-AIOS-COMPOUND-AUTONOMY-V1
PROGRAM NAME: AI_OS Compound Engineering Autonomy
EPIC ID: EPIC-AIOS-WORK-BRAID-ORCHESTRATION-V1
EPIC NAME: AI_OS Work-Braid Orchestration
BUCKET ID: BUCKET-AIOS-OPEN-LOOP-CONSOLIDATION-V1
BUCKET NAME: Repository Open-Loop Consolidation
PACKET NAME: Compound canonical_work_packet_obligation

ALLOWED PATHS:
- automation/orchestration/bootstrap/Start-AiOsDay.ps1
- automation/orchestration/operator/AIOS_OPERATOR_RULES.json
- automation/orchestration/supervisor/Resolve-AiOsSupervisorAssignment.DRY_RUN.ps1
- automation/orchestration/work_packets/complete/PKT-CREW-CAMPAIGN-BRIDGE-DRYRUN.md
- automation/orchestration/work_packets/complete/PKT-FOREX-FIRST-DOLLAR-COUNTDOWN-CLI-EVIDENCE-V1.md
- docs/workflows/aios-operator-workflows.md

FORBIDDEN PATHS:
- AGENTS.md
- RISK_POLICY.md
- SECURITY.md
- .git/
- .github/
- .env
- secrets/
- credentials/
- private/
- automation/forex_engine/
- Every path not explicitly listed under ALLOWED PATHS.

APPROVAL AUTHORITY:
Human Owner Anthony must explicitly approve this continuation before execution. No protected action is authorized.

VALIDATOR CHAIN:
1. Read back every changed file.
2. Confirm every changed path is in ALLOWED PATHS.
3. Run targeted tests declared by the selected cable.
4. Run git diff --check.
5. Run git status --short --branch.

STOP POINT:
Stop after implementation, validation, evidence generation, and owner handoff. Do not stage, commit, push, open or modify a PR, merge, deploy, access credentials, access a broker, or place an order.

MISSION:
Execute the selected dependency-correct cable only after owner approval: Compound canonical_work_packet_obligation.

PREFLIGHT:
Run pwd, git status --short --branch, git branch --show-current, git remote -v, git rev-parse HEAD, git diff --name-only, and git diff --stat. Stop on state mismatch.

FINAL REPORT FORMAT:
SUMMARY:
WHAT CHANGED:
FILES CHANGED:
VALIDATION:
REMAINING DIRTY FILES:
SAFE NEXT COMMAND:
STATUS: COMPLETE, NO COMMIT, NO PUSH
