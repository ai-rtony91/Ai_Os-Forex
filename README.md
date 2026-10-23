# AI_OS

AI_OS is a governed AI-assisted operating environment for building, managing, and improving projects through human-readable prompts, scoped worker lanes, canonical authority files, and validation before mutation.

It is not an autonomous replacement for human judgment. It is a structured project operating system: humans set direction, AI workers perform bounded work, governance defines safe behavior, and validation proves what changed.

For Trading Lab / Forex, AI_OS is a governed, human-controlled, broker-capable trading system and execution platform framework. AI_OS is the platform. Backtesting, paper simulation, supervised demo, and governed broker execution are execution stages inside the platform, not the full identity of AI_OS.

AI_OS aims for industrial-standard, professional-grade repo hygiene and automation discipline: scoped changes, traceable evidence, validation before claims, and clear safety boundaries by default.

Trading Lab / Forex is the first production vertical. AI_OS may support paper simulation, backtesting, signal validation, risk controls, supervised demo review, broker-readiness evidence, owner approval workflows, dashboard truth, and governed broker execution pathways. General live trading remains blocked. Broker credentials, account identifiers, real orders, webhooks, schedulers, daemons, and uncontrolled automation remain blocked. A single governed live micro-trade exception may exist only through `AIOS_FOREX_FINAL_LIVE_OPERATOR_BRIDGE_V1` with explicit human approval, runtime-only credentials, one-order-only enforcement, micro-size enforcement, stop loss, take profit, max loss gate, daily stop gate, kill-switch state validation, sanitized evidence, and no credential or account persistence.

## Current Status

- GitHub repo: `ai-rtony91/Ai_Os-Forex`
- GitHub repository ID: `1227385337`
- Active branch: `main`
- Active repo path: `C:\Dev\Ai.Os`
- Legacy inactive paths:
  - `C:\Dev\Ai_Os_OLD_DO_NOT_USE`
  - `C:\Dev\Ai.Os_OLD_DO_NOT_USE`
  - `C:\Users\mylab\OneDrive\GitHub\AI_OS_V2_OLD_DO_NOT_USE`
- Current focus: front-door documentation, source-of-truth clarity, worker orchestration, telemetry, safe workflows, Trading Lab / Forex stage work, governed broker-readiness evidence, and dashboard truth
- Operating model: Phase -> Stage -> Workload Pack -> Task ID -> DRY_RUN/APPLY -> validation -> selective commit
- Commit/push rule: never commit or push unless explicitly approved

## Active Repository Location

Active repo path:

```text
C:\Dev\Ai.Os
```

Active branch:

```text
main
```

Legacy inactive paths:

```text
C:\Dev\Ai.Os_OLD_DO_NOT_USE
C:\Users\mylab\OneDrive\GitHub\AI_OS_V2_OLD_DO_NOT_USE
```

The legacy OneDrive path must not be used for active repo work. It is backup/reference only until the operator explicitly deletes it. Any worker that starts under the OneDrive path must STOP and report before running Git, Codex, merge, push, startup, or automation commands.

Before any repo task, workers must confirm:

```powershell
pwd
git status --short --branch
git branch --show-current
git remote -v
```

Expected state:

- path: `C:\Dev\Ai.Os`
- branch: `main`
- status: clean and synced with `origin/main`

## Repository Identity Rule

AI_OS is the project/system identity.

Ai.Os is the active local folder name, not a separate GitHub repository.

Current identity:

- GitHub repo: `ai-rtony91/Ai_Os-Forex`
- GitHub repository ID: `1227385337`
- Active branch: `main`
- Current local folder: `C:\Dev\Ai.Os`
- Legacy inactive local folders:
  - `C:\Dev\Ai_Os_OLD_DO_NOT_USE`
  - `C:\Dev\Ai.Os_OLD_DO_NOT_USE`
  - `C:\Users\mylab\OneDrive\GitHub\AI_OS_V2_OLD_DO_NOT_USE`

Future desired naming is not active yet:

- GitHub repo may later be renamed to `AiOS`.
- Local folder may later be renamed to `AIOS`.
- Do not assume those names are active until an approved rename pass occurs.

Do not search for or assume:

- `aiosv2`
- `ai-rtony91_aiosv2`
- `AI-OS-Project`
- `Ai.Os`
- `ai-rtony91_Ai_Os_CLEAN`

Any AI, Codex, Claude, or assistant inspecting AI_OS must target repo `ai-rtony91/Ai_Os-Forex` on branch `main` unless the user explicitly says otherwise.

If a tool only sees `ai-rtony91/Ai_Os-Forex`, that is correct. It must switch/check branch `main` before judging project state.

The old `v2/aios` branch is legacy/reference unless the operator explicitly instructs otherwise.

## Start Here

For any human contributor, AI assistant, or Codex worker:

1. Read `AGENTS.md`.
2. Confirm the branch with `git status --short --branch`.
3. Read `docs/governance/source-of-truth-map.md`.
4. Read `docs/audits/active-system-map.md`.
5. Identify the existing canonical file that owns the topic.
6. Use DRY_RUN before APPLY unless the prompt explicitly authorizes edits.
7. Edit only the approved files.
8. Validate before reporting completion.

The default posture is: resume from existing authority, do not create a new brain.

For OpenAI CLI, Codex, ChatGPT, and Night Supervisor onboarding, use `docs/workflows/OPENAI_CODEX_NIGHT_SUPERVISOR_ONBOARDING.md` and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File automation/onboarding/Test-AiOsOpenAiCodexNightSupervisorOnboarding.ps1 -Mode DRY_RUN
```

## What AI_OS Is

AI_OS is a human-first automation and orchestration platform. It helps convert goals written in normal language into controlled project work:

- inspect the current repo state
- identify ownership and canonical authority
- prevent duplicate documentation and conflicting instructions
- route work to a bounded worker lane
- protect runtime, trading, security, dashboard, and orchestration systems
- run validation before mutation
- report exactly what changed and what remains unknown

The system is designed to make complex work easier to control, not to remove human decision-making.

## What AI_OS Is Not

AI_OS is not:

- AGI, sentience, consciousness, or magical autonomy
- an uncontrolled live trading bot
- a permission-free broker execution bypass
- a credential store or secret manager
- a direct LLM live-order controller
- a reason to skip validation
- a place for duplicate source-of-truth documents

AI_OS can help build systems. It must not silently become the authority over them.

## Operating Philosophy

AI_OS uses a few strict ideas to keep work safe and legible:

- Existing canonical file first.
- DRY_RUN before APPLY.
- Smallest safe edit first.
- One responsibility per file or folder.
- One worker, one lane, one task, one output.
- Human approval for risky actions.
- No mass delete, move, rename, reset, merge, push, or credential changes without explicit approval.
- Runtime, orchestration, trading, dashboard, telemetry, and protected governance files require clear scope before edits.

Canonical authority matters because AI-assisted projects can drift quickly. When multiple files claim to be the same "brain," workers lose the ability to resume safely. AI_OS prevents that by defining where authority lives and by treating generated reports, archives, drafts, and runtime state as different kinds of evidence.

## DRY_RUN vs APPLY

`DRY_RUN` means inspect, plan, report, and validate without changing files unless the user explicitly approves mutation.

`APPLY` means create or edit only the approved files, then validate and report the result.

Every work session should end with:

- files inspected
- files created
- files changed
- validation result
- git status
- commit status
- push status
- next safe action

## Repository Map

| Path | Role |
|---|---|
| `README.md` | Human front door, quick start, repo orientation, contributor entry point |
| `AGENTS.md` | Required behavior rules for Codex and AI coding workers |
| `docs/governance/` | Source-of-truth maps, ownership, doctrine, file placement rules |
| `docs/workflows/` | Operator workflows, resume flow, APPLY routing, branch/lane rules |
| `docs/AI_OS/design/` | Visual language specs for terminal flair, worker HUDs, and operator-facing command presentation |
| `docs/security/` | Security posture, approval model, secret prevention, access boundaries |
| `docs/architecture/` | Durable system architecture and long-term AI_OS vision |
| `docs/audits/` | Inspection history, cleanup decisions, active system maps |
| `automation/` | Orchestration scripts, worker routing, approval gates, validators |
| `services/` | Runtime, dispatcher, policy, telemetry, and orchestrator services |
| `scripts/` | Developer and operator helper commands |
| `apps/` | User-facing apps, including dashboard and Trading Lab / Forex surfaces |
| `telemetry/` | Runtime state, work ledgers, visibility data, and generated evidence |
| `archive/` | Historical/reference-only material, not active authority |

## Authority Model

The active source-of-truth map is `docs/governance/source-of-truth-map.md`.

The active system dependency map is `docs/audits/active-system-map.md`.

Root authority files such as `README.md`, `AGENTS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, `SOURCE_LOG.md`, `ERROR_LOG.md`, `HALLUCINATION_LOG.md`, `AAR.md`, `DAILY_REPORT.md`, and `WHITEPAPER.md` remain protected. Edit them only when explicitly scoped.

If a draft, archive, generated report, legacy CLEAN-era document, or runtime artifact conflicts with active root or governance authority, active authority wins unless the user approves a promotion.


## Prompt Routing Visual Rule

The canonical prompt-routing rule lives in AGENTS.md.
Any prompt intended to be pasted into Codex must follow the
AGENTS.md Prompt Routing Visual Rule. README preserves this pointer
for front-door orientation only; it does not duplicate or override
the operating rule.

## Worker Model

AI_OS workers are controlled contributors. A worker should know:

- purpose
- branch or worktree
- allowed files
- blocked files
- task ID or workload pack
- validation chain
- expected output
- stop condition

Codex workers must read `AGENTS.md` first. They should not create new docs when an existing canonical file owns the topic. They should not edit the same file tree as another worker. Main control owns merge and push approval. Workers must also follow the `AGENTS.md` Operator Efficiency and Modern CLI-First Workflow Rule: prefer the simplest safe local CLI path, distinguish Git state from filesystem/process locks, and avoid browser workflows when CLI can complete the work safely.

Current AI_OS operation uses ChatGPT Personal for orchestration, Codex East for bounded repo execution, Claude Chat for inspection/review, Claude Code West only when assigned, and Relay/Night Supervisor for evidence and status. The canonical AI Tool Routing Contract lives in `docs/governance/operational-doctrine.md`.

## Branch Philosophy

Branches are work lanes, not memory storage.

Use a branch for a meaningful work batch. Finish, validate, report, and close the lane before starting unrelated work. Do not rely on a branch to remember context that belongs in canonical docs, workflow docs, ledgers, or audit records.

## Trading Lab Boundary

Trading Lab / Forex is the first production vertical. AI_OS is the platform; backtesting, paper simulation, supervised demo, and governed broker execution are execution stages inside it. General live trading remains blocked by default.

Allowed when explicitly scoped:

- paper simulation
- backtesting
- latency tracking
- signal validation
- paper route previews
- supervised demo review
- broker-readiness evidence
- owner approval workflows
- dashboard truth
- governed broker execution pathway design and evidence, without activating broker execution
- local-only telemetry

Single governed live exception:

- A single governed live micro-trade exception may exist only through `AIOS_FOREX_FINAL_LIVE_OPERATOR_BRIDGE_V1`.
- It requires explicit human approval, runtime-only credentials, one-order-only enforcement, micro-size enforcement, stop loss, take profit, max loss gate, daily stop gate, kill-switch state validation, sanitized evidence, and no credential or account persistence.

Blocked:

- general live broker execution
- real orders outside the governed single-live-micro-trade exception
- broker credentials or account identifiers in repo files
- webhooks, schedulers, daemons, and uncontrolled automation
- broker credentials or API keys
- LLMs directly in live order execution paths

## Long-Term Direction

AI_OS may eventually help humans build and manage systems such as trading bots, dashboards, automation workflows, orchestration layers, validation pipelines, and operational tools.

The recursive idea is practical: AI_OS itself is also a project. The same governance, validation, workflow, ownership, and orchestration rules used to build another project should eventually help AI_OS organize and improve itself safely.

That means AI_OS should become better at identifying missing ownership, detecting duplicate authority, recommending next safe steps, improving maintainability, and stabilizing its own structure over time.

## Validate A Documentation Edit

For a documentation-only change to this front door, run:

```powershell
git diff --check
git diff -- README.md docs/architecture/AI_OS_WHITEPAPER.md
git status --short --branch
```

Do not commit or push unless the user explicitly approves that action.
