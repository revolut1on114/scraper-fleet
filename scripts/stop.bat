@echo off
REM Зупинити advanced-стек (дані в data\ зберігаються)
cd /d "%~dp0.."
docker compose --profile advanced --profile basic down
pause
