# AIOS Codex Packet Generator

## Purpose and boundary

This existing PowerShell surface creates a review draft. It does not approve,
execute, deliver, or enqueue work. The filename is retained for existing links;
the shared contract, generator, and validator now report their v2 schemas.

A valid result proves the text meets this contract. It does not prove that its
claimed branch, hierarchy, lock, scope, or approval is authentic. The receiving
worker must verify those facts against current repository and owner evidence.

## Required inputs

Supply every required field explicitly. The generator never invents missing
hierarchy, ownership, approval, or repository state.

| Input group | Parameters | Source |
| --- | --- | --- |
| Hierarchy | MissionId, MissionName, ProgramId, ProgramName, EpicId, EpicName, BucketId, BucketName, PacketId, PacketName | Exact assigned work packet or campaign |
| Identity | IdentityMarker, SupervisorIdentity, WorkerIdentity, LockIdentity | Assigned lane and matching ownership record |
| Repository | Mode, Zone, Lane, Worktree, Branch | Assigned scope and current repository preflight |
| Scope | AllowedPaths, ForbiddenPaths | Reviewed exact write boundary |
| Validation | Preflight, Validators, StopPoint, FinalReportFormat | Assigned checks and stop condition |
| Approval | ApprovalAuthority, StagingAuthority, CommitAuthority, PushAuthority, PullRequestAuthority, MergeAuthority | Actual owner instruction; absent protected permission is NOT AUTHORIZED |
| Additional reads | ReadFirst | Assigned lane instructions beyond the fixed bootstrap |

Required repository preflight commands are: pwd; git status --short --branch;
git branch --show-current; git remote -v; git rev-parse HEAD; git diff --name-only.
The shared contract owns their exact strings.

A lock name is a declaration, not a lock acquisition. Verify matching packet,
worker, lane, active status, and claimed paths before shared or APPLY work.
Drafting never modifies the lock registry.

## Legacy parameter migration

| Older input | v2 behavior |
| --- | --- |
| AllowedMutationFiles | Supplies AllowedPaths when absent; conflicting nonempty lists are rejected |
| StartBranch | Supplies Branch when absent; is also retained separately |
| Mission | Supplies MissionName when absent; is retained as the work description |
| ReadFirst | Retained in the draft; malformed or unresolved values are blocked |
| FromContinuationPlan / ContinuationPlanScript | Blocked with continuation_requires_explicit_v2_inputs; no script is run |

Branch and StartBranch may intentionally differ for an explicitly reviewed branch
plan. MissionName names the hierarchy; Mission describes the work. These are not
unconditional aliases when both are supplied.

Older argument names work with complete v2 safety context. An old invocation
without that context is deliberately blocked. Raw incomplete v1 packet text is
not grandfathered past the v2 checks.

## Output and validation

OutputJson returns AIOS_CODEX_PACKET_GENERATOR.v2 JSON containing packet_valid,
generated_packet_text, missing_required_fields, and validation_defects. Invalid
results contain empty generated_packet_text. Prompt mode emits a short failure
report instead of an incomplete executable draft.

The generated text starts with CODEX-ONLY PROMPT and includes the execution
marker, fixed bootstrap instructions, hierarchy, identity, scope, preflight,
validators, stop point, report format, and protected-action sections.

The generator runs the canonical Test-AiOsCodexPacket.DRY_RUN.ps1 validator
against the serialized result before returning a valid draft. The validator
rejects missing context, unresolved values, duplicate headings (including
embedded approval headings), malformed lists, NUL characters, and missing,
duplicate, or changed safety flags. Bootstrap instructions must be present in
the required order.

Every valid draft carries exactly one false value for execution_allowed,
can_continue_without_anthony, and writes_files. These are drafting boundaries;
they do not grant or replace a later execution decision.

The contract retains current main's operator_delivery guidance: one complete
handoff, no repeated full prompts, and the smallest safe recovery delta.

## Existing development queue

This PowerShell review draft is not a queue item. Its packet_valid value must
never be copied into queue approval, readiness, or execution authority.

The current Python route uses
automation/orchestration/runtime_queue/aios_execution_packet_resolver.py and
automation/orchestration/aios_codex_packet_builder.py. The autonomy runner supplies
its rich queue item separately from the normalized dispatch view. That route
owns its schema and source checks; it does not call this PowerShell generator.

No PowerShell-to-queue adapter is introduced. The inspected Python packet text
does not pass this strict v2 text format. Its separate unit checks must not be
reported as v2 integration, real delivery, worker execution, or full autonomy.
A future common-format migration must change the existing owner and validate the
actual consumer without adding another queue or controller.

## Verification

Run on a host with PowerShell installed:

```powershell
python -m pytest -p no:cacheprovider tests/orchestration/test_codex_packet_generator.py tests/orchestration/test_capability_packet_draft.py -q
git diff --check
```

The generator tests include complete new-format and legacy-name examples,
missing-context rejection, serialization checks, approval injection, safety
flags, bootstrap, and no-write checks. Test identities are fixtures, not owner
approval or real lock claims. Behavioral tests require a real PowerShell host;
static contract tests still run without it.

All approval, execution, staging, commit, push, PR, merge, broker, credential,
and trading decisions remain governed by AGENTS.md and the existing gates.
