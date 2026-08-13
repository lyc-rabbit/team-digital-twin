@echo off
chcp 65001 >nul
echo =========================================
echo   团队数字孪生系统 · 启动后端
echo =========================================

REM 激活 conda 环境
call D:\Software\condas\Scripts\activate.bat team-twin

REM 切换到后端目录并启动
cd /d "%~dp0backend"
python main.py

pause
