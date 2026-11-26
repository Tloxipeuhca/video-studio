# reply_comment.ps1 - Reply to YouTube comments through the publishing server
#
#   powershell -ExecutionPolicy Bypass -File tools\deploy\reply_comment.ps1                      # interactive walk
#   powershell -ExecutionPolicy Bypass -File tools\deploy\reply_comment.ps1 -List                # pending comments
#   powershell -ExecutionPolicy Bypass -File tools\deploy\reply_comment.ps1 -Id <id> -Text "Thanks!"
#
# Comment ids are shown on the statistics page (open_stats.ps1) and by -List.
# The reply text is sent as UTF-8 on standard input, so accents and emoji are preserved.
param([string]$Id = "", [string]$Text = "", [switch]$List, [string]$Target = "")
. "$PSScriptRoot\common.ps1"
if (-not $Target) { $Target = $DefaultTarget }

if ($List) {
    Invoke-Remote $Target ".venv/bin/python tools/stats/reply.py --list"
} elseif ($Id) {
    if (-not $Text) { throw "-Text is required with -Id" }
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false   # UTF-8 without BOM on the pipe
    $Text | ssh $Target "cd $RemoteDir && .venv/bin/python tools/stats/reply.py '$Id' --stdin"
    if ($LASTEXITCODE -ne 0) { throw "Reply failed" }
} else {
    ssh -t $Target "cd $RemoteDir && .venv/bin/python tools/stats/reply.py --interactive"
}
