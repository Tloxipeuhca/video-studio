# open_stats.ps1 - Opens the statistics page built on the server
#
#   powershell -ExecutionPolicy Bypass -File tools\deploy\open_stats.ps1            # last built page
#   powershell -ExecutionPolicy Bypass -File tools\deploy\open_stats.ps1 -Refresh   # collect first (about 10-30 s)
#
# The page (self-contained, no external resource) is copied to %TEMP% and opened in the browser.
param([switch]$Refresh, [string]$Target = "")
. "$PSScriptRoot\common.ps1"
if (-not $Target) { $Target = $DefaultTarget }

if ($Refresh) {
    Write-Host "Collecting on $Target..." -ForegroundColor Cyan
    Invoke-Remote $Target ".venv/bin/python tools/stats/collect.py"
}
$out = Join-Path $env:TEMP "video-studio-stats.html"
scp "${Target}:$RemoteDir/stats/index.html" $out
if ($LASTEXITCODE -ne 0) { throw "Page not found on the server: run with -Refresh" }
Start-Process $out
