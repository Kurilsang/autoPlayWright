@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

REM ==========================================================
REM  apw 全量调试运行器：调试模式（页面可见 + 慢动作）跑全部用例。
REM  阶段：P1 框架自测 → P2 真实环境登录冒烟 → P3 夹具样例链路
REM        → P4 网页端业务链路 → P5 桌面端业务链路（自动保障 CDP）。
REM
REM  用法：
REM    run_full_debug.bat                  全量执行（web + 桌面端）
REM    run_full_debug.bat --co -q          只收集不执行（快速体检脚本/环境）
REM    run_full_debug.bat -k smoke         透传 pytest 参数到每个阶段
REM    set APW_SLOWMO=500 调慢动作（默认 250ms）
REM
REM  桌面客户端可执行文件来源（优先级从高到低）：
REM    1. 环境变量 APW_DESKTOP_EXE
REM    2. configs\desktop.local.bat（本地配置，gitignored；
REM       模板见 configs\desktop.local.example.bat）
REM
REM  桌面端 CDP 保障逻辑（P5 前执行）：
REM    探测 CDP 端口未开 → 强制结束客户端进程
REM    → 带 --remote-debugging-port=9333 重新启动 → 轮询等 CDP 就绪。
REM ==========================================================

set "CDP_PORT=9333"
set "CDP_URL=http://127.0.0.1:%CDP_PORT%"
REM Electron 宿主终端会把 ELECTRON_RUN_AS_NODE=1 传给子进程，导致客户端
REM 以纯 Node 启动（拒绝调试参数并立即退出）——启动客户端前先清掉。
set "ELECTRON_RUN_AS_NODE="
if not defined APW_SLOWMO set "APW_SLOWMO=250"
set "EXTRA_ARGS=%*"
set "FAILED="
set EXITCODE=0
set /a PHASE_NO=0

if not exist ".venv\Scripts\pytest.exe" goto :novenv
if not exist "configs\envs\test.yaml" goto :noenv

REM ---- 解析桌面客户端可执行文件 ----
if defined APW_DESKTOP_EXE goto :exe_ok
if exist "configs\desktop.local.bat" call "configs\desktop.local.bat"
if defined APW_DESKTOP_EXE goto :exe_ok
goto :noexe

:exe_ok
if not exist "%APW_DESKTOP_EXE%" goto :noexe
for %%I in ("%APW_DESKTOP_EXE%") do (
    set "APP_DIR=%%~dpI"
    set "APP_EXE_NAME=%%~nxI"
)

REM ==========================================================
REM  P1 框架自测（本地夹具站点，浏览器端到端）
REM ==========================================================
set /a PHASE_NO+=1
echo.
echo [run_full] ========== 阶段 %PHASE_NO%：框架自测（fixture） ==========
call :run tests
if errorlevel 1 set "FAILED=%FAILED% %PHASE_NO%:tests"

REM ==========================================================
REM  P2 真实环境登录冒烟（仅 test 环境执行的连通用例）
REM ==========================================================
set /a PHASE_NO+=1
echo.
echo [run_full] ========== 阶段 %PHASE_NO%：登录冒烟（test） ==========
call :run "tests\test_real_login.py" test
if errorlevel 1 set "FAILED=%FAILED% %PHASE_NO%:test_real_login"

REM ==========================================================
REM  P3 夹具样例业务链路（fixture）
REM ==========================================================
set /a PHASE_NO+=1
echo.
echo [run_full] ========== 阶段 %PHASE_NO%：样例链路（fixture） ==========
call :run flows fixture
if errorlevel 1 set "FAILED=%FAILED% %PHASE_NO%:flows/fixture"

REM ==========================================================
REM  P4 网页端业务链路（真实测试环境；桌面端专属链路自动 skip 留痕）
REM ==========================================================
set /a PHASE_NO+=1
echo.
echo [run_full] ========== 阶段 %PHASE_NO%：网页端业务链路（test） ==========
call :run flows test
if errorlevel 1 set "FAILED=%FAILED% %PHASE_NO%:flows/test"

REM ==========================================================
REM  P5 桌面端业务链路（CDP attach 客户端；网页端专属链路自动 skip 留痕）
REM ==========================================================
set /a PHASE_NO+=1
echo.
echo [run_full] ========== 阶段 %PHASE_NO%：桌面端业务链路（desktop） ==========
call :ensure_cdp
if errorlevel 1 goto :cdp_fail
call :run flows desktop
if errorlevel 1 set "FAILED=%FAILED% %PHASE_NO%:flows/desktop"

if not "%FAILED%"=="" set EXITCODE=1
goto :finish

REM ==========================================================
REM  前置检查失败分支
REM ==========================================================
:novenv
echo [run_full] .venv 未找到。先执行：
echo              python -m venv .venv
echo              .venv\Scripts\pip install -e ".[dev]"
echo              .venv\Scripts\playwright install chromium
set EXITCODE=1
goto :finish

:noenv
echo [run_full] 缺少 configs\envs\test.yaml（真实测试环境配置，gitignored）。
echo              模板见 configs\envs\test.example.yaml，填本地真实值后重试。
set EXITCODE=1
goto :finish

:noexe
echo [run_full] 未找到桌面客户端可执行文件。任选其一配置后重试：
echo              1. set APW_DESKTOP_EXE=^<客户端安装目录^>^\<app^>.exe
echo              2. 复制 configs\desktop.local.example.bat
echo                 为 configs\desktop.local.bat 并填真实路径
set EXITCODE=1
goto :finish

:cdp_fail
echo [run_full] 桌面端 CDP 保障失败，桌面端阶段未执行。
set "FAILED=%FAILED% %PHASE_NO%:flows/desktop（CDP 未就绪）"
set EXITCODE=1
goto :finish

REM ==========================================================
REM  收尾汇总
REM ==========================================================
:finish
echo.
echo [run_full] ============================================
if %EXITCODE%==0 (
    echo [run_full] 全部阶段 PASSED - 报告见 reports\ 最新目录
) else (
    echo [run_full] 存在失败阶段：%FAILED%
    echo [run_full] 取证与报告见 reports\ 最新目录
)
echo [run_full] ============================================
pause
exit /b %EXITCODE%

REM ==========================================================
REM  子过程
REM ==========================================================

REM ---- :run <pytest目标> [环境名]：跑一个阶段，退出码透传 ----
:run
set "PHASE_TARGET=%~1"
set "ENVARG="
if not "%~2"=="" set "ENVARG=--apw-env %~2"
echo [run_full] 目标=%PHASE_TARGET%  %ENVARG%  调试=--apw-headed --apw-slowmo %APW_SLOWMO%
.venv\Scripts\pytest %PHASE_TARGET% %ENVARG% --apw-headed --apw-slowmo %APW_SLOWMO% %EXTRA_ARGS%
exit /b

REM ---- :ensure_cdp：CDP 未开则强杀客户端并以 CDP 模式重启，等待就绪 ----
:ensure_cdp
echo [run_full] 探测 CDP：%CDP_URL% （客户端：%APP_EXE_NAME%）
call :probe_cdp
if not errorlevel 1 goto :cdp_ready
echo [run_full] CDP 未开启 - 强制结束 %APP_EXE_NAME% 并以 CDP 模式重新启动
taskkill /f /im "%APP_EXE_NAME%" >nul 2>&1
ping -n 3 127.0.0.1 >nul
start "" /d "%APP_DIR%" "%APW_DESKTOP_EXE%" --remote-debugging-port=%CDP_PORT%
set /a CDP_TRIES=0
:cdp_wait
set /a CDP_TRIES+=1
call :probe_cdp
if not errorlevel 1 goto :cdp_ready
if %CDP_TRIES% GEQ 60 goto :cdp_timeout
echo [run_full] 等待 CDP 就绪……（%CDP_TRIES%/60）
ping -n 2 127.0.0.1 >nul
goto :cdp_wait
:cdp_ready
echo [run_full] CDP 就绪：%CDP_URL%
exit /b 0
:cdp_timeout
echo [run_full] CDP 等待超时（60s）- 客户端未能以调试模式启动
exit /b 1

REM ---- :probe_cdp：CDP /json/version 可达且确为调试端点则退出码 0 ----
:probe_cdp
powershell -NoProfile -Command "try { $c = (Invoke-WebRequest -Uri '%CDP_URL%/json/version' -UseBasicParsing -TimeoutSec 3).Content; if ($c -match 'Browser') { exit 0 } else { exit 1 } } catch { exit 1 }"
exit /b
