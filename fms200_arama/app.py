#!/usr/bin/env python3
"""FMS-200 arama arayüzü (FastAPI).

Çalıştır:
    uvicorn fms200_arama.app:app --host 127.0.0.1 --port 8765
"""
import os
import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from . import search as se

try:                      # markdown render (opsiyonel: yoksa düz metin döner)
    import markdown as _md
except ImportError:       # pragma: no cover
    _md = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "MacAir", "fms-200"))  # varsayılan arşiv
DB = os.path.abspath(os.path.join(HERE, "..", "data", "fms200.db"))
WEB = os.path.abspath(os.path.join(HERE, "..", "web"))

app = FastAPI(title="FMS-200 Arama")


def _root():
    return os.environ.get("FMS200_ROOT", ROOT)


@app.get("/", response_class=HTMLResponse)
def index():
    return open(os.path.join(WEB, "index.html"), encoding="utf-8").read()


@app.get("/api/search")
def api_search(q: str = Query(""), lang: str | None = None, doc: str | None = None,
               mode: str = "hybrid", limit: int = 30):
    if not q.strip():
        return {"count": 0, "results": []}
    rows = se.search(q, db=DB, limit=limit, lang=lang or None, doc=doc or None, mode=mode)
    out = [{"doc": r["doc"], "page": r["page"], "lang": r["lang"], "kind": r["kind"],
            "snippet": r.get("snippet") or "", "score": r.get("score") or 0,
            "rrf": r.get("rrf") or 0, "has_image": bool(r.get("image_path"))} for r in rows]
    return {"count": len(out), "results": out}


def _markdown_renderle(doc: str, text: str) -> str | None:
    """Kok .md dökümanlarını HTML'e çevirir; markdown yoksa/başarısızsa None."""
    if _md is None or not text:
        return None
    src = os.path.join(_root(), doc + ".md")
    if not os.path.exists(src):        # yalnız gerçek bir .md dosyasıysa render et
        return None
    try:
        return _md.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "nl2br"])
    except Exception:                  # pragma: no cover
        return None


@app.get("/api/page")
def api_page(doc: str, page: int | None = None):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    if page is None:
        row = con.execute("SELECT * FROM pages WHERE doc=? ORDER BY id LIMIT 1", (doc,)).fetchone()
    else:
        row = con.execute("SELECT * FROM pages WHERE doc=? AND page=?", (doc, page)).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, "sayfa bulunamadı")
    return {"doc": row["doc"], "page": row["page"], "lang": row["lang"], "text": row["text"],
            "html": _markdown_renderle(row["doc"], row["text"]),
            "image_url": f"/api/file?p={row['image_path']}" if row["image_path"] else None}


@app.get("/api/file")
def api_file(p: str):
    """İndeksteki göreli görsel yolunu güvenli şekilde sunar."""
    root = _root()
    full = os.path.abspath(os.path.join(root, p))
    if not full.startswith(root) or not os.path.exists(full):
        raise HTTPException(404, "dosya yok")
    return FileResponse(full)


@app.get("/api/docs")
def api_docs():
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT doc, lang, COUNT(*) c FROM pages GROUP BY doc, lang ORDER BY doc").fetchall()
    con.close()
    return {"docs": [{"doc": r[0], "lang": r[1], "count": r[2]} for r in rows]}


@app.get("/api/doc_pages")
def api_doc_pages(doc: str):
    """Bir dokümanın tüm sayfalarını (metin/görsel) listeler — şema gözatma için."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT page, lang, image_path, length(text) AS tlen FROM pages"
        " WHERE doc=? ORDER BY (page IS NULL), page", (doc,)).fetchall()
    con.close()
    return {"doc": doc, "pages": [
        {"page": r["page"], "lang": r["lang"], "tlen": r["tlen"],
         "image_url": f"/api/file?p={r['image_path']}" if r["image_path"] else None} for r in rows]}
