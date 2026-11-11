@echo off
rem ROBI kiosk: install + lock. Asks for the robiadmin password (UAC), then restarts the tablet.
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0setup\install-on-tablet.ps1\"'"