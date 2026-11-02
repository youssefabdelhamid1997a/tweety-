@echo off
setlocal
echo Dota Ascent - optional local vision model setup.
echo This downloads gemma3:4b through your installed Ollama.
echo Open Ollama from the Start menu before continuing.
echo.
where ollama >nul 2>&1
if errorlevel 1 goto missing_ollama
ollama pull gemma3:4b
set coach_exit=%errorlevel%
if not "%coach_exit%"=="0" goto model_error
echo.
echo Vision model downloaded. Double-click run.bat and open Live coach.
echo Share the Dota window, then choose Analyze once or Start periodic.
pause
exit /b 0
:model_error
echo.
echo Download did not finish. Check that Ollama is running and retry.
pause
exit /b %coach_exit%
:missing_ollama
echo Ollama was not found. Install or update Ollama for Windows.
echo Reopen this setup window after installation so PATH is refreshed.
echo https://ollama.com/download/windows
pause
exit /b 1
