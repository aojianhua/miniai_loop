@echo off
setlocal
python "%~dp0agent.py" %*
exit /b %errorlevel%

