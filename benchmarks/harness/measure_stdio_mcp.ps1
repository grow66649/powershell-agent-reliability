[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Command,
    [string]$Arguments = "",
    [ValidateRange(1, 50)]
    [int]$Trials = 5,
    [ValidateRange(0, 10000)]
    [int]$SampleDelayMs = 250,
    [ValidateRange(100, 30000)]
    [int]$IoTimeoutMs = 5000,
    [string]$ProtocolVersion = "2025-11-25"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-LineWithTimeout {
    param(
        [Parameter(Mandatory = $true)]$Reader,
        [Parameter(Mandatory = $true)][int]$TimeoutMs
    )
    $task = $Reader.ReadLineAsync()
    if (-not $task.Wait($TimeoutMs)) {
        throw "Timed out waiting for MCP stdout"
    }
    return $task.Result
}
function Get-Median {
    param([double[]]$Values)
    if (-not $Values -or $Values.Count -eq 0) { return $null }
    $sorted = @($Values | Sort-Object)
    $middle = [int][math]::Floor($sorted.Count / 2)
    if (($sorted.Count % 2) -eq 1) { return [double]$sorted[$middle] }
    return ([double]$sorted[$middle - 1] + [double]$sorted[$middle]) / 2.0
}

function Invoke-StdIoProbe {
    param([int]$Trial)

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $Command
    $psi.Arguments = $Arguments
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $process = [System.Diagnostics.Process]::Start($psi)
    $forcedCleanup = $false
    try {
        $initialize = @{
            jsonrpc = "2.0"
            id = 1
            method = "initialize"
            params = @{
                protocolVersion = $ProtocolVersion
                capabilities = @{}
                clientInfo = @{ name = "psr-resource-probe"; version = "0" }
            }
        } | ConvertTo-Json -Compress -Depth 6
        $process.StandardInput.WriteLine($initialize)
        $process.StandardInput.Flush()
        $initializeLine = Read-LineWithTimeout -Reader $process.StandardOutput -TimeoutMs $IoTimeoutMs
        if ([string]::IsNullOrWhiteSpace($initializeLine)) {
            throw "MCP initialize returned no response"
        }
        $initializeResult = $initializeLine | ConvertFrom-Json
        if ($initializeResult.PSObject.Properties.Name -contains "error") {
            throw "MCP initialize returned an error"
        }

        $initialized = @{ jsonrpc = "2.0"; method = "notifications/initialized" } |
            ConvertTo-Json -Compress
        $process.StandardInput.WriteLine($initialized)
        $listTools = @{ jsonrpc = "2.0"; id = 2; method = "tools/list"; params = @{} } |
            ConvertTo-Json -Compress -Depth 4
        $process.StandardInput.WriteLine($listTools)
        $process.StandardInput.Flush()

        $listLine = Read-LineWithTimeout -Reader $process.StandardOutput -TimeoutMs $IoTimeoutMs
        $listResult = $listLine | ConvertFrom-Json
        if ($listResult.PSObject.Properties.Name -contains "error") {
            throw "MCP tools/list returned an error"
        }
        $toolCount = @($listResult.result.tools).Count
        $readyMs = $timer.Elapsed.TotalMilliseconds

        if ($SampleDelayMs -gt 0) {
            Start-Sleep -Milliseconds $SampleDelayMs
        }
        $process.Refresh()
        $row = [ordered]@{
            trial = $Trial
            tool_count = $toolCount
            ready_ms = [math]::Round($readyMs, 3)
            private_mb = [math]::Round($process.PrivateMemorySize64 / 1MB, 3)
            working_set_mb = [math]::Round($process.WorkingSet64 / 1MB, 3)
            alive_at_sample = (-not $process.HasExited)
        }

        $process.StandardInput.Close()
        $cleanupPass = $process.WaitForExit(3000)
        if (-not $cleanupPass) {
            $process.Kill()
            $process.WaitForExit()
            $forcedCleanup = $true
        }
        $row.cleanup_pass = $cleanupPass
        $row.forced_cleanup = $forcedCleanup
        $row.exit_code = $process.ExitCode
        $row.total_ms = [math]::Round($timer.Elapsed.TotalMilliseconds, 3)
        return [pscustomobject]$row
    }
    finally {
        if (-not $process.HasExited) {
            $process.Kill()
            $process.WaitForExit()
        }
        $process.Dispose()
    }
}
$rows = @(1..$Trials | ForEach-Object { Invoke-StdIoProbe -Trial $_ })
$ready = $rows | Measure-Object -Property ready_ms -Average
$private = $rows | Measure-Object -Property private_mb -Average
$workingSet = $rows | Measure-Object -Property working_set_mb -Average

$report = [ordered]@{
    schema_version = 1
    command_name = [System.IO.Path]::GetFileName($Command)
    protocol_version = $ProtocolVersion
    trials = $Trials
    sample_delay_ms = $SampleDelayMs
    results = $rows
    summary = [ordered]@{
        ready_ms_mean = [math]::Round($ready.Average, 3)
        ready_ms_median = [math]::Round((Get-Median -Values @($rows.ready_ms)), 3)
        private_mb_mean = [math]::Round($private.Average, 3)
        private_mb_median = [math]::Round((Get-Median -Values @($rows.private_mb)), 3)
        working_set_mb_mean = [math]::Round($workingSet.Average, 3)
        working_set_mb_median = [math]::Round((Get-Median -Values @($rows.working_set_mb)), 3)
        all_cleanup = -not ($rows.cleanup_pass -contains $false)
        no_forced_cleanup = -not ($rows.forced_cleanup -contains $true)
    }
}

$report | ConvertTo-Json -Depth 6
