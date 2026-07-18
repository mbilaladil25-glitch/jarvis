@echo off
title J.A.R.V.I.S Web UI
cd /d "%~dp0"
start /min python web_ui.py
timeout /t 3 /nobreak >nul
start http://localhost:5000
