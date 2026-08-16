@echo off
title Kaggle Competition Monitor
cd /d "%~dp0"

echo ===================================================
echo   Kaggle Competition Monitor Launcher
echo ===================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.9+ from https://python.org
    echo.
    pause
    exit /b 1
)

python start.py
if errorlevel 1 (
    echo.
    echo [NOTE] The application exited with an error.
    pause
)
