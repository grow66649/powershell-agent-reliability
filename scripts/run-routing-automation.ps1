param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('profile-check', 'run-row')]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $repoRoot 'benchmarks/harness/codex_automation.py'
$python = (Get-Command python.exe -ErrorAction Stop).Source

& $python $runner $Command @Arguments
exit $LASTEXITCODE
