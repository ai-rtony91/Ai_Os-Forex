param(
    [string]$HandoffPath = "Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_DROP_HANDOFF.md"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$inbox = ".aios/runtime/forex_institutional_data_breakthrough_v1/manual_drop_inbox"

Write-Output "AIOS HUMAN-ONLY OFFICIAL DATA DROP PREPARATION"
Write-Output "Read handoff: $HandoffPath"
Write-Output "Place only public official files in: $inbox"
Write-Output "Do not include credentials, account IDs, cookies, screenshots, or bank/card data."
Write-Output "Do not edit downloaded file contents."
Write-Output "This script performs no network request and collects no secret."
