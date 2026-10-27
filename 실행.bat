@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 1. Tk 9 이상이 들어 있는 Python 찾기 (Python 3.14 이상. 입력칸 예시 글자 등에 필요)
rem    예전 Python이 PATH에 먼저 있어도 조건에 맞는 Python을 골라서 씀. 없으면 winget으로 설치
set "PY="
call :find_python python
if not defined PY call :find_python py -3
if not defined PY call :find_python "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if defined PY goto :packages

echo Python 3.14 이상이 없어 설치합니다. 1~2분 걸립니다...
winget install --id Python.Python.3.14 -e --scope user --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto :python_failed
call :find_python "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not defined PY goto :python_failed

:packages
rem 2. 필요한 패키지 확인, 하나라도 없으면 requirements.txt로 설치
"%PY%" -c "import win32com.client, win32clipboard, pdfplumber, pypdfium2, PIL, anthropic, winrt.windows.media.ocr" >nul 2>nul
if not errorlevel 1 goto :hwp

echo 필요한 패키지를 설치합니다...
"%PY%" -m pip install -r requirements.txt
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
rem 찾은 Python 옆의 pythonw.exe(검은 창 없이 실행)로 입력창을 띄움
start "" "%PYW%" -m hidoc
exit /b 0

:find_python
rem 인자로 받은 Python 이 Tk 9 이상이면 PY(python.exe), PYW(pythonw.exe) 경로를 정함
rem (-c 로 코드를 넘기면 cmd 가 > = 같은 글자를 바꿔 버려서 확인용 파일을 따로 둠)
for /f "usebackq delims=" %%i in (`%* hidoc\check_python.py 2^>nul`) do set "PY=%%i"
if not defined PY exit /b 0
set "PYW=%PY:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PY%"
exit /b 0

:python_failed
echo.
echo Python 3.14 이상을 찾거나 설치하지 못했습니다.
echo https://www.python.org/downloads/ 에서 최신 Python을 직접 설치한 뒤 다시 실행해 주세요.
pause
exit /b 1

:pip_failed
echo.
echo 패키지 설치에 실패했습니다. 인터넷 연결을 확인한 뒤 다시 실행해 주세요.
pause
exit /b 1
