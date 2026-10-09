import os
import sqlite3

from fms200_arama import build_index as bi
from fms200_arama import search as se


def _fixture(root):
    """İki dokümanlı sahte arşiv: biri OCR (öncelikli), biri metin."""
    d1 = os.path.join(root, "dokuman", "FMS200_Y")
    os.makedirs(os.path.join(d1, "metin"), exist_ok=True)
    os.makedirs(os.path.join(d1, "ocr_deepseek"), exist_ok=True)
    os.makedirs(os.path.join(d1, "sayfalar"), exist_ok=True)
    # OCR (öncelikli) — temiz
    open(os.path.join(d1, "ocr_deepseek", "sayfa_001.txt"), "w", encoding="utf-8").write(
        "BODY SUPPLY MODULE GRAFCET istasyon")
    # metin (düşük öncelik) — harf aralı bozuk
    open(os.path.join(d1, "metin", "sayfa_001.txt"), "w", encoding="utf-8").write(
        "T E C H N I C A L garbage")
    open(os.path.join(d1, "metin", "sayfa_002.txt"), "w", encoding="utf-8").write(
        "Estación de rodamiento sistema neumático")
    open(os.path.join(d1, "sayfalar", "sayfa_002.jpg"), "wb").write(b"\xff\xd8" + b"0" * 5000)
    return root


def test_indeks_kurulur(tmp_path):
    root = _fixture(str(tmp_path))
    db = os.path.join(str(tmp_path), "t.db")
    n = bi.build(root=root, db=db, verbose=False)
    assert n == 2
    con = sqlite3.connect(db)
    rows = con.execute("SELECT doc,page,lang,image_path,text FROM pages ORDER BY page").fetchall()
    assert rows[0][0] == "FMS200_Y" and rows[0][1] == 1
    assert "BODY SUPPLY" in rows[0][4]          # OCR metni kazandı
    assert rows[1][3] and rows[1][3].endswith("sayfa_002.jpg")


def test_idempotent(tmp_path):
    root = _fixture(str(tmp_path))
    db = os.path.join(str(tmp_path), "t.db")
    bi.build(root=root, db=db, verbose=False)
    n2 = bi.build(root=root, db=db, verbose=False)
    assert n2 == 2                               # çift kayıt yok


def _setup(tmp):
    _fixture(tmp)
    db = os.path.join(tmp, "t.db")
    bi.build(root=tmp, db=db, verbose=False)
    return db


def test_fts_normalize_ile_bulur(tmp_path):
    db = _setup(str(tmp_path))
    r = se.search("GRAFCET", db=db)
    assert r and r[0]["page"] == 1


def test_dil_filtresi(tmp_path):
    db = _setup(str(tmp_path))
    r = se.search("rodamiento", db=db, lang="es")
    assert len(r) == 1 and r[0]["page"] == 2
    assert se.search("rodamiento", db=db, lang="en") == []


def test_dokuman_filtresi(tmp_path):
    db = _setup(str(tmp_path))
    assert se.search("GRAFCET", db=db, doc="FMS200_Y")
    assert se.search("GRAFCET", db=db, doc="YOK") == []


def test_snippet_var(tmp_path):
    db = _setup(str(tmp_path))
    r = se.search("GRAFCET", db=db)
    assert r and "[" in (r[0].get("snippet") or "")


def test_bos_sorgu(tmp_path):
    db = _setup(str(tmp_path))
    assert se.search("", db=db) == []


def test_lexical_hibrit_kapsar(tmp_path):
    db = _setup(str(tmp_path))
    lex = {(x["doc"], x["page"]) for x in se.search("GRAFCET", db=db, mode="lexical")}
    hyb = {(x["doc"], x["page"]) for x in se.search("GRAFCET", db=db, mode="hybrid")}
    assert lex <= hyb


def test_en_iyi_en_yuksek_oncelik(tmp_path):
    """en_iyi/ (kalite_karsilastir cikisi) TUM diger kaynaklardan once gelir."""
    root = str(tmp_path)
    d = os.path.join(root, "dokuman", "FMS200_W")
    for alt in ("en_iyi", "ocr_deepseek", "ocr_deepseek_plain", "ocr_metin", "metin"):
        os.makedirs(os.path.join(d, alt), exist_ok=True)
    open(os.path.join(d, "en_iyi", "sayfa_001.txt"), "w", encoding="utf-8").write("KAZANAN en_iyi metni")
    open(os.path.join(d, "ocr_deepseek", "sayfa_001.txt"), "w", encoding="utf-8").write("deepseek metni")
    open(os.path.join(d, "ocr_deepseek_plain", "sayfa_001.txt"), "w", encoding="utf-8").write("plain metni")
    open(os.path.join(d, "ocr_metin", "sayfa_001.txt"), "w", encoding="utf-8").write("tesseract metni")
    open(os.path.join(d, "metin", "sayfa_001.txt"), "w", encoding="utf-8").write("scribd metni")
    db = os.path.join(root, "t.db")
    bi.build(root=root, db=db, verbose=False)
    con = sqlite3.connect(db)
    metin = con.execute("SELECT text FROM pages WHERE page=1").fetchone()[0]
    assert metin == "KAZANAN en_iyi metni"


def test_en_iyi_yoksa_deepseek_yedek(tmp_path):
    """en_iyi/ yoksa (henuz uretilmemis) ocr_deepseek devralir, sonra plain."""
    root = str(tmp_path)
    d = os.path.join(root, "dokuman", "FMS200_V")
    os.makedirs(os.path.join(d, "ocr_deepseek_plain"), exist_ok=True)
    os.makedirs(os.path.join(d, "ocr_metin"), exist_ok=True)
    open(os.path.join(d, "ocr_deepseek_plain", "sayfa_001.txt"), "w", encoding="utf-8").write("plain kazandi")
    open(os.path.join(d, "ocr_metin", "sayfa_001.txt"), "w", encoding="utf-8").write("tesseract")
    db = os.path.join(root, "t.db")
    bi.build(root=root, db=db, verbose=False)
    con = sqlite3.connect(db)
    assert con.execute("SELECT text FROM pages WHERE page=1").fetchone()[0] == "plain kazandi"
