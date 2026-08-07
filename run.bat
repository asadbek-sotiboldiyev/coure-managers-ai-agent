@echo off
color 0F

title Run FastAPI

if not exist "myenv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Run install.bat first.
    echo Trying with global python env.
uvicorn main_app.server:app --reload
)
else (
    echo Activating virtual environment...
    call myenv\Scripts\activate.bat
uvicorn main_app.server:app --reload
)

pause