# Runs on the ROBI tablet from the USB stick, elevated (INSTALL.cmd).
# Copies the release, checks it against the tablet's Python, installs the
# locked kiosk and restarts. Everything is logged to <usb>\results.
# Plain ASCII on purpose.

param([switch]$Unlock)
$ErrorActionPreference = 'Stop'

# A finger on the console window turns on QuickEdit selection, which PAUSES
# the script until the selection is cancelled (seen on the tablet). Off.
try {
    Add-Type -Namespace RobiUsb -Name Con -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern System.IntPtr GetStdHandle(int h);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(System.IntPtr h, out uint m);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(System.IntPtr h, uint m);
'@
    $h = [RobiUsb.Con]::GetStdHandle(-10); $m = 0
    if ([RobiUsb.Con]::GetConsoleMode($h, [ref]$m)) { [void][RobiUsb.Con]::SetConsoleMode($h, (($m -band (-bnot 0x40)) -bor 0x80)) }
} catch { }
$usb = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$results = Join-Path $usb 'results'
New-Item -ItemType Directory -Force $results | Out-Null
$mode = if ($Unlock) { 'unlock' } else { 'install' }
Start-Transcript -Path (Join-Path $results "$mode-$env:COMPUTERNAME-$stamp.txt") | Out-Null

function Done([bool]$ok, [string]$msg) {
    Write-Host ''
    if ($ok) { Write-Host "OK: $msg" -ForegroundColor Green } else { Write-Host "FAILED: $msg" -ForegroundColor Red }
    Stop-Transcript | Out-Null
    if (-not $ok) { Read-Host 'Press Enter to close' | Out-Null; exit 1 }
}

try {
    Write-Host "ROBI kiosk $mode, computer $env:COMPUTERNAME, user $env:USERNAME, usb $usb"
    $installer = Join-Path $usb 'robi-release\scripts\kiosk\install-kiosk.ps1'

    if ($Unlock) {
        & $installer -Unlock
        Done $true 'lockdown lifted. Restarting in 30 s.'
        & shutdown.exe /r /t 30 /c 'ROBI: kiosk unlocked, restarting'
        exit 0
    }

    # 1. What the tablet must already have (provisioning steps 7.x).
    $root = 'C:\ROBI'
    $py = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) { Done $false "no Python venv at $py - the kiosk was never set up on this tablet" }
    if (-not (Test-Path (Join-Path $root 'device.toml'))) { Done $false 'no C:\ROBI\device.toml (device secret and CRM settings)' }
    Write-Host ("python: " + (& $py --version))

    # 2. Copy the release next to the previous ones (they stay as rollback).
    $rel = Join-Path $root "kiosk-releases\$stamp-usb"
    & robocopy.exe (Join-Path $usb 'robi-release') $rel /E /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { Done $false "robocopy failed ($LASTEXITCODE)" }
    Write-Host "release copied to $rel"

    # 3. Optional scanner decoder; without it the scan button simply hides.
    & $py -m pip install --no-index --find-links (Join-Path $usb 'wheels') 'zxing-cpp>=3.1,<4' -q 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { Write-Host 'warning: zxing-cpp not installed, scanner will stay hidden' -ForegroundColor Yellow }

    # 4. Smoke test BEFORE locking anything: the new code must import and
    #    parse this tablet's device.toml. A broken release must not end up
    #    as the only thing on a locked screen.
    $src = Join-Path $rel 'app\src'
    $code = "import sys; sys.path.insert(0, r'$src'); from robi.config import Config; import robi.web.service, robi.bootstrap; Config.load(r'C:\ROBI\device.toml'); print('smoke ok')"
    & $py -c $code 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { Done $false 'new release does not start with this tablet Python/config - nothing was locked' }

    # 5. Kiosk + lockdown.
    & $installer -Release $rel
    Write-Host ''
    Write-Host '--- state'
    Get-ScheduledTask -TaskName 'ROBI Kiosk' | Select-Object TaskName, State | Format-Table | Out-Host
    Get-Content 'C:\ROBI\kiosk\kiosk.json' | Out-Host

    Done $true 'kiosk installed and locked. Restarting in 30 s; after login ROBI opens by itself.'
    & shutdown.exe /r /t 30 /c 'ROBI: kiosk installed, restarting'
} catch {
    Done $false $_.Exception.Message
}
