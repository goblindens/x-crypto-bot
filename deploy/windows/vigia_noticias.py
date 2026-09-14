"""Vigia do loop de noticias no X (VPS de Toquio, Windows, usuario sem admin).

A tarefa do ig2yt chama isto a cada 2 min. Se o processo continuo do loop nao
estiver vivo (PID em logs/noticias.pid), sobe ele destacado. O loop olha os
feeds a cada 20 s e publica na hora -- "tempo real", decisao dele de 14/09/2026.
Nao usa tasklist (o servidor nega /v pra usuario comum): confere o PID direto
na API do Windows.
"""
import ctypes
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS = os.path.join(ROOT, "logs")
PID = os.path.join(LOGS, "noticias.pid")
LOG = os.path.join(LOGS, "noticias.log")
A_CADA = "20"


def vivo(pid: int) -> bool:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return bool(ok) and code.value == 259          # STILL_ACTIVE


def loop_vivo() -> bool:
    """O loop segura um mutex nomeado; se ele ja existe, tem loop rodando."""
    h = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\x-crypto-bot-loop")
    existe = ctypes.windll.kernel32.GetLastError() == 183          # ERROR_ALREADY_EXISTS
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
    return existe


def main() -> int:
    os.makedirs(LOGS, exist_ok=True)
    if loop_vivo():
        return 0
    try:
        pid = int(open(PID).read().strip())
        if vivo(pid):
            return 0
    except (OSError, ValueError):
        pass
    if os.path.exists(LOG) and os.path.getsize(LOG) > 5_000_000:      # teto de 5 MB no log
        os.replace(LOG, LOG + ".1")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    DETACHED = 0x00000008 | 0x00000200                                  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    # cada partida escreve no proprio log (evita trava de arquivo entre processos no Windows)
    log = os.path.join(LOGS, "noticias.log")
    try:
        out = open(log, "ab")
    except OSError:
        out = open(os.path.join(LOGS, f"noticias-{os.getpid()}.log"), "ab")
    with out:
        # -u: sem buffer, senao o log so aparece a cada 8 KB
        p = subprocess.Popen([sys.executable, "-u", "-X", "utf8", "-m", "src.main", "--mode", "loop", "--a-cada", A_CADA, "--minutos", "525600"],
                             cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=env, creationflags=DETACHED, close_fds=True)
    open(PID, "w").write(str(p.pid))            # o loop reescreve com o proprio pid ao subir
    print(f"[vigia] loop de noticias iniciado, pid {p.pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
