# run_bench.ps1 - Runs the performance test on Windows, then on the Linux server (VS_SERVER from .env)
# Usage (from the project root):
#   powershell -ExecutionPolicy Bypass -File tools\bench\run_bench.ps1 -Script videos\<folder>\montage\<script>.py -Source videos\<folder>\source\<capture>
# The script is called as "script SOURCE OUTPUT"; assets\ is copied too for scripts that use it.
param(
    [Parameter(Mandatory = $true)][string]$Script,
    [Parameter(Mandatory = $true)][string]$Source,
    [string]$Target = "",
    [string]$BenchDir = "video-studio-bench",   # relative to the server home, separate from the project folder
    [int]$Runs = 3,
    [switch]$SkipWindows,
    [switch]$SkipLinux
)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\..\deploy\common.ps1"
if (-not $Target) { $Target = $DefaultTarget }
$Root  = (Resolve-Path "$PSScriptRoot\..\..").Path
$ScriptRel = (Resolve-Path $Script).Path.Substring($Root.Length + 1).Replace("\", "/")
$SourceRel = (Resolve-Path $Source).Path.Substring($Root.Length + 1).Replace("\", "/")
$Py    = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

if (-not $SkipWindows) {
    Write-Host "=== Windows ===" -ForegroundColor Cyan
    & $Py "$Root\tools\bench\bench.py" $Runs --script "$Root\$ScriptRel" --source "$Root\$SourceRel"
    if ($LASTEXITCODE -ne 0) { throw "Windows benchmark failed" }
}

if (-not $SkipLinux) {
    Write-Host "`n=== Linux ($Target): checking prerequisites ===" -ForegroundColor Cyan
    # Pillow is not installed system-wide: it goes into a dedicated .venv (created below).
    $pre = ssh $Target "for c in python3 ffmpeg ffprobe; do command -v `$c >/dev/null || echo MISSING:`$c; done; python3 -c 'import venv, ensurepip' 2>/dev/null || echo MISSING:python3-venv; ls /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf >/dev/null 2>&1 || echo MISSING:fonts-dejavu-core"
    if ($pre -match "MISSING") {
        $pre | Write-Host -ForegroundColor Yellow
        throw "System prerequisites missing on $Target (see MISSING: above), then run again with -SkipWindows"
    }
    Write-Host "Prerequisites OK"

    Write-Host "`n=== Copying files (source about 330 MB, through tar | ssh) ===" -ForegroundColor Cyan
    # tar.exe (built into Windows) + ssh: a single connection, folder structure kept, no issue with ~ or missing folders.
    # The pipe goes through cmd.exe because PowerShell 5 corrupts binary streams between native programs.
    $files = @(
        $SourceRel,
        $ScriptRel,
        "assets/emoji",
        "tools/bench/bench.py"
    ) | ForEach-Object { '"' + $_ + '"' }
    $line = "tar -cf - -C `"$Root`" $($files -join ' ') | ssh $Target `"mkdir -p $BenchDir && tar -xf - -C $BenchDir`""
    $tmpCmd = Join-Path $env:TEMP "vs_bench_copy.cmd"
    Set-Content -Path $tmpCmd -Value "@echo off`r`n$line`r`nexit /b %ERRORLEVEL%" -Encoding Ascii
    cmd /c $tmpCmd
    if ($LASTEXITCODE -ne 0) { throw "Copy to $Target failed" }
    ssh $Target "ls -la $BenchDir/tools/bench"

    Write-Host "`n=== Linux .venv ($BenchDir/.venv) ===" -ForegroundColor Cyan
    ssh $Target "cd $BenchDir && { [ -x .venv/bin/python ] || python3 -m venv .venv; } && .venv/bin/python -m pip install -q --upgrade pip && .venv/bin/python -m pip install -q 'Pillow>=10.0' && .venv/bin/python -c 'import PIL; print(PIL.__version__)'"
    if ($LASTEXITCODE -ne 0) { throw "Linux .venv failed" }

    Write-Host "`n=== Running on Linux ===" -ForegroundColor Cyan
    ssh $Target "cd $BenchDir && .venv/bin/python tools/bench/bench.py $Runs --script '$ScriptRel' --source '$SourceRel'"
    if ($LASTEXITCODE -ne 0) { throw "Linux benchmark failed" }
    New-Item -ItemType Directory -Force "$Root\tools\bench\results" | Out-Null
    # Fetched with ssh + cat (text files): more reliable than scp with a remote wildcard
    $rh = (ssh $Target "hostname").Trim()
    foreach ($ext in "txt", "json") {
        $content = ssh $Target "cat $BenchDir/tools/bench/results/$rh.$ext"
        if ($LASTEXITCODE -ne 0) { throw "Result $rh.$ext not found on $Target" }
        Set-Content -Path "$Root\tools\bench\results\$rh.$ext" -Value $content -Encoding UTF8
    }
}

Write-Host "`n=== Results ===" -ForegroundColor Green
Get-ChildItem "$Root\tools\bench\results\*.txt" | ForEach-Object { Write-Host "--- $($_.Name)"; Get-Content $_ }
