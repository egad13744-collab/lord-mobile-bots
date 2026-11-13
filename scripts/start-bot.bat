@echo off
REM Klik dua kali file ini di sesi RDP untuk menjalankan bot.
REM LMBot - Dibuat oleh Egandika
title LMBot - Dibuat oleh Egandika
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo venv belum ada. Jalankan dulu: powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
  pause
  exit /b 1
)
.venv\Scripts\python.exe code.py serve %*
pause
