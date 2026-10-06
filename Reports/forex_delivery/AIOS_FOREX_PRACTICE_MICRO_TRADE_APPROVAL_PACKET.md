# AIOS Forex Practice Micro-Trade Approval Packet

## Status

- Engineering readiness: `YES`
- Certification: `BLOCKED`
- Repository work remaining: `NO`
- Owner approval required: `YES`

## Packet fields

- Broker path: `OANDA Practice`
- Instrument: `GBP_USD`
- Side: `OWNER_VALUE_REQUIRED`
- Units / notional: `OWNER_VALUE_REQUIRED`
- Maximum loss: `OWNER_VALUE_REQUIRED`
- Daily loss cap: `OWNER_VALUE_REQUIRED`
- Stop loss: `OWNER_VALUE_REQUIRED`
- Take profit: `OWNER_VALUE_REQUIRED`
- Order type: `OWNER_VALUE_REQUIRED`
- Approval start: `OWNER_VALUE_REQUIRED`
- Approval expiry: `OWNER_VALUE_REQUIRED`
- Evidence bundle: `PAPER_CERTIFICATION_REQUIRED`
- Deployment commit: `OWNER_VALUE_REQUIRED`
- Source fingerprint: `3f5c5c0241d68e3f796c5706e9c2e433ccc14d3f58adf01d621df1ca0bbf2800`
- Kill switch: `ARMED_FOR_FAIL_CLOSED_ONLY`
- Arming step: `OWNER_APPROVAL_REQUIRED`
- Stop point: `ABORT_IF_OWNER_VALUES_CHANGE`
- Rollback procedure: `DISARM_AND_REVERT_TO_PAPER_ONLY`
- Post-trade review: `REQUIRED_AFTER_ANY_EXECUTION`

## Notes

- No practice order is submitted by this packet.
- The packet is structurally complete only for handoff and review.
- The missing decision is the owner's approval of the demo order parameters and execution window.

