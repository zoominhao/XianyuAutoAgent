@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting XianyuAutoAgent...
python main.py
pause
