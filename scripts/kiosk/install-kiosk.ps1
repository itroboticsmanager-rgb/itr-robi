# ROBI kiosk installer (D-064). Run as administrator (robiadmin).
#
#   install-kiosk.ps1 -Release C:\ROBI\kiosk-releases\2026-11-11-kiosk
#   install-kiosk.ps1 -Release ... -StartNow     # also (re)start the guardian now
#   install-kiosk.ps1 -Unlock                     # give Robi explorer back, lift lockdown
#   install-kiosk.ps1 -Uninstall                  # -Unlock + remove the task
#
# Lockdown for the kiosk user `Robi` (takes effect at its NEXT logon):
#   * shell = the supervisor instead of explorer.exe: no taskbar, no Start,
#     no Win key, no desktop to fall back to;
#   * guardian task every minute restarts the supervisor if it ever dies;
#   * Ctrl+Alt+Del screen: no Task Manager, lock, sign out, password change or
#     power - only "Switch user", which needs the robiadmin password;
#   * Edge (for Robi only): only http://127.0.0.1:<port>/, localhost and the
#     -AllowOrigin sites (CRM enrollment form, D-065), no downloads, file
#     dialogs, printing or DevTools;
#   * no notifications, edge swipes, lock screen, widgets, tips, crash dialogs;
#   * power / sleep buttons do nothing (a long 10 s press still forces off).
#
# Idempotent. Plain ASCII on purpose (Windows PowerShell 5.1 + no BOM = ANSI).

[CmdletBinding(DefaultParameterSetName = 'Install')]
param(
    [Parameter(ParameterSetName = 'Install', Mandatory = $true)]
    [string]$Release,
    [Parameter(ParameterSetName = 'Install')]
    [int]$Port = 4173,
    [Parameter(ParameterSetName = 'Install')]
    [switch]$Offline,
    # Sites the kiosk Edge may open besides the local kiosk page. The CRM is
    # needed for the enrollment form shown in a frame (D-065).
    [Parameter(ParameterSetName = 'Install')]
    [string[]]$AllowOrigin = @('https://crm.itrobotics.com.ua'),
    [Parameter(ParameterSetName = 'Install')]
    [switch]$SkipPolicies,
    # Keep explorer as Robi's shell (task-only autostart, softer lock).
    [Parameter(ParameterSetName = 'Install')]
    [switch]$NoCustomShell,
    [Parameter(ParameterSetName = 'Install')]
    [switch]$StartNow,
    [Parameter(ParameterSetName = 'Unlock', Mandatory = $true)]
    [switch]$Unlock,
    [Parameter(ParameterSetName = 'Uninstall', Mandatory = $true)]
    [switch]$Uninstall,
    [string]$KioskUser = 'Robi',
    [string]$Root = 'C:\ROBI'
)

$ErrorActionPreference = 'Stop'
$TaskName = 'ROBI Kiosk'
$KioskDir = Join-Path $Root 'kiosk'
$LogDir = Join-Path $Root 'logs'
$Supervisor = Join-Path $KioskDir 'robi-kiosk.ps1'
$Conhost = Join-Path $env:WINDIR 'System32\conhost.exe'
$Launch = "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Supervisor`""

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as administrator (robiadmin, elevated PowerShell).'
}

function Say([string]$m) { Write-Host "[robi-kiosk] $m" }

$account = "$env:COMPUTERNAME\$KioskUser"
$sid = (New-Object Security.Principal.NTAccount($account)).Translate([Security.Principal.SecurityIdentifier]).Value
if ($sid -eq [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) {
    throw "Do not lock down the account you are running as ($account)."
}
$profilePath = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$sid").ProfileImagePath

function Set-Dword([string]$Path, [string]$Name, [int]$Value) {
    if (-not (Test-Path -LiteralPath $Path)) { New-Item -Path $Path -Force | Out-Null }
    try { New-ItemProperty -LiteralPath $Path -Name $Name -Value $Value -PropertyType DWord -Force | Out-Null }
    catch { Say "warning: could not set $Path\$Name ($($_.Exception.Message))" }
}
function Set-Str([string]$Path, [string]$Name, [string]$Value) {
    if (-not (Test-Path -LiteralPath $Path)) { New-Item -Path $Path -Force | Out-Null }
    New-ItemProperty -LiteralPath $Path -Name $Name -Value $Value -PropertyType String -Force | Out-Null
}
function Remove-Val([string]$Path, [string]$Name) {
    if (Test-Path -LiteralPath $Path) { Remove-ItemProperty -LiteralPath $Path -Name $Name -ErrorAction SilentlyContinue }
}

# Kiosk user's hive: loaded while Robi is logged on (autologin), else load it.
function Invoke-WithUserHive([scriptblock]$Body) {
    $hku = "Registry::HKEY_USERS\$sid"
    $loadedHere = $false
    if (-not (Test-Path -LiteralPath $hku)) {
        & reg.exe load 'HKU\ROBI_KIOSK_TMP' (Join-Path $profilePath 'NTUSER.DAT') | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "could not load the registry hive of $account" }
        $hku = 'Registry::HKEY_USERS\ROBI_KIOSK_TMP'
        $loadedHere = $true
    }
    try { & $Body "$hku\Software" }
    finally {
        if ($loadedHere) {
            [GC]::Collect(); [GC]::WaitForPendingFinalizers()
            & reg.exe unload 'HKU\ROBI_KIOSK_TMP' | Out-Null
        }
    }
}

$UserLockValues = @(
    @('Microsoft\Windows\CurrentVersion\Policies\System', 'DisableTaskMgr'),
    @('Microsoft\Windows\CurrentVersion\Policies\System', 'DisableLockWorkstation'),
    @('Microsoft\Windows\CurrentVersion\Policies\System', 'DisableChangePassword'),
    @('Microsoft\Windows\CurrentVersion\Policies\Explorer', 'NoLogoff'),
    @('Microsoft\Windows\CurrentVersion\Policies\Explorer', 'NoClose'),
    @('Microsoft\Windows\CurrentVersion\Policies\Explorer', 'NoWinKeys'),
    @('Microsoft\Windows\CurrentVersion\Policies\Explorer', 'NoRun')
)

function Unlock-User {
    Invoke-WithUserHive {
        param($u)
        Remove-Val "$u\Microsoft\Windows NT\CurrentVersion\Winlogon" 'Shell'
        foreach ($v in $UserLockValues) { Remove-Val "$u\$($v[0])" $v[1] }
        if (Test-Path -LiteralPath "$u\Policies\Microsoft\Edge") { Remove-Item -LiteralPath "$u\Policies\Microsoft\Edge" -Recurse -Force }
    }
    Say "lockdown lifted for $account (explorer comes back at its next logon); notification policies kept"
}

if ($Unlock -or $Uninstall) {
    Unlock-User
    if ($Uninstall) {
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Say "task '$TaskName' removed"
        }
    }
    Say 'sign Robi out or restart to apply'
    exit 0
}

# ------------------------------------------------------------- 1. files ---

$Release = (Resolve-Path -LiteralPath $Release).Path
if (-not (Test-Path -LiteralPath (Join-Path $Release 'web\index.html'))) { throw "not a kiosk release (no web\index.html): $Release" }
if (-not (Test-Path -LiteralPath (Join-Path $Release 'app\src\robi'))) { throw "not a kiosk release (no app\src\robi): $Release" }
$python = Join-Path $Root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "python venv not found: $python" }
$deviceConfig = Join-Path $Root 'device.toml'
if (-not (Test-Path -LiteralPath $deviceConfig)) { throw "device config not found: $deviceConfig" }

New-Item -ItemType Directory -Path $KioskDir, $LogDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'robi-kiosk.ps1') -Destination $Supervisor -Force
$cfg = [ordered]@{
    release = $Release; port = $Port; python = $python
    device_config = $deviceConfig; log_dir = $LogDir; offline = [bool]$Offline
}
[IO.File]::WriteAllText((Join-Path $KioskDir 'kiosk.json'), ($cfg | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
Say "kiosk.json -> release $Release, port $Port"

# Robi writes logs only. Supervisor, kiosk.json and the pause file stay
# admin-only, so nobody at the desk can switch the kiosk off or repoint it.
# (Folders under C:\ inherit "Authenticated Users: Modify", hence the reset.)
# Folder only, then files back to plain inheritance. Do NOT add /T to the
# first call: it strips inheritance from the files but cannot put the
# (OI)(CI) grants on them, leaving files nobody can read (2026-11-11, tablet).
& icacls.exe $KioskDir /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' /Q | Out-Null
& icacls.exe (Join-Path $KioskDir '*') /reset /T /Q | Out-Null
if (-not (Get-Content -LiteralPath (Join-Path $KioskDir 'kiosk.json') -Raw)) { throw 'kiosk.json unreadable after setting permissions' }
& icacls.exe $LogDir /grant "*${sid}:(OI)(CI)M" /T /Q | Out-Null

# ------------------------------------------------------------ 2. policy ---

if (-not $SkipPolicies) {
    $hklm = 'HKLM:\SOFTWARE'
    Set-Dword "$hklm\Policies\Microsoft\Windows\EdgeUI" 'AllowEdgeSwipe' 0
    Set-Dword "$hklm\Policies\Microsoft\Windows\Personalization" 'NoLockScreen' 1
    Set-Dword "$hklm\Policies\Microsoft\Dsh" 'AllowNewsAndInterests' 0
    Set-Dword "$hklm\Policies\Microsoft\Windows\CloudContent" 'DisableWindowsConsumerFeatures' 1
    Set-Dword "$hklm\Policies\Microsoft\Windows\CloudContent" 'DisableSoftLanding' 1
    Set-Dword "$hklm\Policies\Microsoft\Windows\CloudContent" 'DisableConsumerAccountStateContent' 1
    Set-Dword "$hklm\Policies\Microsoft\Windows\WindowsUpdate" 'SetUpdateNotificationLevel' 1
    Set-Dword "$hklm\Policies\Microsoft\Windows\WindowsUpdate" 'UpdateNotificationLevel' 2
    Set-Dword "$hklm\Microsoft\Windows\Windows Error Reporting" 'DontShowUI' 1
    Set-Dword "$hklm\Microsoft\Windows\CurrentVersion\AutoRotation" 'Enable' 0

    # Edge, all users: harmless defaults (admin's Edge keeps working normally).
    $edge = "$hklm\Policies\Microsoft\Edge"
    foreach ($p in @(
        @('HideFirstRunExperience', 1), @('TranslateEnabled', 0), @('PasswordManagerEnabled', 0),
        @('AutofillAddressEnabled', 0), @('AutofillCreditCardEnabled', 0), @('StartupBoostEnabled', 0),
        @('HubsSidebarEnabled', 0), @('EdgeShoppingAssistantEnabled', 0), @('ShowRecommendationsEnabled', 0),
        @('PromotionalTabsEnabled', 0), @('SpotlightExperiencesAndRecommendationsEnabled', 0),
        @('ShowPDFDefaultRecommendationsEnabled', 0)
    )) { Set-Dword $edge $p[0] $p[1] }

    # Power and sleep buttons do nothing, on mains and on battery.
    foreach ($s in 'PBUTTONACTION', 'SBUTTONACTION') {
        & powercfg.exe /setacvalueindex SCHEME_CURRENT SUB_BUTTONS $s 0 | Out-Null
        & powercfg.exe /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS $s 0 | Out-Null
    }
    & powercfg.exe /setactive SCHEME_CURRENT | Out-Null
    Say 'machine policies applied'

    Invoke-WithUserHive {
        param($u)
        Set-Dword "$u\Policies\Microsoft\Windows\CurrentVersion\PushNotifications" 'NoToastApplicationNotification' 1
        Set-Dword "$u\Policies\Microsoft\Windows\CurrentVersion\PushNotifications" 'NoTileApplicationNotification' 1
        Set-Dword "$u\Microsoft\Windows\CurrentVersion\PushNotifications" 'ToastEnabled' 0
        Set-Dword "$u\Policies\Microsoft\Windows\Explorer" 'DisableNotificationCenter' 1
        Set-Dword "$u\Policies\Microsoft\Windows\CloudContent" 'DisableWindowsSpotlightFeatures' 1
        Set-Dword "$u\Policies\Microsoft\Windows\CloudContent" 'DisableTailoredExperiencesWithDiagnosticData' 1
        foreach ($n in 'SubscribedContent-338389Enabled', 'SubscribedContent-338388Enabled', 'SubscribedContent-310093Enabled',
                       'SubscribedContent-353698Enabled', 'SystemPaneSuggestionsEnabled', 'SoftLandingEnabled', 'SilentInstalledAppsEnabled') {
            Set-Dword "$u\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" $n 0
        }
        Set-Dword "$u\Microsoft\Windows\CurrentVersion\UserProfileEngagement" 'ScoobeSystemSettingEnabled' 0

        # Lockdown of the Ctrl+Alt+Del screen and shortcuts.
        foreach ($v in $UserLockValues) { Set-Dword "$u\$($v[0])" $v[1] 1 }

        # Edge, kiosk user only: nowhere but the local kiosk page.
        $ue = "$u\Policies\Microsoft\Edge"
        if (Test-Path -LiteralPath $ue) { Remove-Item -LiteralPath $ue -Recurse -Force }
        Set-Str "$ue\URLBlocklist" '1' '*'
        Set-Str "$ue\URLAllowlist" '1' "http://127.0.0.1:$Port"
        Set-Str "$ue\URLAllowlist" '2' "http://localhost:$Port"
        $n = 3
        foreach ($o in $AllowOrigin) {
            if ($o -match '^https://[A-Za-z0-9.-]+(:\d+)?$') { Set-Str "$ue\URLAllowlist" ([string]$n) $o; $n++ }
            else { Say "warning: -AllowOrigin '$o' ignored (expected https://host)" }
        }
        foreach ($p in @(
            @('DownloadRestrictions', 3), @('AllowFileSelectionDialogs', 0), @('PrintingEnabled', 0),
            @('DeveloperToolsAvailability', 2), @('BrowserSignin', 0), @('DefaultNotificationsSetting', 2),
            @('BrowserAddProfileEnabled', 0), @('BrowserGuestModeEnabled', 0)
            # No InPrivateModeAvailability: Edge kiosk itself runs InPrivate.
        )) { Set-Dword $ue $p[0] $p[1] }

        if ($NoCustomShell) {
            Remove-Val "$u\Microsoft\Windows NT\CurrentVersion\Winlogon" 'Shell'
        } else {
            Set-Str "$u\Microsoft\Windows NT\CurrentVersion\Winlogon" 'Shell' "`"$Conhost`" $Launch"
        }
    }
    if ($NoCustomShell) { Say "policies for $account applied; shell stays explorer" }
    else { Say "policies for $account applied; shell = ROBI supervisor (from next logon)" }
}

# ------------------------------------------------------------ 3. task -----

$action = New-ScheduledTaskAction -Execute $Conhost -Argument $Launch -WorkingDirectory $KioskDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
# Guardian: fire every minute for as long as Robi is logged on. A tick that
# finds the supervisor alive exits at once (mutex); a tick after a crash
# becomes the new supervisor.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1)).Repetition
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $taskPrincipal `
    -Settings $settings -Description 'ROBI kiosk guardian: keeps the supervisor alive (D-064)' -Force | Out-Null
Say "task '$TaskName' registered for $account"

$startupDirs = @((Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\StartUp'),
                 (Join-Path $profilePath 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup'))
foreach ($d in $startupDirs) {
    if (Test-Path -LiteralPath $d) {
        Get-ChildItem -LiteralPath $d -File | Where-Object { $_.Name -match 'robi|kiosk' } | ForEach-Object {
            Move-Item -LiteralPath $_.FullName -Destination (Join-Path $KioskDir ('old-autostart-' + $_.Name)) -Force
            Say "old autostart entry moved out of Startup: $($_.Name)"
        }
    }
}

if ($StartNow) {
    $pause = Join-Path $KioskDir 'pause'
    if (Test-Path -LiteralPath $pause) { Remove-Item -LiteralPath $pause -Force; Say 'pause file removed' }
    Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
        Where-Object { $_.CommandLine -like '*robi-kiosk.ps1*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-ScheduledTask -TaskName $TaskName
    Say "guardian started (works only while $account is logged on)"
}

Say 'done. Logs: C:\ROBI\logs\kiosk.log. Maintenance: create C:\ROBI\kiosk\pause'
