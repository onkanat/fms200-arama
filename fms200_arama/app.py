#!/usr/bin/env python3
"""FMS-200 arama + düzenleme arayüzü (FastAPI).

Çalıştır:
    uvicorn fms200_arama.app:app --host 0.0.0.0 --port 8765
"""
import os
import sqlite3
import subprocess

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from . import search as se
from . import build_index as _bi
from . import vec as _vec
from .norm import norm

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


# ---------------------------------------------------------------- markdown edit
# Düzenlenebilir (".md" ile temsil edilen) dokümanların konumları:
_MD_ALT = ("", "durum", "yazilim")


def _md_yolu(doc: str) -> str | None:
    """doc adına karşılık gelen .md dosyasını bulur (kök / durum / yazilim)."""
    for sub in _MD_ALT:
        p = os.path.join(_root(), sub, doc + ".md")
        if os.path.exists(p):
            return p
    return None


def _markdown_renderle(doc: str, text: str) -> str | None:
    """Düzenlenebilir .md dökümanlarını HTML'e çevirir; .md değilse None."""
    if _md is None or not text or not _md_yolu(doc):
        return None
    try:
        return _md.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "nl2br"])
    except Exception:                  # pragma: no cover
        return None


def _git_root(yol: str) -> str | None:
    """Dosyanın içinde bulunduğu git deposunun kökünü döndürür (yoksa None)."""
    try:
        out = subprocess.run(["git", "-C", os.path.dirname(yol), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def _git_imza(user: str) -> tuple[str, str]:
    """Kullanıcı adını güvenli bir git yazar kimliğine çevirir."""
    ad = (user or "anonim").strip()[:60] or "anonim"
    slug = "".join(c if c.isalnum() else "-" for c in ad.lower()).strip("-") or "anonim"
    return ad, f"{slug}@fms200.local"


def _git_commit(yol: str, user: str, mesaj: str) -> dict:
    """Dosyayı git'e ekler ve yazar kimliğiyle commit eder (kim ne yaptı kaydı)."""
    kok = _git_root(yol)
    if not kok:
        return {"commit": False, "sebep": "git deposu yok"}
    ad, ep = _git_imza(user)
    rel = os.path.relpath(os.path.realpath(yol), os.path.realpath(kok))
    try:
        subprocess.run(["git", "-C", kok, "add", rel],
                       capture_output=True, text=True, timeout=15)
        r = subprocess.run(["git", "-C", kok, "-c", f"user.name={ad}", "-c", f"user.email={ep}",
                            "commit", "-q", "-m", mesaj], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            if "nothing to commit" in (r.stdout + r.stderr):
                return {"commit": False, "sebep": "değişiklik yok"}
            return {"commit": False, "sebep": (r.stderr or r.stdout).strip()[:160]}
        h = subprocess.run(["git", "-C", kok, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10).stdout.strip()
        return {"commit": True, "hash": h, "yazar": f"{ad} <{ep}>"}
    except Exception as e:                                  # pragma: no cover
        return {"commit": False, "sebep": str(e)[:160]}


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
    yol = _md_yolu(row["doc"])
    return {"doc": row["doc"], "page": row["page"], "lang": row["lang"], "text": row["text"],
            "html": _markdown_renderle(row["doc"], row["text"]),
            "label": row["label"] if "label" in row.keys() else None,
            "md": bool(yol), "md_path": os.path.relpath(yol, _root()) if yol else None,
            "image_url": f"/api/file?p={row['image_path']}" if row["image_path"] else None}


@app.post("/api/save")
def api_save(payload: dict):
    """Düzenlenebilir .md dökümanını diske yazar, indeksi günceller, git'e commit eder."""
    doc = (payload.get("doc") or "").strip()
    text = payload.get("text")
    user = payload.get("user") or "anonim"
    if not doc or text is None:
        raise HTTPException(400, "doc ve text gerekli")
    yol = _md_yolu(doc)
    if not yol:
        raise HTTPException(400, f"{doc} düzenlenebilir bir .md değil")
    with open(yol, encoding="utf-8") as f:
        eski = f.read()
    if eski == text:
        return {"ok": True, "degisti": False, "commit": {"commit": False, "sebep": "değişiklik yok"}}
    with open(yol, "w", encoding="utf-8") as f:
        f.write(text)
    # --- indeks güncelle (pages.text + FTS + vektör) ---
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT id FROM pages WHERE doc=? ORDER BY id LIMIT 1", (doc,)).fetchone()
    vektor_ok = None
    if row:
        con.execute("UPDATE pages SET text=? WHERE id=?", (text, row["id"]))
        con.execute("UPDATE pages_fts SET normtext=? WHERE rowid=?", (norm(text), row["id"]))
        try:
            _, model, _ = _vec.backend_info()
            v = _vec.embed_batch([text[:1800] or " "], backend="server")[0]
            con.execute("UPDATE pages SET vector=? WHERE id=?", (_vec.to_blob(v), row["id"]))
            vektor_ok = True
        except Exception:
            vektor_ok = False
        con.commit()
    con.close()
    # --- git kaydı (kim ne değiştirdi) ---
    ozet = text.strip().splitlines()[0][:60] if text.strip() else "(boş)"
    commit = _git_commit(yol, user, f"{doc}: {ozet} [düzenleyen: {user}]")
    return {"ok": True, "degisti": True, "vektor": vektor_ok, "commit": commit}


@app.post("/api/md_preview")
def api_md_preview(payload: dict):
    """Markdown metnini HTML'e çevirir (düzenleyicide canlı önizleme için)."""
    if _md is None:
        raise HTTPException(503, "markdown modülü yok")
    try:
        return {"html": _md.markdown(payload.get("text") or "",
                                     extensions=["tables", "fenced_code", "sane_lists", "nl2br"])}
    except Exception as e:                                  # pragma: no cover
        return {"html": "", "hata": str(e)}


@app.get("/api/history")
def api_history(doc: str, limit: int = 20):
    """Bir .md dökümanının git geçmişi (kim, ne zaman, ne)."""
    yol = _md_yolu(doc)
    if not yol:
        return {"doc": doc, "commits": []}
    kok = _git_root(yol)
    if not kok:
        return {"doc": doc, "commits": []}
    try:
        r = subprocess.run(
            ["git", "-C", kok, "log", f"-{max(1, min(limit, 100))}",
             "--pretty=%h\x1f%an\x1f%ad\x1f%s", "--date=format:%Y-%m-%d %H:%M",
             "--", os.path.relpath(os.path.realpath(yol), os.path.realpath(kok))],
            capture_output=True, text=True, timeout=15)
        commits = []
        for satir in r.stdout.strip().splitlines():
            p = satir.split("\x1f")
            if len(p) == 4:
                commits.append({"hash": p[0], "yazar": p[1], "tarih": p[2], "mesaj": p[3]})
        return {"doc": doc, "commits": commits}
    except Exception as e:                                  # pragma: no cover
        return {"doc": doc, "commits": [], "hata": str(e)[:160]}


@app.get("/api/status")
def api_status():
    """İndeks durumu: arka uç, kayıt sayısı, DB yaşı."""
    con = sqlite3.connect(DB)
    n = con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    lbl = con.execute("SELECT COUNT(*) FROM pages WHERE label IS NOT NULL AND label<>''").fetchone()[0]
    meta = {k: v for k, v in con.execute("SELECT k,v FROM meta").fetchall()} if _has_meta(con) else {}
    con.close()
    db_mtime = os.path.getmtime(DB)
    arsiv_mtime = _en_yeni_mtime(_root())
    return {"kayit": n, "etiketli": lbl, "embed": meta.get("embed_backend", "?"),
            "model": meta.get("embed_model", ""), "db": db_mtime,
            "arsiv_en_yeni": arsiv_mtime, "bayat": arsiv_mtime > db_mtime + 1}


@app.post("/api/reindex")
def api_reindex():
    """Arşivi yeniden indeksler (arka uç otomatik seçilir)."""
    try:
        n = _bi.build(_root(), DB, verbose=False)
        return {"ok": True, "kayit": n}
    except Exception as e:
        raise HTTPException(500, f"indeks hatası: {e}")


@app.post("/api/label")
def api_label(payload: dict):
    """Sayfa/görsel için etiket kaydeder (arama bu etiketle de bulur)."""
    doc = (payload.get("doc") or "").strip()
    label = (payload.get("label") or "").strip()
    page = payload.get("page")
    if not doc or not label:
        raise HTTPException(400, "doc ve label gerekli")
    con = sqlite3.connect(DB)
    if page is None:
        con.execute("UPDATE pages SET label=? WHERE doc=? AND page IS NULL", (label, doc))
    else:
        con.execute("UPDATE pages SET label=? WHERE doc=? AND page=?", (label, doc, int(page)))
    con.commit()
    # etiket metnini FTS'e de yaz (anında aranabilir olsun)
    for rid, in con.execute(
            "SELECT id FROM pages WHERE doc=? AND (? IS NULL OR page=?)", (doc, page, page)).fetchall():
        con.execute("UPDATE pages_fts SET normtext=normtext||' '||? WHERE rowid=?", (label, rid))
    con.commit()
    con.close()
    return {"ok": True}


def _has_meta(con):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone())


def _en_yeni_mtime(root):
    yeni = 0.0
    for d, _, fs in os.walk(root):
        if "/." in d or "/.venv" in d or "/__pycache__" in d:
            continue
        for f in fs:
            if f.lower().endswith((".md", ".txt", ".jpg", ".jpeg", ".png", ".webp", ".pdf")):
                try:
                    yeni = max(yeni, os.path.getmtime(os.path.join(d, f)))
                except OSError:
                    pass
    return yeni


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
    return {"docs": [{"doc": r[0], "lang": r[1], "count": r[2], "md": bool(_md_yolu(r[0]))}
                     for r in rows]}


@app.get("/api/doc_pages")
def api_doc_pages(doc: str):
    """Bir dokümanın tüm sayfalarını (metin/görsel) listeler — şema gözatma için."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT page, lang, image_path, length(text) AS tlen FROM pages"
        " WHERE doc=? ORDER BY (page IS NULL), page", (doc,)).fetchall()
    con.close()
    return {"doc": doc, "md": bool(_md_yolu(doc)), "pages": [
        {"page": r["page"], "lang": r["lang"], "tlen": r["tlen"],
         "image_url": f"/api/file?p={r['image_path']}" if r["image_path"] else None} for r in rows]}
