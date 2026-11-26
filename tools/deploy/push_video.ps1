# push_video.ps1 - Sends an edited video from the PC to the Linux server, which will publish it
#
#   powershell -ExecutionPolicy Bypass -File tools\deploy\push_video.ps1 videos\2026-11-28_xxx
#   powershell -ExecutionPolicy Bypass -File tools\deploy\push_video.ps1 videos\2026-11-28_xxx -Schedule "2026-11-28T18:00"
#
# Sent: publish.json and output\ (final video, thumbnails), without output\archive.
# Never sent: source\ (heavy and not needed to publish). published.json: only if the server has none.
# -Schedule writes "schedule" into publish.json (server local time if no time zone) before sending:
#           the server timer publishes at that time. Without "schedule", publishing is manual only.
param([Parameter(Mandatory = $true)][string]$Folder, [string]$Schedule = "", [string]$Target = "")
. "$PSScriptRoot\common.ps1"
if (-not $Target) { $Target = $DefaultTarget }

$full = (Resolve-Path $Folder).Path
if (-not $full.StartsWith("$Root\videos\")) { throw "The folder must be inside $Root\videos" }
$rel = $full.Substring($Root.Length + 1).Replace("\", "/")
$meta = Join-Path $full "publish.json"
if (-not (Test-Path $meta)) { throw "publish.json missing in $full" }

$json = Get-Content $meta -Raw -Encoding UTF8 | ConvertFrom-Json
$video = Join-Path $full $json.video
if (-not (Test-Path $video)) { throw "Video not found: $video" }

if ($Schedule) {
    [void][datetime]::Parse($Schedule)   # format check before writing
    $py = Join-Path $Root ".venv\Scripts\python.exe"; if (-not (Test-Path $py)) { $py = "python" }
    # Written through Python: keeps UTF-8 without BOM and the file layout
    & $py -c "import json,sys; p=sys.argv[1]; d=json.load(open(p,encoding='utf-8')); d['schedule']=sys.argv[2]; open(p,'w',encoding='utf-8').write(json.dumps(d,ensure_ascii=False,indent=2)+'\n')" $meta $Schedule
    if ($LASTEXITCODE -ne 0) { throw "Could not write schedule" }
    Write-Host "schedule = $Schedule" -ForegroundColor Cyan
}

Write-Host "=== Sending $rel to $Target ===" -ForegroundColor Cyan
$paths = @("$rel/publish.json", "$rel/output")
# published.json: sent only if the server has none yet (after that, the server is the reference)
if (Test-Path (Join-Path $full "published.json")) {
    $remote = ssh $Target "test -f '$RemoteDir/$rel/published.json' && echo PRESENT || echo ABSENT"
    if ($remote -match "ABSENT") { $paths += "$rel/published.json"; Write-Host "published.json missing on the server: sent." -ForegroundColor Yellow }
}
Send-Tar -Target $Target -Paths $paths -Exclude @("$rel/output/archive")
Invoke-Remote $Target ".venv/bin/python tools/publish/run.py '$rel' --dry-run"
Write-Host "`nOn the server. Publishing: automatic at the 'schedule' time, or manual:" -ForegroundColor Green
Write-Host "  ssh $Target `"cd $RemoteDir && .venv/bin/python tools/publish/run.py '$rel'`""
