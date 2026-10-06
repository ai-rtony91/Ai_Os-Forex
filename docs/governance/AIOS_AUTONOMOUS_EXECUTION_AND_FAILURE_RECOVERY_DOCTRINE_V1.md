# AIOS Autonomous Execution And Failure Recovery Doctrine V1

## Purpose

Define the operating law for long-running AIOS documentation, governance, workflow, validation, and reporting campaigns that can continue through multiple safe work items without treating every successful subtask as the end of the lane.

This doctrine turns recoverable failures into governed work items, makes checkpoints mandatory evidence, and preserves human approval for every protected action.

## Scope

The `AGENTS.md` **Continue Through And Through Law** is authoritative. Runtime workers prepare, run, save, check, checkpoint and select the next safe work under the same current authority. Units, batches, good or bad research results, reports, checkpoints, stages, context turns and bounded recoverable retries are progress events. They must not require an owner continuation prompt.

Every real stop records one class: `OWNER_ACTION_REQUIRED`, `SAFETY_INTEGRITY_BLOCK`, `RESOURCE_TIME_BLOCK`, `UNRECOVERABLE_FAILURE` or `CAMPAIGN_COMPLETE`. Checkpoints preserve completed, failed and remaining work, current claims and locks, the next safe action and whether owner action is needed. Finish safe preparation and save the exact handoff before an owner gate. Explicit owner pauses and all signature, HMAC, claim, path, data, cost, risk and PAPER/LIVE gates remain binding.

The canonical adaptive workforce Goal supervisor and PKT045 binding enforce continuation under their existing process lease and durable receipt store. The root continuation controller remains a read-only projection; it does not issue research authority. Changes to pinned runtime code require a newly signed successor before that research runtime can run. Runtime behavior tests must cover progress events, retry recovery, duplicate ownership, no repeat of accepted work and preserved safety gates.

This doctrine applies to AIOS packets that explicitly authorize campaign-style local APPLY or DRY_RUN work inside a named lane, branch, worktree, allowed path boundary, validator chain, and stop point.

This artifact does not authorize broker/API access. This artifact does not authorize credential access. This artifact does not authorize trading execution. This artifact does not authorize money movement. This artifact does not authorize commit/push/merge without explicit Human Owner approval. It does not authorize PR creation, scheduler activation, webhook activation, daemon activation, production activation, reset, clean, stash, deletion, or file movement unless a separate packet and approval explicitly allow the exact action.

## Authority Hierarchy

`AGENTS.md` remains the highest local repository authority for Codex and AI assistant conduct. `RISK_POLICY.md` remains the root safety and execution authority. `docs/governance/aios-identity-and-lane-governance.md` remains the identity, lane, packet, validator, lock, and stop-point authority. This doctrine supports those authorities and cannot override them.

The governed development hierarchy remains:

```text
Mission -> Program -> Epic -> Bucket -> Packet -> Apply -> Validation -> Report -> Pull Request -> Merge -> Main
```

This doctrine operates at the Packet, Apply, Validation, and Report layers only. Pull Request, Merge, and Main remain protected publishing layers.

## Campaign Execution Doctrine

The lane is the execution target. The packet is the authorization boundary. The worktree is the isolation boundary. Recoverable failures become work items. Reports are evidence, not endpoints. Codex continues inside approved scope. Codex stops at true governance gates.

A campaign executor works from a bounded queue:

1. Confirm authority, identity, branch, worktree, allowed paths, forbidden paths, validators, and stop point.
2. Inspect existing related authority before editing.
3. Complete one approved work item.
4. Write or update checkpoint evidence.
5. Run the relevant local validator or record why it is blocked.
6. Ask the self-critique question: `Can I safely contribute more inside approved scope?`
7. Continue when the answer is yes.
8. Stop only when the lane is complete, validation fails and cannot be safely repaired, scope is exhausted, a protected action is required, or a higher authority gate blocks continuation.

## Packet Authorization Boundary

The packet defines the maximum authority for the campaign. A campaign may continue across multiple artifacts only when each artifact is listed in the packet or fits unambiguously inside the named allowed write boundary and objective.

The packet must identify:

- Mission ID and Mission Name.
- Program ID and Program Name.
- Epic ID and Epic Name.
- Bucket ID and Bucket Name.
- Packet ID and Packet Name.
- Mode.
- Zone.
- Lane.
- Supervisor identity.
- Worker identity.
- Worktree.
- Branch or branch-resolution preflight.
- Allowed paths.
- Forbidden paths.
- Approval authority.
- Validator chain.
- Stop point.
- Final report format.

If any required execution field is missing, campaign execution stops under `AGENTS.md` packet validation rules.

## Lane Completion Rule

A lane is not complete when the first artifact is written, the first report is generated, or the first validator passes. A lane is complete only when every approved artifact exists, cross-links correctly, validation has run or is explicitly recorded as blocked, the checkpoint is current, and the final protected-action handoff is ready.

Reports, checkpoints, and validator results are evidence. They do not end the lane unless the packet's objective is fully satisfied or a true stop gate is reached.

## Worktree Isolation Boundary

The active worktree is the campaign isolation boundary. Codex must not switch away from dirty owner work, reset, clean, stash, or delete files to create a clean lane. If the source worktree is dirty with unrelated work, campaign arbitration must decide whether to continue in the same worktree, create an isolated worktree, queue the campaign, or hand off to the owner.

Related workflow: `docs/workflows/AIOS_ISOLATED_WORKTREE_CAMPAIGN_EXECUTION_V1.md`.

## Recoverable Failure Doctrine

A recoverable failure is a bounded problem that can be classified, recorded, and worked around without violating the packet boundary. Examples include a missing report directory, a markdown validation miss, a parser false positive, a transient read-only shell launch failure, or a missing cross-link.

Recoverable failures become work items when:

- the recovery stays inside allowed paths.
- the recovery does not require destructive commands.
- the recovery does not require protected Git or GitHub actions.
- the recovery does not touch broker/API, credentials, trading execution, money movement, production activation, schedulers, webhooks, daemons, or secrets.
- the validator after recovery is known.

Unrecoverable or unsafe failures become stop gates.

Related workflow: `docs/workflows/AIOS_FAILURE_RECOVERY_PLAYBOOKS_V1.md`.

## Failure Memory Doctrine

Failure memory preserves repeatable lessons without turning every incident into new governance law. Operational failures are recorded in checkpoints and reports. Only recurring, high-impact, or policy-relevant failures are promoted into durable governance memory.

Failure memory must include detection signature, root cause, recovery attempted, recovery result, validator evidence, prevention rule, and promotion status.

Related governance: `docs/governance/AIOS_FAILURE_MEMORY_V1.md`.

## Checkpoint Doctrine

Campaign checkpoints are mandatory recovery evidence. A checkpoint records current objective, completed work, pending work, touched files, validators, failures, recoveries, next safe action, stop reason, and resume prompt.

Checkpoints do not approve execution. They help the next worker resume safely and preserve operator visibility.

Related workflow: `docs/workflows/AIOS_CAMPAIGN_CHECKPOINT_AND_RESUME_V1.md`.

## Stop Gate Doctrine

Codex stops at true governance gates:

- required authority files are unavailable.
- packet identity, allowed paths, forbidden paths, validator chain, approval authority, or stop point is missing.
- observed branch/worktree state conflicts with packet assumptions and no safe preservation path exists.
- dirty work belongs to another campaign or owner lane.
- a requested action requires commit, push, PR creation, merge, reset, clean, stash, deletion, file movement, protected root edits outside scope, broker/API access, credential access, trading execution, money movement, production activation, scheduler activation, webhook activation, daemon activation, or secrets.
- validation fails and no approved bounded recovery exists.
- a sandbox, shell, Git, or GitHub failure blocks a required action.
- continuation would require scope expansion.

Stop gates must produce a short recovery report with next safe action or owner PowerShell handoff.

## Protected Action Preservation

Protected actions remain protected during a campaign. A campaign packet can authorize local documentation edits, report generation, and validation, but it does not authorize staging, committing, pushing, PR creation, check watching, merging, local main sync, reset, clean, branch deletion, or destructive cleanup unless those actions are separately and explicitly approved.

Protected publishing handoff belongs in `docs/workflows/AIOS_PROTECTED_PUBLISHING_HANDOFF_V1.md`, `docs/workflows/AI_OS_COMMIT_PUSH_GATE.md`, and `docs/workflows/AI_OS_PR_LANE_RUNNER.md`.

## Human Owner Approval Boundaries

Human Owner approval is action-specific and non-transferable. Approval for local APPLY does not approve commit. Commit approval does not approve push. Push approval does not approve PR creation. PR creation approval does not approve merge. Check success does not approve merge. Merge approval does not approve branch deletion, reset, clean, or future lane work.

Validator `PASS`, dashboard readiness, checkpoint state, telemetry state, and report language are evidence only.

## Safety Non-Override Rule

This doctrine expands recovery behavior only inside approved packet scope. It never overrides `AGENTS.md`, `RISK_POLICY.md`, security policy, protected paths, owner approval gates, fail-closed rules, trading safety boundaries, credential boundaries, or protected-action gates.

Any conflict is resolved by the stricter higher authority.

## Relationship To AGENTS.md

`AGENTS.md` governs prompt routing, packet execution tokens, identity headers, state alignment, failure recovery response format, completion report format, protected actions, safe commits, and operator guidance.

This doctrine gives Codex a long-campaign continuation model after `AGENTS.md` has already authorized a complete packet. It does not make incomplete packets executable.

## Relationship To AI_OS_COMMIT_PUSH_GATE.md

`docs/workflows/AI_OS_COMMIT_PUSH_GATE.md` governs protected staging, commit, push, PR creation, check watching, merge, and local main sync readiness. This doctrine cannot produce `SAFE_TO_COMMIT`, `SAFE_TO_PUSH`, or any other protected gate state by itself.

Campaign output must end with exact protected-action handoff commands when publishing is needed, but Codex must not run those commands without separate approval.

## Relationship To AI_OS_PR_LANE_RUNNER.md

`docs/workflows/AI_OS_PR_LANE_RUNNER.md` governs the protected PR lane from branch to review, checks, merge, and local main sync. This doctrine prepares a lane for that protected workflow by producing validated docs, checkpoints, and reports.

The PR lane remains a separate protected publishing path.

## Related Doctrine And Workflows

- `docs/governance/AIOS_CAMPAIGN_ARBITRATION_DOCTRINE_V1.md`
- `docs/governance/AIOS_FAILURE_MEMORY_V1.md`
- `docs/workflows/AIOS_AUTONOMOUS_EXECUTION_ENGINE_V1.md`
- `docs/workflows/AIOS_FAILURE_RECOVERY_PLAYBOOKS_V1.md`
- `docs/workflows/AIOS_CAMPAIGN_CHECKPOINT_AND_RESUME_V1.md`
- `docs/workflows/AIOS_ISOLATED_WORKTREE_CAMPAIGN_EXECUTION_V1.md`
- `docs/workflows/AIOS_LONG_CAMPAIGN_CODEX_OPERATING_MODE_V1.md`
- `docs/workflows/AIOS_PROTECTED_PUBLISHING_HANDOFF_V1.md`
- `docs/workflows/AIOS_GITHUB_CI_FAILURE_RECOVERY_V1.md`
