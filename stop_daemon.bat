@echo off
title Dung Antigravity API Hub
echo ========================================================
echo        DUNG TIEN TRINH ANTIGRAVITY API HUB (PORT 8088)
echo ========================================================
echo.

echo Dang tim tien trinh tren cong 8088...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8088" ^| findstr "LISTENING"') do (
    echo Tim thay PID: %%a - Dang dung tien trinh...
    taskkill /F /PID %%a >nul 2>&1
)

echo Dang quet tien trinh tray_app.py / pythonw...
taskkill /F /FI "WINDOWTITLE eq Antigravity*" >nul 2>&1

echo.
echo Da dung tat ca tien trinh Gateway thanh cong!
echo.
ping 127.0.0.1 -n 2 >nul
