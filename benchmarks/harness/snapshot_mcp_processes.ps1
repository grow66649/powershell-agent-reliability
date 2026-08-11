[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExecutablePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolved = [System.IO.Path]::GetFullPath($ExecutablePath)
$basename = [System.IO.Path]::GetFileName($resolved)
$processes = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ExecutablePath -and
            ([System.IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $resolved)
        }
)

$rows = @()
foreach ($process in $processes) {
    $runtime = Get-Process -Id ([int]$process.ProcessId) -ErrorAction SilentlyContinue
    $rows += [pscustomobject][ordered]@{
        pid = [int]$process.ProcessId
        parent_pid = [int]$process.ParentProcessId
        start_time = if ($runtime) { $runtime.StartTime.ToString("o") } else { $null }
        private_mb = if ($runtime) { [math]::Round($runtime.PrivateMemorySize64 / 1MB, 3) } else { $null }
        working_set_mb = if ($runtime) { [math]::Round($runtime.WorkingSet64 / 1MB, 3) } else { $null }
    }
}
$privateSum = if ($rows.Count -eq 0) { 0.0 } else { ($rows | Measure-Object -Property private_mb -Sum).Sum }
$workingSetSum = if ($rows.Count -eq 0) { 0.0 } else { ($rows | Measure-Object -Property working_set_mb -Sum).Sum }

$report = [ordered]@{
    schema_version = 1
    executable_name = $basename
    observed_at = (Get-Date).ToString("o")
    count = $rows.Count
    aggregate_private_mb = [math]::Round($privateSum, 3)
    aggregate_working_set_mb = [math]::Round($workingSetSum, 3)
    processes = $rows
}

$report | ConvertTo-Json -Depth 5
