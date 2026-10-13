@echo off
title Cliptrove
rem Double-click to open Cliptrove in your browser. Keep this window open while you use it,
rem or turn on "Start with Windows" in Cliptrove's settings so it runs in the background.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (python -m cliptrove %*) else (py -3 -m cliptrove %*)
if errorlevel 1 pause
