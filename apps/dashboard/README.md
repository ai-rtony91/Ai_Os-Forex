# AIOS Dashboard

## Canonical Forex Dashboard

The owner-approved current Forex dashboard is:

`apps/dashboard/aios-forex-dashboard.html`

It is a focused, low-clutter operator surface for the 30-trade forward paper campaign and the evidence needed to judge Forex readiness.

## Current Status

The page is a static, read-only UI. Its data contract is not connected, so unavailable evidence is labeled `PENDING` or `NOT CONNECTED`. It separates:

- forward paper evidence from genuine pretend-money trades;
- historical and research evidence from development replay and statistical analysis;
- readiness and safety evidence from governed gates and controls.

Historical results must never be presented as forward PAPER30 progress.

## Safety Boundary

This dashboard has no broker execution, credentials, account identifiers, live-order control, backend activation, network submission, persistence, or hidden automation. `LIVE DISABLED` is a safety status, not a control.

## Legacy Dashboard

`apps/dashboard/AIOS_STATIC_PREVIEW.html` is the noncanonical legacy planetary dashboard. It remains in the repository only while existing build, manifest, companion UI, and validator dependencies still reference it. New Forex dashboard work must target the canonical page above.

## Next Direction

The next dashboard packet should define and validate a read-only data contract for the three evidence classes before wiring any values. Missing evidence must remain visibly pending; it must not be fabricated or inferred.
