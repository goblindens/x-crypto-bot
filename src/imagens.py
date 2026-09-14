"""Hospeda uma imagem num endereco https publico -- do jeito que a Meta exige.

O Threads nao aceita upload de arquivo: precisa de URL publica. O repositorio
e publico, entao a imagem vai pra `artes/auto/`, e commitada e enviada, e a URL
raw do GitHub vira o endereco. Funciona no GitHub Actions (GITHUB_REPOSITORY
no ambiente) e no Mac (le o remoto do git).
"""
from __future__ import annotations

import os
import re
import subprocess
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA = os.path.join(ROOT, "artes", "auto")


def _git(*args, check=True):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, check=check)


def _repo_e_branch():
    repo = os.environ.get("GITHUB_REPOSITORY")
    branch = os.environ.get("GITHUB_REF_NAME")
    if not repo:
        url = _git("remote", "get-url", "origin").stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
        repo = m.group(1) if m else None
    if not branch:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
    return repo, branch


def publicar(caminho: str, esperar: int = 40) -> str:
    """Commita + envia a imagem e devolve a URL raw publica (espera ela responder 200)."""
    repo, branch = _repo_e_branch()
    if not repo:
        raise RuntimeError("nao achei o repositorio do GitHub (remoto origin)")
    rel = os.path.relpath(os.path.abspath(caminho), ROOT).replace(os.sep, "/")
    if os.environ.get("GITHUB_ACTIONS"):
        _git("config", "user.name", "bot-cripto")
        _git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    _git("add", rel)
    if _git("diff", "--cached", "--quiet", check=False).returncode != 0:
        _git("commit", "-q", "-m", f"arte: {os.path.basename(rel)} [skip ci]")
        _git("pull", "--rebase", "--autostash", "-q", "origin", branch, check=False)
        r = _git("push", "-q", "origin", f"HEAD:{branch}", check=False)
        if r.returncode != 0:
            raise RuntimeError(f"push da imagem falhou: {r.stderr.strip()[-200:]}")
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{rel}"
    fim = time.time() + esperar
    while time.time() < fim:
        try:
            if requests.head(url, timeout=10, allow_redirects=True).status_code == 200:
                return url
        except requests.RequestException:
            pass
        time.sleep(3)
    raise RuntimeError(f"imagem enviada mas a URL ainda nao responde: {url}")


def limpar_antigas(dias: int = 14) -> int:
    """Apaga artes automaticas com mais de N dias (o repo nao precisa guardar historico de imagem)."""
    if not os.path.isdir(PASTA):
        return 0
    corte = time.time() - dias * 86400
    n = 0
    for f in os.listdir(PASTA):
        p = os.path.join(PASTA, f)
        if f.endswith(".png") and os.path.getmtime(p) < corte:
            _git("rm", "-q", "--cached", os.path.relpath(p, ROOT), check=False)
            os.remove(p); n += 1
    return n
