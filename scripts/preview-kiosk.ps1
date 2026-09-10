param([int]$Port = 4174)
$ErrorActionPreference = 'Stop'
$robiRoot = Split-Path -Parent $PSScriptRoot
$robiPreview = Join-Path $robiRoot 'artifacts/kiosk-preview'
New-Item -ItemType Directory -Path $robiPreview -Force | Out-Null
Push-Location (Join-Path $robiRoot 'prototypes/robi-room')
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Kiosk build failed.' }
} finally { Pop-Location }
$robiContent = (Join-Path $robiRoot 'app/config/content.example.toml').Replace('\', '/')
$robiConfig = Join-Path $robiPreview 'device.toml'
$robiConfigText = @"
device_id = "robi-local-preview"
site = "reception"
[crm]
enabled = false
[content]
path = "$robiContent"
timeout_s = 45
[features]
camera = false
nfc = false
"@
[IO.File]::WriteAllText($robiConfig, $robiConfigText, [Text.UTF8Encoding]::new($false))
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Use -Port with a free port."
}
$robiPython = Join-Path $robiRoot '.venv/Scripts/pythonw.exe'
$robiCode = "import sys; sys.path.insert(0, r'$robiRoot/app/src'); from robi.web.__main__ import main; main()"
$robiArgs = @('-c', ('"' + $robiCode + '"'), '--config', ('"' + $robiConfig + '"'), '--root', ('"' + (Join-Path $robiRoot 'prototypes/robi-room/dist') + '"'), '--port', $Port, '--offline')
$robiProcess = Start-Process -FilePath $robiPython -ArgumentList $robiArgs -WorkingDirectory $robiRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $robiPreview 'service.log') -RedirectStandardError (Join-Path $robiPreview 'service-error.log')
$robiProcess.Id | Set-Content (Join-Path $robiPreview 'service.pid')
Write-Output "Kiosk preview: http://127.0.0.1:$Port/ (PID $($robiProcess.Id))"
