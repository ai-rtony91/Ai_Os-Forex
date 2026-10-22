CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

## IDENTITY MARKER
PROJECT: AI_OS
REPOSITORY: ai-rtony91/Ai_Os
WORKTREE: C:\\Dev\\Ai.Os
PACKET_ID: AIOS_FOREX_PROMOTION_PIPELINE_AUTOMATOR_V1
MODE: APPLY
ZONE: FOREX_PROMOTION_READINESS
LANE: Forex / promotion pipeline / readiness gates
SUPERVISOR IDENTITY: ChatGPT planning supervisor
WORKER IDENTITY: Codex

## CURRENT STATE
Pipeline ID: AIOS_FOREX_PROMOTION_PIPELINE_V1
Status: BROKER_READINESS_REQUIRED
Selected gate: BROKER_ACCOUNT_READINESS
Next action: PREPARE_BROKER_READINESS_REVIEW

## ALLOWED PATHS
- automation/forex_engine/forex_promotion_pipeline_v1.py
- tests/forex_engine/test_forex_promotion_pipeline_v1.py
- scripts/forex_delivery/Invoke-ForexPromotionPipeline.V1.ps1
- Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_REPORT.md
- Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_STATE.json
- Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_CHECKPOINT.md
- Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_OWNER_APPROVAL_CARD.md
- Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_NEXT_CODEX_PACKET_V1.md
- automation/forex_engine/forex_autonomous_campaign_manager_v1.py
- Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_V1_STATE.json
- Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_V1_CHECKPOINT.md
- Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_NEXT_CODEX_PROMPT_V1.md

## FORBIDDEN PATHS
- .env
- .env.*
- *.key
- *.pem
- *.p12
- *.pfx
- secrets/*
- credentials/*
- services/*
- apps/*
- telemetry/*

## APPROVAL AUTHORITY
- run required validators listed below
- do not edit broker/API/credential/order/live files
- preserve existing campaign manager artifacts

## VALIDATOR CHAIN
python -m py_compile automation/forex_engine/forex_promotion_pipeline_v1.py
python -m pytest tests/forex_engine/test_forex_promotion_pipeline_v1.py -q
pwsh -File scripts/forex_delivery/Invoke-ForexPromotionPipeline.V1.ps1 -DryRun -NoPublish -MaxMinutes 30
python -m py_compile automation/forex_engine/forex_autonomous_campaign_manager_v1.py
python -m pytest tests/forex_engine/test_forex_autonomous_campaign_manager_v1.py -q
git diff --check -- automation/forex_engine/forex_promotion_pipeline_v1.py tests/forex_engine/test_forex_promotion_pipeline_v1.py scripts/forex_delivery/Invoke-ForexPromotionPipeline.V1.ps1 Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_REPORT.md Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_STATE.json Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_CHECKPOINT.md Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_OWNER_APPROVAL_CARD.md Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_NEXT_CODEX_PACKET_V1.md automation/forex_engine/forex_autonomous_campaign_manager_v1.py Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_V1_STATE.json Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_V1_CHECKPOINT.md Reports/forex_delivery/AIOS_FOREX_AUTONOMOUS_CAMPAIGN_MANAGER_NEXT_CODEX_PROMPT_V1.md

## STOP POINT
STOP when PROMOTION_COMPLETE or PROMOTION_BLOCKED.

## CURRENT WORK FILES
STATE_PATH:C:\Dev\Ai.Os\Reports\forex_delivery\AIOS_FOREX_PROMOTION_PIPELINE_V1_STATE.json
CHECKPOINT_PATH:C:\Dev\Ai.Os\Reports\forex_delivery\AIOS_FOREX_PROMOTION_PIPELINE_V1_CHECKPOINT.md
OWNER_APPROVAL_CARD_PATH:C:\Dev\Ai.Os\Reports\forex_delivery\AIOS_FOREX_PROMOTION_PIPELINE_V1_OWNER_APPROVAL_CARD.md
NEXT_CODEX_PACKET_PATH:C:\Dev\Ai.Os\Reports\forex_delivery\AIOS_FOREX_PROMOTION_PIPELINE_NEXT_CODEX_PACKET_V1.md

## NEXT SAFE ACTION
Use the generated report and evidence artifacts to complete current gate requirements.

## FINAL REPORT FORMAT
PROMOTION_PIPELINE_STATUS:
CURRENT_BRANCH:
CURRENT_HEAD:
FILES_CREATED:
FILES_CHANGED:
VALIDATORS_RUN:
VALIDATORS_PASSED:
VALIDATORS_FAILED:
PROMOTION_STATUS:
SELECTED_GATE:
NEXT_ACTION:
MISSING_EVIDENCE:
OWNER_ACTIONS_REQUIRED:
BROKER_GATE:
HUMAN_GATE:
CHECKPOINT_PATH:
OWNER_APPROVAL_CARD_PATH:
NEXT_CODEX_PACKET_PATH:
PR_CREATED:
PR_MERGED:
FINAL_GIT_STATUS:
SAFETY_BOUNDARY:
BROKER_API_ACCESS:
CREDENTIALS_USED:
ORDER_EXECUTION:
LIVE_TRADING:
MONEY_MOVEMENT:
SCHEDULERS_DAEMONS_WEBHOOKS:
NEXT_SAFE_ACTION:
STOP_REASON:
