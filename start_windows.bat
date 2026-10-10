@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Khong tao duoc moi truong Python. Hay cai Python 3.11 hoac 3.12.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Cai thu vien that bai. Kiem tra Internet hoac pip.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run app.py
pause
