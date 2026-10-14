# AI_OS Repo Memory

## Purpose

This file records the latest operator-confirmed repo state that future AI_OS workers should consult before asking the operator to repeat known push-state, dirty-state, or queue-state checks.

This memory is a starting context, not command authority. If the branch changes, a new commit or push occurs, or local evidence contradicts this file, workers must mark the mismatch and refresh the state through the normal governed workflow.

## Last Updated

- Timestamp: 2026-08-07
- Updated by: Codex worker, lane `REPO_MEMORY_STATE_ALIGNMENT`

## Last Known Push State (historical, not refreshed)

main is synced with origin/main after the latest push.

## Last Pushed Commits

- ee2129a chore: establish archive structure for OneDrive snapshots
- 3a88c6c docs(governance): clarify AI_OS naming and repo path authority
- d333cd6 Add hard duplicate-prevention rule for Codex workers

## Historical Local Dirty State (2026-06-05; stale)

- README.md is modified and unstaged.
- Multiple untracked automation/ and docs/ files remain local.
- AGENTS.md duplicate-prevention rule is committed and pushed.

## Historical Pending Local Work (2026-06-05; stale)

- Classify remaining untracked automation/ and docs/ files before assigning fixed parallel worker lanes.
- Decide whether the local README.md modification should be kept, reverted, or moved into a scoped lane.
- Keep untracked local material out of authority until it is classified.

## Historical Next Safe Queue (2026-06-05; stale)

1. Classify remaining untracked automation/ and docs/ files.
2. Decide whether README.md should be kept, reverted, or moved into a lane.
3. Do not create fixed parallel worktrees until the dirty local state is classified.
4. Do not repeatedly ask the operator to re-check the already-known push state unless the branch changes or a new commit/push occurs.

## Current Verified Repository State

- Verified timestamp: 2026-08-07.
- Verified worktree: `C:\Dev\Ai.Os`.
- Verified branch: `main`.
- Verified HEAD: `a5a941835cb7e797694e76074a7573a1ca23d415`.
- Verified origin: `https://github.com/ai-rtony91/Ai_Os.git`.
- Working tree: dirty only because this memory file is intentionally modified; `git status --short --branch` returns `## main...origin/main` and ` M docs/governance/AI_OS_REPO_MEMORY.md`.
- README.md modified: no; `git diff -- README.md` returned no output.
- Untracked-file count: `0`; `git status --short` returned no output.
- Current live Git evidence supersedes the historical dirty-state snapshot for present execution decisions.
- Future contradictions must fail closed and trigger another governed repo-memory refresh.

## Worker Rule

Before asking for another git status or push-state confirmation, workers must read this memory file and use it as the starting context.

Workers should re-check git state only when one of these applies:

- The branch changed.
- A new commit or push occurred.
- The worker needs current file-level evidence before editing.
- The recorded memory conflicts with visible repo evidence.
- The operator explicitly requests a fresh status check.

## Assessment Memory Loop

Purpose:

Future AI_OS assessments and reassessments must check this memory before producing conclusions. This section is a recurrence-prevention control, not new approval authority. It records prior fixes, accepted risks, expected outcomes, regression checks, and reopen conditions so future workers do not repeat known mistakes or create duplicate governance.

Assessment loop:

1. Run the current-state assessment from repo evidence.
2. Review the latest relevant memory entry below.
3. Compare the current issue against prior problems, root causes, fixes, and accepted risks.
4. Decide whether the issue is new, an old regression, or a duplicate-authority risk.
5. Reopen a prior decision only when current evidence matches a listed reopen condition.

Future-assessment checklist:

- What did the last assessment conclude?
- What changed since?
- Did the expected improvement happen?
- Did the old issue return?
- Did the fix create a new bottleneck?
- Is this a new issue or an old regression?
- Are we creating duplicate authority?
- Should this decision be reopened?

### Tracked Reassessment Themes - 2026-06-05

#### Blast Radius Governance

- Problem discovered: Governance burden was being applied too broadly, causing low-risk inspection and planning work to inherit packet burdens meant for higher-risk mutation or production work.
- Root cause: Governance rules did not clearly scale required process to actual blast radius before packet validation began.
- Fix applied: Added a tiered blast-radius model in `AGENTS.md` through commit `8de08e3 docs(governance): align governance burden with blast radius`.
- Expected outcome: Low-risk read-only and planning work can proceed with lighter governance, while local apply, authority changes, production, secrets, trading, broker/API, and protected actions remain strict.
- Accepted risk: Tier classification can be misread if future packets omit scope or hide mutation behind analysis wording.
- Regression checks: Confirm future packets classify READ_ONLY, DRY_RUN PLAN, SANDBOX_OUTPUT, LOCAL_APPLY, PROMOTION, or PRODUCTION_OR_LIVE before validation; confirm protected actions still require explicit approval.
- Reopen conditions: Reopen if low-risk work is blocked by excessive packet burden again, or if the tier model is used to weaken commit, push, merge, secrets, live trading, broker/API, or authority gates.

#### Morning Brief v2

- Problem discovered: Morning decision surfaces mixed active approval decisions with examples, completed records, and stale digest state.
- Root cause: Presentation logic counted raw pending-human-review items without enough filtering for example records, completed approvals, and stale projection mismatches.
- Fix applied: Added repeatable Morning Brief v2 output in commit `3489f61 feat(night-supervisor): add repeatable morning brief v2 output`, then refined consumption during Bridge Intelligence v1 work.
- Expected outcome: Morning Brief v2 presents current active decision cards separately from noise and stale-state warnings.
- Accepted risk: Digest state and markdown can still be stale if only the bridge state is refreshed or if old generated outputs are read as current.
- Regression checks: Confirm `MORNING_BRIEF_V2_LATEST.json` exposes active decision cards, noise cards, stale-state warnings, `recommendation_only`, and current status fields; confirm examples and completed records are not counted as active approvals.
- Reopen conditions: Reopen if Morning Brief v2 again shows completed records, examples, or stale relay/digest artifacts as active approval work.

#### Bridge Intelligence v1

- Problem discovered: Autonomy Bridge reported `BLOCKED` while the latest Night Supervisor report was `READY`.
- Root cause: Bridge status scanned broad historical/source artifacts and allowed any classified blocked item to dominate top-level status.
- Fix applied: Committed Bridge Intelligence v1 in `5ef27a8 feat(night-supervisor): anchor bridge status to active evidence`.
- Expected outcome: Latest Night Supervisor report anchors bridge status; active blockers drive `BLOCKED`; active approvals drive `NEEDS_APPROVAL`; historical relay artifacts remain detail-only evidence.
- Accepted risk: Broad raw evidence still contains blocked-looking text and old artifacts, so future consumers must honor `status_impact` and active/current buckets instead of raw item status alone.
- Regression checks: Confirm `AUTONOMY_BRIDGE_STATE.json` includes `bridge_status`, `active_current`, `active_decision_cards`, `current_blockers`, `raw_evidence`, and `status_impact`; confirm old relay errors, examples, samples, completed records, and stale projections do not force `BLOCKED`.
- Reopen conditions: Reopen if bridge top-level status is again driven by historical relay artifacts, examples, completed records, stale projections, or old test blockers instead of current active operational evidence.

#### Operator Guidance Layer

- Source: ChatGPT export full-shard aggregate tally. No raw transcript was imported, no private content was stored, and no attachment content was inspected.
- Problem discovered: Repeated human-AI productivity friction concentrated in Git/GitHub/PR/branch handling, repo/path selection, terminal/CLI and PowerShell use, Codex approval prompts, manual repair burden, stale-state confusion, and unclear next actions.
- Root cause: AI guidance often assumed operational vocabulary, current UI shape, repo state, or approval-risk context that the operator needed translated into immediate action.
- Process fix: Added an Operator Guidance Layer rule in `AGENTS.md` requiring action-first, beginner-readable, scope-aware guidance for Git, repo paths, terminal commands, validation, UI/web steps, and Codex approval prompts.
- Expected outcome: Fewer manual repair loops, clearer next actions, safer approval choices, and less repeated confusion around repo path, PR flow, branch state, command purpose, success condition, and stop condition.
- Accepted risk: Over-explaining can become new noise if assistants turn the guidance layer into long tutorials instead of short action-first translation.
- Regression checks: Confirm future prompts explain the immediate action clearly; confirm Codex approval prompts get plain-language risk translation; confirm Git/GitHub/branch/path instructions include success condition and stop condition; confirm UI guidance avoids stale button assumptions and uses current official documentation or visible-state fallback when exact UI matters.
- Reopen conditions: Reopen if repeated frustration from unclear commands, repo paths, PR flow, approval prompts, missing vocabulary, or stale UI assumptions returns.

#### Instruction Ownership Layer

- Problem discovered: Mixed copied prompts caused actor confusion and manual repair when human instructions, Codex packets, ChatGPT notes, GitHub context, PowerShell commands, placeholders, and repo rules appeared in one pasted block.
- Root cause: Instructions lacked explicit ownership classification before assistants interpreted or acted on the block.
- Process fix: Added an Instruction Ownership Layer rule in `AGENTS.md` requiring assistants to identify artifact type, intended actor, executability, Anthony action, urgent approve/reject/stop instructions, placeholders, and the correct response mode before acting.
- Expected outcome: Future assistants identify who each instruction is for, whether the block is executable, whether Anthony must act, and whether placeholders block execution before generating, repairing, summarizing, translating, or refusing.
- Accepted risk: Ownership classification can add a small amount of up-front response overhead if agents overuse it for simple single-lane prompts.
- Regression checks: Confirm wrong-agent execution, malformed packet handling, hidden human actions, and placeholder execution do not recur; confirm mixed pasted context without an execution token is treated as reference-only by Codex.
- Reopen conditions: Reopen if actor confusion, ChatGPT obeying Codex-only text, Codex acting on context-only blocks, hidden urgent human actions, or placeholder-as-real-target handling returns.

#### Human-in-the-Loop Guidance Scope

- Problem discovered: Operator guidance could become new friction if applied to fully autonomous worker flows that do not require Anthony to act.
- Root cause: Human-facing explanation rules needed scope boundaries so they would not slow safe internal AI_OS worker-to-worker execution.
- Process fix: Added a Human-in-the-Loop Guidance Scope rule in `AGENTS.md` requiring operator guidance at human decision, approval, command, UI, terminal, PR, merge, push, and handoff boundaries while allowing concise machine-readable status, logs, and evidence for safe internal processing.
- Expected outcome: Less human burden while preserving clear decisions, success conditions, and stop conditions whenever Anthony action is required.
- Accepted risk: Workers can under-explain if they mistake a human-facing handoff for internal processing.
- Regression checks: Confirm future workers do not interrupt Anthony for safe internal processing, but explain clearly when Anthony action is required; confirm Morning Briefs, approval cards, and operator-facing reports remain human-readable.
- Reopen conditions: Reopen if the guidance layer becomes too verbose during autonomous execution, or if human approval prompts, terminal commands, PR/merge/push actions, or UI handoffs become unclear again.

#### T9 Snapshot / Mirror Authority Boundary

- Problem discovered: T9 snapshots can preserve deleted, stale, obsolete, or superseded files that should not re-enter active repo truth.
- Root cause: Backup preservation and active authority can be confused when historical snapshots look like current source files.
- Process fix: Updated `docs/workflows/AI_OS_T9_BACKUP_WORKFLOW.md` so GitHub `origin/main` remains current truth, T9 snapshots are recovery-only evidence, T9 mirrors require explicit current-HEAD labeling, and restore/import requires exact human approval.
- Expected outcome: Future workers compare T9 material to current `main` and Git history before any restore review instead of treating T9-only files as active.
- Accepted risk: T9 can still contain useful recovery material, so overly broad `DO_NOT_ADOPT` classification could hide a valid restore candidate unless the restore checklist is used.
- Regression checks: Confirm future workers do not classify T9-only files as active guidance, governance, scripts, or runtime artifacts without restore review; confirm deleted files remain deleted unless a restore packet proves why they should return.
- Reopen conditions: Reopen if stale or deleted T9 files reappear as active guidance, governance, scripts, runtime artifacts, or source-of-truth evidence.

#### SOS-Only Operating Rule

- Problem discovered: Anthony was still being pulled into routine PR, GitHub, CLI, and approval flow when the desired operating model is AI does the work and Anthony approves only SOS or protected-action decisions.
- Root cause: Normal human-needed status, stale warnings, routine approvals, and recommendation-only defers were not clearly separated from SOS wake or interruption conditions.
- Process fix: Use SOS-only alerting. AI_OS continues normal evidence and recommendation work, and interrupts Anthony only when safe continuation is blocked or a protected action needs explicit approval or intervention.
- Expected outcome: Less operator burden; AI_OS handles normal workflow; Anthony only sees true SOS and protected-action decisions.
- Accepted risk: A display alert can still look urgent if a consumer does not distinguish `display_alert` from `sos_wake_required`.
- Regression checks: Confirm future Morning Brief, Pi5, Night Supervisor, and notification logic distinguish `display_alert` from `sos_wake_required`; confirm `NEEDS_APPROVAL`, stale warnings, historical noise, and recommendation-only defers do not wake Anthony.
- Reopen conditions: Reopen if Anthony is interrupted for routine warnings or noise, or if protected-action attempts fail to alert.

#### Clipboard Evidence Intake Dedup

- Problem discovered: Clipboard evidence captures can be over-counted or overwritten.
- Root cause: Timestamp-only filenames can collide on same-second saves, and file-level counting misses content-level duplicates when generated capture headers differ.
- Fix applied: Added a repo-tracked local-install template at `tools/evidence/Save-Clipboard-To-AIOS-Evidence.template.ps1` and workflow documentation at `docs/workflows/AI_OS_EVIDENCE_INTAKE_DEDUP.md`. The template uses collision-safe filenames, `CreateNew` writes, metadata sidecars, `raw_file_sha256`, `normalized_body_sha256`, and strong-sentence duplicate classification.
- Expected outcome: AI_OS can reproduce the corrected clipboard evidence behavior without committing private Desktop evidence captures or metadata sidecars.
- Accepted risk: Live local evidence folders still require privacy review and must not be imported into repo telemetry without explicit approval.
- Regression checks: Future evidence metrics must count canonical `normalized_body_sha256` groups, not raw files; short 2-5 word overlap must remain `WEAK_SIMILARITY_IGNORE`; strong sentence overlap with different body hashes must remain `PARTIAL_OVERLAP_STRONG_SENTENCE`.
- Reopen conditions: Reopen if duplicate captures inflate telemetry, same-second captures overwrite, raw evidence is imported into the repo without approval, or weak phrase overlap is treated as duplicate content.

#### Human-AI Friction Local Telemetry Boundary

- Problem discovered: `telemetry/human_ai_friction/` can contain sensitive local friction evidence and was appearing as untracked status noise.
- Root cause: The local-only folder was not protected by a narrow repo ignore rule.
- Fix applied: Classified `telemetry/human_ai_friction/` as `LOCAL_ONLY`, `SANITIZE_LATER`, and `DO_NOT_COMMIT`; added a narrow `.gitignore` rule so raw local friction evidence remains out of repo status.
- Expected outcome: Future workers do not read, import, summarize, stage, or commit raw friction evidence without explicit approval.
- Regression checks: Confirm `git status --short --branch` does not show `telemetry/human_ai_friction/`; confirm only sanitized summaries are proposed for repo inclusion after approval.
- Reopen conditions: Reopen if raw friction evidence appears in git status, is imported into repo telemetry, or is proposed for commit.

#### Overnight Priority Lane

- Problem discovered: Anthony needs to delegate overnight priority without manually managing every step.
- Root cause: Overnight work needed a queue-tray model that ranks and classifies tasks before any worker, API, scheduler, or protected-action path is touched.
- Fix applied: Added `docs/workflows/AI_OS_OVERNIGHT_PRIORITY_LANE.md` to define the queue tray, task classes, schemas, roles, protected boundaries, SOS rule, and display-only summary targets.
- Expected outcome: AI_OS can rank work, draft exact packets, and stop before protected actions while Anthony handles only SOS or protected-action decisions.
- Regression checks: Future overnight work must classify task classes before execution and preserve allowed paths, forbidden paths, validator chain, and stop point.
- Reopen conditions: Reopen if workers self-select work, execute without exact packets, or Anthony is pulled into routine non-SOS decisions.

#### SOS Display vs Wake Boundary

- Problem discovered: `NEEDS_APPROVAL` could be rendered with SOS-like wording even though it should be review/display-only when no execution was attempted.
- Root cause: Display alerts and wake-worthy SOS alerts were not exposed as separate machine fields everywhere.
- Fix applied: `NEEDS_APPROVAL` now maps to `display_alert: true`, `sos_wake_required: false`, and `wake_class: REVIEW_ONLY`; `BLOCKED` remains `display_alert: true`, `sos_wake_required: true`, and `wake_class: SOS`.
- Expected outcome: Pi5, Morning Brief, file notifications, and Telegram dry-run classification can show human-needed review without waking Anthony unless safe continuation is blocked.
- Regression checks: Confirm future notifier and bridge outputs do not label `NEEDS_APPROVAL` as SOS and do not include `#AIOS_SOS` for non-SOS review states.
- Reopen conditions: Reopen if routine approvals, stale warnings, or display alerts wake Anthony, or if true `BLOCKED` states fail to surface as SOS.

#### Pi5 Device Health Baseline

- Problem discovered: Pi5/NVMe health needed a retrievable baseline after suspected corruption.
- Evidence: Pi5 is online at `192.168.1.167`, NVMe is mounted, disk usage is low, and read-only scans found no obvious active ext4/NVMe corruption.
- Process fix: Keep a sanitized device-health note at `docs/devices/PI5_DEVICE_HEALTH.md`; future checks compare against this baseline.
- Regression checks: Do not run repair commands or GPIO/motor actions from repo guidance.
- Reopen conditions: Reopen if I/O errors, ext4 errors, read-only remounts, boot failures, SMART failures, or unexplained data loss appear.

#### Forex Paper Bot Contract

- Problem discovered: Forex Paper Lab had report-only planning fragments but no canonical paper bot build contract.
- Fix applied: Added `docs/AI_OS/trading_laboratory/AI_OS_FOREX_PAPER_BOT_CONTRACT.md` as a docs-only contract before runner/runtime work.
- Expected outcome: Future Forex work starts from fixture price input, paper signal intake, validation, risk gate, paper ledger, report output, Pi5 display, and validator boundaries.
- Regression checks: Future Forex work must preserve paper/simulation and demo gates unless separately approved; broker-capable progression must stay governed.
- Reopen conditions: Reopen if broker/OANDA/live market/real order/webhook paths appear in a paper lane.

#### Industrial-Standard / Professional-Grade Quality Bar

- Problem discovered: AI_OS work can drift into rushed, vague, duplicated, or low-quality changes when multiple lanes are moving quickly.
- Root cause: Quality expectations were implied but not strongly stated as an industrial-standard / professional-grade operating bar.
- Process fix: Patch root/workflow guidance so every AI_OS packet must be scoped, validated, reversible where practical, non-duplicative, and safety-bounded before being considered ready.
- Regression checks: Future packets must reject vague goals, missing validators, duplicate authority, mixed scopes, or unbounded protected actions.
- Reopen conditions: Reopen if a future lane produces broad, low-quality, unvalidated, duplicate, or unsafe work under the excuse of speed.

#### Telegram Tasker Control Surface

- Problem discovered: The Telegram/Tasker bridge plan was too execution-forward for current AI_OS maturity.
- Fix applied: Converted the plan to a staged control-surface roadmap with interface-only authority, command allowlist, identity gate, replay/idempotency requirements, and protected-action classification.
- Regression checks: Telegram/Tasker must never directly execute repo, scheduler, worker, trading, GPIO, production, approval, commit, push, merge, or secret-handling actions.
- Reopen conditions: Reopen if future Telegram/Tasker work bypasses Protected Action Readiness or treats chat commands as authority.
