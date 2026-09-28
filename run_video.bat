@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM ==========================================================
REM  apw report video: one-click Remotion render.
REM  Any extra arguments are passed through to the renderer.
REM
REM    run_video.bat                  render video\out\apw-report.mp4
REM    run_video.bat preview          open Remotion Studio instead
REM    run_video.bat --codec=h264     extra flags go to remotion render
REM ==========================================================

where node >nul 2>nul
if errorlevel 1 goto :nonode

cd /d "%~dp0video"

if "%~1"=="preview" goto :preview

if not exist "node_modules" (
  call :install
  if errorlevel 1 goto :end
)

echo [run_video] rendering apw-report.mp4  (first run downloads Chrome Headless Shell, be patient)
npx remotion render ApwReport out\apw-report.mp4 %*
set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE%==0 goto :ok
echo [run_video] FAILED - debug with: run_video.bat preview
goto :end

:ok
echo [run_video] PASSED - opening video\out\apw-report.mp4
start "" "out\apw-report.mp4"
goto :end

:preview
echo [run_video] opening Remotion Studio (http://localhost:3000) ...
call npm run dev
set EXITCODE=%ERRORLEVEL%
goto :end

:install
echo [run_video] first run - installing node dependencies ...
call npm install --no-audit --no-fund
exit /b %ERRORLEVEL%

:nonode
echo [run_video] node/npm not found. Install Node.js LTS from https://nodejs.org
set EXITCODE=1

:end
pause
exit /b %EXITCODE%
