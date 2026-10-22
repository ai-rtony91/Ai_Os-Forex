# AI_OS Orchestration

## Platform V1 public API

`automation.orchestration.platform` is the canonical integration surface for
queue, dispatcher, packet builder/generator, resolver, orchestration spine,
validation, reporting, and countdown behavior. Existing modules remain
backward-compatible implementation and CLI surfaces. New callers should use the
facade rather than duplicating component composition. See
`docs/orchestration/AIOS_ORCHESTRATION_PLATFORM_V1_MIGRATION.md`.

`OrchestrationPlatform.compound_work_braid()` composes the canonical work-packet
inventory into deterministic strands, braids, and execution cables. The
controller is local planning only: it does not mutate a queue, dispatch a worker,
execute its continuation packet, or grant protected authority. See
`docs/orchestration/AIOS_COMPOUND_WORK_BRAID_V1.md`.

This folder holds safe control files for AI_OS worker coordination.

The goal is simple: before a worker starts, AI_OS should know which packet the worker is allowed to handle, which paths are allowed, which paths are blocked, which approval gate applies, and which validation is required.

This folder is not for live trading, broker connections, OANDA access, API keys, secrets, startup tasks, scheduled tasks, or automatic commits.

## Current Boundary

Treat this folder as the approved canonical orchestration layer and an active but still unconsolidated orchestration workbench.

Active areas that should be preserved while consolidation is planned:

- clean-state checks and preflight gates
- work packet creation and state movement
- worker registry and worker inbox helpers
- approval inbox and approval gate helpers
- validator recommendation and validator chain helpers
- commit package recommendation helpers
- lock and path-conflict helpers

Areas that require consolidation before further scaling:

- duplicate worker registries
- command queue compatibility labels versus canonical work packet authority
- duplicate approval inbox examples and processors
- duplicate supervisor/runtime/control-loop concepts
- root-level `show-*` scripts that overlap with subfolder tools
- tracked example JSON state files that represent generated/runtime snapshots
- overlap between `scripts/` and `automation/orchestration/`

See `docs/audits/orchestration-consolidation-plan.md` for the cleanup plan.

## Canonical Paths

Display and status tools should prefer these approved active paths first:

- worker registry: `automation/orchestration/workers/AIOS_WORKER_REGISTRY.json`
- worker profiles: `automation/orchestration/workers/AIOS_WORKER_PROFILES.json`
- worker inbox: `automation/orchestration/workers/inbox/AIOS_WORKER_INBOX.json`
- campaign registry: `automation/orchestration/campaign_registry/AIOS_STRATEGIC_CAMPAIGN_REGISTRY.json`
- queue/work packets: `automation/orchestration/work_packets/`
- command queue compatibility/evidence: `automation/orchestration/command_queue/AIOS_COMMAND_QUEUE.json` (not active work authority when the file marks itself stale or non-canonical)
- approval inbox: `automation/orchestration/approval_inbox/APPROVAL_INBOX_001.json`
- approval gate: `automation/orchestration/approval_inbox/APPLY_APPROVAL_GATE_001.json`
- validator chain: `automation/orchestration/validators/`
- commit packages: `automation/orchestration/commit_packages/`
- orchestration runtime bundle: `automation/orchestration/runtime/Get-AiOsRuntimeStateBundle.DRY_RUN.ps1`
- runtime next-command recommendation: `automation/runtime/recommendation/Get-AiOsNextCommand.ps1`
- attack-to-finish completion contract: `docs/governance/AIOS_ATTACK_TO_FINISH_CONTRACT_V1.md`
- attack-to-finish schema: `schemas/aios/orchestration/AIOS_ATTACK_TO_FINISH_CONTRACT.v1.schema.json`
- frontend-safe state projection contract: `schemas/aios/orchestration/STATE_PROJECTION_RULES.md`
- runtime visibility read-model schema: `schemas/aios/orchestration/RUNTIME_VISIBILITY_SCHEMA.json`
- operator status: `automation/orchestration/control/Get-AiOsOperatorControlLoop.DRY_RUN.ps1`

Legacy root fallback examples were archived after canonical paths became the preferred source and fallback reads were made optional:

- `archive/orchestration_legacy/root_examples/packet_queue.example.json`
- `archive/orchestration_legacy/root_examples/worker_registry.example.json`
- `archive/orchestration_legacy/root_examples/approval_inbox.example.json`
- `archive/orchestration_legacy/root_examples/validator_chain.example.json`
- `archive/orchestration_legacy/root_examples/commit_package.example.json`

Status and display scripts may still mention those filenames as optional compatibility labels, but canonical paths above are the active source of truth.

## Current Safe Defaults

- Cleanup is not approved from this README.
- Old/example/reference files must not be moved until references are checked.
- Runtime/generated state is protected evidence until a retention policy exists.
- `automation/operator/` remains active launcher/legacy-mixed until dependency review.
- Dashboard status remains fixture-driven until API migration to `services/orchestrator/` is approved.
- Trading Lab package ownership remains REVIEW_REQUIRED; both `apps/trading_lab/trading_lab/` and `aios/modules/trader/` stay active.
- `docs/AI_OS/**` remains reference/source material until file-by-file classification.
- Root `work_packets/**` is not active queue authority; it needs a retention or migration decision before archive.
- Root `approvals/**` is not active approval authority; it needs a retention or migration decision before archive.
- Active work routing should prefer `automation/orchestration/work_packets/` plus the campaign registry over command queue compatibility files.
- `automation/orchestration/work_packets/proposed/`, `deferred/`, `rejected/`, `templates/`, and `examples/` are not active executable work queues.
- `automation/operator/AIOS_PARALLEL_WORKER_REGISTRY.json` is compatibility evidence until adapter-first use is proven and retirement is approved.
- `automation/orchestration/*.example.json` files require fixture ownership review before archive.
- Current duplicate-brain cleanup evidence identifies 0 safe delete candidates.

## Local-First Orchestration Primitives

Append-only ledgers, runtime logs, and telemetry artifacts are evidence/audit records only and are not command authority.

`approval_inbox` and `APPLY_APPROVAL_GATE_001.json` remain the APPLY authority checkpoint.

Validator-chain output is evidence and validation guidance only; validators do not grant APPLY authority.

Worker registry, worker profiles, lock registry, lane status, and path-conflict policy remain worker-boundary enforcement mechanisms.

ATTACK-TO-FINISH output is completion evidence and routing metadata only. Completion packets must use `docs/governance/AIOS_ATTACK_TO_FINISH_CONTRACT_V1.md` and `schemas/aios/orchestration/AIOS_ATTACK_TO_FINISH_CONTRACT.v1.schema.json` to name the exact blocker, owner file, validator/test, runner/script, missing evidence field, unlock status, next packet, owner action, stop condition, and no-bloat guard.

State projection and frontend display boundaries are defined in `schemas/aios/orchestration/STATE_PROJECTION_RULES.md`, `schemas/aios/orchestration/RUNTIME_VISIBILITY_SCHEMA.json`, and `schemas/aios/orchestration/runtime_state_bundle.schema.json`.

Future dashboard, GUI, UE5, VR, or AR layers may read display-safe projections only. They must preserve `execution_allowed=false`, `mutation_allowed=false`, `safe_for_frontend_display=true`, blocked actions, source paths, source type, freshness, and next safe action. Visual layers must not expose direct controls for APPLY, approval mutation, packet movement, worker launch, lock mutation, runtime mutation, protected git actions, broker/live trading, webhooks, orders, or secrets.

## Safe Use

Run the clean-state gate before assigning work:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/clean_state_gate.ps1
```

If PowerShell 7 is installed, this command may also work:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File automation/orchestration/clean_state_gate.ps1
```

The gate reports whether the repo is clean enough for a launch decision. A blocked result means the operator should review the listed reasons before continuing.

## Cleanup Rule

Do not delete or move orchestration files blindly. Before archiving any file, verify references from:

- `aios.ps1`
- `automation/operator/`
- `automation/orchestration/`
- `scripts/`
- `docs/AI_OS/`
- `.github/`

When uncertain, write an audit note instead of changing files.
# Master runtime

Use `python aios.py status|plan|run|resume|validate` from the repository root. The V1 master runtime is a deterministic coordinator over the existing `OrchestrationPlatform`, not a replacement for its component algorithms. Runtime checkpoints are local-only under `.aios/runtime/`.
