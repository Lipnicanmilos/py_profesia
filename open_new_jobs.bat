@echo off
title Otvarac pracovnych ponuk
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" open_new_jobs.py
pause
