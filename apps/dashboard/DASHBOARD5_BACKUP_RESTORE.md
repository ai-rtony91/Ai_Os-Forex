# Dashboard #5 Backup And Restore Handoff

This file records the safe recovery scope for the Dashboard #5 integration branch. It contains no secret values.

## Included In Git

- Dashboard #5 React source, styles, theme tokens, icons, and assets under `apps/dashboard/src/`.
- Dashboard server code under `apps/dashboard/server/` and `apps/dashboard/server.js`.
- Mock/demo read-model JSON files under `apps/dashboard/mock-data/`.
- Tests under `apps/dashboard/tests/`.
- Safe environment variable names and descriptions in `AZURE_AUTH_ENVIRONMENT.template.md`.
- Package manifest and lockfile needed to rebuild the dashboard.

## Excluded From Git

- `node_modules/`.
- `dist/` build output.
- Browser screenshots and local test artifacts.
- Real Azure publish profiles.
- Cloudflare, Entra, Turnstile, GitHub, broker, or database secrets.
- Local runtime files under `.aios/` or telemetry directories unless separately reviewed.
- Forex task dirty work from other worktrees or the main checkout.

## Restore From Backup Branch

1. Check out the backup branch in a clean worktree.
2. Run `npm ci` from `apps/dashboard`.
3. Run `npm run test` from `apps/dashboard`.
4. Run `npm run build` from `apps/dashboard`.
5. Configure App Service settings from `AZURE_AUTH_ENVIRONMENT.template.md` using secret storage only.
6. Deploy only after Azure, Cloudflare Access, Entra, and Turnstile settings have been verified.

## Production Rollback

- Restore the previous App Service settings captured before deployment.
- Redeploy the previous known-good App Service package or deployment slot artifact.
- Keep Cloudflare Access enabled while rolling back.
- Do not enable broker access or live trading as part of dashboard rollback.
