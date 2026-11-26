# deploy_linux.ps1 - Deploys video-studio to the server (VS_SERVER:VS_SERVER_DIR from .env) and sets up its .venv
#
#   powershell -ExecutionPolicy Bypass -File tools\deploy\deploy_linux.ps1
#   powershell -ExecutionPolicy Bypass -File tools\deploy\deploy_linux.ps1 -InstallTimer    # + systemd timers (publishing 15 min, statistics 6 h)
#
# Sent: tools/, assets/, docs/, tests/, requirements*.txt, pytest.ini, README.md, .env.example and .env
#       (the machine configuration: the same file serves the PC and the server).
# Never sent: secrets/, private/, .venv, videos (see push_video.ps1).
param([string]$Target = "", [switch]$InstallTimer, [switch]$SkipTests)
. "$PSScriptRoot\common.ps1"
if (-not $Target) { $Target = $DefaultTarget }

Write-Host "=== System prerequisites on $Target ===" -ForegroundColor Cyan
$pre = ssh $Target "for c in python3 ffmpeg ffprobe gopass; do command -v `$c >/dev/null || echo MISSING:`$c; done; python3 -c 'import venv, ensurepip' 2>/dev/null || echo MISSING:python3-venv; ls /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf >/dev/null 2>&1 || echo MISSING:fonts-dejavu-core"
if ($pre -match "MISSING") { $pre | Write-Host -ForegroundColor Yellow; throw "System prerequisites missing on $Target" }
Write-Host "OK"

Write-Host "`n=== Uploading the code ===" -ForegroundColor Cyan
$paths = @("tools", "assets", "docs", "tests", "requirements.txt", "requirements-dev.txt", "pytest.ini", "README.md", ".env", ".env.example") |
    Where-Object { Test-Path (Join-Path $Root $_) }
Send-Tar -Target $Target -Paths $paths -Exclude @("__pycache__", "*.pyc", "tools/bench/results")
Invoke-Remote $Target "chmod 600 .env && grep -E '^VS_(SECRETS|GOPASS)' .env"

Write-Host "`n=== .venv ===" -ForegroundColor Cyan
Invoke-Remote $Target "{ [ -x .venv/bin/python ] || python3 -m venv .venv; } && .venv/bin/python -m pip install -q --upgrade pip && .venv/bin/python -m pip install -q -r requirements.txt -r requirements-dev.txt && .venv/bin/python -m pip list --format=freeze | grep -iE 'pillow|google-api|requests|pytest'"

if (-not $SkipTests) {
    Write-Host "`n=== Unit tests (no network) ===" -ForegroundColor Cyan
    Invoke-Remote $Target ".venv/bin/python -m pytest -q tests"
}

if ($InstallTimer) {
    Write-Host "`n=== systemd timers (user) ===" -ForegroundColor Cyan
    Invoke-Remote $Target "mkdir -p ~/.config/systemd/user && for u in publish stats; do sed 's|@VS_SERVER_DIR@|$RemoteDir|g' tools/deploy/systemd/video-studio-`$u.service > ~/.config/systemd/user/video-studio-`$u.service && cp tools/deploy/systemd/video-studio-`$u.timer ~/.config/systemd/user/; done && systemctl --user daemon-reload && systemctl --user enable --now video-studio-publish.timer video-studio-stats.timer && systemctl --user list-timers 'video-studio-*' --no-pager"
    Write-Host "To run them without an open session: ssh $Target 'sudo loginctl enable-linger `$USER'" -ForegroundColor Yellow
}

Write-Host "`nDeployment done. Check: ssh $Target 'cd $RemoteDir && .venv/bin/python tools/publish/selftest.py'" -ForegroundColor Green
