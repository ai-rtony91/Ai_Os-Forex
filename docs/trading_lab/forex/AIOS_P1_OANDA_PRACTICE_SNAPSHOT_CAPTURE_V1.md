# AIOS P1 OANDA Practice Snapshot Capture V1

This adapter connects the canonical GET-only `OandaReadOnlyClient` pricing method to the canonical P1 supervised paper-session controller. It creates no competing broker client, controller, ledger, or evaluator.

The default `preflight` command is offline. A one-shot capture requires `--owner-local-runtime`, `--environment practice`, `--instrument EUR_USD`, and the approved runtime output. Production/fxTrade mode is rejected. Broker responses are reduced in memory to the schema allowlist; credentials, account identifiers, headers, order identifiers, and raw payloads are never written.

`capture-and-open` additionally requires a current sanitized `PAPER_ELIGIBLE` candidate, owner reviewer identity, and explicit supervision confirmation. It uses the observed ask as the paper entry and calls the existing session controller. Opening creates runtime-only active state and grants zero completed-trade or P1 evidence credit. If no candidate exists, the owner handoff performs capture-only.

Run `python scripts/forex_delivery/run_forex_p1_oanda_practice_snapshot_capture_v1.py print-owner-handoff` to print the exact ASUS PowerShell handoff. No OANDA call, credential load, genuine capture, paper session, or order occurred during the build.
