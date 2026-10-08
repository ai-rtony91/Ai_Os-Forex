# AIOS Forex Bait Factory V1

Packet ID: `PKT-FOREX-BAIT-FACTORY-V1`
Status: BAIT_READY_FOR_REVIEW
Stop reason: TARGET_BAIT_COUNT_FOUND_REPO_SAFE
Pipeline: hypothesis_builder -> warm_cold_scorer -> proof_ledger -> edge_autopilot -> paper_campaign_handoff
Cycles completed: 1/3
Bait ready: 3/3

## Warm/Cold Counts
- HOT: 1
- WARM: 2
- COLD: 2

## Bait Box
- HOT c1-eur-buy: score 96.0, expectancy 200.0, PF 999.0, next send_to_proof_ledger_and_edge_autopilot_review
- WARM c2-usd-buy: score 83.515081, expectancy 20.3, PF 10.02222222, next collect_more_evidence_before_paper_handoff
- WARM c3-eur-sell: score 61.090718, expectancy 9.3125, PF 17.55555556, next collect_more_evidence_before_paper_handoff
- COLD c5-gbp-buy: score 51.5, expectancy 82.33333333, PF 13.35, next reject_or_park_as_false_positive_risk
- COLD c4-jpy-buy: score 23.833333, expectancy -0.4375, PF 0.93457944, next reject_or_park_as_false_positive_risk

## Paper Handoff
- Status: READY_WHEN_BAIT_BOX_EMPTY_OR_OWNER_PRACTICE_CREDS_PRESENT
- Command: `python scripts\forex_delivery\run_forex_p1_supervised_paper_campaign_v1.py --owner-local-runtime --cycles 30`
- Executes now: False

## Safety
- Broker/API calls: false
- Credential/env reads: false
- Demo/live/order authority: false
- Scheduler/daemon/background loop started: false

## Next Safe Action
Use the bait box for proof review; start PAPER only from owner local runtime when more closed trades are needed.
