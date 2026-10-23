param([string]$PacketText = "", [string]$PacketPath = "", [switch]$OutputJson)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "AiOsCodexPacketContract.ps1")
$contract = Get-AiOsCodexPacketContract

if ([string]::IsNullOrWhiteSpace($PacketText) -and -not [string]::IsNullOrWhiteSpace($PacketPath)) {
    if (-not (Test-Path -LiteralPath $PacketPath -PathType Leaf)) { throw "PacketPath not found: $PacketPath" }
    $packetBytes = [System.IO.File]::ReadAllBytes($PacketPath)
    try {
        $PacketText = ([System.Text.UTF8Encoding]::new($false, $true)).GetString($packetBytes)
    }
    catch [System.Text.DecoderFallbackException] {
        throw "PACKET_TEXT_INVALID_UTF8: PacketPath must contain valid UTF-8."
    }
    if ($PacketText.Length -gt 0 -and $PacketText[0] -eq [char]0xFEFF) {
        $PacketText = $PacketText.Substring(1)
    }
}
$normalized = ($PacketText -replace "`r`n", "`n") -replace "`r", "`n"
$lines = @($normalized -split "`n")

function Get-Section([string]$Label) {
    $heading = "${Label}:"
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq $heading) {
            $values = @()
            for ($j = $i + 1; $j -lt $lines.Count; $j++) {
                $line = $lines[$j]
                if ($line.Trim() -cmatch '^[A-Z][A-Z _-]+:$' -or $line -match '^(execution_allowed|can_continue_without_anthony|writes_files)=') { break }
                if (-not [string]::IsNullOrWhiteSpace($line)) { $values += $line.Trim() }
            }
            return @($values)
        }
    }
    return @()
}

$missing = @()
$defects = @()
if ($normalized.IndexOf([char]0) -ge 0) { $defects += "nul_character" }
$bootstrapPosition = -1
foreach ($instruction in @($contract.required_bootstrap_lines)) {
    $position = [array]::IndexOf($lines, $instruction)
    if ($position -le $bootstrapPosition) { $defects += "missing_bootstrap_instruction" }
    $bootstrapPosition = $position
}
foreach ($flag in @($contract.safety_flags)) {
    $flagPattern = '(?i)(?<![A-Za-z0-9_])' + [regex]::Escape($flag) + '[ \t]*='
    if ([regex]::Matches($normalized, $flagPattern).Count -ne 1 -or $lines -cnotcontains "$flag=false") {
        $defects += "invalid_safety_flag:$flag"
    }
}
if ($lines.Count -eq 0 -or $lines[0] -cne $contract.exact_first_line) { $missing += $contract.exact_first_line; $defects += "wrong_first_line" }
foreach ($marker in @($contract.required_markers)) {
    if ($lines -cnotcontains $marker) { $missing += $marker }
}
foreach ($field in @($contract.required_scalar_fields) + @($contract.protected_action_fields) + @($contract.list_valued_fields)) {
    # A second heading is conflicting even when injected inside a scalar value.
    $headerPattern = '(?i)(?<![A-Za-z0-9_])' + [regex]::Escape($field) + '[ \t]*:'
    if ([regex]::Matches($normalized, $headerPattern).Count -gt 1) { $defects += "duplicate_field:$field" }
}
foreach ($field in @($contract.required_scalar_fields) + @($contract.protected_action_fields)) {
    $value = @(Get-Section $field)
    if ($value.Count -eq 0 -or [string]::IsNullOrWhiteSpace(($value -join ""))) { $missing += $field }
    elseif ($value.Count -ne 1) { $defects += "multiline_field:$field" }
}
foreach ($field in @($contract.protected_action_fields)) {
    $value = @(Get-Section $field)
    if ($value.Count -gt 0 -and $value[0] -notmatch $contract.protected_authority_pattern) {
        $defects += "malformed_protected_authority:$field"
    }
}
foreach ($field in @($contract.list_valued_fields)) {
    $value = @(Get-Section $field)
    if ($value.Count -eq 0 -or @($value | Where-Object { $_ -match '^\s*-\s*\S' }).Count -ne $value.Count) {
        $missing += $field; $defects += "empty_or_malformed_list:$field"
    }
}
foreach ($pattern in @($contract.unresolved_placeholder_patterns)) {
    if ($normalized -match $pattern) { $defects += "unresolved_placeholder:$pattern" }
}
$mode = @(Get-Section "MODE")
if ($mode.Count -ne 1 -or $mode[0] -notin @("DRY_RUN", "APPLY")) { $defects += "invalid_mode" }
$preflight = @(Get-Section "PREFLIGHT") -replace '^\s*-\s*', ''
foreach ($command in @($contract.required_repository_state_commands)) {
    if ($preflight -cnotcontains $command) { $defects += "missing_preflight_command:$command" }
}

$warnings = @()
foreach ($term in @($contract.terminology.drift_terms)) {
    if ($normalized.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        $warnings += "Terminology drift: prefer software-engineering terminology over '$term' in new explanatory prose."
    }
}
$result = [ordered]@{
    schema="AIOS_CODEX_PACKET_VALIDATOR.v2"
    packet_valid=($missing.Count -eq 0 -and $defects.Count -eq 0)
    missing_required_fields=@($missing | Select-Object -Unique)
    validation_defects=@($defects | Select-Object -Unique)
    terminology_warnings=@($warnings)
    writes_files=$false; execution_allowed=$false; can_continue_without_anthony=$false
}
$result | ConvertTo-Json -Depth 20
