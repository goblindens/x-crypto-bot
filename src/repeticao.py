"""Trava de repeticao: nao falar do mesmo assunto duas vezes no mesmo dia.

Por que existe (17/09/2026): o erro que ele reclamou nao foi so falsidade --
foram TRES posts sobre o Fed em uma hora (20:58, 21:30, 22:02). O leitor abre o
feed e ve a mesma noticia tres vezes, com numeros diferentes, e conclui que a
pagina nao sabe do que fala.

Agora que a publicacao e em tempo real, sem aprovacao dele, esta e a trava que
protege contra enxurrada: o mesmo ASSUNTO so volta depois de N horas.
"""
from __future__ import annotations

from datetime import timedelta

from .confirmacao import _conceitos, _mesmo_assunto
from .util import now_utc


def _quando(ts: str):
    from .state import _parse
    return _parse(ts)


def repetido(artigo, state, horas: int = 6) -> tuple[bool, str]:
    """True se ja falamos do mesmo assunto nas ultimas `horas`."""
    corte = now_utc() - timedelta(hours=horas)
    conceitos_novo = _conceitos(artigo.title)
    for post in reversed(state.data.get("posts", [])[-40:]):
        quando = _quando(post.get("ts", ""))
        if not quando or quando < corte:
            continue
        titulo_antigo = post.get("title") or ""
        if not titulo_antigo:
            continue
        if _mesmo_assunto(artigo.title, titulo_antigo):
            return True, f"mesmo assunto de {quando:%H:%M}: {titulo_antigo[:60]}"
        # 3 conceitos iguais ja bastam pra ser "mais do mesmo"
        if len(conceitos_novo & _conceitos(titulo_antigo)) >= 3:
            return True, f"assunto parecido com o de {quando:%H:%M}: {titulo_antigo[:60]}"
    return False, ""
