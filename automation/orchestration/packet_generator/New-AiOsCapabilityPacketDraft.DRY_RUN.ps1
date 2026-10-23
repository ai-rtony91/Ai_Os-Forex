param(
    [string]$CapabilityName = "",
    [string]$CapabilityIntent = "",
    [string]$TargetActor = "",
    [string]$SuggestedZone = "",
    [string]$SuggestedLane = "",
    [ValidateSet("DRY_RUN", "APPLY")]
    [string]$Mode = "DRY_RUN",
    [string]$Worktree = "C:\Dev\Ai.Os",
    [string]$MissionId = "", [string]$MissionName = "",
    [string]$ProgramId = "", [string]$ProgramName = "",
    [string]$EpicId = "", [string]$EpicName = "",
    [string]$BucketId = "", [string]$BucketName = "",
    [string]$LockIdentity = "",
    [switch]$OutputJson,
    [switch]$AsPromptBlock
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Mode -ne "DRY_RUN") {
    Write-Warning "Mode must stay DRY_RUN for capability draft generation. Forcing Mode=DRY_RUN."
}

$Mode = "DRY_RUN"

$ScriptRoot = $PSScriptRoot
$RepoRoot = if ([string]::IsNullOrWhiteSpace($Worktree)) { (Get-Location).Path } else { $Worktree }
$GeneratorScript = Join-Path $ScriptRoot "New-AiOsCodexPacket.DRY_RUN.ps1"
$ValidatorScript = Join-Path $ScriptRoot "Test-AiOsCodexPacket.DRY_RUN.ps1"
$ActorRegistryPath = Join-Path (Join-Path $RepoRoot "control/relay_bus/actors") "AIOS_RELAY_ACTORS.json"

function Get-SafeSlug {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "capability"
    }

    $clean = [regex]::Replace($Value.ToLowerInvariant(), "[^a-z0-9]+", "-")
    $clean = $clean.Trim("-")
    if ([string]::IsNullOrWhiteSpace($clean)) {
        return "capability"
    }
    return $clean
}

function Load-RelayActors {
    if (-not (Test-Path -LiteralPath $ActorRegistryPath -PathType Leaf)) {
        return @()
    }

    try {
        $raw = Get-Content -LiteralPath $ActorRegistryPath -Raw -Encoding UTF8
        $json = $raw | ConvertFrom-Json
        return @($json.actors)
    }
    catch {
        return @()
    }
}

function Is-KnownActor {
    param([string]$ActorId)

    if ([string]::IsNullOrWhiteSpace($ActorId)) {
        return $false
    }

    foreach ($item in $actors) {
        if ([string]$item.actor_id -eq $ActorId) {
            return $true
        }
    }

    return $false
}

function Resolve-Defaults {
    param([string]$CapabilityType)

    switch ($CapabilityType) {
        "local_code" {
            return [ordered]@{
                Zone = if ($SuggestedZone) { $SuggestedZone } else { "SELF_EXTENSION" }
                Lane = if ($SuggestedLane) { $SuggestedLane } else { "PACKET_GENERATOR" }
                ReadFirst = @(
                    "AGENTS.md"
                    "README.md"
                    "RISK_POLICY.md"
                    "docs/governance/source-of-truth-map.md"
                    "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1"
                )
                AllowedMutationFiles = @(
                    "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/Test-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/New-AiOsCapabilityPacketDraft.DRY_RUN.ps1"
                    "tests/orchestration/test_codex_packet_generator.py"
                    "tests/orchestration/test_capability_packet_draft.py"
                    "docs/AI_OS/autonomy/AIOS_CODEX_PACKET_GENERATOR_V1.md"
                    "docs/AI_OS/autonomy/AIOS_SELF_EXTENSION_PACKET_GENERATOR_V1.md"
                )
                ForbiddenPaths = @(
                    "broker/OANDA/webhook/order/secrets paths"
                    "runtime state"
                    "scheduler"
                    "daemon"
                    "worker launch"
                    "queue"
                    "locks"
                    "approval inbox"
                    "telemetry"
                    "backup"
                    "dashboard"
                )
                Validators = @(
                    "python -m pytest tests/orchestration/test_codex_packet_generator.py -q -p no:cacheprovider"
                    "python -m pytest tests/orchestration/test_capability_packet_draft.py -q -p no:cacheprovider"
                    "powershell -NoProfile -ExecutionPolicy Bypass -File .\aios.ps1 -Mode status"
                )
            }
        }

        "cli_tool" {
            return [ordered]@{
                Zone = if ($SuggestedZone) { $SuggestedZone } else { "ORCHESTRATION" }
                Lane = if ($SuggestedLane) { $SuggestedLane } else { "CAPABILITY_TO_PACKET_GENERATOR" }
                ReadFirst = @(
                    "AGENTS.md"
                    "README.md"
                    "RISK_POLICY.md"
                    "docs/governance/source-of-truth-map.md"
                )
                AllowedMutationFiles = @(
                    "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/Test-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/New-AiOsCapabilityPacketDraft.DRY_RUN.ps1"
                    "tests/orchestration/test_codex_packet_generator.py"
                    "tests/orchestration/test_capability_packet_draft.py"
                    "docs/AI_OS/autonomy/AIOS_CODEX_PACKET_GENERATOR_V1.md"
                    "docs/AI_OS/autonomy/AIOS_SELF_EXTENSION_PACKET_GENERATOR_V1.md"
                )
                ForbiddenPaths = @(
                    "broker/OANDA/webhook/order/secrets paths"
                    "runtime state"
                    "scheduler"
                    "daemon"
                    "approval inbox"
                    "queue"
                    "locks"
                    "worker launch"
                    "telemetry"
                    "dashboard"
                    "backup"
                )
                Validators = @(
                    "python -m pytest tests/orchestration/test_capability_packet_draft.py -q -p no:cacheprovider"
                    "python -m pytest tests/orchestration/test_codex_packet_generator.py -q -p no:cacheprovider"
                    "powershell -NoProfile -ExecutionPolicy Bypass -File .\aios.ps1 -Mode status"
                )
            }
        }

        "saas_api" {
            return [ordered]@{
                Zone = if ($SuggestedZone) { $SuggestedZone } else { "SELF_EXTENSION" }
                Lane = if ($SuggestedLane) { $SuggestedLane } else { "CAPABILITY_TO_PACKET_GENERATOR" }
                ReadFirst = @(
                    "AGENTS.md"
                    "README.md"
                    "RISK_POLICY.md"
                    "docs/governance/source-of-truth-map.md"
                )
                AllowedMutationFiles = @(
                    "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/Test-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/New-AiOsCapabilityPacketDraft.DRY_RUN.ps1"
                    "tests/orchestration/test_codex_packet_generator.py"
                    "tests/orchestration/test_capability_packet_draft.py"
                    "docs/AI_OS/autonomy/AIOS_CODEX_PACKET_GENERATOR_V1.md"
                    "docs/AI_OS/autonomy/AIOS_SELF_EXTENSION_PACKET_GENERATOR_V1.md"
                )
                ForbiddenPaths = @(
                    "broker/OANDA/webhook/order/secrets paths"
                    "real market data paths"
                    "runtime state"
                    "scheduler"
                    "daemon"
                    "approval inbox"
                    "queue"
                    "locks"
                    "telemetry"
                    "dashboard"
                    "secret_or_api_key_load"
                    "backup"
                )
                Validators = @(
                    "python -m pytest tests/orchestration/test_capability_packet_draft.py -q -p no:cacheprovider"
                    "python -m pytest tests/orchestration/test_codex_packet_generator.py -q -p no:cacheprovider"
                    "powershell -NoProfile -ExecutionPolicy Bypass -File .\aios.ps1 -Mode status"
                )
            }
        }

        "browser_ui" {
            return [ordered]@{
                Zone = if ($SuggestedZone) { $SuggestedZone } else { "SELF_EXTENSION" }
                Lane = if ($SuggestedLane) { $SuggestedLane } else { "CAPABILITY_TO_PACKET_GENERATOR" }
                ReadFirst = @(
                    "AGENTS.md"
                    "README.md"
                    "RISK_POLICY.md"
                    "docs/governance/source-of-truth-map.md"
                )
                AllowedMutationFiles = @(
                    "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/Test-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/New-AiOsCapabilityPacketDraft.DRY_RUN.ps1"
                    "tests/orchestration/test_codex_packet_generator.py"
                    "tests/orchestration/test_capability_packet_draft.py"
                    "docs/AI_OS/autonomy/AIOS_CODEX_PACKET_GENERATOR_V1.md"
                    "docs/AI_OS/autonomy/AIOS_SELF_EXTENSION_PACKET_GENERATOR_V1.md"
                )
                ForbiddenPaths = @(
                    "broker/OANDA/webhook/order/secrets paths"
                    "runtime state"
                    "scheduler"
                    "daemon"
                    "worker launch"
                    "queue"
                    "locks"
                    "approval inbox"
                    "telemetry"
                    "backup"
                )
                Validators = @(
                    "python -m pytest tests/orchestration/test_capability_packet_draft.py -q -p no:cacheprovider"
                    "python -m pytest tests/orchestration/test_codex_packet_generator.py -q -p no:cacheprovider"
                    "powershell -NoProfile -ExecutionPolicy Bypass -File .\aios.ps1 -Mode status"
                )
            }
        }

        "file_bridge" {
            return [ordered]@{
                Zone = if ($SuggestedZone) { $SuggestedZone } else { "SELF_EXTENSION" }
                Lane = if ($SuggestedLane) { $SuggestedLane } else { "FILE_BRIDGE" }
                ReadFirst = @(
                    "AGENTS.md"
                    "README.md"
                    "RISK_POLICY.md"
                    "docs/governance/source-of-truth-map.md"
                )
                AllowedMutationFiles = @(
                    "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/Test-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/New-AiOsCapabilityPacketDraft.DRY_RUN.ps1"
                    "tests/orchestration/test_codex_packet_generator.py"
                    "tests/orchestration/test_capability_packet_draft.py"
                    "docs/AI_OS/autonomy/AIOS_CODEX_PACKET_GENERATOR_V1.md"
                    "docs/AI_OS/autonomy/AIOS_SELF_EXTENSION_PACKET_GENERATOR_V1.md"
                )
                ForbiddenPaths = @(
                    "broker/OANDA/webhook/order/secrets paths"
                    "runtime state"
                    "scheduler"
                    "daemon"
                    "worker launch"
                    "queue"
                    "locks"
                    "approval inbox"
                    "telemetry"
                    "dashboard"
                    "backup"
                )
                Validators = @(
                    "python -m pytest tests/orchestration/test_capability_packet_draft.py -q -p no:cacheprovider"
                    "python -m pytest tests/orchestration/test_codex_packet_generator.py -q -p no:cacheprovider"
                    "powershell -NoProfile -ExecutionPolicy Bypass -File .\aios.ps1 -Mode status"
                )
            }
        }

        "game_engine" {
            return [ordered]@{
                Zone = if ($SuggestedZone) { $SuggestedZone } else { "GAME_ENGINE" }
                Lane = if ($SuggestedLane) { $SuggestedLane } else { "GAME_ENGINE_FILE_BRIDGE" }
                ReadFirst = @(
                    "AGENTS.md"
                    "README.md"
                    "RISK_POLICY.md"
                    "docs/governance/source-of-truth-map.md"
                    "docs/AI_OS/autonomy/AIOS_RELAY_OPERATOR_MODE_V1.md"
                    "docs/AI_OS/autonomy/AIOS_ACTOR_RELAY_BUS_V1.md"
                )
                AllowedMutationFiles = @(
                    "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/Test-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/New-AiOsCapabilityPacketDraft.DRY_RUN.ps1"
                    "tests/orchestration/test_codex_packet_generator.py"
                    "tests/orchestration/test_capability_packet_draft.py"
                    "docs/AI_OS/autonomy/AIOS_CODEX_PACKET_GENERATOR_V1.md"
                    "docs/AI_OS/autonomy/AIOS_SELF_EXTENSION_PACKET_GENERATOR_V1.md"
                )
                ForbiddenPaths = @(
                    "broker/OANDA/webhook/order/secrets paths"
                    "runtime state"
                    "scheduler"
                    "daemon"
                    "worker launch"
                    "queue"
                    "locks"
                    "approval inbox"
                    "telemetry"
                    "dashboard"
                    "backup"
                )
                Validators = @(
                    "python -m pytest tests/orchestration/test_capability_packet_draft.py -q -p no:cacheprovider"
                    "python -m pytest tests/orchestration/test_codex_packet_generator.py -q -p no:cacheprovider"
                    "powershell -NoProfile -ExecutionPolicy Bypass -File .\aios.ps1 -Mode status"
                )
            }
        }

        "devops" {
            return [ordered]@{
                Zone = if ($SuggestedZone) { $SuggestedZone } else { "SELF_EXTENSION" }
                Lane = if ($SuggestedLane) { $SuggestedLane } else { "CAPABILITY_TO_PACKET_GENERATOR" }
                ReadFirst = @(
                    "AGENTS.md"
                    "README.md"
                    "RISK_POLICY.md"
                    "docs/governance/source-of-truth-map.md"
                )
                AllowedMutationFiles = @(
                    "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/Test-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/New-AiOsCapabilityPacketDraft.DRY_RUN.ps1"
                    "tests/orchestration/test_codex_packet_generator.py"
                    "tests/orchestration/test_capability_packet_draft.py"
                    "docs/AI_OS/autonomy/AIOS_CODEX_PACKET_GENERATOR_V1.md"
                    "docs/AI_OS/autonomy/AIOS_SELF_EXTENSION_PACKET_GENERATOR_V1.md"
                )
                ForbiddenPaths = @(
                    "broker/OANDA/webhook/order/secrets paths"
                    "runtime state"
                    "worker launch"
                    "queue"
                    "locks"
                    "approval inbox"
                    "dashboard"
                    "backup"
                    "Cloudflare"
                )
                Validators = @(
                    "python -m pytest tests/orchestration/test_capability_packet_draft.py -q -p no:cacheprovider"
                    "python -m pytest tests/orchestration/test_codex_packet_generator.py -q -p no:cacheprovider"
                    "powershell -NoProfile -ExecutionPolicy Bypass -File .\aios.ps1 -Mode status"
                )
                }
        }

        "broker_sandbox" {
            return [ordered]@{
                Zone = if ($SuggestedZone) { $SuggestedZone } else { "ORCHESTRATION" }
                Lane = if ($SuggestedLane) { $SuggestedLane } else { "CAPABILITY_TO_PACKET_GENERATOR" }
                ReadFirst = @(
                    "AGENTS.md"
                    "README.md"
                    "RISK_POLICY.md"
                    "docs/governance/source-of-truth-map.md"
                    "docs/AI_OS/autonomy/AIOS_CODEX_PACKET_GENERATOR_V1.md"
                )
                AllowedMutationFiles = @(
                    "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/Test-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/New-AiOsCapabilityPacketDraft.DRY_RUN.ps1"
                    "tests/orchestration/test_codex_packet_generator.py"
                    "tests/orchestration/test_capability_packet_draft.py"
                    "docs/AI_OS/autonomy/AIOS_CODEX_PACKET_GENERATOR_V1.md"
                    "docs/AI_OS/autonomy/AIOS_SELF_EXTENSION_PACKET_GENERATOR_V1.md"
                )
                ForbiddenPaths = @(
                    "broker/OANDA/webhook/order/secrets paths"
                    "real market data paths"
                    "live_market_data_fetch"
                    "real_order_submission"
                    "secret_or_api_key_load"
                    "worker launch"
                    "scheduler"
                    "daemon"
                    "runtime state"
                    "approval inbox"
                    "queue"
                    "locks"
                    "telemetry"
                    "dashboard"
                    "backup"
                )
                Validators = @(
                    "python -m pytest tests/orchestration/test_capability_packet_draft.py -q -p no:cacheprovider"
                    "python -m pytest tests/orchestration/test_codex_packet_generator.py -q -p no:cacheprovider"
                    "powershell -NoProfile -ExecutionPolicy Bypass -File .\aios.ps1 -Mode status"
                )
            }
        }

        default {
            return [ordered]@{
                Zone = if ($SuggestedZone) { $SuggestedZone } else { "SELF_EXTENSION" }
                Lane = if ($SuggestedLane) { $SuggestedLane } else { "CAPABILITY_TO_PACKET_GENERATOR" }
                ReadFirst = @(
                    "AGENTS.md"
                    "README.md"
                    "RISK_POLICY.md"
                    "docs/governance/source-of-truth-map.md"
                )
                AllowedMutationFiles = @(
                    "automation/orchestration/packet_generator/New-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/Test-AiOsCodexPacket.DRY_RUN.ps1"
                    "automation/orchestration/packet_generator/New-AiOsCapabilityPacketDraft.DRY_RUN.ps1"
                    "tests/orchestration/test_codex_packet_generator.py"
                    "tests/orchestration/test_capability_packet_draft.py"
                    "docs/AI_OS/autonomy/AIOS_CODEX_PACKET_GENERATOR_V1.md"
                    "docs/AI_OS/autonomy/AIOS_SELF_EXTENSION_PACKET_GENERATOR_V1.md"
                )
                ForbiddenPaths = @(
                    "broker/OANDA/webhook/order/secrets paths"
                    "runtime state"
                    "scheduler"
                    "daemon"
                    "worker launch"
                    "queue"
                    "locks"
                    "approval inbox"
                    "telemetry"
                    "dashboard"
                    "backup"
                    "Cloudflare"
                )
                Validators = @(
                    "python -m pytest tests/orchestration/test_capability_packet_draft.py -q -p no:cacheprovider"
                    "python -m pytest tests/orchestration/test_codex_packet_generator.py -q -p no:cacheprovider"
                    "powershell -NoProfile -ExecutionPolicy Bypass -File .\aios.ps1 -Mode status"
                )
            }
        }
    }
}

function Classify-Capability {
    param([string]$Name, [string]$Intent, [string]$ActorHint)

    $probe = @($Name, $Intent) -join " "
    $probeLower = $probe.ToLowerInvariant()
    $actorHintLower = $ActorHint.ToLowerInvariant()

    if ($actorHintLower -eq "claude_code" -or $actorHintLower -eq "claude code" -or $probeLower -match "claude\s*code") {
        return @("cli_tool", "DRY_RUN_ONLY", "claude_code")
    }

    if ($probeLower -match "ue5|unreal\s*5|unreal\s+engine|game\s+engine" -or $actorHintLower -eq "unreal_engine_5") {
        return @("game_engine", "DRY_RUN_ONLY", "unreal_engine_5")
    }

    if ($probeLower -match "broker|oanda|live|trading|order|sandbox") {
        return @("broker_sandbox", "REQUIRES_SECRET_REVIEW", "aios_relay")
    }

    if ($actorHintLower -eq "openai_cli" -or $probeLower -match "notion|openai|third[- ]?party|saas|api|http|webhook|service") {
        return @("saas_api", "DRY_RUN_ONLY", "openai_cli")
    }

    if ($actorHintLower -eq "github_actions" -or $probeLower -match "github actions|pipeline|ci|build|deploy") {
        return @("devops", "DRY_RUN_ONLY", "github_actions")
    }

    if ($probeLower -match "browser|ui|frontend|web|inspect.*page") {
        return @("browser_ui", "DRY_RUN_ONLY", "codex_cli")
    }

    if ($probeLower -match "file|path|build\s+log|parse\s+logs|artifact|bridge|bridge\s+file|log") {
        return @("file_bridge", "DRY_RUN_ONLY", "codex_cli")
    }

    if ($actorHintLower -eq "powershell_operator" -or $actorHintLower -eq "codex_cli" -or $actorHintLower -eq "chatgpt_supervisor" -or $actorHintLower -eq "aios_relay") {
        return @("cli_tool", "DRY_RUN_ONLY", $actorHintLower)
    }

    if ($probeLower -match "cli|command|powershell|tool|operator|terminal") {
        return @("cli_tool", "DRY_RUN_ONLY", "codex_cli")
    }

    if ($probeLower -match "destructive|payment|delete|destroy|erase|wipe|wipe|system") {
        return @("unknown", "BLOCKED_HIGH_RISK", "unknown_actor")
    }

    if ($probeLower -match "module|package|code|script|local|class|function") {
        return @("local_code", "SCOPED_APPLY", "codex_cli")
    }

    return @("unknown", "DRY_RUN_ONLY", "unknown_actor")
}

$actors = Load-RelayActors

$nameText = if ([string]::IsNullOrWhiteSpace($CapabilityName)) { "Unnamed Capability" } else { $CapabilityName }
$intentText = if ([string]::IsNullOrWhiteSpace($CapabilityIntent)) { "No additional intent provided." } else { $CapabilityIntent }

$classification = Classify-Capability -Name $nameText -Intent $intentText -ActorHint $TargetActor
$capabilityType = [string]$classification[0]
$safetyTier = [string]$classification[1]
$suggestedActor = [string]$classification[2]

if (-not (Is-KnownActor -ActorId $suggestedActor)) {
    $suggestedActor = "unknown_actor"
}
if (-not [string]::IsNullOrWhiteSpace($TargetActor) -and (Is-KnownActor -ActorId $TargetActor)) {
    $suggestedActor = $TargetActor
}

$profile = Resolve-Defaults -CapabilityType $capabilityType
$zone = $profile.Zone
$lane = $profile.Lane
$readFirst = @($profile.ReadFirst)
$allowedMutationFiles = @($profile.AllowedMutationFiles)
$forbiddenPaths = @($profile.ForbiddenPaths)
$validators = @($profile.Validators)

$readFirst = @($readFirst + "docs/AI_OS/autonomy/AIOS_SELF_EXTENSION_PACKET_GENERATOR_V1.md") | Select-Object -Unique
$safeReadFirst = @($readFirst)
$safeAllowedMutationFiles = @($allowedMutationFiles)
$safeForbidden = @($forbiddenPaths)

$slug = Get-SafeSlug -Value ("{0} {1}" -f $nameText, $intentText)
$generatedPacketId = "AIOS-CAPABILITY-{0}-{1}" -f $capabilityType.ToUpperInvariant(), $slug.ToUpperInvariant()
if ($generatedPacketId.Length -gt 120) {
    $generatedPacketId = $generatedPacketId.Substring(0, 120)
}

$safeMission = "Draft AGENTS-compliant packet for {0} capability: {1}" -f $capabilityType, $nameText
$stopPoint = "Review this draft packet. Keep execution in human approval flow and do not execute any integration path."
if ($safetyTier -eq "BLOCKED_HIGH_RISK") {
    $stopPoint = "BLOCKED_HIGH_RISK: produce research packet only and stop for manual review before any integration path."
}
elseif ($safetyTier -eq "REQUIRES_SECRET_REVIEW") {
    $stopPoint = "No live integration. Draft must stay research-only until separate secret-risk review is complete."
}
elseif ($safetyTier -eq "DRY_RUN_ONLY") {
    $stopPoint = "Research/scaffold packet only. Keep execution path in human review."
}

$branchSuffix = Get-SafeSlug -Value $nameText
if ([string]::IsNullOrWhiteSpace($branchSuffix)) {
    $branchSuffix = "capability"
}

$safeApprovalAuthority = "Anthony is the approval authority. This draft grants no approval, integration, network call, or execution rights."
$safeSupervisorIdentity = "ChatGPT Planning Supervisor under Anthony Human Owner"
$safeWorkerIdentity = "Codex CLI local executor inside C:\Dev\Ai.Os"
$exactNextAction = if ($safetyTier -eq "REQUIRES_SECRET_REVIEW" -or $safetyTier -eq "BLOCKED_HIGH_RISK") {
    "Route this RESEARCH draft through explicit risk review before any apply packet is generated."
} else {
    "Run a RESEARCH review of the generated packet through AGENTS-compliant relay flow and review output first."
}

# Read actual branch state. A missing branch stays empty and fails validation.
$observedBranch = ""
try {
    $branchOutput = & git -C $RepoRoot branch --show-current 2>$null
    if ($LASTEXITCODE -eq 0) { $observedBranch = ([string]$branchOutput).Trim() }
}
catch { $observedBranch = "" }
. (Join-Path $ScriptRoot "AiOsCodexPacketContract.ps1")
$packetContract = Get-AiOsCodexPacketContract

$generatorArgs = @{
    MissionId = $MissionId; MissionName = $MissionName
    ProgramId = $ProgramId; ProgramName = $ProgramName
    EpicId = $EpicId; EpicName = $EpicName
    BucketId = $BucketId; BucketName = $BucketName
    PacketName = $nameText
    IdentityMarker = "AIOS_CAPABILITY_RESEARCH_DRAFT"
    LockIdentity = $LockIdentity
    Preflight = @($packetContract.required_repository_state_commands)
    FinalReportFormat = @("SUMMARY", "FILES INSPECTED", "VALIDATION", "UNKNOWNS", "SAFE NEXT ACTION", "STATUS")
    StagingAuthority = "NOT AUTHORIZED."
    CommitAuthority = "NOT AUTHORIZED."
    PushAuthority = "NOT AUTHORIZED."
    PullRequestAuthority = "NOT AUTHORIZED."
    MergeAuthority = "NOT AUTHORIZED."
    PacketId           = $generatedPacketId
    Mode               = "DRY_RUN"
    Zone               = $zone
    Lane               = $lane
    Mission            = $safeMission
    Worktree           = $RepoRoot
    StartBranch        = $observedBranch
    Branch             = $observedBranch
    ApprovalAuthority  = $safeApprovalAuthority
    SupervisorIdentity = $safeSupervisorIdentity
    WorkerIdentity     = $safeWorkerIdentity
    AllowedMutationFiles = $safeAllowedMutationFiles
    ForbiddenPaths      = $safeForbidden
    ReadFirst           = $safeReadFirst
    Validators          = $validators
    StopPoint           = $stopPoint
    OutputJson          = $true
}

$generatedPacketText = ""
$generatorValid = $false
$generatorMissing = @()
$generatorDefects = @()
try {
    $generatedRaw = & $GeneratorScript @generatorArgs
    $generatedJson = $generatedRaw | ConvertFrom-Json -ErrorAction Stop
    $generatorValid = Test-AiOsCodexPacketReport -Report $generatedJson -ExpectedSchema "AIOS_CODEX_PACKET_GENERATOR.v2"
    $generatorMissing = @($generatedJson.missing_required_fields)
    $generatorDefects = @($generatedJson.validation_defects)
    $generatedPacketText = [string]$generatedJson.generated_packet_text
}
catch { $generatorDefects = @("GENERATOR_INVOCATION_ERROR") }

try {
    # Use the current host and the canonical validator. Never replace rejection
    # with the old header-only check, even if the validator is unavailable.
    $validationOutput = & $ValidatorScript -PacketText $generatedPacketText -OutputJson
    $packetValidation = $validationOutput | ConvertFrom-Json -ErrorAction Stop
    if ($null -eq $packetValidation) { throw "EMPTY_VALIDATOR_RESPONSE" }
    $packetValidation.packet_valid = ($generatorValid -and (Test-AiOsCodexPacketReport -Report $packetValidation -ExpectedSchema "AIOS_CODEX_PACKET_VALIDATOR.v2"))
    $packetValidation.missing_required_fields = @($generatorMissing + @($packetValidation.missing_required_fields) | Select-Object -Unique)
    $packetValidation.validation_defects = @($generatorDefects + @($packetValidation.validation_defects) | Select-Object -Unique)
}
catch {
    $packetValidation = @{ packet_valid = $false; missing_required_fields = @($generatorMissing); validation_defects = @($generatorDefects + "VALIDATOR_INVOCATION_ERROR") }
}
if (-not $packetValidation.packet_valid) { $generatedPacketText = "" }

$normalizedMissingFields = @()
if ($null -ne $packetValidation.missing_required_fields) {
    foreach ($field in @($packetValidation.missing_required_fields)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$field)) {
            $normalizedMissingFields += [string]$field
        }
    }
}

$result = [ordered]@{
    schema = "AIOS_CAPABILITY_PACKET_DRAFT.v1"
    capability_name = $nameText
    capability_type = $capabilityType
    safety_tier = $safetyTier
    suggested_actor = $suggestedActor
    generated_packet_id = $generatedPacketId
    generated_packet_text = $generatedPacketText
    packet_valid = if ($packetValidation.packet_valid -eq $true) { $true } else { $false }
    execution_allowed = $false
    can_continue_without_anthony = $false
    requires_human_review = $true
    exact_next_action = $exactNextAction
    reads_input = $intentText
    writes_files = $false
    mode = "DRY_RUN"
    suggested_zone = $zone
    suggested_lane = $lane
    read_first = @($safeReadFirst)
    allowed_mutation_files = @($safeAllowedMutationFiles)
    forbidden_paths = @($safeForbidden)
    validators = @($validators)
    stop_point = $stopPoint
    missing_required_fields = @($normalizedMissingFields)
    validation_defects = @($packetValidation.validation_defects)
}

if ($AsPromptBlock -and $packetValidation.packet_valid) {
    Write-Output $generatedPacketText
    exit 0
}

Write-Output ($result | ConvertTo-Json -Depth 20)
exit 0
