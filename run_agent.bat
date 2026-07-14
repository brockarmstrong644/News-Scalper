@echo off
rem Opens a cmd terminal in the project folder and starts the earnings agent.
cd /d "%~dp0"
title Earnings Agent
python agent.py
echo.
pause
