@echo off
title GG Clips
rem Double-click to open the GG Clips player (and refresh _GG-Titles.html, the saved copy).
python "%~dp0_GG-Titles.py" %*
if errorlevel 1 pause
