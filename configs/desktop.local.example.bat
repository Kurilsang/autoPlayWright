@echo off
REM 桌面客户端路径配置模板：复制为 configs\desktop.local.bat 后填真实路径。
REM desktop.local.bat 已 gitignore，真实路径/产品名不入库（AGENTS 硬约束）。
REM 也可不用本文件，直接 set APW_DESKTOP_EXE=... 后再跑 run_full_debug.bat。
set "APW_DESKTOP_EXE=<客户端安装目录>\<app>.exe"
