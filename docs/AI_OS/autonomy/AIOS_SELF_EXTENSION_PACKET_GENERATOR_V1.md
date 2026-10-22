# AIOS Self-Extension Packet Drafting

## Purpose

New-AiOsCapabilityPacketDraft.DRY_RUN.ps1 classifies capability intent and creates
a draft through the existing PowerShell generator. It performs no integration,
network calls, queue changes, worker launch, lock acquisition, or trading.

The output envelope remains AIOS_CAPABILITY_PACKET_DRAFT.v1. Its contained text
must satisfy AIOS_CODEX_PACKET_CONTRACT.v2 before packet_valid can be true.
The historical documentation filename remains unchanged.

## Required context

In addition to CapabilityName and CapabilityIntent, supply these explicit fields:

| Parameters | Required source |
| --- | --- |
| MissionId, MissionName | Assigned mission |
| ProgramId, ProgramName | Assigned program |
| EpicId, EpicName | Assigned epic |
| BucketId, BucketName | Assigned bucket |
| LockIdentity | Matching assigned lane/ownership context |
| Worktree | Actual repository folder |

Use the real assigned packet or campaign, not values made up from a capability
name. The hierarchy doctrine defines required fields, not their actual values.
An old call that supplies only a capability name and intent now returns a
blocked result with empty generated_packet_text and an explicit missing list.

The wrapper observes the branch in Worktree instead of assuming main. A missing
branch stays blocked. It creates a deterministic draft packet ID, uses DRY_RUN,
and keeps staging, commit, push, PR, and merge authority NOT AUTHORIZED.
A draft lock name does not prove any lock was acquired.

SuggestedZone, SuggestedLane, and TargetActor remain suggestions within the
review draft. Actor recognition does not authorize execution. The rough
capability_type and safety_tier classifications are routing hints, not approval.

## Existing path and rejection behavior

The wrapper is the inspected direct caller of
New-AiOsCodexPacket.DRY_RUN.ps1. It forwards explicit hierarchy/lock context and
the observed repository branch, plus its bounded review scope and checks.

The generator validates its serialized text. The wrapper also runs
Test-AiOsCodexPacket.DRY_RUN.ps1. A rejected, empty, malformed, unavailable, or
throwing validator cannot fall back to checking section headings. Invalid
draft text is withheld.

OutputJson returns the JSON envelope. AsPromptBlock emits text only for a valid
draft. Regardless of validity, execution_allowed, can_continue_without_anthony,
and writes_files remain false; requires_human_review remains true.

## Development queue boundary

This is a manual review/relay drafting surface. It is not a producer of approved
Python runtime queue items. Do not rename its envelope or copy packet_valid
into queue approval. Do not treat the generated text as an executable queue
payload.

The existing Python resolver/builder owns the runtime queue packet route.
Its packet format differs from the strict PowerShell v2 format. The independent
checks of each path do not prove a direct connection, actual task delivery,
sustained operation, or trading readiness.

Use existing assigned work, admission, ownership, validators, and queue machinery
for a later execution packet. This draft never creates that authority.

## Verification and owner decisions

The existing tests/orchestration/test_capability_packet_draft.py supplies clearly
labeled complete test context and checks the wrapper-to-generator-to-validator
path, protected-action denials, missing context, validator failures, and no
repository writes. Fixtures do not create production approval or locks.

```powershell
python -m pytest -p no:cacheprovider tests/orchestration/test_capability_packet_draft.py tests/orchestration/test_codex_packet_generator.py -q
```

Human review must confirm real context and allowed scope. APPLY, publishing,
protected actions, worker launch, broker connections, credentials, and trading
remain separate decisions under existing repository rules.
