@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 1. Python 확인, 없으면 winget으로 설치
python -c "import sys" >nul 2>nul
if not errorlevel 1 goto :packages

echo Python이 없어 설치합니다. 1~2분 걸립니다...
winget install --id Python.Python.3.14 -e --scope user --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto :python_failed
rem 방금 설치한 Python은 이 창의 PATH에 아직 없으므로 직접 추가
set "PATH=%LOCALAPPDATA%\Programs\Python\Python314;%LOCALAPPDATA%\Programs\Python\Python314\Scripts;%PATH%"
python -c "import sys" >nul 2>nul
if errorlevel 1 goto :python_failed

:packages
rem 2. pywin32 확인, 없으면 requirements.txt로 설치
python -c "import win32com.client, win32clipboard" >nul 2>nul
if not errorlevel 1 goto :hwp

echo 필요한 패키지를 설치합니다...
python -m pip install -r requirements.txt
if errorlevel 1 goto :pip_failed

:hwp
rem 3. 한글 확인. 없어도 하이웍스 복사는 되므로 안내만 하고 실행
reg query "HKCR\HWPFrame.HwpObject" >nul 2>nul
if not errorlevel 1 goto :run
echo.
echo 한컴오피스 한글이 설치되어 있지 않습니다.
echo 한글 파일 저장은 되지 않고, 하이웍스 복사만 사용할 수 있습니다.
pause

:run
start "" pythonw purchase_request.py
exit /b 0

:python_failed
echo.
echo Python 설치에 실패했습니다. https://www.python.org/downloads/ 에서 직접 설치한 뒤 다시 실행해 주세요.
pause
exit /b 1

:pip_failed
echo.
echo 패키지 설치에 실패했습니다. 인터넷 연결을 확인한 뒤 다시 실행해 주세요.
pause
exit /b 1
