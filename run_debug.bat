@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

REM ==========================================================
REM  apw debug runner: visible browser + 250ms slow motion.
REM  Any extra arguments are passed through to pytest.
REM
REM    run_debug.bat                        flows on real test env
REM    run_debug.bat --apw-env fixture      flows on local fixture env
REM    run_debug.bat -k smoke               filter by keyword
REM    run_debug.bat --apw-slowmo 500       change slow-mo speed
REM ==========================================================

if not exist ".venv\Scripts\pytest.exe" goto :novenv

.venv\Scripts\pytest flows --apw-env test --apw-headed --apw-slowmo 250 %*
set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE%==0 goto :ok
echo [run_debug] FAILED - see the newest dir under reports\ for triage evidence
goto :end

:ok
echo [run_debug] PASSED - see the newest dir under reports\ for the report
goto :end

:novenv
echo [run_debug] .venv not found. Run: python -m venv .venv
echo              then: .venv\Scripts\pip install -e ".[dev]"
set EXITCODE=1

:end
pause
exit /b %EXITCODE%
