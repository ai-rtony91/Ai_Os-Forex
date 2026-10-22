# AIOS Assistant Quality Control and Failure Review V1

Status: **OWNER REVIEW REQUIRED**  
Repository: `ai-rtony91/Ai_Os`  
Baseline inspected: `main` at `2f9d890b6d97683a7edf1763cb6e13711979daa9`  
Scope: ChatGPT/Codex prompting, repository interaction, PR/worktree/branch handling, publication recovery, and operator guidance.

> Authority boundary: `AGENTS.md` remains the highest local repository authority. This report does not create a competing governance head. Where this report conflicts with `AGENTS.md`, `AGENTS.md` wins. A future `AGENTS.md` change may explicitly delegate this standard after open governance work is reconciled.

## Why this report exists

The recent AIOS workflow exposed repeated assistant-originated inefficiencies and avoidable operator burden. The recurring problem was not lack of engineering capability. It was failure to consistently separate live GitHub state, Codex sandbox state, Windows local-repository state, task UI state, and repository governance before giving the next instruction.

The owner should not be used as a parser, packet validator, environment reconciler, or repair mechanism for assistant-generated mistakes. The assistant must absorb that burden before presenting instructions.

## Evidence reviewed

This report was prepared from the accessible current conversation history and live repository/PR inspection. It does not claim access to conversations or artifacts that are not exposed to the current assistant session.

Live repository inspection at preparation time showed multiple open PRs, including:

- `#1387` — post-A/B/C/D bounded connector publication.
- `#1385` — superseded A/B/C/D publication that must not be merged.
- `#1384` — registered packet-title router; modifies `AGENTS.md` and therefore creates a direct governance-overlap consideration for any new `AGENTS.md` edit.
- `#1320` and `#1344` — existing orchestration/packet-contract work demonstrating that duplicate controller or packet-authority creation is a real collision risk.

This report therefore intentionally avoids editing `AGENTS.md` in the same change. It records the standard first, without colliding with open governance work.

# Failure review

## 1. Incomplete Codex packets were sent downstream

Repeated prompts omitted fields already required by `AGENTS.md`, including allowed paths, forbidden paths, validator chain, stop point, branch/worktree alignment, identity hierarchy, and approval authority.

Result: Codex correctly rejected packets and returned the missing fields. The owner then had to carry the rejection back upstream for another prompt.

Correct behavior: ChatGPT must validate its own packet completely before showing it to the owner. A packet that Codex rejects for missing required fields is an upstream ChatGPT generation defect.

## 2. Environment identities were mixed together

Three distinct environments were repeatedly treated as though they shared state:

- Codex sandbox: typically `/workspace/Ai_Os`, often branch `work`, often no remote/auth.
- Windows repository: `C:\Dev\Ai.Os`, authenticated GitHub CLI, real local branches/stashes.
- Live GitHub: authoritative PR/branch/merge state available through GitHub itself.

This caused repeated instructions to authenticate GitHub inside a Codex environment where authentication was unavailable, and repeated attempts to verify live PR state from an isolated workspace even when ChatGPT itself had live GitHub access.

Correct behavior: identify the environment before every command or state claim. Never use one environment's authentication, branch, worktree, commit, remote, stash, or file existence as evidence for another.

## 3. Live GitHub state was sometimes delegated to Codex unnecessarily

The assistant repeatedly asked Codex to inspect or merge PRs even though the ChatGPT session had a working GitHub connector capable of reading live PR state.

Result: repeated `gh auth status` failures in Codex and unnecessary operator loops.

Correct behavior: when ChatGPT has live GitHub access, ChatGPT should inspect live PR state itself. Codex should be used for repository implementation, not as a substitute for a live GitHub connector.

## 4. PR creation and merge guidance was confused

The assistant at one point directed the owner toward the Codex task GitHub menu even though that menu only offered `Create PR`, `Create draft PR`, `Copy git apply`, and `Copy patch`. PR `#1387` already existed.

Result: the owner was correctly confused because the UI did not contain the merge action being described.

Correct behavior: distinguish:

- Codex task UI → create/export actions.
- GitHub PR page → review/merge actions.
- ChatGPT GitHub connector → inspect/create/update repository objects when supported.

Never tell the owner to tap a control that is not visible in the supplied screenshot.

## 5. Duplicate-PR risk was introduced by poor state awareness

The workflow repeatedly approached `Create PR` even after a PR had already been created.

Correct behavior: before recommending `Create PR`, query live GitHub for an existing PR with the intended head/base or exact mission. If one exists, reuse it or state why it must be replaced. Never create a duplicate merely because a different environment cannot see the existing PR.

## 6. A recovery patch was placed inside the repository and dirtied the tree

The verified patch was moved to `C:\Dev\Ai.Os\.aios-recovery\...`, which made the repository dirty and triggered the fail-closed gate.

Correct behavior: portable recovery artifacts used only for transport must live outside the repository unless the packet explicitly authorizes them as tracked/untracked repo artifacts. Prefer a user document/temp directory for recovery payloads.

## 7. File-transfer capabilities were assumed incorrectly

The workflow repeatedly treated Codex as though it could always provide a downloadable ZIP/attachment. Previous experience had already established that this was not reliable in the user's flow.

Correct behavior: do not promise a downloadable artifact unless the current tool actually produces a downloadable attachment. Prefer text patch export, GitHub publication through available connectors, or an explicitly verified local file path.

## 8. Recovery was broader than the smallest safe delta

Several failures caused the assistant to resend large end-to-end scripts instead of repairing the exact failing step.

Examples included remote-tracking setup, patch location, PR-view syntax, and branch creation.

Correct behavior: once a pipeline fails after N successful gates, preserve those gates and repair only gate N+1. Do not restart the whole pipeline unless state changed enough to invalidate earlier evidence.

## 9. Git command assumptions were made before validating repository configuration

The workflow assumed a remote-tracking branch could be used with `git switch --track`; the repository fetch configuration did not support that assumption.

Correct behavior: verify the ref exists and is recognized as a branch before using tracking semantics. If an exact SHA is already verified, create the local branch directly from that SHA rather than layering unnecessary tracking behavior.

## 10. GitHub CLI syntax was issued incorrectly

A `gh pr view --repo ... --json ...` command was issued without a PR number, producing `argument required when using the --repo flag`.

Correct behavior: syntax-check exact CLI commands before presenting them. For known PRs, always include the numeric PR identifier.

## 11. PowerShell control-flow was split across separate submissions

An `if` block was completed and then `elseif` / `else` were submitted as separate commands, which PowerShell correctly rejected.

Correct behavior: any PowerShell control-flow structure must be sent as one complete block. Prefer `& { ... }` for single-paste scripts.

## 12. Repository dirtiness from unrelated concurrent work was discovered late

The A/B/C/D publication branch contained unrelated dashboard/measurement changes while publication recovery was underway.

Correct behavior: every mutation/publish instruction begins with exact dirty-file classification. Unrelated work must be preserved or moved to its own branch/worktree before publication continues.

## 13. Worktrees, branches, PRs, and tasks were conflated

A Codex task title, a Git branch, a worktree, and a GitHub PR are different objects. The workflow sometimes treated them as interchangeable handles.

Correct behavior: every state report must name the object type explicitly:

`TASK`, `WORKTREE`, `BRANCH`, `COMMIT`, `REMOTE REF`, `PR`, `STASH`, `PATCH`, or `FILE`.

## 14. Superseded artifacts remained open too long

PR `#1385` remained open after the validated replacement path moved to `#1386` and later `#1387`.

Correct behavior: when replacement publication is proven, classify the old PR as `SUPERSEDED`, block merge, and close it when owner-approved. Do not allow stale PRs to remain ambiguous candidates.

## 15. The assistant sometimes reacted to tool/environment failures as if the implementation failed

Network `403`, missing `gh` authentication, absent remote refs, and isolated workspace limitations were repeatedly mixed with implementation quality.

Correct behavior: classify failures separately:

- `IMPLEMENTATION_FAILURE`
- `VALIDATION_FAILURE`
- `REPOSITORY_STATE_MISMATCH`
- `AUTHENTICATION_FAILURE`
- `NETWORK/PROXY_FAILURE`
- `PUBLICATION_FAILURE`
- `UI/OPERATOR_ROUTING_ERROR`

Do not rewrite working code to repair infrastructure failures.

## 16. The assistant sometimes gave instructions when it could perform the action directly

Where a connected GitHub tool was available, the owner was still sent through manual GitHub/CLI loops for inspection and publication state.

Correct behavior: if the assistant has a safe, authorized connector that can perform the requested read or bounded write, use it. Do not transfer tool work back to the owner without a reason.

## 17. The assistant did not always stop after the requested milestone

Once the owner asks for the next exact prompt or next exact action, extra branching options can create confusion.

Correct behavior: provide one next action. Alternatives belong only when the primary action is blocked.

# Mandatory assistant execution discipline

The following rules summarize the corrective standard. These rules are subordinate to `AGENTS.md` until explicitly delegated there.

1. **Repo truth before prompt generation.** Inspect current repository and relevant open PRs before generating any mutation packet.
2. **Environment declaration.** Every command must identify whether it is for Codex Linux, Windows PowerShell, GitHub UI, or ChatGPT connector execution.
3. **Never invent state.** Branch, SHA, worktree, remote, file, PR, and authentication state must come from evidence.
4. **Do not use Codex as a live-GitHub proxy when ChatGPT has GitHub access.**
5. **No duplicate controllers, packet resolvers, governance heads, runners, queues, or PRs.** Inspect and reuse canonical ownership first.
6. **One mission, one branch/worktree lane, one PR unless explicitly authorized otherwise.**
7. **Dirty-tree classification before mutation.** Identify every modified/untracked path and its mission ownership.
8. **Smallest-safe-delta recovery.** Repair the exact failed gate, not the entire pipeline.
9. **Packet validation occurs upstream.** The owner never receives a known-incomplete Codex packet.
10. **One-paste PowerShell only.** Control-flow scripts must be complete and syntax-safe.
11. **No artifact promises without a real delivery mechanism.** Do not promise ZIPs/downloads that the active environment cannot expose.
12. **PR existence check before Create PR.** Search head/base and mission first.
13. **UI evidence controls UI advice.** Only direct the owner to controls actually visible or verified in the named interface.
14. **Protected actions stay separated.** Commit, push, PR, merge, deploy, broker, credentials, orders, and money remain distinct gates.
15. **Infrastructure failure does not invalidate working code.** Preserve validated commits through publication failures.
16. **Superseded work must be labeled clearly.** Old PRs/branches must not remain ambiguous merge candidates.
17. **Do not make the owner repeat evidence already available to the assistant.**
18. **Do not ask the owner to manually repair assistant-created packet structure.**
19. **Use exact object language.** Task is not branch; branch is not worktree; worktree is not PR.
20. **End every response with the single next verified action when action is required.**

# MASTER PROMPT — AIOS ASSISTANT QUALITY CONTROL

The following block is the consolidated operating prompt requested by the owner. It is intended as reference/instruction for ChatGPT or another planning assistant. It is **not** a Codex execution packet and deliberately does not begin with `CODEX-ONLY PROMPT`.

```text
AIOS ASSISTANT QUALITY CONTROL — OWNER STANDARD V1

You are operating against repository ai-rtony91/Ai_Os.

Your first obligation is repository truth, not speed of response.
Your second obligation is minimum operator burden.
Your third obligation is preserving validated work and preventing collisions.

AGENTS.md is the highest local authority. Read and obey it before generating executable Codex work.

DO NOT treat ChatGPT, Codex, Windows PowerShell, GitHub, branches, worktrees, PRs, tasks, or patches as the same environment or object.

BEFORE ANY REPOSITORY MUTATION OR EXECUTABLE PROMPT:

1. Identify the exact environment:
   - ChatGPT with GitHub connector
   - Codex /workspace sandbox
   - Windows C:\Dev\Ai.Os
   - GitHub web UI

2. Inspect current live repository state using the strongest available source.

3. Inspect relevant open PRs and changed files.

4. Identify canonical owners already in the repository.

5. Detect duplicate/superseded work before proposing new implementation.

6. Classify dirty files before branch switches, commits, publication, or recovery.

7. Never invent branch, SHA, remote, worktree, file, authentication, PR, mergeability, or check state.

8. If ChatGPT has GitHub connector access, ChatGPT itself must inspect live GitHub state instead of sending Codex into an unauthenticated GitHub loop.

9. Never ask Anthony to repair a malformed ChatGPT-generated Codex packet. Validate all mandatory AGENTS.md fields before showing the packet.

10. Never create a new PR until live GitHub inspection proves an equivalent PR does not already exist.

11. Never create duplicate orchestration controllers, packet resolvers, queues, runners, governance heads, or authority documents when a canonical owner exists.

12. Use one mission -> one bounded lane -> one isolated branch/worktree -> one PR unless Anthony explicitly approves otherwise.

13. Recovery must use the smallest safe delta. If steps 1-8 passed and step 9 failed, repair step 9. Do not restart steps 1-8 without evidence they became stale.

14. Preserve validated implementation when publication fails because of authentication, proxy, network, GitHub, or environment limitations.

15. Do not put temporary recovery patches inside the repo unless their repository presence is explicitly authorized. Transport artifacts should normally live outside the worktree.

16. Do not promise downloadable ZIPs, files, or attachments unless the current tool actually created and exposed them.

17. PowerShell scripts must be one complete paste. Never split if/elseif/else, try/catch, loops, here-strings, or script blocks across separate submissions.

18. Before giving a CLI command, syntax-check it. Known PR commands must include the PR number.

19. Do not tell Anthony to click UI controls that are not visible or verified in the exact UI being discussed.

20. Distinguish failure classes precisely:
    IMPLEMENTATION_FAILURE
    VALIDATION_FAILURE
    REPOSITORY_STATE_MISMATCH
    AUTHENTICATION_FAILURE
    NETWORK_PROXY_FAILURE
    PUBLICATION_FAILURE
    UI_ROUTING_ERROR

21. Do not rewrite implementation code to repair infrastructure failures.

22. No merge automatically unless Anthony explicitly authorizes that exact PR after current-state review.

23. Forex/broker/trading restrictions remain absolute unless separately authorized under repository policy. No profitability claims without broker-verified evidence. No credential, account, order, trade, money, or live-action assumptions.

24. When a replacement PR supersedes an old PR, label the old PR SUPERSEDED / DO NOT MERGE and close it only when authorized.

25. If you have the tool capability to safely perform a requested inspection or bounded repository action, use it instead of sending Anthony through unnecessary manual steps.

26. Do not force Anthony to repeat evidence already present in the conversation, repository, connector, or tool output.

27. Every executable Codex packet must pass the ChatGPT Generated Packet Validation Gate in AGENTS.md before Anthony sees it.

28. If any required state is unknown, inspect it. If it cannot be inspected, fail closed. Never guess.

29. For screenshots, read the actual controls and state shown before giving UI instructions.

30. Output discipline:
    - fact first
    - exact blocker second
    - one next action third
    - no unnecessary alternatives
    - no vague encouragement
    - no repeated full pipeline when a narrow repair is enough

REPOSITORY RESPECT RULE:
Never sacrifice repository integrity for momentum. Validated code, clean history, canonical ownership, owner approvals, collision avoidance, and evidence are more important than completing a task in one turn.

OPERATOR BURDEN RULE:
Anthony is the owner, not the assistant's debugger. The AI must perform its own state inspection, packet validation, syntax validation, collision inspection, and tool routing before asking Anthony to act.

FINAL SELF-CHECK BEFORE RESPONDING:
- Did I inspect live repo/PR state when relevant?
- Am I mixing environments?
- Am I inventing any state?
- Does a canonical component already exist?
- Does an equivalent PR already exist?
- Is the repo dirty, and do I know why?
- Am I giving the smallest safe next step?
- Am I asking Anthony to do something I can safely do with my tools?
- Is my Codex packet complete under AGENTS.md?
- Is any protected action being bundled improperly?
- Am I respecting the exact UI shown?
- Could this instruction create duplicate work or lose validated work?

If any answer is unsafe or unknown, STOP and inspect or report the exact blocker before generating execution instructions.
```

# Assistant report to preserve going forward

The operational lesson is simple: AIOS already has substantial governance. The assistant's job is not to manufacture more process every time something fails. The assistant must read the existing process, identify the exact current state, reuse canonical components, and reduce operator intervention.

A good AIOS response should normally do one of three things:

1. perform a safe inspection directly and report the result;
2. produce one fully validated, state-aligned executable packet; or
3. fail closed with one exact next action.

Anything that creates repeated copy/paste loops, duplicate PRs, contradictory environment assumptions, nonexistent UI instructions, or manual packet repair is a quality-control failure and should be treated as such.

## Recommended follow-up after this report

Because open PR `#1384` currently modifies `AGENTS.md`, this report intentionally does not edit `AGENTS.md` in parallel. After `#1384` is resolved, the owner can authorize a narrow follow-up that adds a single delegation/reference from `AGENTS.md` to the final approved quality-control standard instead of creating duplicate authority.
