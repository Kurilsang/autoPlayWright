@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8

REM ==========================================================
REM  apw one-click: run business flows then mail the report.
REM  Any extra arguments are passed through to pytest.
REM
REM    run_and_mail.bat                     flows @ test env + mail w/ zip
REM    run_and_mail.bat --no-mail           run only, no mail
REM    run_and_mail.bat --env fixture       other env (local fixture site)
REM    run_and_mail.bat -k smoke            filter by keyword
REM    run_and_mail.bat --to a@x,b@y        override recipients
REM
REM  Recipients live in configs/notify.local.yaml (gitignored) under
REM  "notify:" -- edit that file to change the list, not this script.
REM
REM  Flows only. "pytest tests" is framework self-test and needs
REM  --apw-env fixture; mixing it with the real env yields false reds.
REM ==========================================================

if not exist ".venv\Scripts\python.exe" goto :novenv

set SENDMAIL=1
set ENVNAME=test
set TOARG=
set CCARG=
set PASSTHRU=

:parse
if "%~1"=="" goto :run
if /i "%~1"=="--no-mail" ( set SENDMAIL=0& shift& goto :parse )
if /i "%~1"=="--env" ( set ENVNAME=%~2& shift& shift& goto :parse )
if /i "%~1"=="--to" ( set TOARG=%~2& shift& shift& goto :parse )
if /i "%~1"=="--cc" ( set CCARG=%~2& shift& shift& goto :parse )
set PASSTHRU=!PASSTHRU! %1
shift
goto :parse

:run
if "%ENVNAME%"=="test" if not exist "configs\envs\test.yaml" goto :noenv
echo [run_and_mail] env=%ENVNAME%
if not "%TOARG%"=="" echo [run_and_mail] to=%TOARG%
if "%TOARG%"=="" echo [run_and_mail] to is read from configs\notify.local.yaml

.venv\Scripts\python.exe -m pytest flows --apw-env %ENVNAME% -p no:randomly %PASSTHRU%
set EXITCODE=%ERRORLEVEL%

REM newest run dir that actually has a summary
set RUNDIR=
for /f "delims=" %%d in ('.venv\Scripts\python.exe -c "from pathlib import Path;c=[p for p in Path('reports').iterdir() if p.is_dir() and p.name[:8].isdigit() and (p/'run-summary.json').exists()];print(max(c,key=lambda p:p.stat().st_mtime) if c else '')"') do set RUNDIR=%%d
if "%RUNDIR%"=="" goto :norun
echo [run_and_mail] report dir: %RUNDIR%

if %SENDMAIL%==0 goto :nomail
set MAILARGS=--summary "%RUNDIR%\run-summary.json" --policy always --report-zip --env-label %ENVNAME%
if not "%TOARG%"=="" set MAILARGS=%MAILARGS% --to %TOARG%
if not "%CCARG%"=="" set MAILARGS=%MAILARGS% --cc %CCARG%
.venv\Scripts\python.exe -m apw.notify %MAILARGS%
if errorlevel 1 echo [run_and_mail] mail failed (test result unaffected; report is in %RUNDIR%)
goto :report

:nomail
echo [run_and_mail] --no-mail: skipped sending
goto :report

:report
echo.
if %EXITCODE%==0 goto :ok
echo [run_and_mail] FAILED - triage evidence in %RUNDIR%
goto :end

:ok
echo [run_and_mail] PASSED - report in %RUNDIR%
goto :end

:noenv
echo [run_and_mail] configs\envs\test.yaml not found (gitignored).
echo                Copy configs\envs\test.example.yaml and fill in the real env.
set EXITCODE=1
goto :end

:norun
echo [run_and_mail] no report dir found under reports\ (run-summary.json missing)
goto :end

:novenv
echo [run_and_mail] .venv not found. Run: python -m venv .venv
echo                 then: .venv\Scripts\pip install -e ".[dev]"
set EXITCODE=1

:end
pause
exit /b %EXITCODE%
