<#
.SYNOPSIS
    PowerShell wrapper around mu2e-ssh-setup.py.

.DESCRIPTION
    Locates a Python 3.9+ interpreter and forwards every argument unchanged.
    Set $env:MU2E_SSH_PYTHON to force a particular interpreter.

.EXAMPLE
    .\scripts\mu2e-ssh-setup.ps1 --interactive

.EXAMPLE
    .\scripts\mu2e-ssh-setup.ps1 --fnal-user jdoe --layout monolithic --install

.NOTES
    If PowerShell refuses to run this file, either allow local scripts for the
    current user:

        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

    or use scripts\mu2e-ssh-setup.cmd instead, which needs no policy change.
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot 'mu2e-ssh-setup.py'
if (-not (Test-Path -LiteralPath $scriptPath)) {
    Write-Error "cannot find $scriptPath"
    exit 1
}

function Test-Python3 {
    param([string]$Exe, [string[]]$Prefix = @())
    try {
        $probe = @('-c', 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)')
        & $Exe @($Prefix + $probe) 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$exe = $null
$prefix = @()

if ($env:MU2E_SSH_PYTHON) {
    $exe = $env:MU2E_SSH_PYTHON
} elseif ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-Python3 'py' @('-3'))) {
    $exe = 'py'
    $prefix = @('-3')
} elseif ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Python3 'python')) {
    $exe = 'python'
} elseif ((Get-Command python3 -ErrorAction SilentlyContinue) -and (Test-Python3 'python3')) {
    $exe = 'python3'
}

if (-not $exe) {
    Write-Host ''
    Write-Host 'mu2e-ssh-setup: no Python 3.9 or newer found on PATH.' -ForegroundColor Red
    Write-Host ''
    Write-Host 'Install it with one of:'
    Write-Host '    winget install Python.Python.3.12'
    Write-Host '    https://www.python.org/downloads/windows/'
    Write-Host ''
    Write-Host 'Then open a NEW terminal so the PATH change takes effect.'
    exit 1
}

& $exe @($prefix + @($scriptPath) + $Arguments)
exit $LASTEXITCODE
