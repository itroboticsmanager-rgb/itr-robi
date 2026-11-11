@echo off
rem ROBI kiosk: emergency unlock - gives the Robi account its normal desktop back, then restarts.
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0setup\install-on-tablet.ps1\" -Unlock'"