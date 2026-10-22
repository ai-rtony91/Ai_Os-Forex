# AIOS Post-Mortem Engine V1

The engine is a deterministic, evidence-only analyzer for repository, worker, packet, validation, publication, and durability failures. It implements strict event validation, bounded classifications, hypotheses, evidence-bound lessons, independent-incident pattern memory, anti-overfitting promotion gates, and a fail-closed lifecycle.

It does **not** create governance authority or mutate Git, queues, workers, approvals, strategies, risk settings, brokers, trading, deployment, or production. A normal pattern requires two independent incidents. Safety-critical observations remain ineligible for automatic promotion and require Human Owner review. Reports are operational evidence only.

## Entry points

Run the module with `analyze`, `classify`, `learn`, `plan`, `verify`, or `close` and a JSON input file. Commands are read-only unless `--output` is supplied. Output is restricted to `Reports/orchestration/postmortem/` and is canonical JSON.

Durability is one of `REMOTE_VERIFIED`, `USER_VISIBLE_CAPSULE_VERIFIED`, or `AT_RISK`. A local-only commit is always `AT_RISK`; it is never described as remotely recoverable.

Both event and pattern objects are validated as closed records. Pattern validation also checks that the declared independent-incident count equals the unique incident IDs and rejects promotion based on a single incident.

## Trade analytics

The evidence-only trade analyzer validates typed provenance, admits only proven closed trades, preserves unknown optional facts as null, and calculates deterministic PnL statistics. Pattern hooks require their named metrics and never infer cause from PnL alone. Experiment recommendations cite supporting trades and evidence, remain blocked below a configurable threshold, and have no runtime authority. Progress keeps software, evidence, analysis, and release readiness separate; missing campaign evidence is `NOT_PROVEN`.

Qualification distinguishes open, nonqualifying, unproven, malformed, duplicate, missing-evidence, and qualifying records. Pattern metrics must be finite numeric values and carry their required signal or market-condition evidence. Campaign progress requires both typed campaign-runtime and validation evidence; caller flags cannot promote readiness.

The event schema exposes a closed `analysisResult` definition tying normalized trades, qualification results, statistics, ranked patterns, recommendations, and progress together. Engine output is validated against the same closed contract before it is returned.
