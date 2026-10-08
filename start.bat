@echo off
chcp 65001 >nul
title BigData Platform Launcher
cd /d "%~dp0"

echo =====================================================================
echo           🚀 HỆ THỐNG BIGDATA BĐS - ANTIGRAVITY OS
echo =====================================================================
echo.
echo   [1] Chạy đồng thời 2 Dashboard (Flask :5000 + Streamlit :8502) [MẶC ĐỊNH]
echo   [2] Chỉ chạy Flask Dashboard (:5000 - Ads Engine & Lead CRM)
echo   [3] Chỉ chạy Streamlit Analytics (:8502 - Data Health & 360 Profile)
echo   [4] Kiểm tra trạng thái Cơ sở Dữ liệu & Thống kê Lead
echo   [5] Chạy Data Pipeline (Phase 1, 2, 3)
echo   [6] Triển khai chạy nền qua PM2 (Background Daemon)
echo   [0] Thoát
echo.
echo =====================================================================
set /p choice="Nhập lựa chọn của bạn (0-6) [Mặc định 1]: "

if "%choice%"=="" set choice=1
if "%choice%"=="1" goto BOTH
if "%choice%"=="2" goto FLASK
if "%choice%"=="3" goto STREAMLIT
if "%choice%"=="4" goto CHECKDB
if "%choice%"=="5" goto PIPELINE
if "%choice%"=="6" goto PM2
if "%choice%"=="0" goto EXIT
goto BOTH

:BOTH
echo.
echo [*] Đang khởi động 2 Dashboard...
C:\Users\LENOVO\AppData\Local\Python\pythoncore-3.14-64\python.exe start.py --both
goto END

:FLASK
echo.
echo [*] Đang khởi động Flask Dashboard tại http://localhost:5000...
C:\Users\LENOVO\AppData\Local\Python\pythoncore-3.14-64\python.exe start.py --flask
goto END

:STREAMLIT
echo.
echo [*] Đang khởi động Streamlit Dashboard tại http://localhost:8502...
C:\Users\LENOVO\AppData\Local\Python\pythoncore-3.14-64\python.exe start.py --streamlit
goto END

:CHECKDB
echo.
echo [*] Đang kiểm tra dữ liệu...
C:\Users\LENOVO\AppData\Local\Python\pythoncore-3.14-64\python.exe check_db.py
echo.
pause
goto END

:PIPELINE
echo.
echo [*] Đang thực thi Data Pipeline Phase all...
C:\Users\LENOVO\AppData\Local\Python\pythoncore-3.14-64\python.exe main.py --phase all
echo.
pause
goto END

:PM2
echo.
echo [*] Đang kích hoạt dịch vụ chạy nền PM2...
call pm2 start ecosystem.config.js
call pm2 status
echo.
echo [*] Truy cập:
echo     - Flask Dashboard     : http://localhost:5000
echo     - Streamlit Analytics : http://localhost:8502
echo.
pause
goto END

:EXIT
exit /b 0

:END
