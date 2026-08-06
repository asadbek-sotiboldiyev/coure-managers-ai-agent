@echo off
color 0F

title Run FastAPI

if not exist "myenv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Run install.bat first.
    pause
    exit /b 1
)

call myenv\Scripts\activate.bat

uvicorn main_app.server:app --reload

pause