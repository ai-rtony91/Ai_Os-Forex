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

## Optional GitHub Sign-In

| Name | Required | Purpose | Source / Notes |
|---|---:|---|---|
| `AIOS_GITHUB_CLIENT_ID` | For GitHub login | Public client ID of a dedicated GitHub OAuth App. | Server setting; never a repository or personal access token. |
| `AIOS_GITHUB_CLIENT_SECRET` | For GitHub login | Confidential OAuth client secret. | Keep only in approved server secret storage. Never use a `VITE_` variable. |
| `AIOS_GITHUB_ALLOWED_USER_IDS` | For GitHub login | Comma-separated positive numeric GitHub user IDs permitted to enter AIOS. | Uses stable account IDs, not mutable usernames or email matching. An empty or malformed list disables GitHub login. |

Register the OAuth App callback as exactly `${AIOS_PUBLIC_ORIGIN}/auth/github/callback`, using the approved HTTPS public origin. The Microsoft callback remains `/auth/callback`. Use a dedicated identity-only OAuth App: this flow requests only `read:user` and rejects broader token scopes. It does not request repository access or automatically link accounts by email.

GitHub stays unavailable until all three settings are present. The existing Microsoft and shared security configuration must also remain valid. GitHub uses state, PKCE S256, a server-side code exchange, an authenticated GitHub profile lookup, and the approved user-ID list. It still requires Cloudflare Access and successful Turnstile verification before an AIOS session is created. Provider tokens stay server-side and are not placed in session cookies.

Signing out of an AIOS GitHub session clears the AIOS cookies and returns to `/login`; it does not sign the user out of github.com or Cloudflare. New GitHub sign-ins request account selection. MFA must be enforced through the identity provider or Cloudflare policy; the button does not configure MFA.

GitHub setup, policy changes, and production deployment remain separate external changes requiring owner approval. The existing Cloudflare verifier failure is not repaired by this feature.

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
| `exchangeGitHubAuthorizationCode` | Exchange a GitHub code with PKCE and check the verified account ID against the allow-list. | Optional; fixed GitHub endpoints, minimal scopes, no browser token storage. |
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
