@echo off
title ClipShelf
rem Double-click to open ClipShelf in your browser. Keep this window open while you use it,
rem or turn on "Start with Windows" in ClipShelf's settings so it runs in the background.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (python -m clipshelf %*) else (py -3 -m clipshelf %*)
if errorlevel 1 pause
