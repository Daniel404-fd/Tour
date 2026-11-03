@echo off
rem Сборка HabitTracker.exe на Windows. Нужен Python 3.10+ (python.org).
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv python -m venv .venv || goto :error
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt || goto :error
pytest -q || goto :error
pyinstaller --noconfirm --clean HabitTracker.spec || goto :error
echo.
echo Готово: dist\HabitTracker.exe
pause
exit /b 0
:error
echo Сборка не удалась.
pause
exit /b 1
