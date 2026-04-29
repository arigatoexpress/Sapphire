# Backwards-compatible entrypoint for the Windows TV agent scheduled tasks.
#
# Older runbooks referenced this script. It now delegates to the repo-owned,
# read-only TV agent task installer so task names and paths match live Sapphire
# reality instead of the removed legacy backend.

param(
    [string]$RepoPath = "E:\Sapphire\Code\Sapphire",
    [string]$PythonPath = "python",
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8081,
    [string]$CdpUrl = "http://127.0.0.1:9222",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

$installer = Join-Path $PSScriptRoot "create_tv_agent_task.ps1"
if (-not (Test-Path $installer)) {
    throw "TV agent task installer not found: $installer"
}

& $installer `
    -RepoPath $RepoPath `
    -PythonPath $PythonPath `
    -HostAddress $HostAddress `
    -Port $Port `
    -CdpUrl $CdpUrl `
    -StartNow:$StartNow
