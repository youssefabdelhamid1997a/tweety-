@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto folder_error
echo Dota Ascent - keep this window open while using the coach.
echo To reopen later, double-click run.bat.
echo.
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto use_python
echo Please install Python 3.10 or newer from https://www.python.org/downloads/windows/
echo Tick "Add Python to PATH" during installation, then double-click run.bat again.
pause
exit /b 1
:use_py
py -3 server.py --open
goto finished
:use_python
python server.py --open
goto finished
:folder_error
echo Could not open the coach folder. Extract the ZIP into a folder you can access.
pause
exit /b 1
:finished
set coach_exit=%errorlevel%
if not "%coach_exit%"=="0" pause
exit /b %coach_exit%
