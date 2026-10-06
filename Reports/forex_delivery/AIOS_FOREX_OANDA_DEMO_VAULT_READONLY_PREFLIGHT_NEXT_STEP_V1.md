# AIOS Forex OANDA Demo Vault Read-Only Preflight Next Step V1

## Next Packet

`AIOS-FOREX-OANDA-DEMO-VAULT-READONLY-PREFLIGHT-V1`

## Purpose

The next lane proves that owner-run saved DEMO credentials can be loaded from secure Windows vault storage and used only for a read-only OANDA DEMO preflight.

## Required Inputs

- owner-run Windows vault save/load proof;
- OANDA DEMO only;
- token-visible demo account `[REDACTED_DEMO_ACCOUNT_ID]`;
- no live credentials;
- no `.env` file;
- no repo credential material.

## Required Broker Boundary

- GET-only read-only preflight.
- No `/orders`.
- No POST, PUT, PATCH, or DELETE.
- No demo order placement.
- No live order placement.
- No broker mutation.
- No scheduler, daemon, webhook, or background execution.

## Required Fail-Closed Conditions

The next packet must fail closed if:

- secure vault load is unavailable;
- account loaded from vault does not match the token-visible DEMO account;
- a live account is supplied;
- any credential value would be printed, logged, or written to repo;
- any order route is requested.

## Required Output

The output must be sanitized proof only:

- credential values redacted;
- account proof reduced to the known DEMO account reference;
- broker response summarized without secrets;
- no raw authorization material.

