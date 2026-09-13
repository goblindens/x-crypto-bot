@echo off
rem Espelho Instagram -> X. Chamado pelo run.cmd do ig2yt (que a tarefa
rem agendada roda a cada 2 minutos, 24h). Nao precisa de tarefa propria.
rem Log com teto: mantem so as ultimas 400 linhas.
cd /d "C:\Users\sinval\x-crypto-bot"
set PYTHONUTF8=1
rem Para pausar sem desligar a tarefa: set ESPELHO_ARGS=--dry-run
set ESPELHO_ARGS=
if not exist logs mkdir logs
if exist logs\espelho.log (
  powershell -NoProfile -Command "Get-Content logs\espelho.log -Tail 400 | Set-Content logs\espelho.tmp" && move /y logs\espelho.tmp logs\espelho.log >nul
)
echo ===== %date% %time% ===== >> logs\espelho.log
rem A tarefa chama isto a cada 2 min; --repeat 3 --every 40 = olha o Instagram a cada 40 s (tempo real).
".venv\Scripts\python.exe" -m src.main --mode espelho --repeat 3 --every 40 %ESPELHO_ARGS% >> logs\espelho.log 2>&1
rem Healthchecks.io: "terminei". A URL vem de hc.cmd (gerado pela Formula). Sem ela, nada acontece.
if exist hc.cmd call hc.cmd
if defined HC_ESPELHO curl -fsS -m 10 "%HC_ESPELHO%" >nul 2>&1
