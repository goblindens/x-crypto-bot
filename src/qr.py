"""QR code do grupo do WhatsApp pra ir pequeno nos cards, ao lado da logo
(pedido dele, 14/09/2026). O link fica na imagem, nunca no texto do post
(regra do Threads: link no corpo derruba alcance)."""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "artes", "qr-grupo.png")
LINK_PADRAO = "https://chat.whatsapp.com/Kg3lM88Q5tu17jXqbxxWRw"   # link que ele mandou em 14/09/2026 (Secret Lab)


def imagem(link: str = LINK_PADRAO, tamanho: int = 150):
    """Devolve um PIL.Image RGBA do QR (branco sobre transparente, modulos verdes escuros)."""
    from PIL import Image
    try:
        import qrcode
    except ImportError:
        return None
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=1)
    q.add_data(link); q.make(fit=True)
    im = q.make_image(fill_color=(6, 8, 6), back_color=(236, 240, 236)).convert("RGB")
    im = im.resize((tamanho, tamanho), Image.NEAREST)
    return im
