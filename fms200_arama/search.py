"""FMS-200 hibrit arama: FTS5 (bm25) + hashing-vektör, RRF ile birleşik.

CLI:
    python -m fms200_arama.search "plc programlama"
    python -m fms200_arama.search "rodamiento" --lang es --limit 5
"""
import argparse
import os
import re
import sqlite3

from .norm import norm
from .vec import embed_batch, cosine, from_blob

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(HERE, "..", "data", "fms200.db")
RRF_K = 60


def _fts_query(q: str) -> str:
    """Serbest metni FTS5 sorgusuna çevir: token'lar AND'lenir, son token prefix."""
    toks = [t for t in re.findall(r"[^\s]+", norm(q)) if re.search(r"[A-Za-z0-9]", t)]
    if not toks:
        return ""
    parts = []
    for i, t in enumerate(toks):
        safe = re.sub(r"['()*:^\"-]", " ", t).strip()
        if not safe:
            continue
        parts.append(f'"{safe}"*' if i == len(toks) - 1 else f'"{safe}"')
    return " AND ".join(parts)


def _where(lang, doc):
    """WHERE koşullarını (alias'sız) ve parametreleri döndürür."""
    w, a = [], []
    if lang:
        w.append("lang = ?"); a.append(lang)
    if doc:
        w.append("doc = ?"); a.append(doc)
    return (" AND ".join(w)) if w else "", a


def _lexical(con, fts_q, lang, doc, limit):
    wsql, args = _where(lang, doc)
    fts_where = f" AND {wsql}" if wsql else ""
    sql = (
        "SELECT p.id,p.doc,p.page,p.lang,p.kind,p.src_path,p.image_path,p.text,"
        " bm25(pages_fts) AS score,"
        " snippet(pages_fts,0,'[',']',' … ',14) AS snippet"
        " FROM pages_fts f JOIN pages p ON p.id=f.rowid"
        f" WHERE pages_fts MATCH ?{fts_where} ORDER BY score LIMIT ?"
    )
    return con.execute(sql, [fts_q, *args, limit]).fetchall()


def _semantic(con, q, lang, doc, pool):
    """Sorguyu DB'deki vektörlerle karşılaştırır (vektörler DB'de saklı)."""
    wsql, args = _where(lang, doc)
    sql = "SELECT id,vector FROM pages"
    if wsql:
        sql += " WHERE " + wsql
    rows = con.execute(sql, args).fetchall()
    backend = _meta(con, "embed_backend", "hashing")
    try:
        qv = embed_batch([q], backend=backend)[0]
    except Exception:
        qv = embed_batch([q], backend="hashing")[0]
        backend = "hashing"
    scored = []
    for rid, blob in rows:
        if not blob:
            continue
        s = cosine(qv, from_blob(blob))
        if s > 0:
            scored.append((s, rid))
    scored.sort(reverse=True)
    return [rid for _, rid in scored[:pool]]


def _meta(con, k, default=None):
    try:
        r = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else default
    except sqlite3.Error:
        return default


def search(q, db=DEFAULT_DB, limit=20, lang=None, doc=None, mode="hybrid"):
    """Hibrit arama. mode: 'lexical' | 'semantic' | 'hybrid'."""
    if not q or not q.strip():
        return []
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    fts_q = _fts_query(q)
    lex = _lexical(con, fts_q, lang, doc, limit * 3) if fts_q else []
    sem_ids = _semantic(con, q, lang, doc, limit * 3) if mode in ("semantic", "hybrid") else []
    sem_rows = {}
    if sem_ids:
        ph = ",".join("?" * len(sem_ids))
        sem_rows = {r[0]: r for r in con.execute(
            f"SELECT id,doc,page,lang,kind,src_path,image_path,text,0 AS score,'' AS snippet"
            f" FROM pages WHERE id IN ({ph})", sem_ids).fetchall()}
    con.close()

    fused = {}
    if mode in ("lexical", "hybrid"):
        for rank, r in enumerate(lex):
            fused.setdefault(r["id"], {"row": dict(r), "rrf": 0.0})["rrf"] += 1.0 / (RRF_K + rank + 1)
    if mode in ("semantic", "hybrid"):
        lex_ids = {r["id"] for r in lex}
        for rank, rid in enumerate(sem_ids):
            if rid not in sem_rows:
                continue
            e = fused.setdefault(rid, {"row": dict(sem_rows[rid]), "rrf": 0.0})
            e["rrf"] += 1.0 / (RRF_K + rank + 1)
            if not e["row"].get("snippet") and rid in lex_ids:
                e["row"] = dict(next(r for r in lex if r["id"] == rid))
    out = [dict(v["row"]) | {"rrf": v["rrf"]} for v in fused.values()]
    out.sort(key=lambda x: -x["rrf"])
    return out[:limit]


def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--lang", default=None)
    ap.add_argument("--doc", default=None)
    ap.add_argument("--mode", default="hybrid", choices=["lexical", "semantic", "hybrid"])
    a = ap.parse_args()
    for r in search(a.query, db=a.db, limit=a.limit, lang=a.lang, doc=a.doc, mode=a.mode):
        print(f"  {r['doc']:44s} s.{str(r['page']):>4s} [{r['lang']}] rrf={r['rrf']:.4f}")
        if r.get("snippet"):
            print(f"      … {r['snippet'][:160]}")


if __name__ == "__main__":
    _cli()
