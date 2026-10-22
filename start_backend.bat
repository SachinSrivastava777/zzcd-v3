@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher ^(py^) was not found. Install Python 3.10+ and enable PATH.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating project virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Could not create venv. Install Python 3.10+ and retry.
    pause
    exit /b 1
  )
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)
echo Starting backend at http://127.0.0.1:8000
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
pause
