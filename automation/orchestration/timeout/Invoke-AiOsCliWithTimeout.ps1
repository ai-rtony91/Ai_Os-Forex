[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [string[]]$ArgumentList = @(),
    [ValidateRange(1, 2147483)][int]$TimeoutSec = 600,
    [AllowNull()][string]$StdIn = $null,
    [AllowNull()][string]$WorkingDirectory = $null,
    [ValidateRange(1, 16777216)][int]$MaximumOutputCharacters = 1048576,
    [AllowNull()][System.Collections.IDictionary]$LaunchEnvironment = $null,
    [object]$ProcessApi = $null, [switch]$RequireObservation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Import-AiOsCliProcessPrimitive {
    # Source reuse only: do not run the validator chain or its top-level code.
    $path = Join-Path $PSScriptRoot '../validator_chain_runner/Invoke-AiOsValidatorChain.DRY_RUN.ps1'
    $tokens = $null; $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw 'Owned process primitive failed syntax validation.' }
    $names = @('Join-AiOsProcessArguments', 'Initialize-AiOsOwnedValidatorProcess', 'Invoke-AiOsValidatorProcess')
    $definitions = @($ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -cin $names }, $false))
    if ($definitions.Count -ne $names.Count) { throw 'Owned process primitive definitions are missing or duplicated.' }
    foreach ($definition in $definitions) { . ([scriptblock]::Create($definition.Extent.Text)) }
    # Dot-source this importer so its three functions live in the adapter scope.
}

function Invoke-AiOsCliProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [ValidateRange(1, 2147483)][int]$TimeoutSec = 600,
        [AllowNull()][string]$StdIn = $null,
        [AllowNull()][string]$WorkingDirectory = $null,
        [ValidateRange(1, 16777216)][int]$MaximumOutputCharacters = 1048576,
    [AllowNull()][System.Collections.IDictionary]$LaunchEnvironment = $null,
    [object]$ProcessApi = $null, [switch]$RequireObservation
    )
    $watch = [Diagnostics.Stopwatch]::StartNew()
    try {
        . Import-AiOsCliProcessPrimitive
        $resolved = Get-Command -Name $FilePath -CommandType Application,ExternalScript -ErrorAction Stop | Select-Object -First 1
        $resolvedPath = [IO.Path]::GetFullPath($resolved.Source)
        if (-not [IO.File]::Exists($resolvedPath)) { throw 'CLI executable does not exist.' }
        $directory = if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) { (Get-Location).ProviderPath } else { [IO.Path]::GetFullPath($WorkingDirectory) }
        if (-not [IO.Directory]::Exists($directory)) { throw 'CLI working directory does not exist.' }
        $effectiveFile = $resolvedPath
        $effectiveArgs = @($ArgumentList)
        $invoke = @{}
        if($PSBoundParameters.ContainsKey('ProcessApi')){$invoke['ProcessApi'] = $ProcessApi}
        if($RequireObservation){$invoke['RequireObservation']=$true}
        if ($PSBoundParameters.ContainsKey('LaunchEnvironment')) {
            if ($null -eq $LaunchEnvironment) { throw 'Explicit launch environment cannot be null.' }
            $invoke['LaunchEnvironment'] = $LaunchEnvironment
        }
        $ext = [IO.Path]::GetExtension($resolvedPath).ToLowerInvariant()
        if ($ext -eq '.ps1') {
            $effectiveFile = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop).Source
            $effectiveArgs = @('-NoProfile', '-File', $resolvedPath) + @($ArgumentList)
        } elseif ($ext -in @('.cmd', '.bat')) {
            # cmd has a separate shell grammar. This adapter supports known safe
            # provider argv; unsupported shell syntax is rejected before launch.
            foreach ($value in @($resolvedPath) + @($ArgumentList)) {
                if ($null -ne $value -and $value -match '["&|<>^%!\r\n\x00]') { throw 'Unsupported CMD shell syntax in path or argument.' }
            }
            $effectiveFile = (Get-Command cmd.exe -CommandType Application -ErrorAction Stop).Source
            $tail = Join-AiOsProcessArguments -Arguments $ArgumentList
            $command = '"' + $resolvedPath + '"'
            if ($tail.Length -gt 0) { $command += ' ' + $tail }
            # cmd.exe consumes a shell tail, not a CRT argv list. /s strips only
            # the outer pair; delayed expansion is explicitly disabled.
            $effectiveArgs = @('/d', '/v:off', '/s', '/c', ('"' + $command + '"'))
            $invoke['RawArguments'] = '/d /v:off /s /c "' + $command + '"'
        } elseif ($ext -ne '.exe' -and $ext -ne '.com') {
            throw 'Unsupported CLI launcher extension.'
        }
        $inputEncoding = [Text.UTF8Encoding]::new($false, $true)
        if ($null -ne $StdIn -and $inputEncoding.GetByteCount($StdIn) -gt 16777216) { throw 'Input exceeds 16 MiB UTF8 bound.' }
        $run = Invoke-AiOsValidatorProcess -PowerShellExe $effectiveFile -Arguments $effectiveArgs -TimeoutSeconds $TimeoutSec -WorkingDirectory $directory -StandardInput $StdIn -Utf8Streams -MaximumOutputCharacters $MaximumOutputCharacters @invoke
        $exitCode = if ($run.cleanup_state -ne 'CONFIRMED') { 'CLEANUP_UNRESOLVED' } elseif ($run.timed_out) { 'TIMEOUT_EXCEEDED' } elseif ($run.startup_failed) { 'STARTUP_FAILED' } elseif (-not $run.stdin_completed) { 'INPUT_INCOMPLETE' } elseif ($run.process_error) { 'PROCESS_FAILED' } else { $run.exit_code }
        $result = [ordered]@{ exit_code=$exitCode; child_exit_code=$run.exit_code; stdout=$run.stdout; stderr=$run.stderr; duration_sec=[Math]::Round($watch.Elapsed.TotalSeconds,3); executable=$effectiveFile; arguments=$effectiveArgs; command_line_arguments=$(if ($invoke.ContainsKey('RawArguments')) { $invoke['RawArguments'] } else { Join-AiOsProcessArguments -Arguments $effectiveArgs }); working_directory=$directory }
        foreach ($name in @('timed_out','startup_failed','root_process_id','cleanup_state','root_exit_confirmed','tree_exit_confirmed','drains_completed','cleanup_error_code','cancellation_error_code','retry_allowed','stdin_completed','stdin_writer_joined','stdin_bytes_written','stdin_error_code','stdin_close_error_code','stdout_truncated','stderr_truncated','process_error')) {
            $property = $run.PSObject.Properties[$name]
            $result[$name] = if ($null -ne $property) { $property.Value } else { $null }
        }
        if ($PSBoundParameters.ContainsKey('LaunchEnvironment')) {
            $property = $run.PSObject.Properties['launch_witness']
            $result['launch_witness'] = if ($null -ne $property) { $property.Value } else { $null }
        }
        if($RequireObservation){
            foreach($name in @('observation_required','observation_ready')){
                $property=$run.PSObject.Properties[$name]
                $result[$name]=if($null -ne $property -and $property.Value -is [bool]){$property.Value}else{$false}
            }
        }
        return [pscustomobject]$result
    }
    catch {
        return [pscustomobject]@{ exit_code='STARTUP_FAILED'; child_exit_code=$null; stdout=''; stderr=$_.Exception.Message; duration_sec=[Math]::Round($watch.Elapsed.TotalSeconds,3); timed_out=$false; startup_failed=$true; root_process_id=0; cleanup_state='CONFIRMED'; root_exit_confirmed=$true; tree_exit_confirmed=$true; drains_completed=$true; stdin_completed=$false; stdin_writer_joined=$true; stdin_bytes_written=0; stdin_error_code=0; stdout_truncated=$false; stderr_truncated=$false; retry_allowed=$false; process_error=$_.Exception.Message }
    }
}

Invoke-AiOsCliProcess @PSBoundParameters
