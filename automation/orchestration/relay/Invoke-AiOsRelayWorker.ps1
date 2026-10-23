<#
.SYNOPSIS
Executes AI_OS relay inbox task packets.

.DESCRIPTION
P10 provider-neutral worker bridge for the local AI_OS relay. The existing
relay runner owns goal and handoff intake. This worker owns inbox execution
only. Claude is the current tested default provider, not the permanent
architecture.

TIER_2 packets are hard-stopped into relay/approvals before any CLI dispatch.
#>

[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$Watch,
    [ValidateRange(1, 3600)]
    [int]$IntervalSeconds = 5,
    [ValidateRange(0, 100000)]
    [int]$MaxPackets = 0,
    [switch]$Report,
    [string]$RepoRoot="", [string]$RelayRoot="", [string]$RequestPath="",
    [string]$ExpectedPacketSha256="", [string]$PythonExecutable=""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SourceRepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$BoundProfile = ($PSBoundParameters.ContainsKey("RequestPath") -or $PSBoundParameters.ContainsKey("ExpectedPacketSha256") -or $PSBoundParameters.ContainsKey("RepoRoot") -or $PSBoundParameters.ContainsKey("RelayRoot") -or $PSBoundParameters.ContainsKey("PythonExecutable"))
if (-not $BoundProfile) { $RepoRoot=$SourceRepoRoot; $RelayRoot=Join-Path $RepoRoot "relay" }
$RunnerPath = Join-Path $PSScriptRoot "Invoke-AiOsRelayRunner.ps1"
$StopFlagPath = Join-Path $RelayRoot "STOP.flag"
$CanWrite = $true
$DefaultEstimateUsd = [decimal]0.02

$RelayPaths = [ordered]@{
    approvals = Join-Path $RelayRoot "approvals"
    done = Join-Path $RelayRoot "done"
    error = Join-Path $RelayRoot "error"
    inbox = Join-Path $RelayRoot "inbox"
    logs = Join-Path $RelayRoot "logs"
    outbox = Join-Path $RelayRoot "outbox"
    reports = Join-Path $RelayRoot "reports"
    running = Join-Path $RelayRoot "running"
}

$RunnerLogPath = Join-Path $RelayPaths.logs "runner.log"

function Import-AiOsRelayRunnerHelpers {
    if (-not (Test-Path -LiteralPath $RunnerPath -PathType Leaf)) {
        throw "Relay runner helper source missing: $RunnerPath"
    }

    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($RunnerPath, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {
        throw "Relay runner helper source failed to parse: $($errors[0].Message)"
    }

    $required = @(
        "Get-AiOsUtcTimestamp",
        "Write-AiOsRelayLog",
        "Test-AiOsProtectedRelayText",
        "Get-AiOsRelayTier"
    )

    foreach ($name in $required) {
        $node = $ast.Find({
            param($candidate)
            $candidate -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $candidate.Name -eq $name
        }, $true)

        if (-not $node) {
            throw "Required relay helper missing from runner: $name"
        }

        $bodyText = $node.Body.Extent.Text.Trim()
        if ($bodyText.StartsWith("{") -and $bodyText.EndsWith("}")) {
            $bodyText = $bodyText.Substring(1, $bodyText.Length - 2)
        }

        Set-Item -Path "function:\global:$name" -Value ([scriptblock]::Create($bodyText)) -Force
    }
}

function Initialize-AiOsRelayWorkerFolders {
    foreach ($path in $RelayPaths.Values) {
        if (-not (Test-Path -LiteralPath $path -PathType Container)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }
}

function Test-AiOsStableFile {
    param([Parameter(Mandatory = $true)][System.IO.FileInfo]$File)

    $first = (Get-Item -LiteralPath $File.FullName).Length
    Start-Sleep -Seconds 1
    $second = (Get-Item -LiteralPath $File.FullName).Length
    return $first -eq $second
}

function Get-AiOsTaskIdFromFile {
    param([Parameter(Mandatory = $true)][System.IO.FileInfo]$File)

    return ([System.IO.Path]::GetFileNameWithoutExtension($File.Name) -replace "\.task$", "")
}

function Get-AiOsStringArray {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) {
        return @()
    }

    if ($Value -is [array]) {
        return @($Value | ForEach-Object { [string]$_ })
    }

    return @([string]$Value)
}

function Move-AiOsRelayPacket {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$TargetFolder
    )

    $targetPath = Join-Path $TargetFolder (Split-Path -Leaf $SourcePath)
    Move-Item -LiteralPath $SourcePath -Destination $targetPath -Force
    return $targetPath
}

function Write-AiOsWorkerReport {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Worker,
        [Parameter(Mandatory = $true)][string]$Provider,
        [Parameter(Mandatory = $true)][string]$ProviderCommand,
        [Parameter(Mandatory = $true)][string]$Tier,
        [Parameter(Mandatory = $true)][datetime]$StartedAt,
        [Parameter(Mandatory = $true)][datetime]$EndedAt,
        [Parameter(Mandatory = $true)][object]$ExitCode,
        [Parameter(Mandatory = $true)][string[]]$AllowedPaths,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string[]]$Body
    )

    $reportPath = Join-Path $RelayPaths.outbox ("{0}.report.txt" -f $Id)
    @(
        "id: $Id"
        "worker: $Worker"
        "provider: $Provider"
        "provider_command: $ProviderCommand"
        "tier: $Tier"
        "started_at: $($StartedAt.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))"
        "ended_at: $($EndedAt.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))"
        "duration_seconds: $([int]($EndedAt - $StartedAt).TotalSeconds)"
        "exit_code: $ExitCode"
        "allowed_paths: $($AllowedPaths -join ', ')"
        ""
        "----- output -----"
        $Body
    ) | Set-Content -LiteralPath $reportPath -Encoding UTF8

    return $reportPath
}

function Write-AiOsPacketError {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Reason,
        [Parameter(Mandatory = $true)][string]$Detail
    )

    $errorPath = Join-Path $RelayPaths.error ("{0}.error.txt" -f $Id)
    @(
        "id: $Id"
        "reason: $Reason"
        "detail: $Detail"
    ) | Set-Content -LiteralPath $errorPath -Encoding UTF8
}

function Add-AiOsDeferredUntil {
    param([Parameter(Mandatory = $true)][string]$PacketPath, [Parameter(Mandatory = $true)][string]$DeferredUntilUtc)
    $packet = Get-Content -Raw -LiteralPath $PacketPath | ConvertFrom-Json
    if ($packet.PSObject.Properties["deferred_until"]) { $packet.deferred_until = $DeferredUntilUtc } else { $packet | Add-Member -NotePropertyName "deferred_until" -NotePropertyValue $DeferredUntilUtc }
    $packet | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $PacketPath -Encoding UTF8
}

function Read-AiOsTaskPacket {
    param([Parameter(Mandatory = $true)][System.IO.FileInfo]$File)

    $id = Get-AiOsTaskIdFromFile -File $File
    try {
        $packet = Get-Content -LiteralPath $File.FullName -Raw | ConvertFrom-Json
    }
    catch {
        return [pscustomobject]@{
            ok = $false
            id = $id
            reason = "PACKET_INCOMPLETE"
            detail = "JSON parse failed: $($_.Exception.Message)"
        }
    }

    $missing = @()
    foreach ($field in @("id", "worker", "tier", "mission", "allowed_paths")) {
        if (-not $packet.PSObject.Properties[$field] -or [string]::IsNullOrWhiteSpace([string]$packet.$field)) {
            $missing += $field
        }
    }

    if ($missing.Count -gt 0) {
        return [pscustomobject]@{
            ok = $false
            id = if ($packet.PSObject.Properties["id"]) { [string]$packet.id } else { $id }
            reason = "PACKET_INCOMPLETE"
            detail = "Missing required field(s): $($missing -join ', ')"
        }
    }

    $worker = ([string]$packet.worker).ToLowerInvariant()
    $provider = if ($packet.PSObject.Properties["provider"] -and -not [string]::IsNullOrWhiteSpace([string]$packet.provider)) {
        ([string]$packet.provider).ToLowerInvariant()
    } else {
        $worker
    }

    if ($worker -notin @("claude", "codex", "openai", "custom", "planner", "builder")) {
        return [pscustomobject]@{
            ok = $false
            id = [string]$packet.id
            reason = "PACKET_INCOMPLETE"
            detail = "Invalid worker '$worker'. Expected a known relay worker label."
        }
    }

    $providerSpec = Resolve-AiOsProviderSpec -Packet $packet -Provider $provider -Worker $worker
    if (-not $providerSpec.ok) {
        return [pscustomobject]@{
            ok = $false
            id = [string]$packet.id
            reason = "PACKET_INCOMPLETE"
            detail = $providerSpec.detail
        }
    }

    $promptText = ""
    if ($packet.PSObject.Properties["prompt_path"] -or $packet.PSObject.Properties["prompt_sha256"]) {
        foreach ($field in @("prompt_path", "prompt_sha256", "prompt_text", "approval_required", "protected_action_flags")) {
            if (-not $packet.PSObject.Properties[$field]) {
                return [pscustomobject]@{ ok = $false; id = [string]$packet.id; reason = "PACKET_INCOMPLETE"; detail = "Prompt-backed task missing field: $field" }
            }
        }
        $promptPath = [string]$packet.prompt_path
        if (-not [System.IO.Path]::IsPathRooted($promptPath) -or -not (Test-Path -LiteralPath $promptPath -PathType Leaf)) {
            return [pscustomobject]@{ ok = $false; id = [string]$packet.id; reason = "PROMPT_VALIDATION_FAILED"; detail = "Prompt path must be an existing absolute file." }
        }
        $actualDigest = (Get-FileHash -LiteralPath $promptPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualDigest -ne ([string]$packet.prompt_sha256).ToLowerInvariant()) {
            return [pscustomobject]@{ ok = $false; id = [string]$packet.id; reason = "PROMPT_SHA256_MISMATCH"; detail = "Prompt digest changed before dispatch." }
        }
        $promptText = Get-Content -Raw -LiteralPath $promptPath
        if ($promptText -ne [string]$packet.prompt_text) {
            return [pscustomobject]@{ ok = $false; id = [string]$packet.id; reason = "PROMPT_CONTENT_MISMATCH"; detail = "Stored prompt content differs from source." }
        }
        if ([bool]$packet.approval_required) {
            return [pscustomobject]@{ ok = $false; id = [string]$packet.id; reason = "APPROVAL_REQUIRED"; detail = "Protected prompt cannot be dispatched from inbox." }
        }
        $promptAllowed = @($promptText -split "\r?\n" | Select-String -Pattern '^\s*-\s+(.+)$' | ForEach-Object { $_.Matches[0].Groups[1].Value.Trim().Replace('\','/') })
        foreach ($allowed in @($packet.allowed_paths)) {
            if ([string]$allowed -notin $promptAllowed) {
                return [pscustomobject]@{ ok = $false; id = [string]$packet.id; reason = "ALLOWED_PATH_MISMATCH"; detail = "Task allowed paths do not match the validated prompt." }
            }
        }
    }

    return [pscustomobject]@{
        ok = $true
        packet = $packet
        id = [string]$packet.id
        worker = $worker
        provider = $providerSpec.provider
        provider_command = $providerSpec.command
        provider_args = $providerSpec.args
        tier = [string]$packet.tier
        mission = [string]$packet.mission
        allowed_paths = @($packet.allowed_paths | ForEach-Object { [string]$_ })
        prompt_text = $promptText
    }
}

function Resolve-AiOsProviderSpec {
    param(
        [Parameter(Mandatory = $true)][object]$Packet,
        [Parameter(Mandatory = $true)][string]$Provider,
        [Parameter(Mandatory = $true)][string]$Worker
    )

    $defaults = @{
        claude = @{
            command = "claude"
            args = @("--permission-mode", "plan", "--output-format", "text")
        }
        codex = @{
            command = "codex"
            args = @("exec", "--sandbox", "workspace-write", "-")
        }
        openai = @{
            command = ""
            args = @()
        }
        custom = @{
            command = ""
            args = @()
        }
    }

    if (-not $defaults.ContainsKey($Provider)) {
        return [pscustomobject]@{
            ok = $false
            detail = "Unknown provider '$Provider'. Supported providers: claude, codex, openai, custom."
        }
    }

    $providerCommand = if ($Packet.PSObject.Properties["provider_command"]) { [string]$Packet.provider_command } else { [string]$defaults[$Provider].command }
    $providerArgs = if ($Packet.PSObject.Properties["provider_args"]) { Get-AiOsStringArray -Value $Packet.provider_args } else { Get-AiOsStringArray -Value $defaults[$Provider].args }

    if ([string]::IsNullOrWhiteSpace($providerCommand)) {
        return [pscustomobject]@{
            ok = $false
            detail = "Provider '$Provider' requires explicit provider_command before dispatch."
        }
    }

    if ($providerCommand -match "[\r\n;&|<>]") {
        return [pscustomobject]@{
            ok = $false
            detail = "Provider command contains blocked shell metacharacters."
        }
    }

    if (@($providerArgs | Where-Object { $_ -match "[\r\n]" }).Count -gt 0) {
        return [pscustomobject]@{
            ok = $false
            detail = "Provider args contain blocked line breaks."
        }
    }

    return [pscustomobject]@{
        ok = $true
        provider = $Provider
        worker = $Worker
        command = $providerCommand
        args = $providerArgs
    }
}

function Invoke-AiOsProviderWorker {
    param(
        [Parameter(Mandatory = $true)][string]$Worker,
        [Parameter(Mandatory = $true)][string]$Provider,
        [Parameter(Mandatory = $true)][string]$ProviderCommand,
        [Parameter(Mandatory = $true)][string[]]$ProviderArgs,
        [Parameter(Mandatory = $true)][string]$Tier,
        [Parameter(Mandatory = $true)][string]$Mission,
        [Parameter(Mandatory = $true)][string[]]$AllowedPaths,
        [AllowEmptyString()][string]$PromptText = ""
    )

    if (-not [string]::IsNullOrWhiteSpace($PromptText)) {
        $stdin = $PromptText
    } elseif ($Provider -eq "claude") {
        $stdin = $Mission
    } else {
        $stdin = @(
            "AI_OS relay worker bounded task."
            "Provider: $Provider"
            "Worker: $Worker"
            "Allowed paths:"
            ($AllowedPaths | ForEach-Object { "- $_" })
            ""
            "Mission:"
            $Mission
        ) -join [Environment]::NewLine
    }

    $result = & "$PSScriptRoot\..\timeout\Invoke-AiOsCliWithTimeout.ps1" -FilePath $ProviderCommand -ArgumentList $ProviderArgs -TimeoutSec $script:CurrentWorkerTimeoutSec -StdIn $stdin -WorkingDirectory $RepoRoot
    $exitCode = $result.exit_code
    $output = @("stdout:", $result.stdout, "stderr:", $result.stderr)

    return [pscustomobject]@{
        exit_code = $exitCode
        output = $output
        command = "$ProviderCommand $($ProviderArgs -join ' ')"
    }
}

function Resolve-AiOsWorkerCostRecord {
    param(
        [Parameter(Mandatory = $true)][object]$ProviderResult,
        [Parameter(Mandatory = $true)][decimal]$DefaultEstimateUsd
    )

    $record = [ordered]@{
        cost_usd = $DefaultEstimateUsd
        input_tokens = 0
        output_tokens = 0
        estimated = $true
        estimate_reason = "fallback_nonzero_worker_invocation"
    }

    try {
        $lines = @($ProviderResult.output | ForEach-Object { [string]$_ })
        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            if (-not ($trimmed.StartsWith("{") -and $trimmed.EndsWith("}"))) {
                continue
            }

            $json = $trimmed | ConvertFrom-Json
            $jsonCost = $null
            if ($json.PSObject.Properties["cost_usd"]) { $jsonCost = [decimal]$json.cost_usd }
            elseif ($json.PSObject.Properties["cost"]) { $jsonCost = [decimal]$json.cost }

            $inputTokens = 0
            $outputTokens = 0
            if ($json.PSObject.Properties["usage"] -and $null -ne $json.usage) {
                if ($json.usage.PSObject.Properties["input_tokens"]) { $inputTokens = [int]$json.usage.input_tokens }
                elseif ($json.usage.PSObject.Properties["prompt_tokens"]) { $inputTokens = [int]$json.usage.prompt_tokens }
                if ($json.usage.PSObject.Properties["output_tokens"]) { $outputTokens = [int]$json.usage.output_tokens }
                elseif ($json.usage.PSObject.Properties["completion_tokens"]) { $outputTokens = [int]$json.usage.completion_tokens }
            } else {
                if ($json.PSObject.Properties["input_tokens"]) { $inputTokens = [int]$json.input_tokens }
                if ($json.PSObject.Properties["output_tokens"]) { $outputTokens = [int]$json.output_tokens }
            }

            if ($null -ne $jsonCost -and $jsonCost -gt 0) {
                $record.cost_usd = $jsonCost
                $record.input_tokens = $inputTokens
                $record.output_tokens = $outputTokens
                $record.estimated = $false
                $record.estimate_reason = "cli_reported_cost"
                break
            }

            if (($inputTokens + $outputTokens) -gt 0) {
                $record.cost_usd = [decimal](($inputTokens * 0.000005) + ($outputTokens * 0.000015))
                if ($record.cost_usd -le 0) { $record.cost_usd = $DefaultEstimateUsd }
                $record.input_tokens = $inputTokens
                $record.output_tokens = $outputTokens
                $record.estimated = $true
                $record.estimate_reason = "token_rate_estimate"
                break
            }
        }
    } catch {
        $record.cost_usd = $DefaultEstimateUsd
        $record.input_tokens = 0
        $record.output_tokens = 0
        $record.estimated = $true
        $record.estimate_reason = "fallback_usage_parse_failed"
    }

    if ($record.cost_usd -le 0) {
        $record.cost_usd = $DefaultEstimateUsd
        $record.estimated = $true
        $record.estimate_reason = "fallback_nonzero_worker_invocation"
    }

    return [pscustomobject]$record
}
function Move-AiOsTier2ToApprovals {
    param(
        [Parameter(Mandatory = $true)][System.IO.FileInfo]$File,
        [Parameter(Mandatory = $true)][object]$PacketInfo
    )

    $approvalPath = Move-AiOsRelayPacket -SourcePath $File.FullName -TargetFolder $RelayPaths.approvals
    $reasonPath = Join-Path $RelayPaths.approvals ("{0}.approval-reason.txt" -f $PacketInfo.id)
    @(
        "id: $($PacketInfo.id)"
        "reason: TIER_2_HARD_STOP"
        "worker: $($PacketInfo.worker)"
        "provider: $($PacketInfo.provider)"
        "provider_command: $($PacketInfo.provider_command)"
        "declared_tier: $($PacketInfo.tier)"
        "classified_tier: $(Get-AiOsRelayTier -Text $PacketInfo.mission)"
        "action: moved to approvals without CLI dispatch"
    ) | Set-Content -LiteralPath $reasonPath -Encoding UTF8

    Write-AiOsRelayLog "[WORKER] $($PacketInfo.id) inbox -> approvals reason=TIER_2_HARD_STOP path=$approvalPath"
}

function Complete-AiOsRelayWorkerPacket {
    param([Parameter(Mandatory = $true)][System.IO.FileInfo]$File)

    if (-not (Test-AiOsStableFile -File $File)) {
        Write-AiOsRelayLog "[WORKER] SKIP unstable file $($File.Name)"
        return "SKIPPED"
    }

    $parsed = Read-AiOsTaskPacket -File $File
    if (-not $parsed.ok) {
        $target = Move-AiOsRelayPacket -SourcePath $File.FullName -TargetFolder $RelayPaths.error
        Write-AiOsPacketError -Id $parsed.id -Reason $parsed.reason -Detail $parsed.detail
        Write-AiOsRelayLog "[WORKER] $($parsed.id) inbox -> error reason=$($parsed.reason) path=$target"
        return "PROCESSED"
    }

    $classifiedTier = Get-AiOsRelayTier -Text $parsed.mission
    $isTier2 = (Test-AiOsProtectedRelayText -Text $parsed.mission) -or
        ($parsed.tier -match "^TIER_2") -or
        ($classifiedTier -match "^TIER_2")

    if ($isTier2) {
        Move-AiOsTier2ToApprovals -File $File -PacketInfo $parsed
        return "PROCESSED"
    }

    $runningPath = Move-AiOsRelayPacket -SourcePath $File.FullName -TargetFolder $RelayPaths.running
    Write-AiOsRelayLog "[WORKER] $($parsed.id) inbox -> running worker=$($parsed.worker) provider=$($parsed.provider) command=$($parsed.provider_command) tier=$($parsed.tier)"

    $started = Get-Date
    $run_start = $started.ToUniversalTime(); $script:CurrentWorkerTimeoutSec = if ($parsed.packet.PSObject.Properties["timeout_sec"]) { [int]$parsed.packet.timeout_sec } else { 600 }
    $exitCode = 0
    $body = @()

    if (-not $Apply) {
        $body = @(
            "[DRY_RUN STUB]"
            "No CLI was called."
            "would_call: $($parsed.worker)"
            "provider: $($parsed.provider)"
            "provider_command: $($parsed.provider_command)"
            "provider_args: $($parsed.provider_args -join ' ')"
            "tier: $($parsed.tier)"
            "allowed_paths: $($parsed.allowed_paths -join ', ')"
            "mission_chars: $($parsed.mission.Length)"
        )
    } else {
        $cycleId = if ([string]::IsNullOrWhiteSpace($env:AIOS_CYCLE_ID)) { (Get-Date).ToUniversalTime().ToString("yyyyMMdd") } else { $env:AIOS_CYCLE_ID }
        $cost = & "$PSScriptRoot\..\cost\Test-AiOsCostCeiling.ps1" -CycleId $cycleId
        if (-not $cost.ok) {
            $target = Move-AiOsRelayPacket -SourcePath $runningPath -TargetFolder $RelayPaths.error
            Write-AiOsPacketError -Id $parsed.id -Reason "COST_CEILING_EXCEEDED" -Detail "$($cost.reason) cycle_spend=$($cost.cycle_spend) day_spend=$($cost.day_spend)"
            $notify = Join-Path $RepoRoot "automation\orchestration\notifications\Send-AiOsNotification.ps1"
            if (Test-Path -LiteralPath $notify -PathType Leaf) { & powershell -NoProfile -ExecutionPolicy Bypass -File $notify -Message "COST_CEILING_EXCEEDED packet=$($parsed.id) reason=$($cost.reason)" -Severity "CRITICAL" -Subject "AI_OS BLOCKER" -Apply | Out-Null }
            Write-AiOsRelayLog "[WORKER] $($parsed.id) running -> error reason=COST_CEILING_EXCEEDED path=$target"
            return "PROCESSED"
        }
        $lock = & "$PSScriptRoot\..\lock\Test-AiOsFileLock.ps1" -AllowedPaths $parsed.allowed_paths -RepoRoot $RepoRoot
        if ($lock.defer) {
            Add-AiOsDeferredUntil -PacketPath $runningPath -DeferredUntilUtc $lock.defer_until_utc
            $target = Move-AiOsRelayPacket -SourcePath $runningPath -TargetFolder $RelayPaths.inbox
            Write-AiOsRelayLog "[WORKER] $($parsed.id) running -> inbox reason=FILE_LOCK_DEFERRED deferred_until=$($lock.defer_until_utc) path=$target"
            return "SKIPPED"
        }
        $result = Invoke-AiOsProviderWorker -Worker $parsed.worker -Provider $parsed.provider -ProviderCommand $parsed.provider_command -ProviderArgs $parsed.provider_args -Tier $parsed.tier -Mission $parsed.mission -AllowedPaths $parsed.allowed_paths -PromptText $parsed.prompt_text
        $costRecord = Resolve-AiOsWorkerCostRecord -ProviderResult $result -DefaultEstimateUsd $DefaultEstimateUsd
        [void](& "$PSScriptRoot\..\cost\Add-AiOsCostLedgerEntry.ps1" -CycleId $cycleId -Cost $costRecord.cost_usd -InputTokens $costRecord.input_tokens -OutputTokens $costRecord.output_tokens -PacketId $parsed.id -Worker $parsed.worker -Estimated $costRecord.estimated -EstimateReason $costRecord.estimate_reason)
        Write-AiOsRelayLog "[WORKER] $($parsed.id) cost_ledger cost_usd=$($costRecord.cost_usd) estimated=$($costRecord.estimated) estimate_reason=$($costRecord.estimate_reason) cycle_id=$cycleId"
        $exitCode = $result.exit_code
        $body = @("command: $($result.command)", "") + @($result.output)
    }

    $ended = Get-Date
    [void](Write-AiOsWorkerReport -Id $parsed.id -Worker $parsed.worker -Provider $parsed.provider -ProviderCommand $parsed.provider_command -Tier $parsed.tier -StartedAt $started -EndedAt $ended -ExitCode $exitCode -AllowedPaths $parsed.allowed_paths -Body $body)

    if ([string]$exitCode -eq "TIMEOUT_EXCEEDED") {
        $target = Move-AiOsRelayPacket -SourcePath $runningPath -TargetFolder $RelayPaths.error
        Write-AiOsPacketError -Id $parsed.id -Reason "WORKER_TIMEOUT" -Detail "Worker exceeded timeout_sec=$script:CurrentWorkerTimeoutSec. See outbox report."; Write-AiOsRelayLog "[WORKER] $($parsed.id) running -> error reason=WORKER_TIMEOUT path=$target"
    } elseif ($exitCode -eq 0) {
        $val = & "$PSScriptRoot\..\validators\output\Test-AiOsWorkerOutput.DRY_RUN.ps1" -PacketId $parsed.id -AllowedPaths $parsed.allowed_paths -RunStartUtc $run_start -RepoRoot $RepoRoot
        if (-not $val.pass) {
            $target = Move-AiOsRelayPacket -SourcePath $runningPath -TargetFolder $RelayPaths.error
            Write-AiOsPacketError -Id $parsed.id -Reason "OUTPUT_OUTSIDE_ALLOWED_PATHS" -Detail "Output validator failed: $($val.violation_reason). See relay/logs/output_validator.log."
            Write-AiOsRelayLog "[WORKER] $($parsed.id) running -> error reason=OUTPUT_OUTSIDE_ALLOWED_PATHS path=$target"
            return "PROCESSED"
        }
        $target = Move-AiOsRelayPacket -SourcePath $runningPath -TargetFolder $RelayPaths.done
        Write-AiOsRelayLog "[WORKER] $($parsed.id) running -> done exit_code=0 path=$target"
    } else {
        $target = Move-AiOsRelayPacket -SourcePath $runningPath -TargetFolder $RelayPaths.error
        Write-AiOsPacketError -Id $parsed.id -Reason "WORKER_EXIT_$exitCode" -Detail "Worker exited non-zero. See outbox report."
        Write-AiOsRelayLog "[WORKER] $($parsed.id) running -> error reason=WORKER_EXIT_$exitCode path=$target"
    }

    return "PROCESSED"
}

function Invoke-AiOsRelayWorkerPass {
    $processed = 0
    $taskFiles = @(Get-ChildItem -LiteralPath $RelayPaths.inbox -File -Filter "*.task.json" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime, Name)

    foreach ($file in $taskFiles) {
        if ($MaxPackets -gt 0 -and $script:ProcessedPackets -ge $MaxPackets) {
            break
        }

        $result = Complete-AiOsRelayWorkerPacket -File $file
        if ($result -eq "PROCESSED") {
            $script:ProcessedPackets++
            $processed++
        }
    }

    return $processed
}

function New-AiOsRelayWorkerReport {
    $today = (Get-Date).ToUniversalTime().Date
    $dateText = $today.ToString("yyyy-MM-dd")
    $reportPath = Join-Path $RelayPaths.reports ("{0}-summary.md" -f $dateText)

    $doneFiles = @(Get-ChildItem -LiteralPath $RelayPaths.done -File -Filter "*.task.json" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTimeUtc.Date -eq $today })
    $errorFiles = @(Get-ChildItem -LiteralPath $RelayPaths.error -File -Filter "*.task.json" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTimeUtc.Date -eq $today })
    $allFiles = @($doneFiles + $errorFiles | Sort-Object LastWriteTimeUtc, Name)

    $lines = @(
        "# AI_OS Relay Summary - $dateText"
        ""
        "done: $($doneFiles.Count)"
        "error: $($errorFiles.Count)"
        ""
        "| id | worker | tier | duration | exit_code | first_line |"
        "|---|---|---|---:|---:|---|"
    )

    foreach ($file in $allFiles) {
        $id = Get-AiOsTaskIdFromFile -File $file
        $reportFile = Join-Path $RelayPaths.outbox ("{0}.report.txt" -f $id)
        $reportText = if (Test-Path -LiteralPath $reportFile -PathType Leaf) { Get-Content -LiteralPath $reportFile -Raw } else { "" }
        $worker = if ($reportText -match "(?m)^worker:\s*(.+?)\r?$") { $Matches[1].Trim() } else { "" }
        $tier = if ($reportText -match "(?m)^tier:\s*(.+?)\r?$") { $Matches[1].Trim() } else { "" }
        $duration = if ($reportText -match "(?m)^duration_seconds:\s*(\d+)\r?$") { $Matches[1] } else { "" }
        $exitCode = if ($reportText -match "(?m)^exit_code:\s*(-?\d+)\r?$") { $Matches[1] } else { "" }
        $firstLine = (($reportText -split "\r?\n") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1)
        if (-not $firstLine) { $firstLine = $file.Name }
        $safeFirstLine = ([string]$firstLine).Replace("|", "/")
        $lines += "| $id | $worker | $tier | $duration | $exitCode | $safeFirstLine |"
    }

    $lines | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-AiOsRelayLog "[WORKER] report -> $reportPath done=$($doneFiles.Count) error=$($errorFiles.Count)"
    return $reportPath
}

function Resolve-AiOsBoundPath {
    param([string]$Path,[string]$Under='')
    if ($Path -notmatch '^[A-Za-z]:\\' -or $Path.Substring(2).Contains(':') -or $Path -match '[\x00-\x1f]' -or $Path -match '(?:^|[\\/])\.{1,2}(?:[\\/]|$)') {throw 'CANONICAL_LOCAL_PATH_REQUIRED'}
    $full=[IO.Path]::GetFullPath($Path)
    if (-not [string]::Equals($full,$Path,[StringComparison]::OrdinalIgnoreCase)){throw 'NONCANONICAL_PATH'}
    foreach($part in $full.Substring(3).Split([char]'\')) {
        if($part -ne $part.TrimEnd(' ','.') -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)'){throw 'AMBIGUOUS_PATH'}
    }
    $cursor=$full
    while($cursor){
        try{if(([IO.File]::GetAttributes($cursor) -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'REPARSE_PATH'}}
        catch{$cause=$_.Exception.GetBaseException();if($cause -isnot [IO.FileNotFoundException] -and $cause -isnot [IO.DirectoryNotFoundException]){throw}}
        $parent=[IO.Path]::GetDirectoryName($cursor);if($parent -eq $cursor){break};$cursor=$parent
    }
    if($Under){$base=Resolve-AiOsBoundPath $Under;if(-not $full.StartsWith($base.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'OUTSIDE_SELECTED_ROOT'}}
    return $full
}

function Import-AiOsBoundFunctions {
    param([string]$Path)
    $tokens=$null;$errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors)
    if($errors.Count){throw 'SELECTED_SOURCE_PARSE_FAILED'}
    foreach($definition in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)) {
        Set-Item -Path ('Function:'+ $definition.Name) -Value $definition.Body.GetScriptBlock()
    }
}

function Get-AiOsBoundHash {
    param([byte[]]$Bytes)
    $hasher=[Security.Cryptography.SHA256]::Create()
    try{return [BitConverter]::ToString($hasher.ComputeHash($Bytes)).Replace('-','').ToLowerInvariant()}
    finally{$hasher.Dispose()}
}

function Write-AiOsBoundBytes {
    param([string]$Path,[string]$Under,[byte[]]$Bytes,[switch]$AllowIdentical)
    $null=Resolve-AiOsBoundPath $Path $Under
    $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
    $null=Resolve-AiOsBoundPath $Path $Under
    if($AllowIdentical -and [IO.File]::Exists($Path)) {
        if((Get-AiOsBoundHash ([IO.File]::ReadAllBytes($Path))) -cne (Get-AiOsBoundHash $Bytes)){throw 'OBSERVATION_COLLISION'}
        return
    }
    $stream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$stream.Write($Bytes,0,$Bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
    if((Get-AiOsBoundHash ([IO.File]::ReadAllBytes($Path))) -cne (Get-AiOsBoundHash $Bytes)){throw 'OBSERVATION_WRITE_INCOMPLETE'}
}

function Invoke-AiOsBoundPython {
    param([string]$PythonExecutable,[string]$RepoRoot,[string]$Code,[object]$InputObject)
    $json=$InputObject|ConvertTo-Json -Depth 30 -Compress
    $run=Invoke-AiOsCliProcess -FilePath $PythonExecutable -ArgumentList @('-B','-c',$Code) -StdIn $json -WorkingDirectory $RepoRoot -TimeoutSec 15
    if($run.exit_code -isnot [int] -or $run.exit_code -ne 0 -or $run.cleanup_state -cne 'CONFIRMED' -or $run.stdin_completed -isnot [bool] -or -not $run.stdin_completed){throw 'BOUND_READER_FAILED'}
    return ($run.stdout|ConvertFrom-Json)
}

function Get-AiOsBoundRepositoryEvidence {
    param($Request)
    $code=@'
import sys,json
from automation.orchestration.aios_repo_state_evidence import collect_repo_identity,collect_repo_state,private_root_boundaries
r=json.load(sys.stdin);root=r['repo_root'];s=collect_repo_state(root)
paths=[]
for e in s['status_entries']:
    paths += [e['path']] + ([e['source_path']] if 'source_path' in e else [])
print(json.dumps({'identity':collect_repo_identity(root),'paths':sorted(set(paths)), 'status':s['status_evidence'], 'private_root_boundaries':private_root_boundaries(root), 'complete':s['evidence_quality']=='strong' and not s['status_parse_errors'] and s['status_evidence'] is not None, 'errors':s['status_parse_errors']}))
'@
    return Invoke-AiOsBoundPython $Request.python_executable $Request.repo_root $code $Request
}

function Test-AiOsBoundPreflight {
    param($Request,$Binding,$LogPath)
    return Test-AiOsToolPreflight -Tools @($Request.provider_executable) -VersionTimeoutSec 10 -RepoRoot $Request.repo_root -RelayRoot $Request.relay_root -LogPath $LogPath -CampaignBinding $Binding
}

function Test-AiOsBoundCostAndLock {
    param($Request,$LedgerPath)
    $cost=& (Join-Path $Request.repo_root 'automation/orchestration/cost/Test-AiOsCostCeiling.ps1') -LedgerPath $LedgerPath -PolicyPath $Request.policy_path -CycleId $Request.cycle_id
    if($cost.ok -isnot [bool] -or -not $cost.ok){return [pscustomobject]@{ok=$false;defer=$false;reason='COST_NOT_ADMITTED'}}
    $lock=& (Join-Path $Request.repo_root 'automation/orchestration/lock/Test-AiOsFileLock.ps1') -AllowedPaths @($Request.allowed_paths) -RepoRoot $Request.repo_root
    if($lock.defer -isnot [bool]){throw 'LOCK_RESULT_MALFORMED'}
    return [pscustomobject]@{ok=$true;defer=$lock.defer;reason=$lock.reason}
}

function Assert-AiOsBoundObservationReady {
    param($Process)
    $ready=$null
    Get-AiOsBoundRawMember $Process 'observation_ready' ([ref]$ready)
    if($ready -isnot [bool] -or -not $ready){throw 'WORKER_OBSERVATION_READINESS_UNCONFIRMED'}
}

function Invoke-AiOsBoundProvider {
    param($Request,[string]$PromptText,[object]$WorkerObservationApi=$null)
    $extra=@{}
    if($Request -is [Collections.IDictionary]){$requestKeys=@($Request.Keys)}
    elseif($Request -is [pscustomobject]){$requestKeys=@($Request.PSObject.Properties.Name)}
    else{throw 'WORKER_LAUNCH_REQUEST_OBJECT_REQUIRED'}
    $present=@($requestKeys | Where-Object {$_ -is [string] -and [string]::Equals($_,'worker_launch_contract',[StringComparison]::OrdinalIgnoreCase)})
    if($present.Count -gt 0){
        if($present.Count -ne 1 -or $present[0] -cne 'worker_launch_contract'){throw 'WORKER_LAUNCH_CONTRACT_KEY_INVALID'}
        $contract=$null;Get-AiOsBoundRawMember $Request 'worker_launch_contract' ([ref]$contract)
        if($contract -is [Collections.IDictionary]){$contractKeys=@($contract.Keys)}
        elseif($contract -is [pscustomobject]){$contractKeys=@($contract.PSObject.Properties.Name)}
        else{throw 'WORKER_LAUNCH_CONTRACT_INVALID'}
        $required=@('schema','environment','environment_block_utf16_sha256','environment_block_bytes')
        if($contractKeys.Count -ne $required.Count){throw 'WORKER_LAUNCH_CONTRACT_FIELDS_INVALID'}
        foreach($key in $contractKeys){if($key -isnot [string] -or $key -cnotin $required){throw 'WORKER_LAUNCH_CONTRACT_FIELDS_INVALID'}}
        $schema=$null;$environment=$null;$hash=$null;$size=$null
        Get-AiOsBoundRawMember $contract 'schema' ([ref]$schema)
        Get-AiOsBoundRawMember $contract 'environment' ([ref]$environment)
        Get-AiOsBoundRawMember $contract 'environment_block_utf16_sha256' ([ref]$hash)
        Get-AiOsBoundRawMember $contract 'environment_block_bytes' ([ref]$size)
        if($schema -isnot [string] -or $schema -cne 'AIOS_SELECTED_WORKER_LAUNCH.v1' -or $hash -isnot [string] -or $hash -cnotmatch '^[0-9a-f]{64}$' -or ($size -isnot [int] -and $size -isnot [long]) -or $size -lt 4 -or $size -gt 1048576 -or $size%2 -ne 0){throw 'WORKER_LAUNCH_CONTRACT_INVALID'}
        if($environment -is [Collections.IDictionary]){$names=@($environment.Keys)}
        elseif($environment -is [pscustomobject]){$names=@($environment.PSObject.Properties.Name)}
        else{throw 'WORKER_LAUNCH_ENVIRONMENT_OBJECT_REQUIRED'}
        if($names.Count -gt 256){throw 'WORKER_LAUNCH_ENVIRONMENT_SIZE_INVALID'}
        $exact=[Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach($name in $names){
            if($name -isnot [string] -or $name -cnotmatch '^[A-Za-z_][A-Za-z0-9_]{0,255}$'){throw 'WORKER_LAUNCH_ENVIRONMENT_NAME_INVALID'}
            $value=$null;Get-AiOsBoundRawMember $environment $name ([ref]$value)
            if($value -isnot [string] -or $value.Length -gt 32767 -or $value.IndexOf([char]0) -ge 0){throw 'WORKER_LAUNCH_ENVIRONMENT_VALUE_INVALID'}
            $exact.Add($name,$value)
        }
        $extra['LaunchEnvironment']=$exact
    }
    $observation=@($requestKeys | Where-Object {$_ -is [string] -and [string]::Equals($_,'worker_observation_contract',[StringComparison]::OrdinalIgnoreCase)})
    if($observation.Count -gt 0){
        if($observation.Count -ne 1 -or $observation[0] -cne 'worker_observation_contract'){throw 'WORKER_OBSERVATION_KEY_INVALID'}
        $apiType='AiOs.ValidatorProcessApi' -as [type]
        if($null -eq $apiType -or $null -eq $WorkerObservationApi -or -not $apiType.IsInstanceOfType($WorkerObservationApi) -or -not $extra.ContainsKey('LaunchEnvironment')){throw 'WORKER_OBSERVATION_RUNTIME_HOST_REQUIRED'}
        $extra['ProcessApi']=$WorkerObservationApi
        $extra['RequireObservation']=$true
    }elseif($null -ne $WorkerObservationApi){throw 'UNBOUND_WORKER_OBSERVATION_RUNTIME_HOST'}
    return Invoke-AiOsCliProcess -FilePath $Request.provider_executable -ArgumentList @($Request.provider_args) -TimeoutSec $Request.timeout_sec -StdIn $PromptText -WorkingDirectory $Request.repo_root @extra
}

function Get-AiOsBoundPreservationSnapshot {
    param($Request,[string]$PacketSha256,[string]$LaunchSha256,[string]$Phase)
    $code=@'
import sys,json
from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import capture_provider_preservation
r=json.load(sys.stdin);print(json.dumps(capture_provider_preservation(**r),ensure_ascii=True))
'@
    return Invoke-AiOsBoundPython $Request.python_executable $Request.repo_root $code @{request=$Request;packet_sha256=$PacketSha256;launch_sha256=$LaunchSha256;phase=$Phase}
}

function Complete-AiOsBoundPreservationInterval {
    param($Request,[string]$PacketSha256,[string]$LaunchSha256,$Capture,$Before,$After,[string]$ProviderStarted)
    $code=@'
import sys,json
from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import complete_provider_preservation
r=json.load(sys.stdin);print(json.dumps(complete_provider_preservation(**r),ensure_ascii=True))
'@
    return Invoke-AiOsBoundPython $Request.python_executable $Request.repo_root $code @{request=$Request;packet_sha256=$PacketSha256;launch_sha256=$LaunchSha256;capture=$Capture;before=$Before;after=$After;provider_started=$ProviderStarted}
}

function Add-AiOsBoundCost {
    param($Request,$Binding,$LedgerPath,$ProviderResult)
    $usage=Resolve-AiOsWorkerCostRecord -ProviderResult ([pscustomobject]@{output=@($ProviderResult.stdout)}) -DefaultEstimateUsd ([decimal]0.02)
    return Add-AiOsCostLedgerEntry -CycleId $Request.cycle_id -PacketId $Request.packet_id -Worker 'codex' -Cost $usage.cost_usd -InputTokens $usage.input_tokens -OutputTokens $usage.output_tokens -Estimated $usage.estimated -EstimateReason $usage.estimate_reason -RepoRoot $Request.repo_root -RelayRoot $Request.relay_root -LedgerPath $LedgerPath -CampaignBinding $Binding
}

function Get-AiOsBoundLaunchWitness {
    param([object]$Witness,[string]$ExpectedExecutable)
    $type='AiOs.ValidatorLaunchWitness' -as [type]
    if($null -eq $type -or $null -eq $Witness -or $Witness.GetType() -ne $type){throw 'WORKER_LAUNCH_WITNESS_TYPE_INVALID'}
    $fields=$type.GetFields([Reflection.BindingFlags]'Public,Instance,DeclaredOnly')
    if($fields.Count -ne 18){throw 'WORKER_LAUNCH_WITNESS_FIELDS_INVALID'}
    $fresh=[ordered]@{}
    foreach($name in @('native_admission','qualification','execution_authority','stdin_present','created','assigned_before_resume','resumed')){
        $field=$type.GetField($name);if($null -eq $field){throw 'WORKER_LAUNCH_WITNESS_BOOLEAN_MISSING'}
        $value=$field.GetValue($Witness);if($value -isnot [bool]){throw 'WORKER_LAUNCH_WITNESS_BOOLEAN_INVALID'}
        if($name -in @('native_admission','qualification','execution_authority') -and $value){throw 'WORKER_LAUNCH_WITNESS_CANNOT_GRANT_AUTHORITY'}
        $fresh[$name]=[bool]$value
    }
    foreach($name in @('creator_process_id','child_process_id','child_creation_filetime','environment_block_bytes')){
        $field=$type.GetField($name);if($null -eq $field){throw 'WORKER_LAUNCH_WITNESS_NUMBER_MISSING'}
        $value=$field.GetValue($Witness)
        if(($name -in @('creator_process_id','child_process_id') -and $value -isnot [uint32]) -or ($name -notin @('creator_process_id','child_process_id') -and $value -isnot [long]) -or $value -lt 0){throw 'WORKER_LAUNCH_WITNESS_NUMBER_INVALID'}
        $fresh[$name]=[long]$value
    }
    foreach($name in @('application_utf16_sha256','command_line_utf16_sha256','directory_utf16_sha256','environment_block_utf16_sha256','stdin_utf8_sha256')){
        $field=$type.GetField($name);if($null -eq $field){throw 'WORKER_LAUNCH_WITNESS_HASH_MISSING'}
        $value=$field.GetValue($Witness);if($value -isnot [string] -or $value -cnotmatch '^[0-9a-f]{64}$'){throw 'WORKER_LAUNCH_WITNESS_HASH_INVALID'}
        $fresh[$name]=[string]$value
    }
    $schema=$type.GetField('schema').GetValue($Witness)
    $image=$type.GetField('actual_image_path').GetValue($Witness)
    if($schema -isnot [string] -or $schema -cne 'aios.windows_launch_witness.v1' -or $image -isnot [string] -or $image.Length -gt 32766){throw 'WORKER_LAUNCH_WITNESS_TEXT_INVALID'}
    if($image.Length -gt 0 -and -not [string]::Equals($image,$ExpectedExecutable,[StringComparison]::OrdinalIgnoreCase)){throw 'WORKER_LAUNCH_WITNESS_IMAGE_MISMATCH'}
    $fresh['schema']=[string]$schema;$fresh['actual_image_path']=[string]$image
    return [pscustomobject]$fresh
}

function Get-AiOsBoundProcessProjection {
    param($Run)
    # Copy only fresh typed scalars/argv. No child output or ETS properties are
    # serialized into durable evidence. A raw child exit cannot override cleanup.
    $projection=[ordered]@{};$valid=$true
    $booleanNames=@('timed_out','startup_failed','root_exit_confirmed','tree_exit_confirmed','drains_completed','retry_allowed','stdin_completed','stdin_writer_joined','stdout_truncated','stderr_truncated')
    foreach($name in $booleanNames){$property=$Run.PSObject.Properties[$name];if($null -eq $property -or $property.Value -isnot [bool]){$valid=$false;$projection[$name]=$null}else{$projection[$name]=[bool]$property.Value}}
    foreach($name in @('root_process_id','stdin_bytes_written','stdin_error_code','stdin_close_error_code','cleanup_error_code','cancellation_error_code')) {
        $property=$Run.PSObject.Properties[$name]
        if($null -eq $property -or ($property.Value -isnot [int] -and $property.Value -isnot [long]) -or $property.Value -lt 0){$valid=$false;$projection[$name]=$null}else{$projection[$name]=[long]$property.Value}
    }
    foreach($name in @('exit_code','child_exit_code')) {
        $property=$Run.PSObject.Properties[$name]
        if($null -ne $property -and ($property.Value -is [int] -or $property.Value -is [long] -or $property.Value -is [string])){$projection[$name]=$property.Value}else{$projection[$name]=$null;$valid=$false}
    }
    foreach($name in @('cleanup_state','executable','working_directory','command_line_arguments')) {
        $property=$Run.PSObject.Properties[$name];if($null -eq $property -or $property.Value -isnot [string]){$projection[$name]=$null;$valid=$false}else{$projection[$name]=[string]$property.Value}
    }
    $projection['arguments']=@();$property=$Run.PSObject.Properties['arguments']
    if($null -eq $property -or $property.Value -isnot [array]){$valid=$false}else{foreach($arg in $property.Value){if($arg -isnot [string]){$valid=$false}else{$projection.arguments+=([string]$arg)}}}
    $property=$Run.PSObject.Properties['duration_sec'];if($null -eq $property -or $property.Value -is [bool] -or ($property.Value -isnot [int] -and $property.Value -isnot [long] -and $property.Value -isnot [double] -and $property.Value -isnot [single] -and $property.Value -isnot [decimal]) -or [double]::IsNaN([double]$property.Value) -or [double]::IsInfinity([double]$property.Value) -or [double]$property.Value -lt 0){$projection.duration_sec=$null;$valid=$false}else{$projection.duration_sec=[double]$property.Value}
    $projection['process_error_present']=($null -ne $Run.PSObject.Properties['process_error'] -and -not [string]::IsNullOrEmpty([string]$Run.process_error))
    $required=$Run.PSObject.Properties['observation_required']
    if($null -ne $required -and $required.Value -is [bool] -and $required.Value){
        $ready=$Run.PSObject.Properties['observation_ready']
        if($null -eq $ready -or $ready.Value -isnot [bool]){$valid=$false;$projection['observation_ready']=$false}else{$projection['observation_ready']=[bool]$ready.Value}
        $projection['observation_required']=$true
    }
    $projection['shape_valid']=$valid
    $witness=$Run.PSObject.Properties['launch_witness']
    if($null -ne $witness -and $null -ne $witness.Value){
        $projection['launch_witness']=Get-AiOsBoundLaunchWitness $witness.Value $projection['executable']
    }
    return $projection
}

function Write-AiOsBoundObservation {
    param($Request,$Binding,[string]$TransportId,[string]$Status,[string]$Reason,[string]$ExecutionPath='',[string]$ExecutionSha256='', [object]$PendingCapture=$null,[string]$PrimaryError='',[string]$SecondaryError='',[string]$PendingAction='',[object]$OutputEvidence=$null)
    $value=[ordered]@{schema='AIOS_RELAY_OBSERVATION.v1';repo_root=[string]$Request.repo_root;relay_root=[string]$Request.relay_root;status=$Status;reason=$Reason;authority_granted=$false;retry_allowed=$false;execution_path=$ExecutionPath;execution_sha256=$ExecutionSha256}
    foreach($name in $Binding.Keys){$value[$name]=$Binding[$name]}
    if($null -ne $PendingCapture){$value['pending_capture']=$PendingCapture}
    if($PrimaryError){$value['primary_capture_error']=$PrimaryError}
    if($SecondaryError){$value['secondary_capture_error']=$SecondaryError}
    if($PendingAction){$value['pending_action']=$PendingAction}
    if($null -ne $OutputEvidence){$value['output_scope']=$OutputEvidence}
    $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($value|ConvertTo-Json -Depth 12 -Compress)+"`n")
    $sha=Get-AiOsBoundHash $bytes;$path=Join-Path $Request.relay_root ('outbox\'+$TransportId+'.result.'+$sha+'.json')
    try{Write-AiOsBoundBytes $path $Request.relay_root $bytes -AllowIdentical}
    catch{$value['secondary_error']='OBSERVATION_PUBLICATION_FAILED';$value['secondary_error_type']=$_.Exception.GetType().Name;return [pscustomobject]$value}
    $value['observation_path']=$path;$value['observation_sha256']=$sha
    return [pscustomobject]$value
}

function Get-AiOsBoundRawMember {
    param([object]$Value,[string]$Name,[ref]$Result)
    # Assign through a reference: returning an array through the PS pipeline
    # would flatten the very raw shape this boundary must reject.
    if($Value -is [Collections.IDictionary]) {
        if(@($Value.Keys) -cnotcontains $Name){throw 'READBACK_MEMBER_MISSING'}
        $Result.Value=$Value[$Name]
    } elseif($Value -is [pscustomobject]) {
        if(@($Value.PSObject.Properties.Name) -cnotcontains $Name){throw 'READBACK_MEMBER_MISSING'}
        $Result.Value=$Value.PSObject.Properties[$Name].Value
    } else {throw 'READBACK_OBJECT_REQUIRED'}
}

function Assert-AiOsBoundReadback {
    param([object]$Value,[object]$Binding,[ValidateSet('Observation','Capture')][string]$Kind,
        [string]$RepoRoot='',[string]$RelayRoot='',[string]$RequestJson='',[string]$PacketSha256='')
    $actual=$null;$expected=$null;$rawBinding=$Value
    Get-AiOsBoundRawMember $Value 'schema' ([ref]$actual)
    $schemas=if($Kind -ceq 'Capture'){@('AIOS_RELAY_EXECUTION.v1','AIOS_RELAY_EXECUTION.v2')}else{@('AIOS_RELAY_OBSERVATION.v1')}
    if($actual -isnot [string] -or $actual -cnotin $schemas){throw 'READBACK_SCHEMA_INVALID'}
    foreach($name in @('authority_granted','retry_allowed')) {
        Get-AiOsBoundRawMember $Value $name ([ref]$actual)
        if($actual -isnot [bool] -or $actual){throw 'READBACK_FLAG_INVALID'}
    }
    $fields=@('request_sha256','task_id','packet_id','attempt_id','attempt_number','claim_task_id','claim_acquired_at','claim_identity_sha256','campaign_id')
    if($Kind -ceq 'Capture') {
        Get-AiOsBoundRawMember $Value 'binding' ([ref]$rawBinding)
        if($rawBinding -is [Collections.IDictionary]){$keys=@($rawBinding.Keys)}
        elseif($rawBinding -is [pscustomobject]){$keys=@($rawBinding.PSObject.Properties.Name)}
        else{throw 'READBACK_BINDING_OBJECT_REQUIRED'}
        if($keys.Count -ne $fields.Count){throw 'READBACK_BINDING_SHAPE_INVALID'}
        foreach($key in $keys){if($key -isnot [string] -or $key -cnotin $fields){throw 'READBACK_BINDING_SHAPE_INVALID'}}
    }
    foreach($name in $fields) {
        Get-AiOsBoundRawMember $rawBinding $name ([ref]$actual)
        Get-AiOsBoundRawMember $Binding $name ([ref]$expected)
        if($name -ceq 'attempt_number') {
            if(($actual -isnot [int] -and $actual -isnot [long]) -or ($expected -isnot [int] -and $expected -isnot [long]) -or $actual -lt 0 -or $actual -gt 2147483647 -or $actual -ne $expected){throw 'READBACK_ATTEMPT_TYPE_OR_VALUE_INVALID'}
        } elseif($actual -isnot [string] -or $expected -isnot [string] -or -not [string]::Equals($actual,$expected,[StringComparison]::Ordinal)) {throw 'READBACK_BINDING_TYPE_OR_VALUE_INVALID'}
    }
    if($Kind -ceq 'Capture'){$strings=@{request_json=$RequestJson;packet_sha256=$PacketSha256}}
    else{$strings=@{repo_root=$RepoRoot;relay_root=$RelayRoot}}
    foreach($name in $strings.Keys) {
        Get-AiOsBoundRawMember $Value $name ([ref]$actual)
        if($actual -isnot [string] -or -not [string]::Equals($actual,$strings[$name],[StringComparison]::Ordinal)){throw 'READBACK_INPUT_TYPE_OR_VALUE_INVALID'}
    }
    if($Kind -ceq 'Observation') {
        Get-AiOsBoundRawMember $Value 'status' ([ref]$actual)
        if($actual -isnot [string] -or $actual -cnotin @('DEFERRED','STOP_FLAG','REQUEST_REJECTED')){throw 'READBACK_OBSERVATION_NOT_SAFE_BASELINE'}
        Get-AiOsBoundRawMember $Value 'reason' ([ref]$actual)
        if($actual -isnot [string]){throw 'READBACK_REASON_TYPE_INVALID'}
    }
}

function Get-AiOsBoundCoveredMetadata {
    param($Request,$Task,$Binding,[object]$Evidence,[string[]]$Metadata)
    if($Evidence.complete -isnot [bool] -or -not $Evidence.complete -or $Evidence.errors -isnot [array] -or @($Evidence.errors).Count -ne 0 -or $Evidence.paths -isnot [array]){throw 'STATUS_COVERAGE_UNAVAILABLE'}
    foreach($field in @('repo_root','git_dir','branch','commit','resolved')){if($Evidence.identity.$field -cne $Request.repository_identity.$field){throw 'REPOSITORY_IDENTITY_CHANGED'}}
    $covered=@(@($Request.source_paths)+@($Metadata))
    foreach($relative in $Evidence.paths){
        if($relative -isnot [string]){throw 'STATUS_PATH_TYPE_INVALID'}
        if($relative -in $covered){continue}
        $prefix=($Request.relay_root.Substring($Request.repo_root.Length+1).Replace('\','/')+'/outbox/'+$Task.id+'.result.')
        if(-not $relative.StartsWith($prefix,[StringComparison]::Ordinal) -or $relative.Substring($prefix.Length) -cnotmatch '^([0-9a-f]{64})\.json$'){throw 'UNKNOWN_PREEXISTING_STATUS_PATH'}
        $expectedHash=$Matches[1];$path=Resolve-AiOsBoundPath (Join-Path $Request.repo_root $relative) $Request.relay_root
        $raw=[IO.File]::ReadAllBytes($path)
        if((Get-AiOsBoundHash $raw) -cne $expectedHash){throw 'CURRENT_OBSERVATION_HASH_CONFLICT'}
        $saved=[Text.UTF8Encoding]::new($false,$true).GetString($raw)|ConvertFrom-Json
        Assert-AiOsBoundReadback -Value $saved -Binding $Binding -Kind Observation -RepoRoot $Request.repo_root -RelayRoot $Request.relay_root
        $Metadata+= $relative;$covered+= $relative
    }
    return @($Metadata|Select-Object -Unique)
}

function Invoke-AiOsBoundRelayRequest {
    [CmdletBinding()]
    param([string]$RepoRoot,[string]$RelayRoot,[string]$RequestPath,[string]$ExpectedPacketSha256,[string]$PythonExecutable,[object]$ExplicitApplyChoice=$false,[object]$WorkerObservationApi=$null)
    # Explicit selection is not owner approval. Rejected intent has no effects,
    # including no finalizer writes or replay of an already captured attempt.
    if($ExplicitApplyChoice -isnot [bool] -or -not $ExplicitApplyChoice) {
        return [pscustomobject]@{status='REQUEST_REJECTED';reason='EXACT_APPLY_REQUEST_REQUIRED';authority_granted=$false;retry_allowed=$false}
    }
    $request=$null;$binding=$null;$executionPath='';$executionSha='';$captured=$false;$identityVerified=$false;$launchObserved=$false;$pendingCapture=$null
    try {
        $null=Resolve-AiOsBoundPath $RepoRoot;$null=Resolve-AiOsBoundPath $RelayRoot $RepoRoot
        $sourceRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
        if(-not [string]::Equals($sourceRoot,$RepoRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'WORKER_SOURCE_ROOT_MISMATCH'}
        $null=Resolve-AiOsBoundPath $RequestPath $RelayRoot;$null=Resolve-AiOsBoundPath $PythonExecutable
        if($ExpectedPacketSha256 -cnotmatch '^[0-9a-f]{64}$'){throw 'PACKET_DIGEST_REQUIRED'}
        $packetBytes=[IO.File]::ReadAllBytes($RequestPath)
        if((Get-AiOsBoundHash $packetBytes) -cne $ExpectedPacketSha256){throw 'PACKET_DIGEST_MISMATCH'}
        $utf8=[Text.UTF8Encoding]::new($false,$true);$rawTask=$utf8.GetString($packetBytes)|ConvertFrom-Json
        $untrusted=$rawTask.request_json|ConvertFrom-Json
        if($untrusted.python_executable -cne $PythonExecutable){throw 'SELECTED_PYTHON_MISMATCH'}
        . Import-AiOsBoundFunctions (Join-Path $RepoRoot 'automation/orchestration/timeout/Invoke-AiOsCliWithTimeout.ps1')
        $code='import sys,json; from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import read_bound_packet; r=json.load(sys.stdin); print(json.dumps(read_bound_packet(**r),ensure_ascii=True))'
        $read=Invoke-AiOsBoundPython $PythonExecutable $RepoRoot $code @{path=$RequestPath;digest=$ExpectedPacketSha256;repo_root=$RepoRoot;relay_root=$RelayRoot}
        $request=$read.request;$task=$read.task;$binding=@{}
        if($null -ne $request.PSObject.Properties['worker_observation_contract'] -and $null -eq $WorkerObservationApi){throw 'WORKER_OBSERVATION_TRANSPORT_UNCONNECTED'}
        foreach($p in $read.binding.PSObject.Properties){$binding[$p.Name]=$p.Value}
        foreach($relative in @('automation/orchestration/preflight/Test-AiOsToolPreflight.ps1','automation/orchestration/cost/Add-AiOsCostLedgerEntry.ps1','automation/orchestration/validators/output/Test-AiOsWorkerOutput.DRY_RUN.ps1')){. Import-AiOsBoundFunctions (Join-Path $RepoRoot $relative)}
        $executionPath=Join-Path $RelayRoot ('outbox\'+$task.id+'.execution.json')
        $launchPath=Join-Path $RelayRoot ('outbox\'+$task.id+'.launch.json')
        $running=Join-Path $RelayRoot ('running\'+$task.id+'.task.json')
        $inbox=Join-Path $RelayRoot ('inbox\'+$task.id+'.task.json')
        $ledger=Join-Path $RelayRoot 'logs\cost_ledger.jsonl';$preflightLog=Join-Path $RelayRoot 'logs\preflight.log';$outputLog=Join-Path $RelayRoot 'logs\output_validator.log'
        $metadata=@($request.controller_metadata_paths)
        $metadata+= $request.policy_path.Substring($RepoRoot.Length+1).Replace('\','/')
        foreach($path in @($inbox,$running,$executionPath,$launchPath,$ledger,$preflightLog,$outputLog)){$metadata+= $path.Substring($RepoRoot.Length+1).Replace('\','/')}
        $earlyEvidence=Get-AiOsBoundRepositoryEvidence $request
        $metadata=@(Get-AiOsBoundCoveredMetadata $request $task $binding $earlyEvidence $metadata)
        $identityVerified=$true
        if([IO.File]::Exists($executionPath)){
            $null=Resolve-AiOsBoundPath $executionPath $RelayRoot
            $savedBytes=[IO.File]::ReadAllBytes($executionPath);$saved=$utf8.GetString($savedBytes)|ConvertFrom-Json
            Assert-AiOsBoundReadback -Value $saved -Binding $binding -Kind Capture -RequestJson $task.request_json -PacketSha256 $ExpectedPacketSha256
            return Write-AiOsBoundObservation $request $binding $task.id 'FINALIZATION_RECONCILIATION_REQUIRED' 'CAPTURED_ATTEMPT_NO_REPLAY' $executionPath (Get-AiOsBoundHash $savedBytes)
        }
        if([IO.File]::Exists($launchPath)){return Write-AiOsBoundObservation $request $binding $task.id 'SAFETY_INTEGRITY_BLOCK' 'LAUNCH_OBSERVED_WITHOUT_CONFIRMED_CAPTURE'}
        if($earlyEvidence.private_root_boundaries -isnot [array]){throw 'PRIVATE_BOUNDARY_NAME_CHECK_INCOMPLETE'}
        if(@($earlyEvidence.private_root_boundaries).Count -gt 0){
            return Write-AiOsBoundObservation $request $binding $task.id 'DEFERRED' 'PRIVATE_BOUNDARY_PROTECTION_REQUIRED'
        }
        if([IO.File]::Exists((Join-Path $RelayRoot 'STOP.flag'))){return Write-AiOsBoundObservation $request $binding $task.id 'STOP_FLAG' 'SELECTED_STOP'}
        $ledger=Join-Path $RelayRoot 'logs\cost_ledger.jsonl';$preflightLog=Join-Path $RelayRoot 'logs\preflight.log';$outputLog=Join-Path $RelayRoot 'logs\output_validator.log'
        $gate=Test-AiOsBoundPreflight $request $binding $preflightLog
        if($gate.ok -isnot [bool] -or -not $gate.ok){return Write-AiOsBoundObservation $request $binding $task.id 'DEFERRED' 'SELECTED_TOOL_NOT_READY'}
        $gate=Test-AiOsBoundCostAndLock $request $ledger
        if($gate.ok -isnot [bool] -or -not $gate.ok -or $gate.defer -isnot [bool] -or $gate.defer){return Write-AiOsBoundObservation $request $binding $task.id 'DEFERRED' 'COST_OR_FILE_LOCK_WAIT'}
        $running=Join-Path $RelayRoot ('running\'+$task.id+'.task.json')
        $null=Resolve-AiOsBoundPath $running $RelayRoot
        if($RequestPath -cne $running){
            $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($running))
            $null=Resolve-AiOsBoundPath $running $RelayRoot
            [IO.File]::Move($RequestPath,$running)
        }
        if((Get-AiOsBoundHash ([IO.File]::ReadAllBytes($running))) -cne $ExpectedPacketSha256){throw 'RUNNING_PACKET_CHANGED'}
        $beforeEvidence=Get-AiOsBoundRepositoryEvidence $request
        $metadata=@(Get-AiOsBoundCoveredMetadata $request $task $binding $beforeEvidence $metadata)
        $inventory=@(@($request.source_paths)+$metadata|Select-Object -Unique)
        $before=Get-AiOsWorkerOutputManifest -RepoRoot $RepoRoot -SourcePaths $inventory
        # Re-read the exact producer packet and source/input bindings immediately
        # before launch. No directory scan or fallback provider is permitted.
        $read=Invoke-AiOsBoundPython $PythonExecutable $RepoRoot $code @{path=$running;digest=$ExpectedPacketSha256;repo_root=$RepoRoot;relay_root=$RelayRoot}
        $started=[DateTime]::UtcNow.ToString('o')
        $launchBytes=$utf8.GetBytes((@{schema='AIOS_RELAY_LAUNCH_OBSERVATION.v1';binding=$binding;request_json=[string]$task.request_json;packet_sha256=$ExpectedPacketSha256;started_at=$started;authority_granted=$false}|ConvertTo-Json -Depth 30 -Compress)+"`n")
        # A failed exclusive write/flush may already have left durable bytes.
        # Treat the attempted intent save as uncertain even before it returns.
        $launchObserved=$true
        Write-AiOsBoundBytes $launchPath $RelayRoot $launchBytes
        $before[$launchPath.Substring($RepoRoot.Length+1).Replace('\','/')]=Get-AiOsBoundHash $launchBytes
        # Launch intent is already durable. Missing/incomplete evidence, worker
        # loss or archive failure consumes that intent and never replays work.
        $launchSha=Get-AiOsBoundHash $launchBytes
        $fullBefore=Get-AiOsBoundPreservationSnapshot $request $ExpectedPacketSha256 $launchSha 'before'
        $providerStarted=[DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'")
        $providerRun=Invoke-AiOsBoundProvider $request $read.task.prompt_text -WorkerObservationApi $WorkerObservationApi
        $ended=[DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'")
        $afterProviderEvidence=Get-AiOsBoundRepositoryEvidence $request
        $fullAfter=Get-AiOsBoundPreservationSnapshot $request $ExpectedPacketSha256 $launchSha 'after'
        $process=Get-AiOsBoundProcessProjection $providerRun
        $capture=[ordered]@{schema='AIOS_RELAY_EXECUTION.v2';binding=$binding;request_json=[string]$task.request_json;packet_sha256=$ExpectedPacketSha256;
            started_at=$started;ended_at=$ended;process=$process;controller_capture_contract=@{path=$executionPath.Substring($RepoRoot.Length+1).Replace('\','/');required_before=$null;write_mode='CreateNew'};before_manifest=$before;before_status_paths=@($beforeEvidence.paths);authority_granted=$false;retry_allowed=$false}
        if($null -ne $request.PSObject.Properties['worker_observation_contract']){
            Assert-AiOsBoundObservationReady $process
            $observationRaw=$WorkerObservationApi.GetWorkerObservation()
            if($observationRaw -isnot [string] -or $observationRaw.Length -lt 1 -or $observationRaw.Length -gt 2097152){throw 'WORKER_OBSERVATION_ORIGINAL_MISSING'}
            $observation=$observationRaw|ConvertFrom-Json -ErrorAction Stop
            if($observation -isnot [pscustomobject] -or $observation.schema -cne 'AIOS_WINDOWS_WORKER_OBSERVATION_HANDOFF.v1' -or $observation.authority_granted -isnot [bool] -or $observation.authority_granted -or $observation.qualification -isnot [bool] -or $observation.qualification){throw 'WORKER_OBSERVATION_ORIGINAL_INVALID'}
            $capture['worker_observation']=$observation
        }
        $capture['status']=@{before=$beforeEvidence.status;after=$afterProviderEvidence.status;parser_sha256=[string]$request.source_manifest.'automation/orchestration/aios_repo_state_evidence.py'}
        $capture['provider_interval']=Complete-AiOsBoundPreservationInterval $request $ExpectedPacketSha256 $launchSha $capture $fullBefore $fullAfter $providerStarted
        $pendingCapture=$capture
        $captureBytes=$utf8.GetBytes(($capture|ConvertTo-Json -Depth 30 -Compress)+"`n")
        # Exclusive creation proves this one exact controller delta. Existing
        # bytes are never accepted as a fresh authentic capture after execution.
        try{Write-AiOsBoundBytes $executionPath $RelayRoot $captureBytes}
        catch{
            $captureFailure=$_.Exception.Message
            $fallback=Join-Path $RelayRoot ('outbox\'+$task.id+'.execution-recovery.'+(Get-AiOsBoundHash $captureBytes)+'.json')
            try{Write-AiOsBoundBytes $fallback $RelayRoot $captureBytes -AllowIdentical}
            catch{
                $secondaryCaptureFailure=$_.Exception.Message
                return Write-AiOsBoundObservation $request $binding $task.id 'FINALIZATION_RECONCILIATION_REQUIRED' 'CAPTURE_AND_RECOVERY_SAVE_FAILED' -PendingCapture $pendingCapture -PrimaryError $captureFailure -SecondaryError $secondaryCaptureFailure -PendingAction 'PERSIST_AVAILABLE_EXECUTION_CAPTURE_THEN_RECONCILE_NO_REPLAY'
            }
            return Write-AiOsBoundObservation $request $binding $task.id 'FINALIZATION_RECONCILIATION_REQUIRED' 'PRIMARY_CAPTURE_SAVE_FAILED_RECOVERY_AVAILABLE' $fallback (Get-AiOsBoundHash $captureBytes) -PrimaryError $captureFailure -PendingAction 'VERIFY_RECOVERY_CAPTURE_THEN_RECONCILE_NO_REPLAY'
        }
        $captured=$true;$executionSha=Get-AiOsBoundHash $captureBytes
        $scopeBefore=@{};foreach($key in $before.Keys){$scopeBefore[$key]=$before[$key]}
        $captureRelative=$executionPath.Substring($RepoRoot.Length+1).Replace('\','/')
        $scopeBefore[$captureRelative]=$executionSha
        # Exact exclusively created delta; no directory/metadata exemption.
        $afterEvidence=Get-AiOsBoundRepositoryEvidence $request
        $afterErrors=@($afterEvidence.errors)
        foreach($field in @('repo_root','git_dir','branch','commit','resolved')){if($afterEvidence.identity.$field -cne $request.repository_identity.$field){$afterErrors+='REPOSITORY_IDENTITY_CHANGED_AFTER_EXECUTION'}}
        $changed=@{complete=($afterEvidence.complete -is [bool] -and $afterEvidence.complete);repo_root=$RepoRoot;
            parser_source_sha256=[string]$request.source_manifest.'automation/orchestration/aios_repo_state_evidence.py';before_paths=@($beforeEvidence.paths);after_paths=@($afterEvidence.paths);errors=$afterErrors}
        $scope=Test-AiOsWorkerOutput -PacketId $request.packet_id -AllowedPaths @($request.allowed_paths) -RepoRoot $RepoRoot -RelayRoot $RelayRoot -LogPath $outputLog -CampaignBinding $binding -BeforeManifest $scopeBefore -ControllerMetadataPaths $metadata -ChangedPathsEvidence $changed -ExpectedStatusParserSha256 $changed.parser_source_sha256 -DiagnosticWriteChoice $ExplicitApplyChoice
        $safety=($process.working_directory -ceq $RepoRoot -and $process.stdin_bytes_written -eq [Text.Encoding]::UTF8.GetByteCount([string]$read.task.prompt_text) -and $process.shape_valid -and $process.cleanup_state -ceq 'CONFIRMED' -and $process.root_exit_confirmed -eq $true -and $process.tree_exit_confirmed -eq $true -and $process.drains_completed -eq $true -and $process.stdin_writer_joined -eq $true)
        if(-not $safety -or $scope.pass -isnot [bool] -or -not $scope.pass){return Write-AiOsBoundObservation $request $binding $task.id 'SAFETY_INTEGRITY_BLOCK' ('PROCESS_OR_SCOPE_UNCONFIRMED:'+ $(if($null -ne $scope.PSObject.Properties['violation_reason']){[string]$scope.violation_reason}else{'MALFORMED_SCOPE_RESULT'})) $executionPath $executionSha -OutputEvidence $scope}
        if($process.exit_code -isnot [int] -or $process.exit_code -ne 0 -or $process.child_exit_code -isnot [int] -or $process.child_exit_code -ne 0 -or -not $process.stdin_completed -or $process.timed_out -or $process.startup_failed -or $process.process_error_present){return Write-AiOsBoundObservation $request $binding $task.id 'EXECUTION_FAILED' 'PROCESS_INPUT_OR_EXIT_FAILED' $executionPath $executionSha -OutputEvidence $scope}
        $diagnosticConfirmed=($null -ne $scope.PSObject.Properties['diagnostic_write_requested'] -and $scope.diagnostic_write_requested -is [bool] -and $scope.diagnostic_write_requested -and $null -ne $scope.PSObject.Properties['diagnostic_write_completed'] -and $scope.diagnostic_write_completed -is [bool] -and $scope.diagnostic_write_completed -and $null -ne $scope.PSObject.Properties['diagnostic_write_error'] -and $scope.diagnostic_write_error -is [string] -and $scope.diagnostic_write_error -ceq '')
        if(-not $diagnosticConfirmed){return Write-AiOsBoundObservation $request $binding $task.id 'FINALIZATION_RECONCILIATION_REQUIRED' 'OUTPUT_DIAGNOSTIC_WRITE_UNCONFIRMED' $executionPath $executionSha -OutputEvidence $scope -PendingAction 'RECONCILE_DIAGNOSTIC_WITH_CAPTURE_NO_REPLAY'}
        $null=Add-AiOsBoundCost $request $binding $ledger $providerRun
        return Write-AiOsBoundObservation $request $binding $task.id 'EXECUTED_AWAITING_VALIDATION' 'INDEPENDENT_ACCEPTANCE_REQUIRED' $executionPath $executionSha
    } catch {
        if($null -eq $request -or $null -eq $binding){return [pscustomobject]@{status='REQUEST_REJECTED';reason='UNTRUSTED_REQUEST';authority_granted=$false;retry_allowed=$false}}
        $reason=$_.Exception.Message
        if(-not $identityVerified){
            $reject=[ordered]@{status='REQUEST_REJECTED';reason=$reason;authority_granted=$false;retry_allowed=$false}
            foreach($name in $binding.Keys){$reject[$name]=$binding[$name]};return [pscustomobject]$reject
        }
        $status=if($captured -or $launchObserved){'FINALIZATION_RECONCILIATION_REQUIRED'}else{'REQUEST_REJECTED'}
        return Write-AiOsBoundObservation $request $binding $task.id $status $reason $executionPath $executionSha -PendingCapture $pendingCapture -PendingAction $(if($launchObserved){'RECONCILE_CAPTURED_OR_UNCONFIRMED_EXECUTION_NO_REPLAY'}else{''})
    }
}

if ($BoundProfile) {
    [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
    if (-not $Apply -or $Watch -or $Report -or $MaxPackets -ne 0 -or -not $RepoRoot -or -not $RelayRoot -or -not $RequestPath -or -not $ExpectedPacketSha256 -or -not $PythonExecutable) {
        [Console]::WriteLine('{"status":"REQUEST_REJECTED","reason":"EXACT_APPLY_REQUEST_REQUIRED","authority_granted":false}');exit 2
    }
    $answer=Invoke-AiOsBoundRelayRequest -RepoRoot $RepoRoot -RelayRoot $RelayRoot -RequestPath $RequestPath -ExpectedPacketSha256 $ExpectedPacketSha256 -PythonExecutable $PythonExecutable -ExplicitApplyChoice ([bool]$Apply.IsPresent)
    [Console]::WriteLine(($answer|ConvertTo-Json -Depth 30 -Compress));exit 0
}
Import-AiOsRelayRunnerHelpers
Initialize-AiOsRelayWorkerFolders

$preflight = & "$PSScriptRoot\..\preflight\Test-AiOsToolPreflight.ps1"
if (-not $preflight.ok) {
    Write-AiOsRelayLog "PREFLIGHT_FAILED missing=$($preflight.missing -join ',') unauth=$($preflight.unauth -join ',')"
    $notify = Join-Path $RepoRoot "automation\orchestration\notifications\Send-AiOsNotification.ps1"
    if (Test-Path -LiteralPath $notify -PathType Leaf) { & powershell -NoProfile -ExecutionPolicy Bypass -File $notify -Message "PREFLIGHT_FAILED missing=$($preflight.missing -join ',') unauth=$($preflight.unauth -join ',')" -Severity "CRITICAL" -Subject "AI_OS BLOCKER" -Apply | Out-Null }
    exit 2
}

$script:ProcessedPackets = 0
Write-AiOsRelayLog ("[WORKER] start Apply={0} Watch={1} MaxPackets={2} Report={3}" -f [bool]$Apply, [bool]$Watch, $MaxPackets, [bool]$Report)

do {
    if (Test-Path -LiteralPath $StopFlagPath -PathType Leaf) {
        Write-AiOsRelayLog "[WORKER] STOP_FLAG_PRESENT path=$StopFlagPath"
        break
    }

    [void](Invoke-AiOsRelayWorkerPass)

    if ($MaxPackets -gt 0 -and $script:ProcessedPackets -ge $MaxPackets) {
        break
    }

    if ($Watch) {
        Start-Sleep -Seconds $IntervalSeconds
    }
} while ($Watch)

if ($Report) {
    [void](New-AiOsRelayWorkerReport)
}

Write-AiOsRelayLog ("[WORKER] stop processed={0}" -f $script:ProcessedPackets)
Write-Host "Commit performed: NO"
Write-Host "Push performed: NO"
