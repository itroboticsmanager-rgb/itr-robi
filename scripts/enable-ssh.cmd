@echo off
rem Launcher for enable-ssh.ps1 - see docs/provisioning.md.
rem Double-click this on the device: it asks for elevation (one tap on the UAC
rem prompt, no keyboard needed) and then runs the PowerShell script next to it.
title ROBI - enable SSH
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%~dp0enable-ssh.ps1'"
