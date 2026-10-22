[CmdletBinding()]
param(
    [string]$ConfigPath = "automation/orchestration/validators/VALIDATOR_CHAIN_CONFIG_001.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-AiOsRepoRoot {
    $root = & git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($root)) {
        throw "Unable to find git repository root."
    }

    return $root.Trim()
}

function ConvertTo-AiOsRelativePath {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ""
    }

    return ($Path -replace "\\", "/").TrimStart([char[]]@("/", "."))
}

function Get-AiOsPropertyValue {
    param(
        [object]$InputObject,
        [string[]]$Names,
        [object]$DefaultValue = $null
    )

    foreach ($name in $Names) {
        if ($InputObject.PSObject.Properties.Name -contains $name) {
            return $InputObject.$name
        }
    }

    return $DefaultValue
}

function Get-AiOsScriptForValidator {
    param([string]$ValidatorId)

    switch ($ValidatorId) {
        "execution_registry_guard" { return "automation/orchestration/validators/Invoke-AiOsExecutionRegistryGuard.ps1" }
        "approval_gate" { return "automation/orchestration/validators/Test-ApplyApprovalGate.DRY_RUN.ps1" }
        "commit_package_review" { return "automation/orchestration/validators/Test-CommitPackageManifest.DRY_RUN.ps1" }
        "json_integrity" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "powershell_syntax" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "git_clean_state" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "allowed_paths" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "blocked_paths" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "markdown_exists" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "no_secrets" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "no_live_trading_enablement" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "final_git_status" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        default { return "" }
    }
}

function Get-AiOsValidatorArguments {
    param(
        [string]$ValidatorId,
        [string]$ScriptPath,
        [string]$ConfigPath
    )

    $args = @("-NoProfile", "-File", $ScriptPath)

    if ($ScriptPath -like "*Invoke-OrchestrationValidatorChain.DRY_RUN.ps1") {
        $args += @("-ConfigPath", $ConfigPath)
    }

    return $args
}

function ConvertTo-AiOsPreview {
    param([string]$Text)

    if ([string]::IsNullOrEmpty($Text)) {
        return ""
    }

    $normalized = ($Text -replace "\r\n", "`n" -replace "\r", "`n").Trim()
    if ($normalized.Length -le 500) {
        return $normalized
    }

    return $normalized.Substring(0, 500)
}

function Join-AiOsProcessArguments {
    param([string[]]$Arguments)

    $escaped = foreach ($arg in $Arguments) {
        if ($null -eq $arg) {
            '""'
        }
        else {
            '"' + ([string]$arg -replace '\\', '\\' -replace '"', '\"') + '"'
        }
    }

    return ($escaped -join " ")
}
function Invoke-AiOsValidatorProcess {
    param(
        [string]$PowerShellExe,
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 60
    )

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $PowerShellExe
    $psi.Arguments = Join-AiOsProcessArguments -Arguments $Arguments
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    [void]$process.Start()

    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $completed = $process.WaitForExit($TimeoutSeconds * 1000)

    if (-not $completed) {
        try { $process.Kill($true) } catch { }
        return [pscustomobject]@{
            timed_out = $true
            exit_code = $null
            stdout = ""
            stderr = "Validator timed out after $TimeoutSeconds seconds."
        }
    }

    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()

    return [pscustomobject]@{
        timed_out = $false
        exit_code = $process.ExitCode
        stdout = $stdout
        stderr = $stderr
    }
}

$repoRoot = Get-AiOsRepoRoot
Set-Location -LiteralPath $repoRoot
$generatedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$resolvedConfigPath = if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $repoRoot $ConfigPath }

try {
    $config = Get-Content -LiteralPath $resolvedConfigPath -Raw | ConvertFrom-Json
}
catch {
    Write-Error "Unable to read validator chain config: $($_.Exception.Message)"
    exit 1
}

$chainId = [string](Get-AiOsPropertyValue -InputObject $config -Names @("chain_id", "validator_chain_id") -DefaultValue "UNKNOWN_VALIDATOR_CHAIN")
$results = [System.Collections.Generic.List[object]]::new()
$chainResult = "PASS"
$validatorsRun = 0
$validatorsPassed = 0
$validatorsFailed = 0
$validatorsMissing = 0
$validatorsTimedOut = 0
$powershellExe = (Get-Command powershell -ErrorAction Stop).Source
$orderedValidators = @($config.validators | Sort-Object { [int](Get-AiOsPropertyValue -InputObject $_ -Names @("order") -DefaultValue 0) })

foreach ($validator in $orderedValidators) {
    $validatorId = [string](Get-AiOsPropertyValue -InputObject $validator -Names @("validator_id", "name", "check_id") -DefaultValue "UNKNOWN_VALIDATOR")
    $scriptPath = [string](Get-AiOsPropertyValue -InputObject $validator -Names @("script_path", "path") -DefaultValue "")
    if ([string]::IsNullOrWhiteSpace($scriptPath)) {
        $scriptPath = Get-AiOsScriptForValidator -ValidatorId $validatorId
    }

    $scriptPath = ConvertTo-AiOsRelativePath -Path $scriptPath
    $required = [bool](Get-AiOsPropertyValue -InputObject $validator -Names @("required") -DefaultValue $false)
    $severity = [string](Get-AiOsPropertyValue -InputObject $validator -Names @("severity_on_failure", "severity") -DefaultValue "FAIL")
    $stopOnFailRaw = Get-AiOsPropertyValue -InputObject $validator -Names @("stop_on_fail") -DefaultValue $null
    $stopOnFail = if ($null -ne $stopOnFailRaw) { [bool]$stopOnFailRaw } else { ($severity -eq "FAIL") }
    $resolvedScriptPath = if ([string]::IsNullOrWhiteSpace($scriptPath)) { "" } elseif ([System.IO.Path]::IsPathRooted($scriptPath)) { $scriptPath } else { Join-Path $repoRoot $scriptPath }

    if ([string]::IsNullOrWhiteSpace($scriptPath) -or -not (Test-Path -LiteralPath $resolvedScriptPath -PathType Leaf)) {
        $validatorsMissing++
        if ($required) { $validatorsFailed++ }
        $result = "MISSING"
        $results.Add([pscustomobject]@{
            validator_id = $validatorId
            script_path = $scriptPath
            result = $result
            exit_code = $null
            required = $required
            stop_on_fail = $stopOnFail
            output_preview = "Validator script missing."
        }) | Out-Null

        if ($required -and $stopOnFail) {
            $chainResult = "BLOCKED"
            break
        }
        elseif ($required -and $chainResult -ne "BLOCKED") {
            $chainResult = "FAIL"
        }

        continue
    }

    $validatorsRun++
    $args = Get-AiOsValidatorArguments -ValidatorId $validatorId -ScriptPath $resolvedScriptPath -ConfigPath $ConfigPath
    $run = Invoke-AiOsValidatorProcess -PowerShellExe $powershellExe -Arguments $args -TimeoutSeconds 60

    if ($run.timed_out) {
        $validatorsTimedOut++
        if ($required) { $validatorsFailed++ }
        $result = "TIMEOUT"
        $exitCode = $null
        $preview = ConvertTo-AiOsPreview -Text $run.stderr
    }
    elseif ($run.exit_code -eq 0) {
        $validatorsPassed++
        $result = "PASS"
        $exitCode = $run.exit_code
        $preview = ConvertTo-AiOsPreview -Text $run.stdout
    }
    else {
        if ($required) { $validatorsFailed++ }
        $result = "FAIL"
        $exitCode = $run.exit_code
        $previewText = if (-not [string]::IsNullOrWhiteSpace($run.stderr)) { $run.stderr } else { $run.stdout }
        $preview = ConvertTo-AiOsPreview -Text $previewText
    }

    $results.Add([pscustomobject]@{
        validator_id = $validatorId
        script_path = $scriptPath
        result = $result
        exit_code = $exitCode
        required = $required
        stop_on_fail = $stopOnFail
        output_preview = $preview
    }) | Out-Null

    if ($result -ne "PASS" -and $required -and $stopOnFail) {
        $chainResult = "BLOCKED"
        break
    }
    elseif ($result -ne "PASS" -and $required -and $chainResult -ne "BLOCKED") {
        $chainResult = "FAIL"
    }
}

$receipt = [pscustomobject]@{
    schema = "AIOS_VALIDATOR_CHAIN_RECEIPT.v1"
    chain_id = $chainId
    generated_at = $generatedAt
    chain_result = $chainResult
    validators_run = $validatorsRun
    validators_passed = $validatorsPassed
    validators_failed = $validatorsFailed
    validators_missing = $validatorsMissing
    validators_timeout = $validatorsTimedOut
    results = @($results)
}

$receipt | ConvertTo-Json -Depth 12
exit 0
