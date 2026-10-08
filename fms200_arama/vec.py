"""0-token hashing embedding (768-dim) + cosine. Ağ/sunucu gerekmez.

Semantik değil "soft-lexical"tir: kelimeleri deterministik pseudo-rastgele bir vektöre
hash'ler. RRF ile lexical sıralamayı destekler. İstenirse `embed()` bir embedding
sunucusuna (nomic-embed-text, 768-dim) bağlanabilir; arayüz aynı kalır.
"""
import hashlib
import math
import re

DIM = 768
_TOK = re.compile(r"[a-z0-9]+")


def _tokens(text: str):
    return _TOK.findall((text or "").lower())


def embed(text: str) -> list:
    """Kelime -> deterministik pseudo-rastgele 768-dim vektör (L2 normalize)."""
    v = [0.0] * DIM
    for tok in _tokens(text):
        h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:8], "big")
        idx = h % DIM
        sign = 1.0 if (h >> 63) & 1 else -1.0
        v[idx] += sign
    n = math.sqrt(sum(x * x for x in v))
    if n == 0.0:
        return v
    return [x / n for x in v]


def cosine(a, b) -> float:
    """İki normalize vektör arası kosinüs (dot product)."""
    return float(sum(x * y for x, y in zip(a, b)))
