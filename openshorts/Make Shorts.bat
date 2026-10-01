@echo off
rem Double-click: paste a YouTube link, get the shorts in the "shorts" folder next to this file.
rem Keep this file next to make_shorts.ps1. Colab (cell 1) must be running.
cd /d "%~dp0"
set /p URL=Paste the YouTube link and press Enter:
if "%URL%"=="" goto :eof
set /p SERVER=New Colab link? (press Enter to reuse the last one):
if "%SERVER%"=="" (
  powershell -ExecutionPolicy Bypass -File "%~dp0make_shorts.ps1" -Url "%URL%" -OutDir "%~dp0shorts"
) else (
  powershell -ExecutionPolicy Bypass -File "%~dp0make_shorts.ps1" -Url "%URL%" -Server "%SERVER%" -OutDir "%~dp0shorts"
)
echo.
pause