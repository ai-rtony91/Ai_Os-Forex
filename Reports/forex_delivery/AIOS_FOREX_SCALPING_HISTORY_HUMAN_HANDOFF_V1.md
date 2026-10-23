# AIOS Forex Scalping History Human Handoff V1

- Status: HUMAN_SCALPING_TIMEFRAME_DATA_ACQUISITION_REQUIRED
- Controlling packet: PKT-EAST-FOREX-PACKET033-FULL-ATTACK-CONTINUATION-R3
- Helper: `scripts/forex_delivery/Acquire-AiOsOandaPracticeScalpingHistory.HUMAN_ONLY.ps1`
- Output root: `.aios/runtime/forex_scalping_history_human_inbox_v1`
- Instruments: `EUR_USD,GBP_USD,USD_JPY`
- Missing granularities: `S5,S10,S15,S30,M1,M2,M4`
- Interval: `2024-01-01T00:00:00Z` inclusive through `2026-08-30T00:00:00Z` exclusive
- Pagination contract: `FROM_PLUS_COUNT`
- Candles per request: `5000`
- Include-first strategy: first request true; later requests use the last accepted candle timestamp with `includeFirst=false`
- Practice host only. GET-only. No orders. No LIVE host. No token persistence.

## Exact Human Plan Command

```powershell
Set-Location 'C:\Dev\Ai.Os'

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

& '.\scripts\forex_delivery\Acquire-AiOsOandaPracticeScalpingHistory.HUMAN_ONLY.ps1' `
  -OutputRoot '.aios/runtime/forex_scalping_history_human_inbox_v1' `
  -Instruments @('EUR_USD','GBP_USD','USD_JPY') `
  -Granularities @('S5','S10','S15','S30','M1','M2','M4') `
  -FromUtc '2024-01-01T00:00:00Z' `
  -ToUtc '2026-08-30T00:00:00Z' `
  -WhatIfOnly
```

## Exact Human Acquisition Command

```powershell
Set-Location 'C:\Dev\Ai.Os'

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

& '.\scripts\forex_delivery\Acquire-AiOsOandaPracticeScalpingHistory.HUMAN_ONLY.ps1' `
  -OutputRoot '.aios/runtime/forex_scalping_history_human_inbox_v1' `
  -Instruments @('EUR_USD','GBP_USD','USD_JPY') `
  -Granularities @('S5','S10','S15','S30','M1','M2','M4') `
  -FromUtc '2024-01-01T00:00:00Z' `
  -ToUtc '2026-08-30T00:00:00Z'
```

The token is entered only into the masked Human-only prompt. Do not paste any token into Codex or a report.

After the physical artifacts exist, resume Packet 033 from `HUMAN_SCALPING_TIMEFRAME_DATA_ACQUISITION_REQUIRED`.
