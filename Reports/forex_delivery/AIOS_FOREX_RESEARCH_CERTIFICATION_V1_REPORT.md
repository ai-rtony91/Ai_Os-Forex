# AIOS Forex Research Certification V1

Status: `PASS_AFTER_PYTEST`
Reference executor: `6dd60fb853a088636f2367a0f58e2a0c305f68ac72f83bd20e9ae6114f2aeba5`

## Findings
- Signals use completed bar T and enter at T+1 executable open.
- Stops and targets use the executable bid/ask side; ambiguous bars stop first.
- Initial R is frozen at entry and drawdown uses running peak equity.
- Legacy cost helpers can double-count spread/slippage when adjusted fills are also passed to apply_cost_to_pnl.
- Packet 009/010 adapters used direct next-open bid/ask fills without the legacy cost helper; their strongly negative conclusions remain confirmed.

No broker write, Practice order, LIVE action, or money movement occurred.
