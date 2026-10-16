@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM ==========================================================
REM  apw project report: open the light-style banner deck.
REM
REM    run_slides.bat            open in default browser
REM    run_slides.bat 3          open directly at banner 3
REM
REM  In the page: arrows / swipe switch banners, space toggles
REM  autoplay, F fullscreen, Ctrl+P exports PDF.
REM ==========================================================

if not exist "docs\banner-light.html" goto :nofile

set HASH=
if not "%~1"=="" set HASH=#/%~1
start "" "docs\banner-light.html%HASH%"
echo [run_slides] opened docs\banner-light.html
goto :end

:nofile
echo [run_slides] docs\banner-light.html not found

:end
exit /b 0
