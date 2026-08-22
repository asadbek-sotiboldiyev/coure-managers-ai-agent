@echo off

color 0F
title Run FastAPI

if not exist "myenv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Run install.bat first.
    echo Trying with global Python...

    python -m uvicorn main_app.server:app --reload
) else (
    echo Starting FastAPI from virtual environment...

    myenv\Scripts\python.exe -m uvicorn main_app.server:app --reload
)

pause