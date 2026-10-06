[CmdletBinding(DefaultParameterSetName = "Roots")]
param(
    [string]$RegistryPath = "automation/orchestration/execution_registry/AIOS_EXECUTION_CLASSIFICATION_REGISTRY.json",

    [Parameter(ParameterSetName = "Roots")]
    [string[]]$ScanRoots = @(
        "automation/orchestration",
        "automation/startup",
        "automation/operator"
    ),

    [Parameter(Mandatory = $true, ParameterSetName = "Files")]
    [string[]]$ScanFiles
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Add-Finding {
    param(
        [Parameter(Mandatory = $true)]
        [ref]$Findings,

        [Parameter(Mandatory = $true)]
        [string]$Severity,

        [Parameter(Mandatory = $true)]
        [string]$CheckId,

        [Parameter(Mandatory = $true)]
        [string]$Message,

        [string]$Evidence = "UNKNOWN",

        [string]$NextSafeAction = "Review the finding and keep execution blocked until resolved."
    )

    $Findings.Value += [pscustomobject]@{
        Severity = $Severity
        CheckId = $CheckId
        Message = $Message
        Evidence = $Evidence
        NextSafeAction = $NextSafeAction
    }
}

function Resolve-AiOsRepoRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StartPath
    )

    $candidate = (Resolve-Path -LiteralPath $StartPath).Path
    while (-not [string]::IsNullOrWhiteSpace($candidate)) {
        if ((Test-Path -LiteralPath (Join-Path $candidate "AGENTS.md") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $candidate "README.md") -PathType Leaf)) {
            return $candidate
        }

        $parent = Split-Path -Parent $candidate
        if ($parent -eq $candidate) {
            break
        }
        $candidate = $parent
    }

    throw "Unable to resolve AI_OS repo root from $StartPath."
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,

        [Parameter(Mandatory = $true)]
        [string]$FullPath
    )

    $baseUri = [System.Uri]::new(($BasePath.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar))
    $fileUri = [System.Uri]::new($FullPath)
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($fileUri).ToString()).Replace("/", "\")
}

function Normalize-RegistryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return $Path.Replace("\", "/").TrimStart("/", ".")
}

function Test-RequiredRegistryFields {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Registry,

        [Parameter(Mandatory = $true)]
        [ref]$Findings
    )

    $requiredTopLevelFields = @(
        "registry_id",
        "schema_version",
        "status",
        "default_policy",
        "allowed_classifications",
        "required_fields_per_script",
        "scripts"
    )

    foreach ($field in $requiredTopLevelFields) {
        if (-not ($Registry.PSObject.Properties.Name -contains $field)) {
            Add-Finding -Findings $Findings -Severity "STOP" -CheckId "registry_schema_missing_field" -Message "Registry is missing required top-level field." -Evidence $field -NextSafeAction "Repair the registry in a separate approved APPLY task."
        }
    }

    if (($Registry.PSObject.Properties.Name -contains "registry_id") -and $Registry.registry_id -ne "AIOS_EXECUTION_CLASSIFICATION_REGISTRY") {
        Add-Finding -Findings $Findings -Severity "STOP" -CheckId "registry_id_mismatch" -Message "Registry ID is not the expected execution classification registry." -Evidence ([string]$Registry.registry_id) -NextSafeAction "Verify the registry path and stop before execution."
    }

    if (($Registry.PSObject.Properties.Name -contains "schema_version") -and $Registry.schema_version -ne "1.0") {
        Add-Finding -Findings $Findings -Severity "STOP" -CheckId "registry_schema_version_unsupported" -Message "Registry schema version is unsupported." -Evidence ([string]$Registry.schema_version) -NextSafeAction "Review schema compatibility before using this guard."
    }

    if (($Registry.PSObject.Properties.Name -contains "status") -and $Registry.status -ne "canonical_execution_classification_registry") {
        Add-Finding -Findings $Findings -Severity "STOP" -CheckId "registry_status_invalid" -Message "Registry is not marked as canonical execution classification registry." -Evidence ([string]$Registry.status) -NextSafeAction "Review registry authority before execution."
    }
}

function Test-RegistryScriptEntries {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Registry,

        [Parameter(Mandatory = $true)]
        [ref]$Findings
    )

    $allowedClassifications = @($Registry.allowed_classifications)
    $requiredScriptFields = @($Registry.required_fields_per_script)
    $seenPaths = @{}

    foreach ($script in @($Registry.scripts)) {
        $pathValue = "UNKNOWN"
        if ($script.PSObject.Properties.Name -contains "path") {
            $pathValue = [string]$script.path
        }

        foreach ($field in $requiredScriptFields) {
            if (-not ($script.PSObject.Properties.Name -contains $field)) {
                Add-Finding -Findings $Findings -Severity "STOP" -CheckId "script_entry_missing_field" -Message "Registry script entry is missing a required field." -Evidence "$pathValue :: $field" -NextSafeAction "Repair the registry entry before using this script."
            }
        }

        if ($script.PSObject.Properties.Name -contains "classification") {
            if ($allowedClassifications -notcontains $script.classification) {
                Add-Finding -Findings $Findings -Severity "STOP" -CheckId "script_entry_invalid_classification" -Message "Registry script entry uses an unsupported classification." -Evidence "$pathValue :: $($script.classification)" -NextSafeAction "Use only approved classification values."
            }
        }

        $normalizedPath = Normalize-RegistryPath -Path $pathValue
        if ($seenPaths.ContainsKey($normalizedPath)) {
            Add-Finding -Findings $Findings -Severity "STOP" -CheckId "script_entry_duplicate_path" -Message "Registry contains duplicate script path entries." -Evidence $normalizedPath -NextSafeAction "Resolve duplicate entries in a separate approved APPLY task."
        } else {
            $seenPaths[$normalizedPath] = $true
        }
    }
}

function Test-DryRunWriteBehavior {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,

        [Parameter(Mandatory = $true)]
        [string]$Content,

        [AllowNull()]
        [object]$RegistryEntry,

        [Parameter(Mandatory = $true)]
        [ref]$Findings
    )

    if ($RelativePath -notmatch "\.DRY_RUN\.ps1$") {
        return
    }

    $writeCommands = @(
        "Set-Content",
        "Add-Content",
        "Out-File",
        "Export-Csv",
        "New-Item",
        "Remove-Item",
        "Move-Item",
        "Rename-Item",
        "Copy-Item"
    )
    $writePattern = "(?im)(^|[\s;&|])(?:Set-Content|Add-Content|Out-File|Export-Csv|ConvertTo-Json\s*\|[^`r`n]*Set-Content|New-Item|Remove-Item|Move-Item|Rename-Item|Copy-Item)(?:\s|$)"
    if ($Content -notmatch $writePattern) {
        return
    }

    $contract = $null
    if ($null -ne $RegistryEntry -and $RegistryEntry.PSObject.Properties.Name -contains "gated_mutation_contract") {
        $contract = $RegistryEntry.gated_mutation_contract
    }

    $contractErrors = [System.Collections.Generic.List[string]]::new()
    if ($null -eq $RegistryEntry) {
        $contractErrors.Add("script is not registered")
    }
    elseif ($null -eq $contract) {
        $contractErrors.Add("gated_mutation_contract is missing")
    }
    else {
        if ([string]$RegistryEntry.classification -ne "HELPER") {
            $contractErrors.Add("classification must be HELPER")
        }
        if ([string]$RegistryEntry.execution_mode -ne "DRY_RUN_DEFAULT_EXPLICIT_APPLY_GATED_HELPER") {
            $contractErrors.Add("execution_mode is not the canonical gated-helper mode")
        }
        if ($RegistryEntry.writes_files -ne $true) {
            $contractErrors.Add("writes_files must be true")
        }
        if ($RegistryEntry.requires_human_approval -ne $true) {
            $contractErrors.Add("requires_human_approval must be true")
        }
        if ([string]$contract.contract_version -ne "AIOS_GATED_APPLY_HELPER.v1") {
            $contractErrors.Add("unsupported gated-mutation contract version")
        }
        if ([string]$contract.default_behavior -ne "NON_MUTATING") {
            $contractErrors.Add("default behavior must be NON_MUTATING")
        }
        if ([string]$contract.write_capability -ne "EXPLICIT_GATED_APPLY_ONLY") {
            $contractErrors.Add("write capability must be EXPLICIT_GATED_APPLY_ONLY")
        }
        if ($contract.apply_requires_explicit_flag -ne $true) {
            $contractErrors.Add("apply_requires_explicit_flag must be true")
        }
        if ($contract.default_invocation_must_remain_dry_run -ne $true) {
            $contractErrors.Add("default_invocation_must_remain_dry_run must be true")
        }
        if ([string]::IsNullOrWhiteSpace([string]$contract.explicit_apply_parameter)) {
            $contractErrors.Add("explicit_apply_parameter is missing")
        }
        if (@($contract.gated_write_functions).Count -eq 0) {
            $contractErrors.Add("gated_write_functions is empty")
        }
        if (@($contract.required_apply_gate_terms).Count -eq 0) {
            $contractErrors.Add("required_apply_gate_terms is empty")
        }

        $blockedActions = @($RegistryEntry.blocked_actions)
        foreach ($requiredBlock in @("APPLY_without_explicit_flag", "APPLY_without_human_owner_packet_approval", "commit", "push", "merge")) {
            if ($blockedActions -notcontains $requiredBlock) {
                $contractErrors.Add("blocked_actions is missing $requiredBlock")
            }
        }
        if ($blockedActions -contains "APPLY") {
            $contractErrors.Add("blocked_actions cannot prohibit the separately approved explicit APPLY path")
        }
    }

    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($Content, [ref]$tokens, [ref]$parseErrors)
    if (@($parseErrors).Count -gt 0) {
        $contractErrors.Add("PowerShell parse errors prevent gated-write validation")
    }

    if ($null -ne $contract -and @($parseErrors).Count -eq 0) {
        $applyParameter = [string]$contract.explicit_apply_parameter
        $applyParameters = @($ast.FindAll({
            param($node)
            $node -is [System.Management.Automation.Language.ParameterAst] -and
            $node.Name.VariablePath.UserPath -eq $applyParameter
        }, $true))
        if ($applyParameters.Count -ne 1 -or $applyParameters[0].StaticType -ne [System.Management.Automation.SwitchParameter]) {
            $contractErrors.Add("explicit apply gate must be declared exactly once as a switch parameter")
        }

        $gatedFunctions = @($contract.gated_write_functions | ForEach-Object { [string]$_ })
        $functionDefinitions = @($ast.FindAll({
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
        }, $true))

        foreach ($functionName in $gatedFunctions) {
            $definitions = @($functionDefinitions | Where-Object { $_.Name -eq $functionName })
            if ($definitions.Count -ne 1) {
                $contractErrors.Add("gated write function $functionName must be defined exactly once")
                continue
            }

            $invocations = @($ast.FindAll({
                param($node)
                $node -is [System.Management.Automation.Language.CommandAst] -and
                $node.GetCommandName() -eq $functionName
            }, $true))
            if ($invocations.Count -eq 0) {
                $contractErrors.Add("gated write function $functionName is never invoked")
            }

            foreach ($invocation in $invocations) {
                $insideApprovedGate = $false
                $ancestor = $invocation.Parent
                while ($null -ne $ancestor) {
                    if ($ancestor -is [System.Management.Automation.Language.IfStatementAst]) {
                        foreach ($clause in $ancestor.Clauses) {
                            $insideClause = (
                                $invocation.Extent.StartOffset -ge $clause.Item2.Extent.StartOffset -and
                                $invocation.Extent.EndOffset -le $clause.Item2.Extent.EndOffset
                            )
                            if (-not $insideClause) {
                                continue
                            }

                            $conditionText = $clause.Item1.Extent.Text
                            $allTermsPresent = $true
                            foreach ($requiredTerm in @($contract.required_apply_gate_terms)) {
                                if ($conditionText -notlike "*$requiredTerm*") {
                                    $allTermsPresent = $false
                                    break
                                }
                            }
                            if ($allTermsPresent) {
                                $insideApprovedGate = $true
                                break
                            }
                        }
                    }
                    if ($insideApprovedGate) {
                        break
                    }
                    $ancestor = $ancestor.Parent
                }
                if (-not $insideApprovedGate) {
                    $contractErrors.Add("gated write function $functionName is invoked outside the registered apply gate")
                }
            }
        }

        $mutationCommands = @($ast.FindAll({
            param($node)
            $node -is [System.Management.Automation.Language.CommandAst]
        }, $true) | Where-Object { $writeCommands -contains $_.GetCommandName() })
        foreach ($mutationCommand in $mutationCommands) {
            $insideGatedFunction = $false
            foreach ($definition in $functionDefinitions | Where-Object { $gatedFunctions -contains $_.Name }) {
                if ($mutationCommand.Extent.StartOffset -ge $definition.Extent.StartOffset -and
                    $mutationCommand.Extent.EndOffset -le $definition.Extent.EndOffset) {
                    $insideGatedFunction = $true
                    break
                }
            }
            if (-not $insideGatedFunction) {
                $contractErrors.Add("mutation command $($mutationCommand.GetCommandName()) exists outside a registered gated write function")
            }
        }
    }

    if ($contractErrors.Count -gt 0) {
        Add-Finding -Findings $Findings -Severity "STOP" -CheckId "dry_run_script_writes_files" -Message "DRY_RUN script contains writes without a valid canonical gated-mutation contract." -Evidence "$RelativePath :: $($contractErrors -join '; ')" -NextSafeAction "Keep the script blocked until registry classification and explicit APPLY gating both validate."
    }
}

function Test-BlockedScriptReferences {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,

        [Parameter(Mandatory = $true)]
        [string]$Content,

        [Parameter(Mandatory = $true)]
        [object[]]$BlockedEntries,

        [Parameter(Mandatory = $true)]
        [ref]$Findings
    )

    $isLauncherLike = (
        $RelativePath -match "(^|/|\\)(Start|Open)-" -or
        $RelativePath -match "(?i)launcher" -or
        $Content -match "(?i)Start-Process|wt\.exe|conhost\.exe|powershell\s+-|pwsh\s+-"
    )

    if (-not $isLauncherLike) {
        return
    }

    foreach ($entry in $BlockedEntries) {
        $blockedPath = Normalize-RegistryPath -Path ([string]$entry.path)
        $blockedBackslash = $blockedPath.Replace("/", "\")
        $escapedForward = [regex]::Escape($blockedPath)
        $escapedBackslash = [regex]::Escape($blockedBackslash)
        if ($Content -match $escapedForward -or $Content -match $escapedBackslash) {
            Add-Finding -Findings $Findings -Severity "STOP" -CheckId "launcher_references_blocked_script" -Message "Launcher-like script references a BLOCKED script." -Evidence "$RelativePath -> $blockedPath" -NextSafeAction "Keep launcher use blocked until references are removed or explicitly approved."
        }
    }
}

$findings = @()

try {
    $repoRoot = Resolve-AiOsRepoRoot -StartPath $PSScriptRoot
} catch {
    Add-Finding -Findings ([ref]$findings) -Severity "STOP" -CheckId "repo_root_resolution_failed" -Message "Could not resolve AI_OS repo root." -Evidence $_.Exception.Message -NextSafeAction "Run from the active AI_OS repo and verify AGENTS.md and README.md exist."
    $repoRoot = (Get-Location).Path
}

$resolvedRegistryPath = Join-Path $repoRoot $RegistryPath
if (-not (Test-Path -LiteralPath $resolvedRegistryPath -PathType Leaf)) {
    Add-Finding -Findings ([ref]$findings) -Severity "STOP" -CheckId "registry_not_found" -Message "Execution classification registry was not found." -Evidence $RegistryPath -NextSafeAction "Create or restore the registry through approved APPLY before execution checks."
    $registry = $null
} else {
    try {
        $registry = Get-Content -LiteralPath $resolvedRegistryPath -Raw | ConvertFrom-Json
    } catch {
        Add-Finding -Findings ([ref]$findings) -Severity "STOP" -CheckId "registry_json_parse_failed" -Message "Execution classification registry JSON parse failed." -Evidence $_.Exception.Message -NextSafeAction "Repair registry JSON in a separate approved APPLY task."
        $registry = $null
    }
}

if ($null -ne $registry) {
    Test-RequiredRegistryFields -Registry $registry -Findings ([ref]$findings)
    if (($registry.PSObject.Properties.Name -contains "scripts") -and ($registry.PSObject.Properties.Name -contains "required_fields_per_script")) {
        Test-RegistryScriptEntries -Registry $registry -Findings ([ref]$findings)
    }
}

$registryByPath = @{}
$blockedEntries = @()
if ($null -ne $registry -and ($registry.PSObject.Properties.Name -contains "scripts")) {
    foreach ($entry in @($registry.scripts)) {
        if ($entry.PSObject.Properties.Name -contains "path") {
            $normalizedEntryPath = Normalize-RegistryPath -Path ([string]$entry.path)
            $registryByPath[$normalizedEntryPath] = $entry
            if (($entry.PSObject.Properties.Name -contains "classification") -and $entry.classification -eq "BLOCKED") {
                $blockedEntries += $entry
            }
        }
    }
}

$ps1Files = @()
$scanDescription = ""
if ($PSCmdlet.ParameterSetName -eq "Files") {
    $scanDescription = "files: $($ScanFiles -join ', ')"
    foreach ($scanFile in $ScanFiles) {
        if ([System.IO.Path]::IsPathRooted($scanFile)) {
            Add-Finding -Findings ([ref]$findings) -Severity "STOP" -CheckId "scan_file_must_be_repo_relative" -Message "Exact scan files must be repository-relative." -Evidence $scanFile -NextSafeAction "Use an exact repository-relative PowerShell path."
            continue
        }
        $resolvedScanFile = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $scanFile))
        $repoPrefix = $repoRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
        if (-not $resolvedScanFile.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Add-Finding -Findings ([ref]$findings) -Severity "STOP" -CheckId "scan_file_outside_repo" -Message "Exact scan file resolves outside the repository." -Evidence $scanFile -NextSafeAction "Keep exact file validation inside the active repository."
            continue
        }
        if (-not (Test-Path -LiteralPath $resolvedScanFile -PathType Leaf) -or [System.IO.Path]::GetExtension($resolvedScanFile) -ne ".ps1") {
            Add-Finding -Findings ([ref]$findings) -Severity "STOP" -CheckId "scan_file_missing_or_invalid" -Message "Exact scan target must be an existing PowerShell file." -Evidence $scanFile -NextSafeAction "Provide an existing exact repository-relative .ps1 path."
            continue
        }
        $ps1Files += Get-Item -LiteralPath $resolvedScanFile
    }
}
else {
    $scanDescription = "roots: $($ScanRoots -join ', ')"
    foreach ($scanRoot in $ScanRoots) {
        $resolvedScanRoot = Join-Path $repoRoot $scanRoot
        if (-not (Test-Path -LiteralPath $resolvedScanRoot -PathType Container)) {
            Add-Finding -Findings ([ref]$findings) -Severity "STOP" -CheckId "scan_root_missing" -Message "Configured scan root does not exist." -Evidence $scanRoot -NextSafeAction "Review scan roots before using this guard."
            continue
        }

        $ps1Files += Get-ChildItem -LiteralPath $resolvedScanRoot -Recurse -File -Filter "*.ps1"
    }
}

foreach ($file in $ps1Files | Sort-Object FullName -Unique) {
    $relativePath = (Get-RelativePath -BasePath $repoRoot -FullPath $file.FullName).Replace("\", "/")
    $normalizedRelativePath = Normalize-RegistryPath -Path $relativePath
    $content = Get-Content -LiteralPath $file.FullName -Raw

    $registryEntry = $null
    if (-not $registryByPath.ContainsKey($normalizedRelativePath)) {
        Add-Finding -Findings ([ref]$findings) -Severity "STOP" -CheckId "unregistered_executable_script" -Message "Executable PowerShell script is not registered in the execution classification registry." -Evidence $normalizedRelativePath -NextSafeAction "Classify this script in the registry through a separate approved APPLY task or keep it blocked."
    }
    else {
        $registryEntry = $registryByPath[$normalizedRelativePath]
    }

    Test-DryRunWriteBehavior -RelativePath $normalizedRelativePath -Content $content -RegistryEntry $registryEntry -Findings ([ref]$findings)
    Test-BlockedScriptReferences -RelativePath $normalizedRelativePath -Content $content -BlockedEntries $blockedEntries -Findings ([ref]$findings)
}

$stopFindings = @($findings | Where-Object { $_.Severity -eq "STOP" })
$status = if ($stopFindings.Count -gt 0) { "STOP" } else { "PASS" }

Write-Host "AI_OS EXECUTION REGISTRY GUARD: $status"
Write-Host "Mode: report-only validation"
Write-Host "Repo root: $repoRoot"
Write-Host "Registry: $resolvedRegistryPath"
Write-Host "Scan scope: $scanDescription"
Write-Host "Scripts scanned: $(@($ps1Files).Count)"
Write-Host "Findings: $($findings.Count)"
Write-Host "No auto-repair, runtime execution, worker launch, startup launch, commit, or push was performed."

if ($findings.Count -gt 0) {
    Write-Host ""
    Write-Host "Findings:"
    foreach ($finding in $findings) {
        Write-Host ("[{0}] {1}: {2}" -f $finding.Severity, $finding.CheckId, $finding.Message)
        Write-Host ("  Evidence: {0}" -f $finding.Evidence)
        Write-Host ("  Next safe action: {0}" -f $finding.NextSafeAction)
    }
}

Write-Host ""
if ($status -eq "PASS") {
    Write-Host "Next safe action: Keep this guard read-only and add it to the validator chain only after registry coverage is reviewed."
    exit 0
}

Write-Host "Next safe action: Review STOP findings and update the registry or scripts only through a separate approved APPLY task."
exit 1
