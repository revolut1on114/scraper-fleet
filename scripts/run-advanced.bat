@echo off
REM ADVANCED: Redis + worker-html + worker-js + beat + Prometheus + Grafana
cd /d "%~dp0.."
docker compose --profile advanced up -d --build || goto :err
timeout /t 10 /nobreak >nul
docker compose exec worker-html python -m app.enqueue all
echo.
echo Grafana:    http://localhost:3000  (admin / admin)
echo Prometheus: http://localhost:9090
echo Логи:       docker compose logs -f worker-html worker-js
pause
exit /b 0
:err
echo Помилка запуску. Перевірте, що Docker Desktop запущено.
pause
exit /b 1
