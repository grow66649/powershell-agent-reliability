[CmdletBinding()]
param(
    [switch]$SkipBaseline
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$manifest = Join-Path $repo "Cargo.toml"
$harness = Join-Path $repo "benchmarks\harness"
$steps = @()

function Invoke-VerificationStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    Write-Host "==> $Name"
    & $Action
    $exitCode = $LASTEXITCODE
    $timer.Stop()
    $script:steps += [pscustomobject][ordered]@{
        name = $Name
        exit_code = $exitCode
        wall_ms = [math]::Round($timer.Elapsed.TotalMilliseconds, 3)
        passed = ($exitCode -eq 0)
    }
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode"
    }
}
Invoke-VerificationStep "cargo test" {
    & cargo test --manifest-path $manifest
}

Invoke-VerificationStep "cargo check" {
    & cargo check --manifest-path $manifest
}

Invoke-VerificationStep "cargo build release" {
    & cargo build --release --manifest-path $manifest
}

Invoke-VerificationStep "release lifecycle" {
    & cargo test --release --manifest-path $manifest --test lifecycle -- --nocapture
}

Invoke-VerificationStep "benchmark scorer tests" {
    Push-Location $harness
    try {
        & python -m unittest test_score_ab.py
    }
    finally {
        Pop-Location
    }
}

if (-not $SkipBaseline) {
    Invoke-VerificationStep "sanitized fixture baseline" {
        & python (Join-Path $harness "run_baseline.py") | Out-Null
    }
}
Invoke-VerificationStep "python compile" {
    Push-Location $harness
    try {
        & python -m py_compile score_ab.py test_score_ab.py run_baseline.py fixture_worker.py
    }
    finally {
        Pop-Location
    }
}

Invoke-VerificationStep "git diff check" {
    & git -C $repo diff --check
}

$binary = Join-Path $repo "target\release\powershell-agent-reliability.exe"
if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) {
    throw "release binary missing after successful build"
}
$binaryInfo = Get-Item -LiteralPath $binary
$binaryHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $binary).Hash
$head = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "failed to read git HEAD"
}

$report = [ordered]@{
    schema_version = 1
    git_head = $head
    release_binary_name = $binaryInfo.Name
    release_binary_bytes = $binaryInfo.Length
    release_binary_sha256 = $binaryHash
    baseline_skipped = [bool]$SkipBaseline
    steps = $steps
}

$report | ConvertTo-Json -Depth 5
