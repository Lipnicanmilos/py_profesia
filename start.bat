@echo off
REM Lokalne spustenie oboch scraperov (Profesia + LinkedIn). Pouzije .venv vedla skriptu.
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" py_search.py
"%PY%" linkedin_search.py
echo.
echo Ponuky su v subore ponuky.txt
pause
