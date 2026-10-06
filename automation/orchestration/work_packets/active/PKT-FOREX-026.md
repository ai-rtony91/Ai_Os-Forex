CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-026
PACKET NAME: Resumable Edge Research Checkpoint
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_61
LANE: FOREX_RESUMABLE_EDGE_RESEARCH_CHECKPOINT
WORKTREE: C:\Dev\Ai.Os
BRANCH: main

MISSION ID: MISSION-AIOS-001
MISSION NAME: AIOS Governed Self-Building Operating System
PROGRAM ID: PRG-FOREX-001
PROGRAM NAME: AIOS Forex Supervised Operational Validation Program V1
EPIC ID: EPC-FOREX-002
EPIC NAME: Strategy Intelligence V1
BUCKET ID: BKT-FOREX-003
BUCKET NAME: Strategy Validation V1

ALLOWED PATHS:
- automation/orchestration/work_packets/active/PKT-FOREX-026.md
- .aios/staging/PKT_FOREX_026/
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json only through claim and release scripts

FORBIDDEN PATHS:
- every path not listed above
- .git/
- AGENTS.md
- RISK_POLICY.md
- Reports/
- .aios/runtime/
- broker/
- oanda/
- secrets/
- credentials/
- live_trading/

APPROVAL AUTHORITY: Anthony explicitly requires a hash-verified RESUMABLE_EDGE_RESEARCH checkpoint at a runtime boundary. No commit, push, merge, promotion, broker access, credentials, PAPER, Practice, LIVE, orders, or money movement is authorized.

PROTECTED ACTION RULE: Commit, push, and merge each need separate explicit approval. Approval does not transfer between actions.

PREFLIGHT:
- require registry SHA-256 7648dd1a2978d17ef44bfb90ff356d3275ea9ddcae217c61a9107d7f7d72ad6d
- require zero active locks
- claim exactly LOCK_EAST_FOREX_RESUMABLE_EDGE_RESEARCH_CHECKPOINT_OCC61

MISSION:
Preserve the exact post-PKT-FOREX-025 state and next materially distinct historical-research action without opening later data or changing strategy evidence.

OBJECTIVE:
Write one deterministic machine-readable checkpoint, validate it, release only OCC61, and finish with zero active locks.

VALIDATOR CHAIN:
- packet governance and completeness
- python -m json.tool checkpoint
- SHA-256 readback
- lock registry integrity
- exact OCC61 release and zero-active-lock verification
- git diff --check

STOP POINT:
After checkpoint validation and OCC61 release. Resume with a bounded Stage-0 duplicate and capacity gate for MONTH_END_FIX_CROSS_SECTIONAL_REBALANCING_REVERSAL.

SAFE NEXT ACTION:
On resume, verify checkpoint hash and post-release registry hash, then preregister the month-end fix candidate without using validation or final-holdout data.

FINAL REPORT FORMAT:
Forced RESUMABLE_EDGE_RESEARCH checkpoint only. No normal completion report.
