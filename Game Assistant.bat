@echo off

setlocal EnableExtensions

chcp 65001 >nul 2>&1

cd /d "%~dp0"



set "LOGDIR=%CD%\data\logs"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1

set "LAUNCHLOG=%LOGDIR%\launcher.log"

echo [%date% %time%] start>> "%LAUNCHLOG%"



set "PYEXE="

if exist ".venv\Scripts\python.exe" set "PYEXE=%CD%\.venv\Scripts\python.exe"

if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (

    set "PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe"

)

if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (

    set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"

)

if not defined PYEXE (

    for /f "delims=" %%i in ('where python 2^>nul') do (

        set "PYEXE=%%i"

        goto :pyfound

    )

)

if not defined PYEXE (

    if exist "%WINDIR%\py.exe" (

        for /f "delims=" %%i in ('"%WINDIR%\py.exe" -3 -c "import sys; print(sys.executable)" 2^>nul') do (

            set "PYEXE=%%i"

            goto :pyfound

        )

    )

)

:pyfound

if not defined PYEXE (

    echo [%date% %time%] ERROR python not found>> "%LAUNCHLOG%"

    mshta "javascript:alert('Python not found. Install Python 3.11+ from python.org');close()"

    exit /b 1

)



echo [%date% %time%] python=%PYEXE%>> "%LAUNCHLOG%"



"%PYEXE%" -c "import keyboard, sounddevice, faster_whisper, PIL, requests" >nul 2>&1

if errorlevel 1 (

    echo [%date% %time%] pip install>> "%LAUNCHLOG%"

    "%PYEXE%" -m pip install -r requirements.txt -q

)



set "PYW=%PYEXE:python.exe=pythonw.exe%"

if not exist "%PYW%" (

    for /f "delims=" %%i in ('where pythonw 2^>nul') do (

        set "PYW=%%i"

        goto :gotw

    )

    set "PYW=%PYEXE%"

)

:gotw

echo [%date% %time%] starting GUI pythonw=%PYW%>> "%LAUNCHLOG%"



powershell -NoProfile -WindowStyle Hidden -Command ^

  "Start-Process -FilePath '%PYW%' -ArgumentList '%CD%\run_assistant.py' -WorkingDirectory '%CD%' -WindowStyle Hidden"



exit /b 0

