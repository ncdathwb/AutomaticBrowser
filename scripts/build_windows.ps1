param(
    [switch]$SkipPythonVersionCheck
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Command"
    }
}

$PythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0) {
    throw "Could not determine Python version."
}
if (-not $SkipPythonVersionCheck -and $PythonVersion -ne "3.12") {
    throw "Production builds must use Python 3.12. Current Python is $PythonVersion."
}

Invoke-CheckedCommand {
    python -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --windowed `
        --name AutoBrowser `
        --hidden-import win32timezone `
        main.py
}

$ReleaseDir = Join-Path $RepoRoot "dist\AutoBrowser"
$ExePath = Join-Path $ReleaseDir "AutoBrowser.exe"
if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Expected build artifact was not created: $ExePath"
}

$Version = python -c "from autobrowser.config import APP_CONFIG; print(APP_CONFIG.version)"
if ($LASTEXITCODE -ne 0) {
    throw "Could not determine AutoBrowser version."
}
$ZipPath = Join-Path $RepoRoot "dist\AutoBrowser-$Version-win64.zip"
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Compress-Archive -Path $ReleaseDir -DestinationPath $ZipPath
Write-Host "Built $ExePath"
Write-Host "Created $ZipPath"
