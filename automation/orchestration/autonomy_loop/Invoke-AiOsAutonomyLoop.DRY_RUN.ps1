param(
    [Parameter(Mandatory = $true)]
    [string]$GoalText,

    [string]$PacketDirectory = "Reports/autonomy_loop/proposed",
    [string]$AutonomyReportDirectory = "Reports/autonomy_loop",
    [string]$PacketRunnerOutputPath,
    [string]$PacketRunnerReportPath,

    [string]$ValidatorScriptPath = "automation/validators/aios_governance_validator.py",
    [string]$PacketRunnerScriptPath = "automation/orchestration/packet_runner/Invoke-AiOsPacketAutoRunner.DRY_RUN.ps1",
    [switch]$PassThrough
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Get-AiOsRepoRoot {
    $root = (& git rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $root) {
        throw "REVIEW_REQUIRED: Unable to resolve repository root."
    }
    return $root.Trim()
}

function Get-AiOsSafeName {
    param([Parameter(Mandatory = $true)][string]$Text)

    $normalized = $Text.ToLowerInvariant() -replace "[^a-z0-9]", "-"
    $normalized = ($normalized -replace "-+", "-").Trim("-")
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return "goal"
    }
    return $normalized.Substring(0, [Math]::Min(48, $normalized.Length))
}

function New-AiOsPacketId {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
    return "AIOS-AUTONOMY-LOOP-$stamp"
}

function Test-AiOsSafePacketText {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) {
        throw "REVIEW_REQUIRED: GoalText cannot be empty."
    }
}

function Resolve-AiOsPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return [string]::Empty
    }

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }

    return [System.IO.Path]::Combine($RepoRoot, $Path)
}

function Write-JsonAtomic {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)]$Object)

    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $tmp = Join-Path $directory ([guid]::NewGuid().ToString("N") + ".tmp")
    $objectJson = $Object | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($tmp, $objectJson + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Force
    }
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

function Invoke-AiOsCommandCapture {
    param(
        [string]$Command,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Command
    $psi.Arguments = ($Arguments -join " ")
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true

    $process = [Diagnostics.Process]::Start($psi)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        StdOut = $stdout
        StdErr = $stderr
    }
}

try {
    $repoRoot = Get-AiOsRepoRoot
    Set-Location -Path $repoRoot

    Test-AiOsSafePacketText -Text $GoalText

    $createdAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $packetId = New-AiOsPacketId
    $packetName = "${packetId}_GOAL.md"
    $packetDirectory = Resolve-AiOsPath -Path $PacketDirectory -RepoRoot $repoRoot
    $reportDirectory = Resolve-AiOsPath -Path $AutonomyReportDirectory -RepoRoot $repoRoot
    $packetPath = Join-Path $packetDirectory $packetName
    New-Item -ItemType Directory -Path $packetDirectory -Force | Out-Null

    $packetText = @"
CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN: OPERATOR_APPROVES_AUTONOMY_LOOP_V0_DRY_RUN
AI_OS BOOTSTRAP REQUIRED: OPERATOR_REVIEW_REQUIRED_BEFORE_APPLY

AUTHORITY FILES:
Read first. Do not modify.
- AGENTS.md
- README.md
- WHITEPAPER.md

IDENTITY MARKER: AIOS-AUTONOMY-LOOP-V0
SUPERVISOR IDENTITY: ChatGPT supervisor/planner

PACKET ID: $packetId
MODE: DRY_RUN_FIRST

ZONE: autonomy_loop
WORKER IDENTITY: Codex East
LANE: AIOS_AUTONOMY_LOOP_V0
WORKTREE: $repoRoot
BRANCH: $(git branch --show-current)

ALLOWED PATHS:
- automation/orchestration/autonomy_loop/
- automation/orchestration/packet_runner/
- automation/orchestration/work_packets/proposed/

FORBIDDEN PATHS:
- AGENTS.md
- README.md
- WHITEPAPER.md
- secrets/
- credentials/
- broker/
- live_trading/
- OANDA/
- .env
- any protected external connector credential path

APPROVAL AUTHORITY:
Anthony is approval authority.
Codex may edit allowed paths only.
No production trading enablement.
No external connector enablement.
No secrets.
No real orders.
No protected repository promotion.

MISSION:
Goal intake for: $($GoalText.Trim())

1. Intake high-level goal as packet context.
2. Generate a single Codex-ready packet proposal with the goal embedded.
3. Run governance validation on the generated packet.
4. Run packet auto-runner in DRY_RUN mode.
5. Emit a JSON report.
6. Stop before any APPLY, protected repository promotion, or production-risk gate.

PREFLIGHT:
- pwd
- git status --short --branch
- git branch --show-current
- git remote -v

VALIDATOR CHAIN:
- python automation/validators/aios_governance_validator.py --input $packetPath
- python -m pytest tests/orchestration/test_packet_auto_runner.py

STOP POINT:
Stop if governance validator fails.

SAFE NEXT ACTION:
Run the generated packet through the packet auto-runner in DRY_RUN mode only.

FINAL REPORT FORMAT:
SUMMARY:
GOAL:
PROPOSAL PATH:
VALIDATION:
AUTORUNNER:
NEXT SAFE COMMAND:
STATUS:
"@

    $packetPathTmp = Join-Path $packetDirectory ("$packetId.tmp")
    [System.IO.File]::WriteAllText($packetPathTmp, $packetText, [Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $packetPath) {
        Remove-Item -LiteralPath $packetPath -Force
    }
    Move-Item -LiteralPath $packetPathTmp -Destination $packetPath -Force

    $validatorCommand = @("python", $ValidatorScriptPath, "--input", $packetPath)
    $validatorResult = Invoke-AiOsCommandCapture -Command "python" -Arguments $validatorCommand[1..($validatorCommand.Count - 1)] -WorkingDirectory $repoRoot

    if ($validatorResult.ExitCode -ne 0) {
        $failureReport = [ordered]@{
            created_at_utc = $createdAt
            goal = $GoalText
            packet_id = $packetId
            packet_path = $packetPath
            validator_status = "FAILED"
            validator_exit_code = $validatorResult.ExitCode
            validator_stdout = $validatorResult.StdOut
            validator_stderr = $validatorResult.StdErr
            auto_runner_status = "SKIPPED"
            report_path = $null
            created_by = "Invoke-AiOsAutonomyLoop.DRY_RUN.ps1"
            blocked = $true
        }
            $fallbackReport = Resolve-AiOsPath -Path (Join-Path $AutonomyReportDirectory "$packetId.report.json") -RepoRoot $repoRoot
            Write-JsonAtomic -Path $fallbackReport -Object $failureReport
            Write-Error "REVIEW_REQUIRED: governance validation failed. Run report: $fallbackReport"
            exit 1
    }

    if ([string]::IsNullOrWhiteSpace($PacketRunnerOutputPath)) {
        $PacketRunnerOutputPath = Resolve-AiOsPath -Path (Join-Path $AutonomyReportDirectory "$($packetName.Replace('.md', '.full_packet.md'))") -RepoRoot $repoRoot
    }

    if ([string]::IsNullOrWhiteSpace($PacketRunnerReportPath)) {
        $PacketRunnerReportPath = Resolve-AiOsPath -Path (Join-Path $AutonomyReportDirectory "$($packetName.Replace('.md', '.auto_runner.report.json'))") -RepoRoot $repoRoot
    }

    $runnerCommand = @("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PacketRunnerScriptPath, "-PacketPath", $packetPath, "-OutputPath", $PacketRunnerOutputPath, "-ReportPath", $PacketRunnerReportPath)
    $runnerResult = Invoke-AiOsCommandCapture -Command $runnerCommand[0] -Arguments $runnerCommand[1..($runnerCommand.Count - 1)] -WorkingDirectory $repoRoot

    if ($runnerResult.ExitCode -ne 0) {
        $failureReport = [ordered]@{
            created_at_utc = $createdAt
            goal = $GoalText
            packet_id = $packetId
            packet_path = $packetPath
            validator_status = "PASS"
            validator_exit_code = $validatorResult.ExitCode
            validator_stdout = $validatorResult.StdOut
            validator_stderr = $validatorResult.StdErr
            auto_runner_status = "FAILED"
            auto_runner_exit_code = $runnerResult.ExitCode
            auto_runner_stdout = $runnerResult.StdOut
            auto_runner_stderr = $runnerResult.StdErr
            report_path = $null
            created_by = "Invoke-AiOsAutonomyLoop.DRY_RUN.ps1"
            blocked = $true
        }
        $fallbackReport = Resolve-AiOsPath -Path (Join-Path $AutonomyReportDirectory "$packetId.report.json") -RepoRoot $repoRoot
        Write-JsonAtomic -Path $fallbackReport -Object $failureReport
        Write-Error "REVIEW_REQUIRED: packet auto-runner failed. Run report: $fallbackReport"
        exit 1
    }

    $autoRunnerStatus = [ordered]@{
        status = "PASS"
        exit_code = $runnerResult.ExitCode
        stdout = $runnerResult.StdOut
        stderr = $runnerResult.StdErr
    }

    $finalReport = [ordered]@{
        schema = "AIOS_AUTONOMY_LOOP_REPORT_V1"
        created_at_utc = $createdAt
        goal = $GoalText
        packet_id = $packetId
        packet_path = $packetPath
        report_output_path = $PacketRunnerReportPath
        packet_output_path = $PacketRunnerOutputPath
        validator_status = "PASS"
        validator_exit_code = $validatorResult.ExitCode
        auto_runner_status = "PASS"
        auto_runner = $autoRunnerStatus
        blocked_actions = @(
            "protected_repository_promotion",
            "apply",
            "live_trading",
            "external_connector_enablement",
            "secret_reads",
            "commit"
        )
        created_by = "Invoke-AiOsAutonomyLoop.DRY_RUN.ps1"
        blocked = $false
    }

    $finalReportPath = Resolve-AiOsPath -Path (Join-Path $AutonomyReportDirectory "$packetId.autonomy_report.json") -RepoRoot $repoRoot
    Write-JsonAtomic -Path $finalReportPath -Object $finalReport

    if ($PassThrough) {
        Write-Output ($finalReport | ConvertTo-Json -Depth 20)
    } else {
        Write-Output "Autonomy loop dry-run complete."
        Write-Output "Packet: $packetPath"
        Write-Output "Report: $finalReportPath"
    }

    exit 0
} catch {
    Write-Error "REVIEW_REQUIRED: $($_.Exception.Message)"
    exit 1
}
