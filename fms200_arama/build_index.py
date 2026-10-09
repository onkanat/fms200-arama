#!/usr/bin/env python3
"""FMS-200 arşivini tarar, SQLite + FTS5 indeksi kurar.

Metin kaynak önceliği (en iyiden alta):
  1. en_iyi/          (kalite_karsilastir.py: sayfa-sayfa EN IYI secilmis metin)
  2. ocr_deepseek/    (DeepSeek-OCR — temiz markdown)
  3. ocr_deepseek_plain/ (DeepSeek-OCR 'Free OCR' modu)
  4. ocr_metin/       (tesseract)
  5. metin/sayfa_*.txt (Scribd metin katmanı / harf aralı olabilir)

Kullanım:
    python -m fms200_arama.build_index --root ../fms-200 --db data/fms200.db
"""
import argparse
import glob
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fms200_arama.norm import norm, detect_lang  # noqa: E402
from fms200_arama import vec as _vec  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DDL = """
CREATE TABLE IF NOT EXISTS pages(
  id         INTEGER PRIMARY KEY,
  doc        TEXT NOT NULL,
  page       INTEGER,
  lang       TEXT,
  kind       TEXT,
  src_path   TEXT,
  image_path TEXT,
  text       TEXT,
  vector     BLOB,
  label      TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
  normtext,
  tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE INDEX IF NOT EXISTS idx_pages_doc ON pages(doc);
CREATE INDEX IF NOT EXISTS idx_pages_lang ON pages(lang);
"""

_PAGE_RE = re.compile(r"sayfa[_\-]?(\d+)", re.I)


def _page_no(stem):
    m = _PAGE_RE.search(stem)
    return int(m.group(1)) if m else None


def _find_image(doc_dir, page):
    if page is None:
        return None
    for sub in ("sayfalar", "semalar", "jpg"):
        d = os.path.join(doc_dir, sub)
        if os.path.isdir(d):
            for cand in (f"sayfa_{page:03d}.jpg", f"sayfa_{page}.jpg",
                         f"sayfa_{page:03d}.webp", f"sayfa_{page}.webp"):
                p = os.path.join(d, cand)
                if os.path.exists(p):
                    return p
    return None


def _collect_doc_pages(doc_dir):
    """Bir doküman klasörü için {page_no: (text, kind, src)} — öncelik sırasına göre."""
    pages = {}
    # öncelik: düşük sayı = yüksek öncelik
    kaynaklar = [
        ("en_iyi", 0),
        ("ocr_deepseek", 1),
        ("ocr_deepseek_plain", 2),
        ("ocr_metin", 3),
        ("metin", 4),
    ]
    for sub, pri in kaynaklar:
        d = os.path.join(doc_dir, sub)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".txt") or f.endswith("_TAM_METIN.txt"):
                continue
            pn = _page_no(f)
            if pn is None:
                continue
            key = (pn,)
            mevcut = pages.get(pn)
            if mevcut is None or pri < mevcut[3]:
                try:
                    txt = open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                pages[pn] = (txt, ("ocr" if "ocr" in sub else "page"), os.path.join(d, f), pri)
    return pages


def _collect_images(doc_dir):
    """Klasördeki sayfa görsellerini {sayfa_no: yol} olarak toplar (metinsiz şemalar dahil).

    Görseller {sayfalar,semalar,jpg} alt klasöründe VEYA doğrudan doc_dir içinde olabilir.
    """
    imgs = {}
    subdirler = [os.path.join(doc_dir, s) for s in ("sayfalar", "semalar", "jpg")] + [doc_dir]
    for d in subdirler:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            pn = _page_no(f)
            if pn is not None and pn not in imgs:
                imgs[pn] = os.path.join(d, f)
    return imgs


def _iter_units(root):
    """(doc, page, text, src_path, image_path) üretir. Metinsiz görsel sayfalar da dahildir."""
    dok = os.path.join(root, "dokuman")
    if os.path.isdir(dok):
        for d in sorted(glob.glob(os.path.join(dok, "*"))):
            if not os.path.isdir(d):
                continue
            doc = os.path.basename(d)
            pages = _collect_doc_pages(d)
            imgs = _collect_images(d)
            # tüm sayfa numaraları birleşimi (metin ∪ görsel)
            for pn in sorted(set(pages) | set(imgs)):
                txt = ""
                src = None
                if pn in pages:
                    txt, _kind, src, _ = pages[pn]
                img = imgs.get(pn) or _find_image(d, pn)
                if txt.strip() or img:
                    yield doc, pn, txt, src, img
            if not pages and not imgs:
                # sayfa yoksa birleşik metin / tekil txt
                for f in sorted(glob.glob(os.path.join(d, "*.txt"))):
                    txt = open(f, encoding="utf-8", errors="replace").read()
                    if txt.strip():
                        yield doc, None, txt, f, None
        # dokuman/*.txt (kataloglar)
        for f in sorted(glob.glob(os.path.join(dok, "*.txt"))):
            txt = open(f, encoding="utf-8", errors="replace").read()
            if txt.strip():
                yield "katalog", None, txt, f, None
        # dokuman/ kökündeki başıboş görseller (HowToOrder vb.)
        for f in sorted(glob.glob(os.path.join(dok, "*.jpg")) + glob.glob(os.path.join(dok, "*.png"))):
            yield os.path.splitext(os.path.basename(f))[0], None, "", f, f
    # mekanik çizimler (metinsiz — yalnız hızlı erişim için görsel olarak indekslenir)
    for d in sorted(glob.glob(os.path.join(root, "mekanik", "*"))):
        if not os.path.isdir(d):
            continue
        doc = "Mekanik_" + os.path.basename(d)
        # görseller alt klasörde OLABİLİR ya da doğrudan bu klasörde
        imgs = {}
        for sub in (d, os.path.join(d, "sayfalar"), os.path.join(d, "jpg")):
            for f in sorted(glob.glob(os.path.join(sub, "*.jpg")) + glob.glob(os.path.join(sub, "*.png"))):
                pn = _page_no(os.path.basename(f)) or (len(imgs) + 1)
                imgs.setdefault(pn, f)
        for pn, img in sorted(imgs.items()):
            yield doc, pn, "", None, img
    # kök düzeyindeki tekil görseller (mekanik/HowToOrder vb.)
    for f in sorted(glob.glob(os.path.join(root, "mekanik", "*.jpg"))):
        yield os.path.splitext(os.path.basename(f))[0], None, "", f, f
    # yazilim/*.txt + kök markdown dökümanları (README, MODUL_LISTESI, ...)
    for f in sorted(glob.glob(os.path.join(root, "*.md"))):
        txt = open(f, encoding="utf-8", errors="replace").read()
        if txt.strip():
            yield os.path.splitext(os.path.basename(f))[0], None, txt, f, None
    for f in sorted(glob.glob(os.path.join(root, "yazilim", "*.txt"))):
        txt = open(f, encoding="utf-8", errors="replace").read()
        if txt.strip():
            yield "yazilim", None, txt, f, None


def build(root, db, verbose=True, do_embed=True):
    root = os.path.abspath(root)
    os.makedirs(os.path.dirname(os.path.abspath(db)) or ".", exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(DDL)
    # şema göçü: eski DB'de vector/label kolonu yoksa ekle
    kolonlar = [r[1] for r in con.execute("PRAGMA table_info(pages)")]
    if "vector" not in kolonlar:
        con.execute("ALTER TABLE pages ADD COLUMN vector BLOB")
    if "label" not in kolonlar:
        con.execute("ALTER TABLE pages ADD COLUMN label TEXT")
    con.execute("DELETE FROM pages")
    con.execute("DELETE FROM pages_fts")
    con.commit()

    # embedding arka ucu (bir kez belirle: tüm vektörler aynı arka uçla üretilmeli)
    backend, model, dim = ("hashing", "", _vec.DIM)
    if do_embed:
        try:
            backend, model, dim = _vec.backend_info()
        except Exception:
            backend = "hashing"
    con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('embed_backend',?)", (backend,))
    con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('embed_model',?)", (model,))
    con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('embed_dim',?)", (str(dim),))

    # önce tüm kayıtları topla, sonra toplu vektör çıkar
    kayitlar = []
    for doc, page, txt, src, img in _iter_units(root):
        kayitlar.append((doc, page, txt, src, img))
    # etiket metni varsa onu (daha temiz bağlam), yoksa sayfa metnini göm
    etiketler = _etiketleri_oku(con)
    texts = [_embed_metni(etiketler.get((doc, page)), doc, page, txt)
             for (doc, page, txt, src, img) in kayitlar]

    vecs = [None] * len(kayitlar)
    if do_embed and any(t.strip() for t in texts):
        B = 24
        for i in range(0, len(texts), B):
            parca = texts[i:i + B]
            parca = [t if t.strip() else " " for t in parca]
            try:
                vs = _vec.embed_batch(parca, backend=backend)
            except Exception:
                # sunucu düştü → hashing'e geç (tutarlılık için tümü hashing yapılır)
                backend = "hashing"
                con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('embed_backend','hashing')")
                vs = _vec.embed_batch(parca, backend="hashing")
            for j, v in enumerate(vs):
                vecs[i + j] = _vec.to_blob(v)

    n = 0
    for (doc, page, txt, src, img), vec in zip(kayitlar, vecs):
        cur = con.execute(
            "INSERT INTO pages(doc,page,lang,kind,src_path,image_path,text,vector,label) VALUES(?,?,?,?,?,?,?,?,?)",
            (doc, page, detect_lang(txt), "page" if page is not None else "doc",
             os.path.relpath(src, root) if src else None,
             os.path.relpath(img, root) if img else None, txt, vec,
             etiketler.get((doc, page))),
        )
        con.execute("INSERT INTO pages_fts(rowid, normtext) VALUES(?,?)", (cur.lastrowid, norm(txt)))
        n += 1
    con.commit()
    con.execute("INSERT INTO pages_fts(pages_fts) VALUES('optimize')")
    con.commit()
    con.close()
    if verbose:
        print(f"indeks: {n} kayit -> {db} | embed={backend}"
              + (f" ({model}, {dim}-dim)" if backend == "server" else ""))
    return n


def _etiketleri_oku(con):
    """pages(label) doluysa {(doc,page): label} — yeniden indekslemede etiketleri korur."""
    out = {}
    try:
        for doc, page, lb in con.execute("SELECT doc,page,label FROM pages WHERE label IS NOT NULL AND label<>''"):
            out[(doc, page)] = lb
    except sqlite3.Error:
        pass
    return out


def _embed_metni(etiket, doc, page, txt):
    """Gömülecek metin: elle etiket varsa etiket + sayfa metni başlığı, yoksa sayfa metni."""
    parts = [etiket or "", doc.replace("_", " ")]
    if page is not None:
        parts.append(f"sayfa {page}")
    parts.append((txt or "")[:1800])
    return "\n".join(p for p in parts if p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.abspath(os.path.join(HERE, "..", "..", "MacAir", "fms-200")))
    ap.add_argument("--db", default=os.path.join(HERE, "..", "data", "fms200.db"))
    a = ap.parse_args()
    build(a.root, a.db)
