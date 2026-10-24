@echo off
rem Windows 설치: Python 3.11 가상환경(.venv) 생성 후 의존성 설치. 전역 설정은 바꾸지 않습니다.
chcp 65001 >nul
cd /d "%~dp0"
py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.11이 필요합니다. https://www.python.org/downloads/ 에서 3.11.x 를 설치하세요.
  echo 설치 시 "py launcher" 옵션을 켜 두세요.
  pause
  exit /b 1
)
py -3.11 -m venv .venv || goto :err
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :err
python -m pip install -r requirements.txt || goto :err
python -m pip install --no-deps basic-pitch==0.4.0 || goto :err
where ffmpeg >nul 2>&1
if errorlevel 1 echo 참고: ffmpeg가 없으면 일부 MP3/M4A 디코딩이 실패할 수 있습니다. README의 ffmpeg 안내를 보세요.
echo.
echo 설치 완료. run_windows.bat 을 실행하세요.
pause
exit /b 0
:err
echo 설치 중 오류가 발생했습니다. 위 메시지를 확인하세요.
pause
exit /b 1
