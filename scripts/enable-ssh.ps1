# Provisioning helper: enable OpenSSH server on the ROBI device and trust the
# workstation key, so configuration (roadmap M1, step 7) can be done remotely.
#
# Why this exists: the tablet has no physical keyboard, and typing the setup
# commands on the on-screen keyboard is slow and error-prone. Copy this file
# together with enable-ssh.cmd onto a flash drive, then run the .cmd on the
# device - it elevates itself and does everything in one pass.
#
# Safe to run repeatedly: nothing here duplicates a key or a firewall rule.
#
# The value below is a PUBLIC key and is not a secret. The matching private key
# lives only on the workstation that manages the device (~/.ssh/robi_tablet).
# To trust a different workstation, replace this line with that machine's
# public key.
#
# See docs/provisioning.md for the full procedure.

$ErrorActionPreference = 'Stop'

$key = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJuROpFstasEATzGnam0ugb7nmWth74FXlWIm/NAjrHX robi-tablet'

try {
    Write-Host 'Installing OpenSSH Server...' -ForegroundColor Cyan
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
    Set-Service -Name sshd -StartupType Automatic
    Start-Service sshd -ErrorAction SilentlyContinue

    # sshd creates C:\ProgramData\ssh on its first start, while generating host
    # keys. On a slow device that takes longer than Start-Service waits, so the
    # directory is not there yet when we need it - hence both the wait and the
    # explicit New-Item below.
    Write-Host 'Waiting for sshd to come up...' -ForegroundColor Cyan
    for ($i = 0; $i -lt 60; $i++) {
        if ((Get-Service sshd).Status -eq 'Running') { break }
        Start-Sleep -Seconds 2
    }
    $state = (Get-Service sshd).Status
    Write-Host ("sshd is " + $state)

    Write-Host 'Trusting workstation key...' -ForegroundColor Cyan
    $dir = Join-Path $env:ProgramData 'ssh'
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    # For accounts in the Administrators group Windows OpenSSH reads this file,
    # not the user profile, and refuses it if the ACL is wider than
    # Administrators + SYSTEM. Encoding must be ascii: PowerShell 5.1 would
    # write a BOM with -Encoding utf8 and the first key would stop parsing.
    $f = Join-Path $dir 'administrators_authorized_keys'
    if (-not (Test-Path $f)) { New-Item -ItemType File -Path $f | Out-Null }
    if (-not (Select-String -Path $f -SimpleMatch $key -Quiet -ErrorAction SilentlyContinue)) {
        Add-Content -Path $f -Value $key -Encoding ascii
    }
    icacls $f /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null

    Write-Host 'Firewall...' -ForegroundColor Cyan
    if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' `
            -DisplayName 'OpenSSH Server (sshd)' -Enabled True `
            -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
    }

    # On a Public profile the inbound rule does not apply and the device stays
    # unreachable on the local network.
    Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Public' } | ForEach-Object {
        Set-NetConnectionProfile -InterfaceAlias $_.InterfaceAlias -NetworkCategory Private
    }

    Restart-Service sshd

    Write-Host ''
    Write-Host '=====================================' -ForegroundColor Green
    Write-Host '  SSH READY - report these values:' -ForegroundColor Green
    Write-Host '=====================================' -ForegroundColor Green
    Write-Host ''
    'USER : ' + (whoami)
    Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        ForEach-Object { 'IP   : ' + $_.IPAddress + '  (' + $_.InterfaceAlias + ')' }
    Get-NetConnectionProfile | ForEach-Object { 'NET  : ' + $_.InterfaceAlias + ' -> ' + $_.NetworkCategory }
    'SSHD : ' + (Get-Service sshd).Status
}
catch {
    Write-Host ''
    Write-Host ('FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Run this file again - it is safe to repeat.' -ForegroundColor Yellow
}

# No Read-Host here: the device has no physical keyboard, and the touch keyboard
# does not open by itself in a console window. The window simply stays up long
# enough to read or photograph, and can be closed with the X at any time.
Write-Host ''
Write-Host 'Close this window with the X when done.' -ForegroundColor DarkGray
Start-Sleep -Seconds 900
