# AIOS Dashboard Azure And Auth Environment Template

This template lists required setting names and their purpose only. Do not store values, secrets, publish profiles, client secrets, tokens, cookies, account identifiers, or private URLs in this file.

## Azure App Service

| Name | Required | Purpose | Source / Notes |
|---|---:|---|---|
| `PORT` | Azure-provided | Port assigned by Azure App Service. | Azure runtime setting. Do not hardcode. |
| `WEBSITE_SITE_NAME` | Azure-provided | Lets the dashboard detect Azure App Service and bind to `0.0.0.0`. | Set by Azure App Service. |
| `AIOS_DASHBOARD_HOST` | Optional | Explicit server bind host override. | Use only when Azure default detection is not enough. Local default remains `127.0.0.1`. |
| `AIOS_PUBLIC_ORIGIN` | Required for auth | Public HTTPS origin for the dashboard, without a trailing path. | Must match the final protected hostname or approved raw Azure origin. Current value is UNKNOWN. |

## Microsoft Entra External ID

| Name | Required | Purpose | Source / Notes |
|---|---:|---|---|
| `AIOS_ENTRA_AUTHORITY` | Required | Entra authority base URL. | Tenant/policy authority. Current value is UNKNOWN. |
| `AIOS_ENTRA_ISSUER` | Optional | Expected issuer for Entra ID-token validation when it differs from authority. | Defaults to `AIOS_ENTRA_AUTHORITY`. Current value is UNKNOWN. |
| `AIOS_ENTRA_JWKS_URI` | Optional | Entra signing-key JWKS URL override. | Defaults to `${AIOS_ENTRA_AUTHORITY}/discovery/v2.0/keys`. |
| `AIOS_ENTRA_TOKEN_URL` | Optional | Entra token endpoint override for authorization-code exchange. | Defaults to `${AIOS_ENTRA_AUTHORITY}/oauth2/v2.0/token`. |
| `AIOS_ENTRA_AUTHORIZE_URL` | Optional | Full authorization endpoint override. | Defaults to `${AIOS_ENTRA_AUTHORITY}/oauth2/v2.0/authorize`. |
| `AIOS_ENTRA_CLIENT_ID` | Required | Public application client ID. | Public identifier, but keep in server app settings for one configuration path. Current value is UNKNOWN. |
| `AIOS_ENTRA_CLIENT_SECRET` | Optional | Confidential-client secret for token exchange if the selected Entra app requires one. | Secret value must stay in Azure App Service settings only. Do not use when tenant policy blocks client secrets. |
| `AIOS_ENTRA_CLIENT_ASSERTION_KEY_VAULT_KEY_ID` | Optional | Full Azure Key Vault key identifier used for Entra certificate client-assertion signing. | Non-secret identifier. Private key must remain non-exportable in Key Vault. |
| `AIOS_ENTRA_CLIENT_CERT_THUMBPRINT` | Optional | Hex SHA-1 thumbprint of the public certificate uploaded to the Entra app registration. | Non-secret identifier used as the JWT `x5t` header. |
| `AIOS_KEY_VAULT_API_VERSION` | Optional | Azure Key Vault REST API version for signing. | Defaults to `7.4`. |
| `AIOS_ENTRA_REDIRECT_URI` | Required | OAuth callback URL. | Defaults to `${AIOS_PUBLIC_ORIGIN}/auth/callback`; must also be registered in Entra. |
| `AIOS_ENTRA_LOGOUT_URL` | Optional | Full logout endpoint override. | Defaults to `${AIOS_ENTRA_AUTHORITY}/oauth2/v2.0/logout`. |
| `AIOS_ENTRA_POST_LOGOUT_REDIRECT_URI` | Required | Return URL after logout. | Defaults to `${AIOS_PUBLIC_ORIGIN}/login`; must be allowed by Entra if required. |
| `AIOS_ENTRA_ALLOWED_EMAILS` | Recommended | Comma-separated owner/user email allow-list enforced after token verification. | Current value is UNKNOWN. |
| `AIOS_ENTRA_ALLOWED_TENANT_IDS` | Recommended | Comma-separated Entra tenant ID allow-list enforced after token verification. | Current value is UNKNOWN. |

## Cloudflare Access

| Name | Required | Purpose | Source / Notes |
|---|---:|---|---|
| `AIOS_CLOUDFLARE_TEAM_DOMAIN` | Required | Cloudflare Access team domain used to fetch JWT signing keys. | Example shape: `https://<team>.cloudflareaccess.com`; current value is UNKNOWN. |
| `AIOS_CLOUDFLARE_ACCESS_AUD` | Required | Expected Cloudflare Access audience for JWT assertion verification. | Current value is UNKNOWN. |

## Cloudflare Turnstile

| Name | Required | Purpose | Source / Notes |
|---|---:|---|---|
| `AIOS_TURNSTILE_SITE_KEY` | Required | Public Turnstile site key sent to the browser after identity verification. | Value must come from Cloudflare. Current value is UNKNOWN. |
| `AIOS_TURNSTILE_SECRET_KEY` | Required | Server-only Turnstile verification secret. | Secret value must stay in Azure App Service settings only. Current value is UNKNOWN. |
| `AIOS_TURNSTILE_ALLOWED_HOSTNAMES` | Recommended | Comma-separated hostnames accepted in Turnstile Siteverify responses. | Current value is UNKNOWN. |

## Server Session

| Name | Required | Purpose | Source / Notes |
|---|---:|---|---|
| `AIOS_AUTH_SESSION_SECRET` | Required | HMAC signing secret for auth state, pending identity, and session cookies. | Secret value must be generated outside the repo and stored only in Azure App Service settings. |

## Optional Local Runtime Data

| Name | Required | Purpose | Source / Notes |
|---|---:|---|---|
| `AIOS_AUTONOMY_BRIDGE_STATE_PATH` | Optional | Repository-relative override for the local autonomy bridge state file. | Used for local read-only dashboard support data. Not a production database connection. |

## GitHub Deployment Secret

| Name | Required | Purpose | Source / Notes |
|---|---:|---|---|
| `AZUREAPPSERVICE_PUBLISHPROFILE_ALGOTRADEZ_AIOS` | Required for current workflow | GitHub Actions publish profile secret for App Service `algotradez-aios`. | Store only as a GitHub repository secret. Never commit, print, decode, or paste the value. |

## Runtime Code Adapters

The production startup wires these adapters through `server/dashboardAuthAdapters.js`. The server still fails closed when required environment settings are missing or external provider verification rejects a request.

| Adapter | Purpose | Current Status |
|---|---|---|
| `verifyAccessAssertion` | Verify Cloudflare Access JWT assertion. | Wired locally and covered by signed-token tests. |
| `exchangeAuthorizationCode` | Exchange Entra authorization code using PKCE. | Supports client-secret when allowed, or Key Vault-backed certificate client assertions when `AIOS_ENTRA_CLIENT_ASSERTION_KEY_VAULT_KEY_ID` and `AIOS_ENTRA_CLIENT_CERT_THUMBPRINT` are configured. |
| `verifyIdentityToken` | Verify Entra ID token and nonce. | Wired locally and covered by signed-token tests. |
| `verifyTurnstile` | Verify Cloudflare Turnstile token server-side. | Wired locally through Cloudflare Siteverify when `AIOS_TURNSTILE_SECRET_KEY` is configured. |

## Callback And Hostname Evidence To Resolve Before Deployment

| Candidate | Evidence | Status |
|---|---|---|
| `https://algotradez-aios.azurewebsites.net` | GitHub workflow and Azure runbook name App Service `algotradez-aios`. | Candidate raw Azure origin; current deployment status UNKNOWN. |
| `https://algotradez-aios-dnh4djahbne6bzfc.westus2-01.azurewebsites.net` | Cloudflare binding doc names this as a canonical Azure origin. | Candidate raw Azure origin; current deployment status UNKNOWN. |
| `https://aios.algobots.trade` | secure-access docs name this as the intended Cloudflare Access front door. | Candidate protected public hostname; current DNS/Cloudflare status UNKNOWN. |

## External Changes Requiring Owner Approval

- Azure resource creation is not authorized by this template.
- Paid storage, database creation, migrations, broker access, and live trading remain blocked unless separately approved.
- App Service settings, GitHub deployment secret updates, Cloudflare Access settings, Entra app registration settings, Turnstile settings, DNS/custom-domain changes, and deployment require the owner-approved external-change lane.
