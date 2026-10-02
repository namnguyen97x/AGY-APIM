@echo off
title Codex CLI voi Antigravity API Hub
echo ========================================================
echo   KHOI DONG CODEX VOI ANTIGRAVITY API HUB (PORT 8088)
echo ========================================================
echo.

set OPENAI_BASE_URL=http://127.0.0.1:8088/v1
set OPENAI_API_KEY=sk-antigravity
set OPENAI_API_BASE=http://127.0.0.1:8088/v1

echo Endpoint: %OPENAI_BASE_URL%
echo.
echo Dang khoi dong Codex CLI...
codex
pause
