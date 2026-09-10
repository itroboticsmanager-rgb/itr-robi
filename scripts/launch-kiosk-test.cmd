@echo off
setlocal
set "ROBI_RELEASE=%~dp0"

REM Isolated preview: the existing ROBI.cmd and ROBI-3D.cmd stay intact.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*robi.web*--port*4174*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
start "" "C:\ROBI\.venv\Scripts\pythonw.exe" -c "import sys; sys.path.insert(0, r'%ROBI_RELEASE%app\src'); from robi.web.__main__ import main; main()" --config "C:\ROBI\device.toml" --root "%ROBI_RELEASE%web" --port 4174

powershell -NoProfile -Command "$ready=$false; for($i=0;$i -lt 40;$i++){ try { Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:4174/api/snapshot' -TimeoutSec 1 | Out-Null; $ready=$true; break } catch { Start-Sleep -Milliseconds 250 } }; if(-not $ready){ exit 1 }"
if errorlevel 1 (
  powershell -NoProfile -WindowStyle Hidden -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('ROBI could not start. Please contact the administrator.', 'ROBI') | Out-Null"
  exit /b 1
)

start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --kiosk http://127.0.0.1:4174/ --edge-kiosk-type=fullscreen --no-first-run --overscroll-history-navigation=0
