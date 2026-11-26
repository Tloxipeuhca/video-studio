# common.ps1 - Helpers shared by the deployment scripts (loaded with ". $PSScriptRoot\common.ps1")
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path

function Read-DotEnv {
    # Reads .env (KEY=value, # comments, optional quotes). See docs/configuration.md
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path $Path)) { return $values }
    foreach ($line in Get-Content $Path -Encoding UTF8) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith("#") -or -not $t.Contains("=")) { continue }
        $i = $t.IndexOf("=")
        $k = $t.Substring(0, $i).Trim(); $v = $t.Substring($i + 1).Trim()
        if ($v.Length -ge 2 -and ($v[0] -eq '"' -or $v[0] -eq "'") -and $v[-1] -eq $v[0]) { $v = $v.Substring(1, $v.Length - 2) }
        $values[$k] = $v
    }
    return $values
}

$EnvFile = Join-Path $Root ".env"
$Config = Read-DotEnv $EnvFile
function Get-Setting([string]$Name) {
    $v = [Environment]::GetEnvironmentVariable($Name)
    if ($v) { return $v }
    $v = $Config[$Name]
    if (-not $v) { throw "$Name is not set: copy .env.example to .env and fill it in (docs\configuration.md)" }
    return $v
}
$DefaultTarget = Get-Setting "VS_SERVER"        # e.g. user@192.168.1.10
$RemoteDir = Get-Setting "VS_SERVER_DIR"        # project folder on the Linux server

function Send-Tar {
    <#
      Sends paths (relative to the project root) to the server, keeping the folder structure.
      tar.exe (built into Windows) | ssh: a single connection. The pipe goes through cmd.exe
      because PowerShell 5 corrupts binary streams between native programs.
    #>
    param([string]$Target, [string[]]$Paths, [string[]]$Exclude = @())
    $quoted = ($Paths | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $excl = ($Exclude | ForEach-Object { "--exclude=`"$_`"" }) -join ' '
    $line = "tar -cf - $excl -C `"$Root`" $quoted | ssh $Target `"mkdir -p $RemoteDir && tar -xf - -C $RemoteDir`""
    $tmp = Join-Path $env:TEMP "vs_send_tar.cmd"
    Set-Content -Path $tmp -Value "@echo off`r`n$line`r`nexit /b %ERRORLEVEL%" -Encoding Ascii
    cmd /c $tmp
    if ($LASTEXITCODE -ne 0) { throw "Upload to $Target failed" }
}

function Invoke-Remote {
    param([string]$Target, [string]$Command)
    ssh $Target "cd $RemoteDir && $Command"
    if ($LASTEXITCODE -ne 0) { throw "Remote command failed: $Command" }
}
