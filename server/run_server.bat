@echo off
rem Starts the central database receiver (keep this window open).
cd /d "%~dp0"
title NewsScalper DB Server
python db_server.py
pause
