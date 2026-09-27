@echo off
rem Графический интерфейс анализатора телеметрии (двойной клик для запуска)
python telemetry_app.py 2>nul || py telemetry_app.py
if errorlevel 1 (
    echo.
    echo Не удалось запустить Python. Установите его с https://www.python.org/downloads/
    echo или выполните: pip install -r requirements.txt
    pause
)
