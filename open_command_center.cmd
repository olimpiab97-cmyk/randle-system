@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0open_command_center.ps1"
set "RANDLE_COMMAND_CENTER_EXIT=%ERRORLEVEL%"
if not "%RANDLE_COMMAND_CENTER_EXIT%"=="0" if not "%RANDLE_COMMAND_CENTER_NO_PAUSE%"=="1" pause
exit /b %RANDLE_COMMAND_CENTER_EXIT%
