# AIOS Dashboard

## Obsidian Liquid Terminal

The React application is the local integrated AIOS web experience. Run `npm run build` and then `npm start` for the loopback integrated preview. During Vite development, run `npm run start:api` in one terminal and `npm run dev` in another. It provides a visual identity gate, eight History API routes, deterministic demonstration data, versioned sanitized read models, Server-Sent Events, read-only broker status, local-only private gallery mapping, and draft-only strategy validation.

Demonstration values are always labeled `DEMONSTRATION DATA — NOT BROKER DATA`. Authentication providers, Cloudflare, deployment, broker connectivity, credentials, trade execution, and shell execution are not configured or authorized.

## Legacy Canonical Forex Dashboard

The preserved focused Forex campaign dashboard is:

`apps/dashboard/aios-forex-dashboard.html`

It is a focused, low-clutter operator surface for the 30-trade forward paper campaign and the evidence needed to judge Forex readiness.

## Legacy Surface Status

The page is a static, read-only UI. Its data contract is not connected, so unavailable evidence is labeled `PENDING` or `NOT CONNECTED`. It separates:

- forward paper evidence from genuine pretend-money trades;
- historical and research evidence from development replay and statistical analysis;
- readiness and safety evidence from governed gates and controls.

Historical results must never be presented as forward PAPER30 progress.

## Safety Boundary

This dashboard has no broker execution, credentials, account identifiers, live-order control, backend activation, network submission, persistence, or hidden automation. `LIVE DISABLED` is a safety status, not a control.

## Legacy Dashboard

`apps/dashboard/AIOS_STATIC_PREVIEW.html` is the noncanonical legacy planetary dashboard. It remains in the repository only while existing build, manifest, companion UI, and validator dependencies still reference it. New Forex dashboard work must target the canonical page above.

## Validation

Run `npm run lint`, `npm run test`, and `npm run build`. No deployment follows automatically.
