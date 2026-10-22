param(
    [Parameter(Mandatory = $false)][int]$Port = 8080
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..')).Path
$dashboardRoot = Join-Path $repoRoot 'apps\dashboard'

Push-Location $dashboardRoot
try {
    $env:PORT = [string]$Port
    npm run start
}
finally {
    Pop-Location
}
