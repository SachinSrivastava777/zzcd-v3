@echo off
setlocal
cd /d "%~dp0frontend"
echo Frontend will be available at http://127.0.0.1:5500
py -m http.server 5500
pause
