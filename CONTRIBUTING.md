# Contributing to AI_OS

AI_OS accepts reviewed contributions through pull requests. Repository access is not required.

## External contributor workflow

1. Fork `ai-rtony91/Ai_Os`.
2. Create one focused branch in your fork.
3. Make one bounded change.
4. Run the relevant tests and validators.
5. Open a pull request against `main`.
6. Wait for repository checks and owner review.

External contributors are not granted write, maintain, or admin access. Only the repository owner may merge into `main`.

## Required pull-request content

Every pull request must state:

- the exact problem being solved;
- the exact files changed;
- the tests and validators run;
- the expected behavior change;
- the security and risk boundaries;
- whether AI-assisted code or generated content was used.

Keep one engineering topic per pull request. Do not mix cleanup, architecture changes, security changes, trading changes, and unrelated refactors.

## Prohibited content

Never commit or paste:

- `.env` files;
- passwords, tokens, API keys, private keys, session data, or account identifiers;
- broker credentials or private broker payloads;
- personal data or sensitive logs;
- generated evidence presented as real evidence;
- binaries or archives without an approved repository need.

Potential vulnerabilities must be reported privately under `SECURITY.md`, not in public issues.

## Protected boundaries

External contributions must not directly change repository authority, security policy, GitHub workflow authority, credentials, broker execution, live-order routing, money movement, or production deployment controls.

Changes to these areas may be proposed in an issue, but the repository owner must author or explicitly approve the implementation:

- `AGENTS.md`;
- `RISK_POLICY.md`;
- `SECURITY.md`;
- `.github/CODEOWNERS`;
- `.github/workflows/`;
- `docs/governance/`;
- `docs/security/`;
- secret, credential, broker, webhook, live-order, withdrawal, or deposit paths.

Do not add `pull_request_target` workflows. Do not request repository secrets for fork-based validation.

## Forex and financial safety

A contribution may improve analysis, validation, evidence handling, demo/practice support, risk controls, or reporting. It does not authorize live trading.

No contribution may:

- place or modify an order;
- connect to a broker with private credentials;
- activate live trading;
- move money;
- bypass owner approval, risk controls, validation, or post-trade review;
- represent paper or simulated results as broker-verified results.

`RISK_POLICY.md` remains authoritative for financial action boundaries.

## Review and merge

A pull request is reviewable only when:

- the diff matches the stated scope;
- required checks pass;
- review conversations are resolved;
- no secret or sensitive-data exposure exists;
- the repository owner approves the final diff and merge.

Do not force-push after substantive review unless the reviewer is notified. Approval of an issue, plan, or earlier commit does not approve a changed final diff.
