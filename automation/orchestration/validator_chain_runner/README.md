# AI_OS Validator Chain Runner

This runner prints a JSON validation receipt to stdout. It does not write evidence files or modify repository state.

The receipt reports one of three outcomes:

- `PASS`: all validators passed.
- `REVIEW`: at least one validator needs operator review.
- `BLOCKED`: a required validator is missing, failed, or timed out.

The registered chain checks execution registry state, repository cleanliness, allowed and blocked paths, JSON and PowerShell syntax, required Markdown, sensitive paths, live-trading enablement, approval gates, commit-package review, and final Git status.

Run with the host's current PowerShell policy:

```powershell
powershell -NoProfile -File automation/orchestration/validator_chain_runner/Invoke-AiOsValidatorChain.DRY_RUN.ps1
```

The command prints JSON to stdout when it can start. It does not override the host policy. If policy blocks the runner or a validator, stop and request the policy owner's approved resolution.

Next safe action: review the receipt. A passing report does not grant approval for APPLY, commit, or push.
