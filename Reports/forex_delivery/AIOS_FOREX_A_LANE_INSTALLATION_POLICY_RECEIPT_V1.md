# AIOS Forex A-Lane Installation Policy Receipt V1

Created UTC: 2026-10-09T20:50:10+00:00
Branch: codex/forex-edge-autopilot-20261008
Head: 4fdf30619fa7c29f0dd9adbd710a1b04526ccdd0

Installation claim ready: False

## Blockers
- CurrentUser execution policy is Restricted
- Claim-AiOsFileLock.DRY_RUN.ps1 is not signed by a trusted signer
- Release-AiOsFileLock.DRY_RUN.ps1 is not signed by a trusted signer

## Protected Actions Not Taken
- no execution policy changed
- no script signing performed
- no claim script executed
- no repair installation performed
- no broker API used
- no credentials read
- no orders placed

## Required Owner Resolution
- Choose a legitimate Windows execution-policy route for reviewed signed scripts
- Review and sign the exact claim/release script contents or provide trusted signed equivalents
- Rerun canonical claim and ownership checks after policy/signature resolution
