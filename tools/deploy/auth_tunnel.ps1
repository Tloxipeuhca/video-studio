# auth_tunnel.ps1 - (Re)authorizes YouTube or TikTok for the Linux server, which has no display
#
#   powershell -ExecutionPolicy Bypass -File tools\deploy\auth_tunnel.ps1 youtube
#   powershell -ExecutionPolicy Bypass -File tools\deploy\auth_tunnel.ps1 tiktok
#
# Opens an SSH tunnel: the authorization redirect ports (127.0.0.1:4781x / 4782x) of the PC are
# forwarded to the server. The server prints the authorization address: open it in Chrome, with
# the profile of the project's Google account. The new token is written straight into gopass on the server.
param([Parameter(Mandatory = $true)][ValidateSet("youtube", "tiktok")][string]$Platform, [string]$Target = "")
. "$PSScriptRoot\common.ps1"
if (-not $Target) { $Target = $DefaultTarget }

$ports = if ($Platform -eq "youtube") { 47811..47815 } else { 47821..47825 }
$fwd = $ports | ForEach-Object { "-L"; "${_}:127.0.0.1:${_}" }
Write-Host "Tunnel for ports $($ports[0])-$($ports[-1]) -> $Target. Open the printed address in Chrome (project profile)." -ForegroundColor Cyan
ssh -t @fwd $Target "cd $RemoteDir && .venv/bin/python tools/publish/$Platform.py --auth-only"
