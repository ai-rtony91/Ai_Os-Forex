# AIOS P1 Supervised Paper Session V1

This local-only controller opens one long paper session from a genuine sanitized read-only market snapshot and a `PAPER_ELIGIBLE` candidate. Active state remains under `.aios/runtime/forex_p1_supervised_paper_sessions/` and is never evidence.

Closing requires a later genuine snapshot for the same instrument. Entry uses ask; exit uses bid; net paper P/L is `(exit bid - entry ask) × units - fees`. Only a valid close is sent through the canonical supervised capture/replay workflow, evidence pipeline, and P1 evaluator. Duplicate trade IDs remain deduplicated by that pipeline.

Fixtures, mock or synthetic snapshots, aborts, and opens receive zero P1 credit. The controller performs no network, broker, credential, account, order, money, margin, scheduler, daemon, webhook, or continuous-execution action. It does not authorize demo or live execution.

Use the runner once per command: `open`, `close`, `status`, `abort`, `validate-snapshot`, or `report`.
