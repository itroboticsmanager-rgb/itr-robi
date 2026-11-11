# ROBI kiosk supervisor (D-064).
#
# Runs in the session of the kiosk user `Robi`: as that user's SHELL instead
# of explorer.exe (no taskbar, no Start, no Win key), and again every minute
# from Task Scheduler as a guardian - the mutex below lets only one copy live,
# so if the shell copy ever dies the next tick replaces it. Keeps alive:
#   1. the local device service (python -m robi.web) of the CURRENT release;
#   2. Edge in fullscreen kiosk mode on http://127.0.0.1:<port>/.
#
# The current release and the port live in C:\ROBI\kiosk\kiosk.json, so a
# release switch is "edit the file, restart the task" - this script itself is
# release-independent and is installed once into C:\ROBI\kiosk.
#
# Maintenance: create C:\ROBI\kiosk\pause (admin only, e.g. over SSH) and the
# supervisor stops both processes and waits; delete the file to resume.
#
# File is plain ASCII on purpose: Windows PowerShell 5.1 reads a BOM-less
# script as ANSI and would garble any other text.

[CmdletBinding()]
param(
    [string]$ConfigPath = 'C:\ROBI\kiosk\kiosk.json',
    # Testing on a workstation: run the service and watchdog without Edge.
    [switch]$NoBrowser,
    # Testing: exit after this many seconds (0 = run forever).
    [int]$RunSeconds = 0
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- config ---

function Read-KioskConfig {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { throw "Kiosk config not found: $Path" }
    $raw = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $cfg = [ordered]@{
        Release       = [string]$raw.release
        Port          = if ($raw.port) { [int]$raw.port } else { 4173 }
        Python        = if ($raw.python) { [string]$raw.python } else { 'C:\ROBI\.venv\Scripts\pythonw.exe' }
        DeviceConfig  = if ($raw.device_config) { [string]$raw.device_config } else { 'C:\ROBI\device.toml' }
        LogDir        = if ($raw.log_dir) { [string]$raw.log_dir } else { 'C:\ROBI\logs' }
        Edge          = if ($raw.edge) { [string]$raw.edge } else { '' }
        Offline       = [bool]$raw.offline
    }
    if (-not $cfg.Release) { throw "kiosk.json: 'release' is empty" }
    return $cfg
}

$KioskDir = Split-Path -Parent $ConfigPath
$PauseFile = Join-Path $KioskDir 'pause'
$Config = Read-KioskConfig $ConfigPath
New-Item -ItemType Directory -Path $Config.LogDir -Force | Out-Null
$LogFile = Join-Path $Config.LogDir 'kiosk.log'
$EdgeProfile = Join-Path $env:LOCALAPPDATA 'ROBI\edge-kiosk'

# ---------------------------------------------------------------- logging --

function Write-Log {
    param([string]$Message)
    try {
        if ((Test-Path -LiteralPath $LogFile) -and ((Get-Item -LiteralPath $LogFile).Length -gt 1MB)) {
            Move-Item -LiteralPath $LogFile -Destination "$LogFile.1" -Force
        }
        $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $PID, $Message
        Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    } catch { }
}

# One supervisor per session: a second copy (task restarted, user double-
# clicked the old shortcut) would fight the first over the port.
$mutex = New-Object System.Threading.Mutex($false, 'Local\ROBI-Kiosk-Supervisor')
if (-not $mutex.WaitOne(0)) {
    # Normal: the guardian task fires every minute and finds the shell's copy
    # alive. Silent on purpose, otherwise the log grows by a line a minute.
    exit 0
}

# ---------------------------------------------------------------- service --

function Find-ServiceProcesses {
    $port = $Config.Port
    Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*robi.web*' -and $_.CommandLine -like "*--port $port*" }
}

function Stop-Service-Robi {
    foreach ($p in @(Find-ServiceProcesses)) {
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { }
    }
}

# $null = service down. PageAge: seconds since the kiosk PAGE last polled the
# snapshot; $null = never (or an old release without /api/health).
function Get-Health {
    $base = "http://127.0.0.1:$($Config.Port)"
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "$base/api/health"
        $j = $r.Content | ConvertFrom-Json
        return @{ PageAge = $j.page_age_s; Watch = $true }
    } catch {
        $code = $null
        try { $code = [int]$_.Exception.Response.StatusCode } catch { }
        if ($code -ne 404) { return $null }
    }
    try {   # rollback to a release that predates /api/health
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "$base/api/snapshot"
        if ($r.StatusCode -eq 200) { return @{ PageAge = $null; Watch = $false } }
    } catch { }
    return $null
}
function Test-ServiceHealthy { return ($null -ne (Get-Health)) }

function Start-Service-Robi {
    $release = $Config.Release
    $src = Join-Path $release 'app\src'
    $web = Join-Path $release 'web'
    if (-not (Test-Path -LiteralPath (Join-Path $web 'index.html'))) { throw "release has no web\index.html: $release" }
    if (-not (Test-Path -LiteralPath (Join-Path $src 'robi'))) { throw "release has no app\src\robi: $release" }
    if (-not (Test-Path -LiteralPath $Config.Python)) { throw "python not found: $($Config.Python)" }

    Stop-Service-Robi   # leftovers from a previous supervisor or the old launcher
    # A killed service lets go of its log files a moment later; rotating them
    # before that failed with "file is being used" (seen on the tablet).
    for ($i = 0; $i -lt 20 -and @(Find-ServiceProcesses).Count -gt 0; $i++) { Start-Sleep -Milliseconds 250 }
    foreach ($name in 'service.log', 'service-error.log') {
        $f = Join-Path $Config.LogDir $name
        if (Test-Path -LiteralPath $f) {
            try { Move-Item -LiteralPath $f -Destination "$f.prev" -Force -ErrorAction Stop } catch { Start-Sleep -Milliseconds 500 }
        }
    }
    $code = "import sys; sys.path.insert(0, r'$src'); from robi.web.__main__ import main; main()"
    $argList = @('-c', ('"' + $code + '"'), '--config', ('"' + $Config.DeviceConfig + '"'),
        '--root', ('"' + $web + '"'), '--port', $Config.Port)
    if ($Config.Offline) { $argList += '--offline' }
    $p = Start-Process -FilePath $Config.Python -ArgumentList $argList -WorkingDirectory $release `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $Config.LogDir 'service.log') `
        -RedirectStandardError (Join-Path $Config.LogDir 'service-error.log')
    $null = $p.Handle   # keep the handle, otherwise ExitCode is empty after exit
    Write-Log "service started, pid $($p.Id), release $release, port $($Config.Port)"

    for ($i = 0; $i -lt 120; $i++) {   # up to ~60 s: first boot fetches content from CRM
        if ($p.HasExited) { throw "service exited during start, code $($p.ExitCode)" }
        if (Test-ServiceHealthy) { Write-Log 'service healthy'; return $p }
        Start-Sleep -Milliseconds 500
    }
    throw 'service did not answer /api/snapshot within 60 s'
}

# ---------------------------------------------------------------- browser --

function Resolve-Edge {
    if ($Config.Edge -and (Test-Path -LiteralPath $Config.Edge)) { return $Config.Edge }
    foreach ($c in "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
                   "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    throw 'msedge.exe not found'
}

function Find-EdgeProcesses {
    # Our Edge is recognised by its own profile directory: the kiosk never
    # shares a process with an ordinary Edge window (that would drop --kiosk).
    Get-CimInstance Win32_Process -Filter "Name = 'msedge.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$EdgeProfile*" }
}

function Stop-Edge {
    foreach ($p in @(Find-EdgeProcesses)) {
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { }
    }
}

function Start-Edge {
    New-Item -ItemType Directory -Path $EdgeProfile -Force | Out-Null
    $edge = Resolve-Edge
    $url = "http://127.0.0.1:$($Config.Port)/"
    $argList = @(
        '--kiosk', $url,
        '--edge-kiosk-type=fullscreen',
        "--user-data-dir=`"$EdgeProfile`"",
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-pinch',
        '--overscroll-history-navigation=0',
        '--disable-features=TranslateUI,msEdgeSidebarV2,msUndersideButton',
        '--autoplay-policy=no-user-gesture-required'
    )
    Start-Process -FilePath $edge -ArgumentList $argList | Out-Null
    $script:edgeStartedAt = Get-Date
    Write-Log "edge started on $url"
}

# ---------------------------------------------------------------- loop -----

$deadline = if ($RunSeconds -gt 0) { (Get-Date).AddSeconds($RunSeconds) } else { [datetime]::MaxValue }
$service = $null
$failures = 0          # consecutive failed health checks
$restarts = New-Object System.Collections.Generic.List[datetime]
$paused = $false
$edgeStartedAt = Get-Date

function Get-Backoff {
    # Crash loop: do not hammer the CPU of a fanless tablet, but never give up.
    $recent = @($restarts | Where-Object { $_ -gt (Get-Date).AddMinutes(-10) })
    if ($recent.Count -ge 5) { return 60 }
    return 2
}

function Restart-All {
    param([string]$Reason)
    Write-Log "restart: $Reason"
    $script:restarts.Add((Get-Date))
    if (-not $NoBrowser) { Stop-Edge }
    try {
        $script:service = Start-Service-Robi
        $script:failures = 0
        if (-not $NoBrowser) { Start-Edge }
    } catch {
        Write-Log "start failed: $($_.Exception.Message)"
        $script:service = $null
        $wait = Get-Backoff
        Write-Log "retry in $wait s"
        Start-Sleep -Seconds $wait
    }
}

Write-Log "supervisor up (user $env:USERNAME, config $ConfigPath, NoBrowser=$NoBrowser)"
try {
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $PauseFile) {
            if (-not $paused) {
                Write-Log 'pause file present: stopping kiosk for maintenance'
                if (-not $NoBrowser) { Stop-Edge }
                Stop-Service-Robi
                $service = $null
                $paused = $true
            }
            Start-Sleep -Seconds 5
            continue
        }
        if ($paused) {
            Write-Log 'pause file removed: resuming'
            $paused = $false
            $Config = Read-KioskConfig $ConfigPath   # release may have changed meanwhile
        }

        if ($null -eq $service -or $service.HasExited) {
            $why = if ($null -eq $service) { 'service not running' } else { "service exited, code $($service.ExitCode)" }
            Restart-All $why
            continue
        }

        $health = Get-Health
        if ($null -ne $health) {
            $failures = 0
            # Edge alive but off the kiosk page (swipe back, blocked or error
            # page, hung renderer): the page stops polling. Restart Edge only.
            if (-not $NoBrowser -and $health.Watch -and ((Get-Date) - $edgeStartedAt).TotalSeconds -gt 60 -and
                ($null -eq $health.PageAge -or $health.PageAge -gt 30)) {
                Write-Log "kiosk page silent (page_age_s=$($health.PageAge)): restarting edge"
                Stop-Edge
                Start-Edge
                Start-Sleep -Seconds 5
                continue
            }
        } else {
            $failures++
            if ($failures -ge 3) { Restart-All 'service stopped answering'; continue }
        }

        if (-not $NoBrowser -and @(Find-EdgeProcesses).Count -eq 0) {
            Write-Log 'edge is gone: relaunching'
            Start-Edge
        }
        Start-Sleep -Seconds 5
    }
} finally {
    Write-Log 'supervisor stopping'
    if ($RunSeconds -gt 0) {
        # Test mode: leave nothing behind.
        if (-not $NoBrowser) { Stop-Edge }
        Stop-Service-Robi
    }
    $mutex.ReleaseMutex()
}
