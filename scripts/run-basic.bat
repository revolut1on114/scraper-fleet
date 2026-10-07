@echo off
REM BASIC: один прогін worker-html (15 сторінок) у Docker
cd /d "%~dp0.."
docker compose --profile basic up --build
echo.
echo Результати: data\normalized\books.toscrape.com
pause
