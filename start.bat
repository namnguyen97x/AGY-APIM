@echo off
title Antigravity API Hub & Smart Rotator
echo ========================================================
echo    ANTIGRAVITY MULTI-ACCOUNT HUB & SMART ROTATOR
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
echo   [1] Chay ngam duoi Khay he thong (System Tray - KHUYEN DUNG)
echo       ^> Khong chiem cua so CMD, thu nho vao khay he thong Taskbar,
echo       ^> Khong so tat nham lam gian doan Hermes / Codex / Cursor.
echo.
echo   [2] Chay truc tiep tren man hinh Console (Hien thi Log chi tiet)
echo.
echo   [3] Dung tat ca tien trinh Gateway dang chay ngam
echo.
set /p choice="Nhap lua chon [1, 2, 3] (Mac dinh 1): "

if "%choice%"=="" set choice=1

if "%choice%"=="1" (
    echo.
    echo Dang khoi dong che do System Tray (An danh)...
    start wscript start_tray.vbs
    ping 127.0.0.1 -n 2 >nul
    start http://127.0.0.1:8088/
    echo Da khoi dong thanh cong! Icon da xuat hien duoi khay he thong (Taskbar).
    ping 127.0.0.1 -n 3 >nul
    exit /b 0
)

if "%choice%"=="3" (
    call stop_daemon.bat
    pause
    exit /b 0
)

echo.
echo Dang mo Web Dashboard tren trinh duyet...
start http://127.0.0.1:8088/

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
