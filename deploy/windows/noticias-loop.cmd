@echo off
rem Vigia do loop de noticias no X (VPS de Toquio). Chamado a cada 2 min pela tarefa do
rem ig2yt; se o processo continuo nao estiver vivo, o vigia em Python sobe ele.
rem O loop em si olha os feeds a cada 20 s e publica na hora (tempo real, 14/09/2026).
cd /d "%~dp0..\.."
set PYTHONUTF8=1
python -X utf8 deploy\windows\vigia_noticias.py >> logs\vigia.log 2>&1
