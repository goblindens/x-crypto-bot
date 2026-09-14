@echo off
rem Vigia do loop de noticias no X (VPS de Toquio). A tarefa do ig2yt chama isto a cada
rem 2 min; se o processo continuo nao estiver rodando, sobe ele. O loop em si olha os
rem feeds a cada 20 s e publica na hora (tempo real, decisao dele de 14/09/2026).
cd /d "%~dp0..\.."
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
tasklist /v /fi "IMAGENAME eq python.exe" 2>nul | find /i "x-noticias-loop" >nul
if %errorlevel%==0 goto :fim
if not exist logs mkdir logs
rem o titulo da janela e a assinatura que o tasklist procura
start "x-noticias-loop" /min cmd /c "python -m src.main --mode loop --a-cada 20 --minutos 525600 >> logs\noticias.log 2>&1"
:fim
