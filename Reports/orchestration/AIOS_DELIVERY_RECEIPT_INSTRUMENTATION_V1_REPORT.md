# AIOS Delivery Receipt Instrumentation V1

## Automatic measurement
Governed APPLY tasks now receive runtime-only starts and COMPLETE or BLOCKED terminal receipts. Measured UTC evidence replaces owner duration estimates; missing start evidence always produces a null duration with an exclusion reason.

## Storage and local ingestion
Start markers and terminal task evidence are stored under `.aios/runtime/engineering_timing/`; terminal CLI commands automatically upsert tracked Codex metadata and append deduplicated forecast-compatible velocity events. GitHub produces sanitized downloadable artifacts. Those artifacts cannot modify repository contents and require explicit local ingestion.

## GitHub validation receipts
The receipt workflow reads `GITHUB_EVENT_PATH`, uses read-only permissions, rejects recursive processing of its own workflow, and uploads only the normalized receipt. It does not commit, push, comment, open issues, approve, or merge.

## Completion credit
A PR qualifies only when merged evidence, a matching nonempty head SHA, and successful validation evidence agree. Closed-unmerged PRs, unavailable checks, tasks, and commits receive no PR completion credit. First Withdrawable Dollar remains a separate milestone.

## Idempotency and conflicts
Identical starts, terminal receipts, GitHub receipts, and velocity events are deduplicated. Conflicting evidence fails closed and does not overwrite prior evidence.

## Current safety and limitations
Local implementation and focused tests are ready. No credentials, secrets, broker access, network API, repository write from Actions, push, or merge authority was added. GitHub artifacts still require download and bounded local ingestion. PowerShell generator validation is platform-blocked, and that noncanonical generator was left unchanged.
