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

Invoke-CheckedCommand { python -m ruff check . }
Invoke-CheckedCommand { python -m ruff format --check . }
Invoke-CheckedCommand { python -m compileall -q main.py autobrowser tests }
Invoke-CheckedCommand { python -m unittest discover -s tests }
Invoke-CheckedCommand { python -m pip check }
