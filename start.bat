@echo off
setlocal
title Antigravity API Hub - Smart Rotator
cls
echo ========================================================
echo    ANTIGRAVITY MULTI-ACCOUNT HUB - SMART ROTATOR
echo    Bien Account Antigravity thanh API + Xoay Quota Tu Dong
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/2] Kiem tra moi truong Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python! Vui long cai dat Python 3.10+ tro len.
    pause
    exit /b 1
)

echo [2/2] Chon che do khoi chay:
echo.
echo   [1] Chay ngam duoi Khay he thong (System Tray - Khuyen dung)
echo       * Khong chiem cua so CMD, thu nho vao Taskbar canh dong ho
echo       * Khong so tat nham lam gian doan Hermes / Codex / Cursor
echo.
echo   [2] Chay truc tiep tren man hinh Console (Hien thi Log chi tiet)
echo.
echo   [3] Dung tat ca tien trinh Gateway dang chay ngam
echo.
set "choice=1"
set /p "choice=Nhap lua chon [1, 2, 3] (Mac dinh 1): "

if "%choice%"=="1" goto start_tray
if "%choice%"=="2" goto start_console
if "%choice%"=="3" goto stop_server
goto start_tray

:start_tray
echo.
echo [!] Dang khoi dong Gateway duoi Khay he thong (System Tray)...
start "" pythonw.exe tray_app.py
ping 127.0.0.1 -n 2 >nul
start http://127.0.0.1:8088/
echo.
echo ========================================================
echo   [OK] KHOI DONG THANH CONG!
echo   - Web Dashboard: http://127.0.0.1:8088/
echo   - OpenAI API:    http://127.0.0.1:8088/v1
echo   - Anthropic API: http://127.0.0.1:8088
echo   - Direct API:    http://127.0.0.1:8088/responses
echo.
echo   * Icon he thong da xuat hien duoi goc phai Taskbar.
echo   * Nhan phim bat ky de dong cua so nay (Gateway van chay ngam).
echo ========================================================
echo.
pause
exit /b 0

:start_console
echo.
echo Dang mo Web Dashboard tren trinh duyet...
start http://127.0.0.1:8088/
echo.
echo Dang khoi dong Antigravity Gateway tren cong 8088...
echo.
echo  - Web Dashboard:      http://127.0.0.1:8088/
echo  - OpenAI Endpoint:    http://127.0.0.1:8088/v1
echo  - Anthropic Endpoint: http://127.0.0.1:8088
echo  - Direct Responses:   http://127.0.0.1:8088/responses
echo.
echo (Nhan Ctrl+C de dung server)
echo.
python main.py
pause
exit /b 0

:stop_server
call stop_daemon.bat
pause
exit /b 0
