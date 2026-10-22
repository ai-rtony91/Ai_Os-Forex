CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS VERIFIED FOREX METRICS TRUTH FEED V1
SUPERVISOR IDENTITY: HUMAN OWNER ANTHONY
MISSION ID: AIOS-SINGLE-RUNTIME
MISSION NAME: AI_OS Single Runtime
PROGRAM ID: AIOS-RUNTIME-CONSOLIDATION
PROGRAM NAME: AI_OS Runtime Consolidation
EPIC ID: AIOS-FOREX-METRICS-TRUTH-V1
EPIC NAME: Verified Forex Metrics Truth
BUCKET ID: AIOS-CABLE-B
BUCKET NAME: Verified Metrics Truth Feed
PACKET ID: AIOS-FOREX-METRICS-TRUTH-V1-DRY-RUN
PACKET NAME: Inspect AI_OS Verified Forex Metrics Truth Feed V1
MODE: DRY_RUN
ZONE: LOCAL_REPOSITORY
WORKER IDENTITY: EAST_OCC_FOREX_TRUTH_01
LANE: FOREX_METRICS_TRUTH_DISCOVERY
WORKTREE: /workspace/Ai_Os
BRANCH: resolve after preflight (generation branch: work)
OBSERVED HEAD: resolve after preflight (generation baseline: 49a59a4b0eae39139e985ec1ea10d5819e49cb10)
ALLOWED PATHS: automation/forex_engine/**, tests/forex_engine/**, schemas/**, docs/**, Reports/** (read only)
FORBIDDEN PATHS: credentials/**, secrets/**, .env, .env.*, infrastructure/**, deployment/**, broker adapters, order execution
APPROVAL AUTHORITY: Human Owner Anthony authorizes read-only discovery only.
COMMIT AUTHORITY: NOT AUTHORIZED
PUSH AUTHORITY: NOT AUTHORIZED
PULL REQUEST AUTHORITY: NOT AUTHORIZED
VALIDATOR CHAIN: repository preflight; source/test/schema inventory; risk-policy review; no-write status proof.
MISSION: Identify the canonical source, validation evidence, ownership conflicts, and smallest safe implementation boundary for a verified Forex metrics truth feed. Do not implement or mutate files.
PREFLIGHT: Run pwd; git status --short --branch; git branch --show-current; git rev-parse HEAD; git remote -v. Stop on observed-state mismatch.
FINAL REPORT: Owner View followed by DRY_RUN summary, tested evidence, findings, recommendation, safe next command, and unchanged-file proof.
STOP POINT: Stop after read-only findings and a state-aligned APPLY packet proposal. Do not edit, commit, push, publish, merge, deploy, access credentials, call a broker, or place orders.
