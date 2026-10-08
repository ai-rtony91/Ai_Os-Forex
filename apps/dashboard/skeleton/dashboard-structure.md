# Dashboard Structure Reference

## Working File

`apps/dashboard/aios-forex-dashboard.html` is the canonical current Forex dashboard selected by the Human Owner.

`apps/dashboard/AIOS_STATIC_PREVIEW.html` is a noncanonical legacy dashboard. It is retained only because current build, manifest, companion UI, and validator dependencies still reference it.

## Canonical Structure

The canonical dashboard uses three explicit evidence zones:

1. Forward Paper — genuine pretend-money PAPER30 progress and realized forward metrics only.
2. Historical / Research — development replay, uncertainty, probability, and edge-classification evidence.
3. Readiness / Safety — approval gates, risk status, reconciliation, kill-switch status, and the live-execution boundary.

The evidence classes must remain visually and semantically separate. Historical trades must never be shown as forward PAPER30 credit.

## Interface Direction

- Dark, compact, card-based Forex layout.
- Clear metric hierarchy and low visual noise.
- Responsive behavior for desktop and mobile.
- Read-only placeholders of `PENDING` or `NOT CONNECTED` until a governed data contract supplies evidence.
- No planetary command wall, large control surface, duplicate panels, or fabricated live data.

## Boundary

This structure does not approve backend calls, API calls, credentials, persistence, service-worker registration, broker automation, order placement, live execution, or production activation.

Future data wiring requires a separate approved packet, explicit source contracts, evidence-class validation, and repository status review.
