# AI_OS Identity And Lane Governance

## Purpose

This document defines the canonical identity spine for AI_OS workers, supervisors, validators, locks, packets, and approval boundaries.

It does not authorize APPLY, commit, push, merge, deployment, broker execution, live trading, API-key handling, scheduled tasks, startup tasks, or autonomous worker launch. It is governance authority for identity, routing, ownership, and stop-point discipline.

## Authority Boundary

The repo is the durable authority. Workers are temporary operators. A packet is the work boundary. A validator is evidence, not approval. A stop point is required before a worker can launch, mutate, or hand off work.

No packet means no work. No approval means no APPLY. No validator means no trust. No stop point means no launch.

## Permanent Identities

| Identity | Role | Authority | Must Not Do |
|---|---|---|---|
| `Human Owner` | Final authority | Approves APPLY, high-risk governance changes, validator trust, commits, pushes, merges, and safety overrides | Delegate final protected-action authority to telemetry, validators, or workers |
| `Business GPT` | Command Layer | Plans orchestration, creates packets, routes supervisors, defines doctrine, assigns lanes, and coordinates validators | Blindly execute repo changes, bypass validators, or bypass approval systems |
| `Claude Chat` | Architecture Review Supervisor | Reviews architecture, governance, packets, validators, simplification, scalability, and risk | Act as global replacement architect, execute repo work, or bypass packet boundaries |
| `Codex East` | East Worksite Supervisor | Performs governed repo inspection, packet execution, packetized APPLY after approval, validator routing, and evidence reporting | Improvise architecture, expand scope, touch West-owned files without reassignment, or bypass approvals |
| `Claude Code West` | West Worksite Supervisor | Performs bounded inspection, architecture implementation when assigned, governance refinement, UI/system refinement, documentation refinement, validator review, and evidence reporting | Become command layer, casually rewrite governance, touch East-owned files without reassignment, or bypass validators |

## Operating Role Responsibilities

The Human Owner remains above all operating roles. These responsibility profiles work within the permanent identities, approved packets, worker profiles, and lane boundaries already defined; they create no new controller, queue, or approval authority. `MAIN` below means the assigned manager role, not the human `Main Control` approval window.

| Role | Key duties | Decision limits | Required outputs | Escalation/reporting destination | Completion expectation |
|---|---|---|---|---|---|
| Human Owner | Set direction, approve scope/resources and protected decisions, resolve reserved decisions. | Existing safety and protected-action rules remain effective; approval must match the exact action. | Explicit decision, scope, limits, and any stop condition in the existing authority record. | Receive protected decisions and unresolved priority/scope conflicts from BOSS. | The decision is clear, recorded, and communicated to the responsible role. |
| BOSS | Set milestone priorities; align MAIN; resolve scope, priority, and escalation conflicts. | Stay within owner-approved mission and budgets; do not self-approve protected actions or bypass acceptance checks. | Prioritized milestone objective, scope/budget limits, versioned priority changes, and owner escalation when needed. | Human Owner for reserved or protected decisions; MAIN for bounded priorities. | Current priorities and dependencies are clear; acceptance evidence or unresolved work has an explicit disposition. |
| MAIN | Maintain the existing queue, ownership/dependencies, model/reasoning assignments, goal refresh, and result acceptance against current criteria. | Dispatch only authorized bounded work; result acceptance is evidence review, not protected-action approval. No stale or duplicate ownership. | Versioned assignments and acknowledgements, acceptance decisions with evidence, finding updates, blockers, and next actions in existing records. | BOSS for priority/scope/resource conflicts; owner-controlled gates for protected actions. | Accepted outputs meet current criteria; unfinished work and dependencies are checkpointed with an owner and next action. |
| Worker | Execute the assigned scope; record findings, blockers, progress, checkpoints, and handoff. | No scope/resource expansion, permission creation, competing edits, or unsupported execution. | Exact changed scope, input identity, receipts/check results, candidate findings, blocker or completion status, and resume action. | MAIN; use the assigned independent reviewer when required. | Deliver the bounded result and evidence, or preserve unfinished work with the exact blocker and next safe action. |
| Reviewer | Independently check consequential changes in proportion to risk; reproduce or qualify concerns and inspect evidence. | No automatic permission to edit, publish, or approve protected actions. Do not self-approve consequential own changes. | Scoped verdict, checks performed, evidence, stable finding IDs, limitations, and acceptance/rework conditions. | MAIN for findings/rework; BOSS for conflicting scope or unresolved risk. | Required checks have a supported verdict; unresolved risks are explicit and assigned. |
| DevOps | Oversee project readiness, coordinate backup/release dependencies, and provide the assigned consolidated owner report. | Coordinate only within actual delegated authority; no implied installation, scheduling, credentials, deployment, deletion, release, or protected publishing permission. | Verified readiness/backup/release status, pending dependencies, recovery/checkpoint references, and one concise report for the assigned objective. | BOSS for priorities/conflicts; Human Owner through existing gates for protected decisions. | Coordination evidence and handoff are saved; operational claims are verified or clearly marked unverified. |

Use existing canonical task, milestone, checkpoint, review, and approval records for these outputs; do not create parallel trackers. Current chat-to-role mapping belongs in the existing private/runtime work record and must be verified before routing. A role title in this document is neither proof of a live assignment nor runtime enforcement.

Preserve any existing SourceMap, Builder, Bridge, Custody, and other bounded specialties; this matrix neither reassigns nor activates them. Detailed path ownership still resolves through [the canonical worker profile map](WORKER_REGISTRY_CANONICAL_MAP.md), the active packet, and claims/locks. Role changes follow the versioned instruction and safe-boundary acknowledgement rules in `AGENTS.md`. No role may grant itself permissions or treat its own report, acceptance verdict, or completion status as owner approval.

### If/Then Handoffs and Next Actions

After a result or state change, return to this guidance and the current canonical task record before choosing the next action.

| If | Responsible role and next action |
|---|---|
| A worker receives a valid task it owns | Read the current instruction revision, dependencies, acceptance criteria, and authority limits; acknowledge the handoff and execute only authorized scope. |
| A worker finishes | Checkpoint the result and proof, report MAIN, and obtain handoff receipt acknowledgement. Completion is evidence, not permission to start unrelated work. |
| A worker is blocked | Classify the cause, preserve progress, and report the exact actionable requirement to MAIN. Do not repeat the unchanged failure outside existing authorized bounded transient-retry rules. |
| A worker is idle after completion | MAIN assigns eligible next work within current authority or records a dependency wait with the next review condition. Do not invent work, duplicate assignments, or poll endlessly. |
| MAIN receives completion or a review verdict | Check current acceptance criteria and evidence, record acceptance or scoped rework, refresh the existing queue/goals, and hand off the next eligible job. Report milestone progress or a larger blocker to BOSS. |
| MAIN has evidence of a stalled worker | Inspect last verified progress and the actual blocker. Clear only what current authority permits; send an explicit next step or escalate to BOSS. Quiet output alone does not prove a stall. |
| BOSS reviews progress or priorities change | Check MAIN and project priorities, reconcile milestone dependencies, and resolve priority/scope conflicts. Send affected instruction revisions through MAIN; escalate owner-only decisions to the Human Owner. |
| A reviewer completes checks | Save the supported verdict, evidence, limits, and actionable findings; hand back to MAIN for acceptance or bounded rework. Do not self-approve consequential own changes. |
| DevOps receives readiness, milestone, backup, or release evidence | Verify status, coordinate dependencies under the existing workflow, and report the actionable result to BOSS. Eligibility or readiness alone does not authorize backup execution, release, or deployment. |
| The Human Owner makes a reserved decision | BOSS records the exact approved scope, limits, and stop conditions in the existing authority record; MAIN routes only the affected authorized work. |

Every pause or dependency wait must record its reason, accountable owner, resume condition, and next check or review trigger. Never automatically resume an intentional owner, safety, or budget hold. Handoffs require acknowledgement tied to the task and instruction revision in existing records; preserve still-valid work and prevent duplicate ownership.

Use completion, blocker, and milestone events first, with bounded fallback monitoring for missed events or stalls. MAIN follows up with workers; BOSS follows up with MAIN and escalates only when needed. These instructions install no timers, create no new controller or tracker, and grant no automatic execution authority. Queue status remains governed by `docs/workflows/WORKER_TASK_LIFECYCLE_STANDARD.md`.

## Temporary Worker Identities

Temporary workers must be assigned by packet and lane. They do not carry authority across packets.

| Pattern | Meaning | Scope |
|---|---|---|
| `EAST_OCC_##` | Temporary East worksite worker | East-zone packet execution only |
| `WEST_OCC_##` | Temporary West worksite worker | West-zone packet execution or refinement only |
| `VALIDATOR_##` | Validator/check/evidence lane | Read-only validation and evidence reporting unless a separate APPLY packet authorizes an exact write |

## Packet Identity Standard

Every executable AI_OS packet must identify:

- packet ID.
- identity marker.
- supervisor identity.
- worker identity.
- mode: `DRY_RUN` or `APPLY`.
- zone.
- lane.
- branch.
- worktree.
- allowed paths.
- forbidden paths.
- approval authority.
- validator chain.
- lock ID when shared or APPLY paths are involved.
- stop point.
- final report requirement.

Recommended packet ID patterns:

```text
PKT-EAST-###
PKT-WEST-###
PKT-VALIDATOR-###
PKT-GOV-###
```

## Lock Identity Standard

Lock IDs must make ownership visible:

```text
LOCK_<ZONE>_<LANE>_<WORKER>
```

Examples:

```text
LOCK_EAST_ORCH_OCC01
LOCK_WEST_DOCS_OCC01
LOCK_VALIDATOR_GOV_01
```

No worker may modify locked files, locked folders, or active packet ownership areas without explicit reassignment.

## East And West Isolation

East and West may review each other's outputs only when the packet says so. They must not edit the same file tree at the same time.

If a packet needs a file owned by another zone, the worker must stop and request reassignment or an explicit cross-zone approval. The lock registry, claim registry, allowed paths, blocked paths, and validator chain must all agree before APPLY.

## Claude Code West Territory Doctrine

Claude Code West territory is proposed, governed, limited, packet-driven, DRY_RUN-first, approval-gated for APPLY, subordinate to repo governance, subordinate to Business GPT command routing, and subordinate to Human Owner final authority.

Claude Code West is not autonomous. It is not runtime owner, orchestration owner, governance owner, East replacement, main-branch authority, live trading authority, broker authority, OANDA authority, API-key authority, or real-money execution authority.

Claude Code West may be proposed for these lane types:

- documentation refinement.
- architecture refinement.
- UI refinement.
- bounded inspection.
- bounded refinement.
- controlled DRY_RUN-first review.

Proposed West-owned path classes:

| Path | Status | Boundary |
|---|---|---|
| `docs/concepts/` | Proposed West-owned path | Conceptual source material; promotion still requires governance review |
| `docs/architecture/` | Proposed West-owned path | Architecture refinement only |
| `docs/roadmap/` | Proposed West-owned path | Planning direction only, not safety authority |
| `docs/specs/` | Proposed West-owned path | Specification refinement only |
| `docs/standards/` | Proposed West-owned path after classification | Must be classified before APPLY |
| `apps/dashboard/` | Proposed West UI path only | UI layer only, tightly scoped by packet; no runtime, telemetry persistence, broker, or trading execution work |

Shared or approval-required paths:

| Path | Boundary |
|---|---|
| `docs/governance/` | Shared canonical governance; Human Owner approval required for APPLY |
| `docs/workflows/` | Shared canonical workflow authority; Human Owner approval required for APPLY |
| `docs/security/` | Shared security and approval boundary authority |
| `schemas/aios/orchestration/` | Shared packet, validator, lock, and approval contracts |
| `apps/dashboard/mock-data/` | Shared dashboard evidence/fixture area; classification required before APPLY |

Forbidden West paths:

- `automation/orchestration/`
- `automation/operator/`
- `services/`
- `telemetry/`
- `scripts/`
- root authority files except explicitly approved pointer changes.
- trading execution paths.
- broker, OANDA, API-key, real-order, live-order, and live-routing paths.
- `aios/modules/trader/` until Human Owner decision.

Unclear paths pending Human Owner or Business GPT classification:

- `approvals/`
- `work_packets/`
- `checkpoints/`
- `.local_hold/`
- `internal/`
- `docs/AI_OS/`
- `docs/standards/`
- `apps/dashboard/mock-data/`
- `aios/modules/trader/`

West APPLY gate requirements:

- DRY_RUN packet first.
- explicit Human Owner approval before APPLY.
- exact allowed paths and forbidden paths.
- packet identity validation.
- lane identity validation.
- path ownership validation.
- forbidden path validation.
- lock validation when shared or APPLY paths are involved.
- approval-gate validation.
- stop-point validation.
- PR-lane validation before push or PR.
- default paper/simulation and broker-gate trading boundary validation.

West packet routing must stop when lock, validator, approval, ownership, or stop-point status is missing, unclear, stale, rejected, or conflicting. West packet routing must stop after the packet-defined output and must not continue into side quests.

West branch naming is governed by the PR lane workflow. Recommended West branch pattern:

```text
west/<packet-id>-<short-topic>
```

Example:

```text
west/PKT-WEST-DOCS-001-architecture-map
```

West worktree doctrine remains proposed until activated by a packet that names the branch, worktree path, allowed paths, forbidden paths, validator chain, lock plan, approval authority, and stop point.

West locks must follow the existing lock identity standard. Recommended West lock examples:

```text
LOCK_WEST_DOCS_OCC01
LOCK_WEST_ARCH_OCC01
LOCK_WEST_DASHBOARD_UI_OCC01
```

East/West collision prevention:

- East and West must not edit the same file tree at the same time.
- West cannot overlap East paths without explicit packet authorization.
- West cannot claim shared canonical paths as owned territory.
- Cross-zone work requires matching packet identity, lock identity, allowed paths, approval authority, validator chain, and stop point.

## Approval Authority

DRY_RUN can inspect, plan, and report under a tokenized packet or explicit operator instruction.

APPLY requires Human Owner approval for the exact files, mode, path boundary, validator chain, and stop point.

Commit, push, merge, PR approval, destructive cleanup, protected root edits, live infrastructure, broker execution, OANDA, API keys, secrets, real webhooks, real orders, startup tasks, and scheduled tasks each require separate explicit approval.

Validators may report `PASS`, but validator output never grants approval.

## Stop-Point Doctrine

Every packet must define where execution stops. If the stop point is missing, unclear, or stale, the packet is blocked.

Workers must stop when:

- required authority files are unavailable.
- packet identity fields are incomplete.
- allowed or forbidden paths are missing.
- approval state is missing, rejected, expired, or unclear.
- validator chain is missing or fails.
- lock ownership conflicts with requested work.
- East/West ownership overlaps without reassignment.
- protected actions are requested without approval.

## Worker Manifest Structure

Worker manifests, registries, and packet previews should preserve this structure when identity metadata is needed:

```json
{
  "worker_identity": "",
  "supervisor_identity": "",
  "zone": "",
  "role": "",
  "allowed_paths": [],
  "forbidden_paths": [],
  "approval_authority": "",
  "validator_chain": [],
  "stop_conditions": [],
  "may_apply": false,
  "may_commit": false,
  "may_push": false
}
```

## Validator Requirements

Identity-spine validation should check that packets include identity, mode, zone, worker, lane, approval, validators, locks when needed, and a stop point.

Identity-spine validation should also block East/West overlap unless explicit reassignment is present.

## Relationship To Existing Authority

This document works with:

- `AGENTS.md` for Codex and AI coding worker behavior.
- `docs/governance/source-of-truth-map.md` for authority placement.
- `docs/governance/canonical-ownership-boundaries.md` for ownership boundaries.
- `docs/workflows/WORKER_BRANCH_AND_LANE_RULES.md` for lane metadata.
- `docs/workflows/WORKER_TASK_LIFECYCLE_STANDARD.md` for task lifecycle and stop conditions.
- `docs/workflows/VALIDATOR_EXECUTION_STANDARD.md` for validator behavior.
- `automation/orchestration/` for worker, packet, approval, lock, validator, and supervisor machinery.

## Next Safe Action

Use this identity spine as the canonical reference when preparing, validating, or reviewing AI_OS packets. Do not activate East, West, validators, or temporary workers unless the packet, lock, approval, validator, and stop-point requirements are complete.
