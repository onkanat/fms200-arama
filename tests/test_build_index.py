"""build_index davranış testleri.

Bağlam: `build()` indeksi kurarken `pages`/`pages_fts` tablolarını DELETE eder. Elle verilen
etiketler (`label`) bu silmeden ÖNCE okunmazsa yeniden indeksleme onları kaybeder
(2026-10-10'da canlıda 81 etiket böyle silindi). Bu dosya o regresyonu kilitler.
"""
import os
import sqlite3

from fms200_arama import build_index as bi


def _kur(root):
    d = os.path.join(root, "dokuman", "FMS200_Z")
    os.makedirs(os.path.join(d, "metin"), exist_ok=True)
    os.makedirs(os.path.join(d, "sayfalar"), exist_ok=True)
    open(os.path.join(d, "metin", "sayfa_001.txt"), "w", encoding="utf-8").write("FMS-200 GRAFCET istasyon")
    open(os.path.join(d, "metin", "sayfa_002.txt"), "w", encoding="utf-8").write("FMS-200 pnömatik şema")
    open(os.path.join(d, "sayfalar", "sayfa_001.jpg"), "wb").write(b"\xff\xd8" + b"0" * 5000)


def _labels(db):
    con = sqlite3.connect(db)
    out = {r[0]: r[1] for r in con.execute(
        "SELECT page, label FROM pages WHERE label IS NOT NULL AND label<>''")}
    con.close()
    return out


def test_yeniden_indeksleme_etiketi_korur(tmp_path):
    """Elle yazılan etiket, yeniden indekslemeden sonra DB'de ve FTS'te kalmalı."""
    root = os.path.join(str(tmp_path), "fms200")
    _kur(root)
    db = os.path.join(str(tmp_path), "t.db")
    bi.build(root=root, db=db, verbose=False)
    con = sqlite3.connect(db)
    con.execute("UPDATE pages SET label=? WHERE doc=? AND page=1", ("EST.1 · zebra besleme", "FMS200_Z"))
    con.commit()
    con.close()

    bi.build(root=root, db=db, verbose=False)          # yeniden indeksleme

    assert _labels(db).get(1) == "EST.1 · zebra besleme", "etiket yeniden indekslemede silindi"
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM pages_fts WHERE pages_fts MATCH 'zebra'").fetchone()[0]
    con.close()
    assert n == 1, "etiket metni FTS'e yazılmadı — etiketle arama yeniden indekslemede kaybolur"


def test_etiket_yoksa_indeks_yine_kurulur(tmp_path):
    """Etiketsiz DB'de davranış değişmemeli (regresyon: eski kod yolu)."""
    root = os.path.join(str(tmp_path), "fms200")
    _kur(root)
    db = os.path.join(str(tmp_path), "t.db")
    n1 = bi.build(root=root, db=db, verbose=False)
    n2 = bi.build(root=root, db=db, verbose=False)
    assert n1 == n2 and n1 == 2
    assert _labels(db) == {}


def test_fts_sema_migrasyonu(tmp_path):
    """Eski tek-kolonlu pages_fts, `labeltext` kolonlu yeni şemaya yükseltilmeli."""
    root = os.path.join(str(tmp_path), "fms200")
    _kur(root)
    db = os.path.join(str(tmp_path), "t.db")
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE pages(id INTEGER PRIMARY KEY, doc TEXT NOT NULL, page INTEGER, lang TEXT,\n"
        "  kind TEXT, src_path TEXT, image_path TEXT, text TEXT, vector BLOB, label TEXT);\n"
        "CREATE VIRTUAL TABLE pages_fts USING fts5(normtext, tokenize='unicode61 remove_diacritics 2');\n")
    con.commit()
    assert "labeltext" not in {r[1] for r in con.execute("PRAGMA table_info(pages_fts)")}
    con.close()

    bi.build(root=root, db=db, verbose=False)

    con = sqlite3.connect(db)
    kol = {r[1] for r in con.execute("PRAGMA table_info(pages_fts)")}
    n = con.execute("SELECT COUNT(*) FROM pages_fts").fetchone()[0]
    con.close()
    assert "labeltext" in kol and n == 2


def test_etiket_metin_eslesmesinden_once_siralanir(tmp_path):
    """Etiket eşleşmesi (labeltext, 8x ağırlık) yoğun metin eşleşmesini geçmeli."""
    import sqlite3 as _s
    root = os.path.join(str(tmp_path), "fms200")
    d = os.path.join(root, "dokuman", "FMS200_Z")
    os.makedirs(os.path.join(d, "metin"), exist_ok=True)
    open(os.path.join(d, "metin", "sayfa_001.txt"), "w", encoding="utf-8").write(
        "zebra zebra zebra zebra cok yogun metin")
    open(os.path.join(d, "metin", "sayfa_002.txt"), "w", encoding="utf-8").write("alakasiz icerik")
    db = os.path.join(str(tmp_path), "t.db")
    bi.build(root=root, db=db, verbose=False)
    con = _s.connect(db)
    rid = con.execute("SELECT id FROM pages WHERE page=2").fetchone()[0]
    con.execute("UPDATE pages SET label=? WHERE id=?", ("cizim zebra etiketi", rid))
    con.execute("UPDATE pages_fts SET labeltext=? WHERE rowid=?", ("cizim zebra etiketi", rid))
    con.commit()
    con.close()

    from fms200_arama import search as se
    r = se.search("zebra", db=db, mode="lexical")
    assert r and r[0]["page"] == 2
