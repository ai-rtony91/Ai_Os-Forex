# AIOS Campaign Arbitration Doctrine V1

## Purpose

Define how AIOS decides whether a campaign should continue in the current worktree, create an isolated worktree, queue behind existing work, or stop for owner handoff when multiple campaigns or dirty worktree states exist.

## Scope

This doctrine applies before campaign APPLY starts and whenever current Git state conflicts with packet assumptions.

This artifact does not authorize broker/API access. This artifact does not authorize credential access. This artifact does not authorize trading execution. This artifact does not authorize money movement. This artifact does not authorize commit/push/merge without explicit Human Owner approval. It does not authorize PR creation, scheduler activation, webhook activation, daemon activation, production activation, reset, clean, stash, deletion, or file movement.

## One Repo May Contain Multiple Campaigns

AIOS can have multiple planned campaigns, but one worktree must not host conflicting APPLY work at the same time. Campaigns must be separated by branch, worktree, lane, allowed paths, and checkpoint evidence.

Reports, telemetry, queue state, and validator output may mention several campaigns. They are evidence only. They do not approve overlap or branch switching.

## Active Dirty Campaign Preservation

Dirty files are owner work until proven otherwise. Codex must preserve dirty work before starting or switching campaigns.

Dirty files must be classified as:

- `same_campaign`: belongs to the active packet and allowed paths.
- `unrelated_campaign`: belongs to another lane or packet.
- `stale_work`: old work needing owner classification.
- `unsafe_unknown`: unclear ownership or safety boundary.

Only `same_campaign` dirty files can be continued by the same campaign.

## Same-Worktree Continuation Rule

Continue in the same worktree only when:

- current branch matches the packet branch or approved branch setup path.
- dirty files are same-campaign.
- every dirty file is inside allowed paths.
- no forbidden path is dirty.
- no protected action is required to continue.
- checkpoint evidence matches current state.

If those conditions hold, Codex continues instead of asking the owner to restart.

## Isolated Worktree Decision Path

Use an isolated worktree when:

- the source worktree has unrelated dirty files.
- the new campaign is approved.
- the target branch does not already exist or has an approved recovery path.
- the target worktree path is empty or already registered as the intended worktree.
- source worktree can remain untouched.

Related workflow: `docs/workflows/AIOS_ISOLATED_WORKTREE_CAMPAIGN_EXECUTION_V1.md`.

## Queue Decision Path

Queue the campaign and hand off when:

- source worktree is dirty with unrelated or unsafe files.
- isolated worktree creation is not approved, not possible, or blocked by sandbox/Git errors.
- the target branch already exists and ownership is unclear.
- required evidence is missing.
- owner classification is required.

Queued campaigns must include next safe action, branch/worktree evidence, and blocked reason.

## Campaign Conflict Detection

A campaign conflict exists when:

- two campaigns need the same file tree.
- a new packet wants to switch away from dirty owner work.
- dirty files overlap forbidden paths.
- a target branch or worktree already exists with unknown ownership.
- checkpoint evidence does not match observed Git state.
- worker identities or East/West lanes overlap without reassignment.
- a protected action is needed before safe continuation.

Conflicts stop APPLY until classified.

## Forbidden Arbitration Moves

- no reset without approval.
- no clean without approval.
- no stash without approval.
- no branch switch away from dirty owner work.
- no deletion to make room for a worktree.
- no overwrite of existing target worktree contents.
- no broad staging or `git add .`.
- no protected publishing action without the relevant protected-action gate and Human Owner approval.

## Decision Tree

```text
A. Is source worktree dirty?
   - No: continue normal preflight and branch/worktree setup.
   - Yes: go to B.

B. Are dirty files part of current packet?
   - Yes: go to C.
   - No or unknown: go to D.

C. If yes, continue same campaign.
   - Verify allowed paths, forbidden paths, checkpoint, and validators first.

D. If no, can isolated worktree be created?
   - Yes: go to E.
   - No or unknown: go to F.

E. If yes, create isolated worktree.
   - Preserve source untouched and follow the isolated worktree workflow.

F. If no, queue campaign and hand off.
   - Report dirty files, branch, worktree, blocked reason, and next safe owner action.
```

## Relationship To AEE Doctrine

`docs/governance/AIOS_AUTONOMOUS_EXECUTION_AND_FAILURE_RECOVERY_DOCTRINE_V1.md` defines the lane, packet, worktree, checkpoint, recovery, and stop-gate law for campaign execution. This arbitration doctrine decides where a campaign may safely run before the campaign execution cycle begins or resumes.

If arbitration detects a true governance gate, the AEE campaign must stop and hand off instead of continuing.

## Related Doctrine And Workflows

- `docs/governance/AIOS_AUTONOMOUS_EXECUTION_AND_FAILURE_RECOVERY_DOCTRINE_V1.md`
- `docs/governance/AIOS_FAILURE_MEMORY_V1.md`
- `docs/workflows/AIOS_AUTONOMOUS_EXECUTION_ENGINE_V1.md`
- `docs/workflows/AIOS_CAMPAIGN_CHECKPOINT_AND_RESUME_V1.md`
- `docs/workflows/AIOS_ISOLATED_WORKTREE_CAMPAIGN_EXECUTION_V1.md`
- `docs/workflows/AIOS_LONG_CAMPAIGN_CODEX_OPERATING_MODE_V1.md`
- `docs/workflows/AI_OS_PR_LANE_RUNNER.md`
- `docs/governance/aios-identity-and-lane-governance.md`

## Master Roadmap Continuity Rule

Every governed AIOS Program must maintain an ordered dependency path from
current work through downstream milestones. The canonical roadmap for a
Program is planning authority for order and return coordinates; it does not
approve APPLY, protected actions, trading, broker access, or money movement.

Temporary side jobs may interrupt the active roadmap when justified by
safety, recovery, evidence integrity, infrastructure, maintenance, backup,
authentication, deployment, research, or another owner-authorized need. A
side job does not become the master roadmap merely because it is newer or
more recent.

When an interruption reaches its stop condition, the worker must:

1. read the last verified master roadmap;
2. identify the first unfinished dependency;
3. verify that dependency against current repository and runtime evidence;
4. resume the first valid unfinished dependency;
5. skip milestones already proven complete; and
6. preserve deferred milestones in their original dependency order.

Recency alone must never select the next master task. AIOS must not silently
abandon an older unfinished milestone because a newer task appeared.

Human Owner Anthony may explicitly reprioritize, insert, remove, replace, or
supersede dependencies. That explicit reprioritization overrides automatic
return-to-path resolution. Current repository and runtime evidence overrides
stale roadmap assumptions; a conflict requires inspection, reconciliation,
roadmap status update, and then return to the first valid unfinished
dependency.

Completed milestones must not be rerun without an evidence-backed reason.
If return coordinates cannot be safely resolved, the worker must inspect the
canonical roadmap and must not guess.

### Packet Continuity Metadata

Every major packet must classify its path as one of:

- `MASTER_PATH`
- `SIDE_JOB`
- `RECOVERY`
- `MAINTENANCE`
- `RESEARCH`

`SIDE_JOB`, `RECOVERY`, `MAINTENANCE`, and `RESEARCH` packets must record,
where resolvable:

- `RETURN_TO_PROGRAM`
- `RETURN_TO_EPIC`
- `RETURN_TO_BUCKET`

Packets that propose skipping an unfinished upstream dependency fail closed
unless the Human Owner explicitly reprioritizes the roadmap. The packet
generator and reviewer must check these fields before large new work.

Side-job completion reports must include:

```text
INTERRUPTED PROGRAM:
INTERRUPTED BUCKET:
SIDE JOB:
SIDE JOB STATUS:
RETURN POINT:
FIRST UNFINISHED DEPENDENCY:
NEXT MASTER ACTION:
```

The canonical current Forex return path is maintained in:

`docs/roadmap/AIOS_FOREX_PROGRAM_B_MASTER_ROADMAP_V1.md`

The existing Strategic Campaign Registry remains the planning registry for
campaign selection. It is not replaced or duplicated by the Program roadmap.
