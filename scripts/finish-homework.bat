@echo off
REM Закриває чекліст здачі ДЗ-03: реальний прогін, тести, скриншот, коміт, push.
REM Запуск: подвійний клік. Потрібні Docker Desktop (запущений) і git.
chcp 65001 >nul
cd /d "%~dp0.."

where docker >nul 2>&1 || (echo [!] Docker не встановлений. https://www.docker.com/products/docker-desktop/ & pause & exit /b 1)
docker info >nul 2>&1 || (echo [!] Docker Desktop не запущений. Запустіть його і повторіть. & pause & exit /b 1)

echo.
echo === [1/4] BASIC: worker-html збирає 15 сторінок books.toscrape.com ===
docker compose --profile basic up --build --abort-on-container-exit --exit-code-from scraper-basic
if errorlevel 1 (echo [!] Прогін завершився з помилкою - див. лог вище. & pause & exit /b 1)

echo.
echo === [2/4] Тести парсерів ===
docker compose --profile basic run --rm scraper-basic pytest -q

echo.
echo Файлів у data\normalized:
dir /s /b data\normalized\*.json | find /c ".json"
echo.
echo === [3/4] СКРИНШОТ ===
echo Зараз натисніть Win+Shift+S, виділіть це вікно і збережіть як:
echo   %cd%\docs\screenshots\basic-run.png
echo Потім поверніться сюди і натисніть будь-яку клавішу.
pause >nul
docker compose --profile basic down

echo.
echo === [4/4] Коміт і push ===
git add data docs
git commit -m "Дані реального прогону (raw + normalized) і скриншот запуску"
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo GitHub-репозиторій ще не підключений. Виконайте один раз:
  echo   gh repo create scraper-fleet --public --source . --push
  echo або створіть порожній repo на github.com і:
  echo   git remote add origin https://github.com/^<user^>/scraper-fleet.git
  echo   git push -u origin HEAD
) else (
  git push -u origin HEAD
)
echo.
echo Готово.
pause
