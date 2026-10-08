CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN: AIOS-PACKET-RESTORE-PR1379-BRANCH-V1
AI_OS BOOTSTRAP REQUIRED: YES
IDENTITY MARKER: AIOS_GOVERNED_BRANCH_RESTORATION
SUPERVISOR IDENTITY: Human Owner Anthony Meza
WORKER IDENTITY: CODEX_LOCAL_BRANCH_WORKER
PACKET ID: AIOS-PACKET-RESTORE-PR1379-BRANCH-V1
MODE: APPLY
ZONE: AIOS_REPOSITORY_GIT
LANE: restore-pr1379-branch-v1
WORKTREE: resolve from pwd during preflight
BRANCH: resolve after preflight

APPROVAL AUTHORITY
OWNER_TITLE_INVOCATION authorizes only the bounded, non-destructive branch change and approved origin restoration declared here. branch_change: true. It does not approve any other protected action.

MISSION
Restore the local tracking branch for repository ai-rtony91/Ai_Os, approved origin https://github.com/ai-rtony91/Ai_Os.git, PR 1379, base main, head phase-a/bootstrap-publication-c015aad, at verified SHA c015aad4b9fc8a808029e6b3368804beb1fdba51.

PREFLIGHT
Resolve and verify the current AIOS worktree; require a clean worktree; verify repository identity; inspect origin. If origin is absent, configure exactly https://github.com/ai-rtony91/Ai_Os.git. If origin has any other URL, stop.

AUTHORIZED ACTIONS
1. Fetch origin without force.
2. Verify origin/phase-a/bootstrap-publication-c015aad resolves exactly to c015aad4b9fc8a808029e6b3368804beb1fdba51.
3. Create the exact local tracking branch only if absent.
4. Switch to that exact branch without force, rebase, reset, stash, or source editing.
5. Verify branch, HEAD, upstream, origin, and clean worktree, then stop.

ALLOWED PATHS
- .git/config
- .git/refs/heads/phase-a/bootstrap-publication-c015aad
- .git/HEAD

FORBIDDEN PATHS
- source files
- generated files
- credentials and secrets
- broker and trading paths

PROTECTED ACTION FLAGS
- staging: false
- commit: false
- push: false
- pull_request: false
- merge: false
- branch_change: true
- scheduler_or_service: false
- credentials_or_secrets: false
- broker_or_oanda: false
- order_submission: false
- live_trading: false
- money_movement: false

FAIL CLOSED
Stop on a dirty worktree, wrong repository identity, different existing origin, network or authentication failure, missing remote branch, remote SHA mismatch, unsafe checkout, or unexpected file mutation.

FORBIDDEN ACTIONS
No source or generated-file edits; staging; commit; push; pull-request changes; merge; rebase; reset --hard; force operations; substitute repository or branch; deployment; credentials; broker access; trading; money movement; or modification of the existing starting branch ref.

VALIDATOR CHAIN
Run git status --short --branch, git branch --show-current, git rev-parse HEAD, git rev-parse --abbrev-ref --symbolic-full-name @{upstream}, and git remote get-url origin.

STOP POINT
Stop immediately after the authorized branch restoration and final validation. Perform no other mutation.

FINAL REPORT FORMAT
Report observed repository, origin, starting branch and SHA, final branch and SHA, upstream, worktree status, validation, and STATUS.
