@echo off
title Python Project Setup

echo Creating virtual environment...
python -m venv myenv

if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
)

echo.
echo Activating virtual environment...
call myenv\Scripts\activate.bat

echo.
echo Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo ============================
echo Installation completed!
echo To activate manually later:
echo myenv\Scripts\activate
echo ============================

pause