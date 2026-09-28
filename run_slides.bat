@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM ==========================================================
REM  apw project report: open the banner-style web deck.
REM
REM    run_slides.bat            open banner deck in browser
REM    run_slides.bat 3          open directly at banner 3
REM    run_slides.bat light      open the light-style banner deck
REM    run_slides.bat deck       open the old PPT-style deck
REM
REM  In the page: arrows / swipe switch banners, space toggles
REM  autoplay, F fullscreen, Ctrl+P exports PDF.
REM ==========================================================

if not exist "docs\banner.html" goto :nofile

if /i "%~1"=="deck" (
  start "" "docs\slides.html"
  echo [run_slides] opened docs\slides.html
  goto :end
)

if /i "%~1"=="light" (
  start "" "docs\banner-light.html"
  echo [run_slides] opened docs\banner-light.html
  goto :end
)

set HASH=
if not "%~1"=="" set HASH=#/%~1
start "" "docs\banner.html%HASH%"
echo [run_slides] opened docs\banner.html
goto :end

:nofile
echo [run_slides] docs\banner.html not found

:end
exit /b 0
