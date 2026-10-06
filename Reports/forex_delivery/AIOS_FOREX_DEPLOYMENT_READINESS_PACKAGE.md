# AIOS Forex Deployment Readiness Package

## Status

- Deployment package complete: `YES`
- Deployment activated: `NO`
- Live execution authorized: `NO`

## Requirements

- Source commit requirement: publish the exact validated runtime source before any deployment
- Source fingerprint: `3f5c5c0241d68e3f796c5706e9c2e433ccc14d3f58adf01d621df1ca0bbf2800`
- Configuration requirements: local runtime paths only, fail-closed gates preserved, no hidden broker writes
- Runtime credential requirements: present only at runtime, never persisted in source, reports, or generated docs
- Secret exclusion: no API token, account ID, or live credential values in repository artifacts
- Rollback target: the previous validated deployed artifact once one exists
- Rollback plan: revert to the prior validated artifact and disarm the current deployment
- Startup validation: verify branch, source fingerprint, runtime lock, and safety gates before launch
- Shutdown procedure: release lock, persist final state, and write a clean stop receipt
- Health check: confirm the canonical runner, fresh heartbeat, and unchanged lock ownership
- Kill switch check: verify that stop files and risk-halt controls remain fail-closed
- Post-deployment validation: confirm runtime state, lock freshness, and evidence receipts
- Audit requirements: preserve an immutable evidence trail for lock acquisition, release, and any recovery

## Notes

- This package does not claim a deployment happened.
- It only records the preconditions and rollback shape needed for a later protected deployment.
- The missing decision is the owner-approved deployment activation.

