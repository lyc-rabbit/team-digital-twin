@echo off
chcp 65001 >nul
echo =========================================
echo   团队数字孪生系统 · 启动后端
echo =========================================

REM 仅当前窗口关闭本机 7897 代理，不改用户/系统环境变量
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
set "http_proxy="
set "https_proxy="
set "all_proxy="

REM 激活 conda 环境
call D:\Software\condas\Scripts\activate.bat team-twin

REM conda activate 可能带回代理，再清一次（仅当前窗口）
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
set "http_proxy="
set "https_proxy="
set "all_proxy="

REM 切换到后端目录并启动
cd /d "%~dp0backend"
python main.py

pause
