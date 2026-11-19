# ROBI kiosk self-update. Runs as SYSTEM from the task "ROBI Update" every
# 15 minutes (installed by install-kiosk.ps1).
#
#   1. reads latest.json (update_url in kiosk.json; same idea as the classroom
#      launcher): { version, url, sha256 };
#   2. nothing to do if that version is current or was already rolled back;
#   3. waits for a quiet moment: the kiosk shows its home screen (never in the
#      middle of an enrollment form or a QR a parent is holding);
#   4. downloads the zip (https, same host as the manifest), checks SHA-256,
#      unpacks to kiosk-releases\<version>, checks that Python imports it;
#   5. points kiosk.json at it and lets the supervisor restart the kiosk
#      through the pause file (the supervisor re-reads kiosk.json on resume);
#   6. waits up to 150 s for the new service AND the kiosk page to come up;
#      otherwise switches back, remembers the version as bad and never tries
#      it again (a newer version is tried as usual).
#
# Log: C:\ROBI\logs\update.log. Plain ASCII (Windows PowerShell 5.1).

param(
    [string]$Root = 'C:\ROBI',
    # Test hook: skip the "home screen" wait.
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
# Without this Invoke-WebRequest draws a progress bar even with no console;
# as SYSTEM from the Task Scheduler that hung the very first update
# (tablet, 2026-11-19) - and it slows downloads down in any case.
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[Net.ServicePointManager]::DefaultConnectionLimit = 16

$KioskDir = Join-Path $Root 'kiosk'
$ConfigPath = Join-Path $KioskDir 'kiosk.json'
$PauseFile = Join-Path $KioskDir 'pause'
$BadFile = Join-Path $KioskDir 'update-bad.txt'
$Releases = Join-Path $Root 'kiosk-releases'
$LogDir = Join-Path $Root 'logs'
$Log = Join-Path $LogDir 'update.log'
$KioskLog = Join-Path $LogDir 'kiosk.log'
$DefaultUpdateUrl = 'https://vps.itrobotics.com.ua/guide-files/robi/latest.json'

function Write-Log([string]$m) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $PID, $m
    Add-Content -LiteralPath $Log -Value $line -Encoding ASCII
}

function Read-Config {
    return (Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json)
}

function Write-Config($cfg) {
    $json = $cfg | ConvertTo-Json
    [IO.File]::WriteAllText($ConfigPath, $json, (New-Object Text.UTF8Encoding($false)))
}

function Get-Json([string]$url, [int]$timeout = 20) {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -DisableKeepAlive -TimeoutSec $timeout
    return ($r.Content | ConvertFrom-Json)
}

function Get-Health([int]$port) {
    try { return Get-Json "http://127.0.0.1:$port/api/health" 4 } catch { return $null }
}

# Supervisor log lines written after $since that contain $text.
function Test-KioskLog([datetime]$since, [string]$text) {
    if (-not (Test-Path -LiteralPath $KioskLog)) { return $false }
    foreach ($line in (Get-Content -LiteralPath $KioskLog -Tail 60)) {
        if ($line.Length -lt 19) { continue }
        $stamp = [datetime]::MinValue
        if (-not [datetime]::TryParseExact($line.Substring(0, 19), 'yyyy-MM-dd HH:mm:ss', $null, 'None', [ref]$stamp)) { continue }
        if ($stamp -ge $since -and $line.Contains($text)) { return $true }
    }
    return $false
}

# Supervisor stops the kiosk on the pause file and re-reads kiosk.json when it
# disappears. Without a running supervisor (Robi logged off) the new release
# simply starts at the next logon.
function Restart-Kiosk([string]$release) {
    $since = (Get-Date).AddSeconds(-1)
    New-Item -ItemType File -Path $PauseFile -Force | Out-Null
    $t = 0
    while (-not (Test-KioskLog $since 'pause file present') -and $t -lt 30) { Start-Sleep -Seconds 1; $t++ }
    Remove-Item -LiteralPath $PauseFile -Force -ErrorAction SilentlyContinue
    return ($t -lt 30)
}

# New service from $release is up and the kiosk page polls it again.
function Wait-Healthy([string]$release, [int]$port, [datetime]$since, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-KioskLog $since "release $release,") {
            $h = Get-Health $port
            if ($h -and $h.ok -and $null -ne $h.page_age_s -and [double]$h.page_age_s -lt 20) { return $true }
        }
        Start-Sleep -Seconds 3
    }
    return $false
}

try {
    if (-not (Test-Path -LiteralPath $ConfigPath)) { exit 0 }
    $cfg = Read-Config
    $current = [string]$cfg.release
    $port = if ($cfg.port) { [int]$cfg.port } else { 4173 }
    $updateUrl = if ($cfg.update_url) { [string]$cfg.update_url } else { $DefaultUpdateUrl }
    if ($updateUrl -eq 'off') { exit 0 }
    if (Test-Path -LiteralPath $PauseFile) { exit 0 }   # maintenance by a person

    $manifest = Get-Json ($updateUrl + '?t=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
    $version = [string]$manifest.version
    if ($version -notmatch '^[A-Za-z0-9._-]{1,64}$') { throw "bad version in manifest: '$version'" }
    $target = Join-Path $Releases $version
    if ($current -and ((Split-Path -Leaf $current) -eq $version)) { exit 0 }
    if ((Test-Path -LiteralPath $BadFile) -and ((Get-Content -LiteralPath $BadFile) -contains $version)) { exit 0 }

    $manifestHost = ([Uri]$updateUrl).Host
    $zipUri = [Uri][string]$manifest.url
    if ($zipUri.Scheme -ne 'https' -or $zipUri.Host -ne $manifestHost) { throw "release url must be https on $manifestHost" }
    $sha = ([string]$manifest.sha256).ToUpperInvariant()
    if ($sha -notmatch '^[0-9A-F]{64}$') { throw 'bad sha256 in manifest' }

    Write-Log "found $version (current: $(Split-Path -Leaf $current))"
    if (-not $Force) {
        $h = Get-Health $port
        if ($h -and $h.mode -and $h.mode -ne 'home') { Write-Log "update $version waits: screen is '$($h.mode)'"; exit 0 }
    }

    # ---- download, verify, unpack (only once per version) ----
    if (-not (Test-Path -LiteralPath (Join-Path $target 'web\index.html'))) {
        $tmp = Join-Path $env:TEMP ("robi-$version.zip")
        Write-Log "downloading $version"
        Invoke-WebRequest -Uri $zipUri -UseBasicParsing -DisableKeepAlive -TimeoutSec 300 -OutFile $tmp
        $got = (Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($got -ne $sha) { Remove-Item -LiteralPath $tmp -Force; throw "sha256 mismatch for $version" }
        $staging = "$target.part"
        if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
        Expand-Archive -LiteralPath $tmp -DestinationPath $staging -Force
        Remove-Item -LiteralPath $tmp -Force
        foreach ($need in 'web\index.html', 'app\src\robi', 'scripts\kiosk\robi-kiosk.ps1') {
            if (-not (Test-Path -LiteralPath (Join-Path $staging $need))) { throw "release $version has no $need" }
        }
        if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
        Rename-Item -LiteralPath $staging -NewName $version
    }

    # The release must at least import with this tablet's Python before it
    # touches the kiosk.
    Write-Log "checking that $version imports"
    $python = ([string]$cfg.python) -replace 'pythonw\.exe$', 'python.exe'
    $src = Join-Path $target 'app\src'
    $probe = "import sys; sys.path.insert(0, r'$src'); import robi.web.__main__, robi.bootstrap"
    & $python -c $probe 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Add-Content -LiteralPath $BadFile -Value $version -Encoding ASCII
        throw "release $version does not import; marked bad"
    }

    # ---- switch ----
    Write-Log "switching $current -> $target"
    $cfg | Add-Member -NotePropertyName previous_release -NotePropertyValue $current -Force
    $cfg.release = $target
    Write-Config $cfg
    $since = Get-Date
    $supervised = Restart-Kiosk $target
    if (-not $supervised) { Write-Log "no supervisor answered; $version starts at next logon"; exit 0 }

    if (Wait-Healthy $target $port $since 150) {
        Write-Log "updated to $version"
        exit 0
    }

    # ---- roll back ----
    Write-Log "$version did not come up in 150 s; rolling back to $current"
    Add-Content -LiteralPath $BadFile -Value $version -Encoding ASCII
    $cfg = Read-Config
    $cfg.release = $current
    Write-Config $cfg
    $since = Get-Date
    if ((Restart-Kiosk $current) -and (Wait-Healthy $current $port $since 150)) { Write-Log "rolled back to $current" }
    else { Write-Log "rolled back to $current, but it is not healthy yet - the supervisor keeps trying" }
    exit 1
}
catch {
    Write-Log ("update failed: " + $_.Exception.Message)
    exit 1
}
