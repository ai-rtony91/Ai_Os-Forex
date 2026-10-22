# AIOS Delivery Receipt Instrumentation V1

This component records measured, offline evidence for governed APPLY work. The canonical Python packet builder inserts `task-start`, `task-complete`, and `task-blocked` commands. A failed start is a stop condition before mutation. DRY_RUN generation is unchanged and performs no timing write.

Active starts are runtime-only files under `.aios/runtime/engineering_timing/`. A terminal receipt is accepted once per task and packet identity; identical retries are idempotent and conflicts fail closed. Missing start evidence yields a null duration and an exact exclusion reason, never an estimate. Terminal CLI commands automatically upsert the tracked Codex metadata and append deduplicated forecast-compatible velocity events; validation and commit events are emitted only when the receipt contains that evidence.

The GitHub workflow uses read-only permissions and event payload data to upload sanitized workflow-validation and closed-PR receipts. It skips its own workflow completion. Artifacts do not write back to the repository: an operator must download them and run bounded local `ingest-github-receipts` processing.

PR forecast completion credit requires a merged PR, a nonempty matching head SHA, and a successful validation receipt. Task completion or commit creation alone does not grant merge or validation credit. First Withdrawable Dollar remains a separate milestone.

The PowerShell packet generator remains unchanged because the repository-aligned Python APPLY builder is the canonical implementation for this lane; PowerShell host validation is also unavailable in the current environment.

No network client, credential loading, broker access, order execution, deployment, repository write from Actions, push, or merge capability is introduced.
