# Встановлення локального середовища на Windows (без Docker)
# Запуск: powershell -ExecutionPolicy Bypass -File scripts\setup-venv.ps1
Set-Location (Join-Path $PSScriptRoot "..")
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# Chromium потрібен лише для worker-js / check_parser без --no-js
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest -q
Write-Host "Готово. Активуйте: .\.venv\Scripts\Activate.ps1, далі: python -m app.run_basic"
