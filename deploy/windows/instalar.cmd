@echo off
rem Instala o x-crypto-bot na VPS Windows (OKX-BOT-TOKYO): venv + dependencias.
rem Uso: instalar.cmd   (na pasta C:\Users\sinval\x-crypto-bot, ja com o .env)
cd /d "C:\Users\sinval\x-crypto-bot"
if not exist .env (
  echo ERRO: falta o .env. Copie do Mac antes.
  exit /b 1
)
if not exist .venv (
  "C:\Program Files\Python313\python.exe" -m venv .venv || exit /b 1
)
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || exit /b 1
if not exist logs mkdir logs
if not exist state mkdir state
echo OK: instalado em %cd%
