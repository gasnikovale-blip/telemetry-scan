@echo off
rem Консольный анализ: перетащите CSV-файл на этот файл,
rem либо запускайте из командной строки с аргументами:
rem analyzer_cli.bat data\session.csv --car cars\vw_polo_sedan_16.ini --report "Мой отчет"
python telemetry_analyzer.py %* 2>nul || py telemetry_analyzer.py %*
echo.
pause
