import os

import pytest
from fastapi.testclient import TestClient

from fms200_arama import app as appmod
from fms200_arama import build_index as bi


@pytest.fixture()
def client(tmp_path, monkeypatch):
    root = os.path.join(str(tmp_path), "fms200")
    d = os.path.join(root, "dokuman", "FMS200_Z")
    os.makedirs(os.path.join(d, "metin"), exist_ok=True)
    os.makedirs(os.path.join(d, "sayfalar"), exist_ok=True)
    open(os.path.join(d, "metin", "sayfa_001.txt"), "w", encoding="utf-8").write("FMS-200 GRAFCET istasyon")
    open(os.path.join(d, "sayfalar", "sayfa_001.jpg"), "wb").write(b"\xff\xd8" + b"0" * 5000)
    db = os.path.join(str(tmp_path), "t.db")
    bi.build(root=root, db=db, verbose=False)
    monkeypatch.setattr(appmod, "DB", db)
    monkeypatch.setattr(appmod, "ROOT", root)
    monkeypatch.setenv("FMS200_ROOT", root)
    return TestClient(appmod.app)


def test_index_sayfa(client):
    r = client.get("/")
    assert r.status_code == 200 and "FMS-200" in r.text


def test_api_search(client):
    r = client.get("/api/search", params={"q": "GRAFCET"})
    assert r.status_code == 200
    j = r.json()
    assert j["count"] >= 1 and "results" in j


def test_api_search_bos(client):
    assert client.get("/api/search", params={"q": ""}).json()["count"] == 0


def test_api_page(client):
    r = client.get("/api/page", params={"doc": "FMS200_Z", "page": 1})
    assert r.status_code == 200 and "GRAFCET" in r.json()["text"]


def test_api_page_yok_404(client):
    assert client.get("/api/page", params={"doc": "YOK", "page": 99}).status_code == 404


def test_api_file(client):
    r = client.get("/api/file", params={"p": "dokuman/FMS200_Z/sayfalar/sayfa_001.jpg"})
    assert r.status_code == 200


def test_api_file_traversal_engellenir(client):
    """Klasör dışına çıkma (../../) reddedilmeli."""
    r = client.get("/api/file", params={"p": "../../../etc/passwd"})
    assert r.status_code == 404


def test_api_doc_pages(client):
    r = client.get("/api/doc_pages", params={"doc": "FMS200_Z"})
    assert r.status_code == 200
    j = r.json()
    assert j["doc"] == "FMS200_Z" and len(j["pages"]) == 1
    assert j["pages"][0]["image_url"].startswith("/api/file?p=")


def test_api_docs(client):
    j = client.get("/api/docs").json()
    assert any(d["doc"] == "FMS200_Z" for d in j["docs"])


def test_md_render(client, tmp_path):
    """Kök .md dökümanı için /api/page html döndürür (tablo render); düz metin için null."""
    import os
    root = os.environ["FMS200_ROOT"]
    open(os.path.join(root, "NOTLAR.md"), "w", encoding="utf-8").write(
        "# Baslik\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    bi.build(root=root, db=appmod.DB, verbose=False)
    r = client.get("/api/page", params={"doc": "NOTLAR"})
    assert r.status_code == 200
    h = r.json()["html"]
    assert h and "<h1" in h and "<table" in h and "<td" in h
    # .md dosyasi olmayan normal sayfa -> html null, text dolu
    r2 = client.get("/api/page", params={"doc": "FMS200_Z", "page": 1})
    assert r2.json()["html"] is None and "GRAFCET" in r2.json()["text"]


def test_api_status(client):
    j = client.get("/api/status").json()
    assert j["kayit"] >= 1 and "embed" in j and "bayat" in j


def test_api_label_ve_arama(client):
    """Etiket kaydi hem label alanina yazilir hem FTS'e eklenir (aramada bulunur)."""
    r = client.post("/api/label", json={"doc": "FMS200_Z", "page": 1, "label": "ozel etiket zebra"})
    assert r.status_code == 200 and r.json()["ok"]
    p = client.get("/api/page", params={"doc": "FMS200_Z", "page": 1}).json()
    assert p["label"] == "ozel etiket zebra"
    s = client.get("/api/search", params={"q": "zebra", "mode": "lexical"}).json()
    assert s["count"] >= 1


def test_api_label_eksik_400(client):
    assert client.post("/api/label", json={"doc": "FMS200_Z"}).status_code == 400


def test_etiket_degisince_eski_terim_duser(client):
    """Etiket değiştirilince ESKİ etiket terimi aramadan düşmeli (2026-10-10 parlatması)."""
    client.post("/api/label", json={"doc": "FMS200_Z", "page": 1, "label": "zebra etiketi"})
    assert client.get("/api/search", params={"q": "zebra", "mode": "lexical"}).json()["count"] >= 1
    client.post("/api/label", json={"doc": "FMS200_Z", "page": 1, "label": "kartal etiketi"})
    assert client.get("/api/search", params={"q": "zebra", "mode": "lexical"}).json()["count"] == 0
    assert client.get("/api/search", params={"q": "kartal", "mode": "lexical"}).json()["count"] >= 1


def test_etiket_arama_sonucunda_doner(client):
    """Arayüz 🏷 rozeti için /api/search sonuçlarında `label` alanı bulunmalı."""
    client.post("/api/label", json={"doc": "FMS200_Z", "page": 1, "label": "zebra ozel etiketi"})
    j = client.get("/api/search", params={"q": "zebra", "mode": "lexical"}).json()
    assert j["results"] and j["results"][0]["label"] == "zebra ozel etiketi"


# ---------------------------------------------------------------- markdown düzenleme
def test_md_render_durum_klasoru(client, tmp_path):
    """/durum/*.md de markdown render edilmeli (kök değil, alt klasörde)."""
    import os
    root = os.environ["FMS200_ROOT"]
    os.makedirs(os.path.join(root, "durum"), exist_ok=True)
    open(os.path.join(root, "durum", "FMS209_DURUM.md"), "w", encoding="utf-8").write(
        "# Durum\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    bi.build(root=root, db=appmod.DB, verbose=False)
    r = client.get("/api/page", params={"doc": "FMS209_DURUM"})
    assert r.status_code == 200
    j = r.json()
    assert j["md"] is True and j["md_path"] and "durum" in j["md_path"]
    assert j["html"] and "<h1" in j["html"] and "<table" in j["html"]


def test_api_save(client, tmp_path):
    """/api/save diske yazar, indeksi günceller; md olmayan dokümanı reddeder."""
    import os
    root = os.environ["FMS200_ROOT"]
    os.makedirs(os.path.join(root, "durum"), exist_ok=True)
    yol = os.path.join(root, "durum", "YENI.md")
    open(yol, "w", encoding="utf-8").write("# eski\n")
    bi.build(root=root, db=appmod.DB, verbose=False)

    r = client.post("/api/save", json={"doc": "YENI", "text": "# yeni baslik\n\nzebra metni", "user": "Ece"})
    assert r.status_code == 200 and r.json()["ok"] and r.json()["degisti"]
    assert open(yol, encoding="utf-8").read().startswith("# yeni baslik")
    # indeks güncellendi mi → yeni metin + aranabilir
    p = client.get("/api/page", params={"doc": "YENI"}).json()
    assert "yeni baslik" in p["text"]
    assert client.get("/api/search", params={"q": "zebra", "mode": "lexical"}).json()["count"] >= 1
    # md olmayan doküman reddedilir
    assert client.post("/api/save", json={"doc": "FMS200_Z", "text": "x"}).status_code == 400


def test_api_md_preview(client):
    r = client.post("/api/md_preview", json={"text": "# B\n\n| a |\n|---|\n| 1 |\n"})
    assert r.status_code == 200 and "<h1" in r.json()["html"] and "<table" in r.json()["html"]


def test_api_history(client, tmp_path):
    """.md olmayan doküman için boş geçmiş döner (git deposu olmasa da patlamaz)."""
    j = client.get("/api/history", params={"doc": "FMS200_Z"}).json()
    assert j["doc"] == "FMS200_Z" and j["commits"] == []
