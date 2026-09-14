"""Lista (e, com --matar, derruba) os python.exe deste usuario na VPS de Toquio.

O servidor nega `tasklist /v`, WMI e `taskkill /IM` pra usuario comum; a API do
Windows direta (EnumProcesses + OpenProcess) funciona pros processos do proprio
usuario. Uso:
    python deploy\\windows\\processos.py           -> lista
    python deploy\\windows\\processos.py --matar   -> derruba todos os python.exe menos este
"""
import ctypes
import os
import sys
from ctypes import wintypes

psapi = ctypes.windll.psapi
k32 = ctypes.windll.kernel32
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001


def nome(pid: int) -> str:
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    buf = ctypes.create_unicode_buffer(1024)
    tam = wintypes.DWORD(1024)
    ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam))
    k32.CloseHandle(h)
    return buf.value if ok else ""


def pythons() -> list:
    arr = (wintypes.DWORD * 4096)()
    got = wintypes.DWORD()
    psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(got))
    saida = []
    for pid in arr[: got.value // ctypes.sizeof(wintypes.DWORD)]:
        n = nome(pid)
        if n and os.path.basename(n).lower() == "python.exe":
            saida.append((pid, n))
    return saida


def loop_vivo() -> bool:
    """True se algum loop novo (com a trava) esta rodando."""
    h = k32.CreateMutexW(None, False, "Local\\x-crypto-bot-loop")
    existe = k32.GetLastError() == 183
    if h:
        k32.CloseHandle(h)
    return existe


def main() -> int:
    eu = os.getpid()
    lista = pythons()
    for pid, n in lista:
        print(f"{pid:>6}  {'(este)' if pid == eu else '      '}  {n}")
    print(f"loop com trava vivo: {loop_vivo()}")
    if "--matar" in sys.argv:
        for pid, _ in lista:
            if pid == eu:
                continue
            h = k32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if h and k32.TerminateProcess(h, 1):
                print(f"derrubado {pid}")
            else:
                print(f"nao consegui derrubar {pid} (erro {k32.GetLastError()})")
            if h:
                k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
