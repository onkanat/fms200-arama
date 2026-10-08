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
