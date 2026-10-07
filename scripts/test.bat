@echo off
REM Тести парсерів і smoke-check у Docker (без локального Python)
cd /d "%~dp0.."
docker compose --profile basic run --rm --build scraper-basic sh -c "pytest -q && python -m app.check_parser --fixtures && python -m app.check_parser --no-js"
pause
