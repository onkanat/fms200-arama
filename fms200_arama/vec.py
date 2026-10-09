"""Embedding arka ucu: (a) sunucu (nomic-embed-text, gerçek anlam), (b) hashing (0-token yedek).

- Varsayılan: `FMS200_EMBED_URL` tanımlıysa **sunucu** embedding'i; değilse **hashing**.
  `FMS200_EMBED_URL` ör. `http://192.168.1.26:11434`, model `FMS200_EMBED_MODEL` (vars. nomic-embed-text).
- Sunucu erişilemezse **sessizce hashing'e düşer** (arama çalışmaya devam eder).
- Vektörler DB'ye float32 blob olarak yazılır; hangi arka uçla üretildiği `meta`da saklanır
  (sorgu aynı arka uçla gömülmeli).

Arayüz: `embed_batch(texts, backend=None)` · `embed(text)` (geriye uyum) · `backend_info()` ·
`to_blob` / `from_blob` · `cosine`.
"""
import hashlib
import json
import math
import os
import re
import struct
import urllib.request

DIM = 768
_TOK = re.compile(r"[a-z0-9]+")


def _tokens(text: str):
    return _TOK.findall((text or "").lower())


def _hashing(text: str) -> list:
    """Kelime -> deterministik pseudo-rastgele 768-dim vektör (L2 normalize)."""
    v = [0.0] * DIM
    for tok in _tokens(text):
        h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:8], "big")
        idx = h % DIM
        sign = 1.0 if (h >> 63) & 1 else -1.0
        v[idx] += sign
    return _norm(v)


def _norm(v: list) -> list:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def _cfg():
    url = os.environ.get("FMS200_EMBED_URL", "").rstrip("/")
    model = os.environ.get("FMS200_EMBED_MODEL", "nomic-embed-text")
    return url, model


def _server_embed(texts, timeout=90):
    url, model = _cfg()
    payload = {"model": model, "input": list(texts)}
    req = urllib.request.Request(
        f"{url}/api/embed", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        embs = json.loads(r.read().decode("utf-8"))["embeddings"]
    return [_norm([float(x) for x in e]) for e in embs]


def embed_batch(texts, backend=None, timeout=90):
    """Metin listesi -> vektör listesi.

    backend: 'server' | 'hashing' | None (None = FMS200_EMBED_URL varsa sunucu dene, olmazsa hashing).
    """
    texts = list(texts)
    if backend == "hashing":
        return [_hashing(t) for t in texts]
    url, _ = _cfg()
    if backend == "server" or (backend is None and url):
        if not url:
            raise RuntimeError("FMS200_EMBED_URL tanımlı değil")
        return _server_embed(texts, timeout=timeout)
    return [_hashing(t) for t in texts]


def embed(text: str) -> list:
    """Geriye uyumlu tek metin gömme (varsayılan: sunucu varsa sunucu)."""
    return embed_batch([text])[0]


def backend_info():
    """(backend, model, dim) — sunucu erişilebilirse ('server', model, 768), yoksa ('hashing', '', 768)."""
    url, model = _cfg()
    if url:
        try:
            v = _server_embed(["ping"], timeout=12)[0]
            return ("server", model, len(v))
        except Exception:
            pass
    return ("hashing", "", DIM)


def to_blob(vec) -> bytes:
    return struct.pack(f"<{len(vec)}f", *[float(x) for x in vec])


def from_blob(b) -> list:
    return list(struct.unpack(f"<{len(b) // 4}f", b))


def cosine(a, b) -> float:
    """İki normalize vektörün kosinüsü (dot product)."""
    return float(sum(x * y for x, y in zip(a, b)))
