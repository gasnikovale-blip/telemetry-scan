@echo off
rem Установка зависимостей анализатора телеметрии
pip install -r requirements.txt || py -m pip install -r requirements.txt
echo.
pause
