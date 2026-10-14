"""Sohbet (RAG) katmanı testleri — ağ YOK: model çağrısı monkeypatch ile taklit edilir."""
import os

import pytest
from fastapi.testclient import TestClient

from fms200_arama import app as appmod
from fms200_arama import build_index as bi
from fms200_arama import sohbet as sh


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """İçinde uzun metinli bir döküman + metinsiz (görsel) sayfa bulunan geçici arşiv."""
    root = os.path.join(str(tmp_path), "fms200")
    d = os.path.join(root, "dokuman", "FMS200_Z")
    os.makedirs(os.path.join(d, "metin"), exist_ok=True)
    os.makedirs(os.path.join(d, "sayfalar"), exist_ok=True)
    uzun = ("FMS-200 GRAFCET istasyon dizisi. " * 120) + "PROFIBUS bornero X3 kapak KPK-5."
    open(os.path.join(d, "metin", "sayfa_001.txt"), "w", encoding="utf-8").write(uzun)
    open(os.path.join(d, "sayfalar", "sayfa_001.jpg"), "wb").write(b"\xff\xd8" + b"0" * 5000)
    db = os.path.join(str(tmp_path), "t.db")
    bi.build(root=root, db=db, verbose=False)
    monkeypatch.setattr(appmod, "DB", db)
    monkeypatch.setattr(appmod, "ROOT", root)
    monkeypatch.setenv("FMS200_ROOT", root)
    monkeypatch.setenv("FMS200_CHAT_MODEL", "test-model")
    return TestClient(appmod.app)


# ------------------------------------------------------------------ birim
def test_dilimle_kisa_tek_parca():
    assert len(sh.dilimle("kısa metin")) == 1


def test_dilimle_uzun_ortusmeli_ve_sinirli():
    d = sh.dilimle("a" * 6000)
    assert len(d) == 4, "en çok 4 dilim (bağlam bütçesi)"
    assert len(d[0]) == 1300
    assert d[0][-200:] == d[1][:200], "dilimler örtüşmeli"


def test_temizle_dusunme_izini_atar():
    kapanis = "<" + "/think" + ">"
    ham = f"Okay, düşünüyorum… {kapanis} Hidrolik pres FMS-203'tür."
    assert sh.temizle(ham) == "Hidrolik pres FMS-203'tür."
    assert sh.temizle("izi yok, düz yanıt") == "izi yok, düz yanıt"


def test_atiflari_ayikla_ve_tekrari_at():
    y = "FMS-203'tür [FMS203_DURUM, sayfa 3]. Ayrıca [MODUL_LISTESI, sayfa None] ve yine [FMS203_DURUM, sayfa 3]."
    a = sh.atiflari_ayikla(y)
    assert ("FMS203_DURUM", 3) in a and ("MODUL_LISTESI", None) in a
    assert len(a) == 2, "tekrarlar atılır"


def test_baglam_kur_metinsiz_sayfayi_atlar_ve_belge_basina_iki_dilim(client):
    baglam, kaynaklar, kr = sh.baglam_kur(appmod.DB, "GRAFCET", topk=5)
    assert kr > 0 and baglam.startswith("--- KAYNAK:")
    assert len([k for k in kaynaklar if k["doc"] == "FMS200_Z"]) <= 2, "belge başına en çok 2 dilim"


def test_baglam_kur_kaynak_yoksa_bos(tmp_path, monkeypatch):
    root = os.path.join(str(tmp_path), "bos")
    os.makedirs(os.path.join(root, "dokuman", "BOS", "metin"), exist_ok=True)
    db = os.path.join(str(tmp_path), "b.db")
    bi.build(root=root, db=db, verbose=False)
    baglam, kaynaklar, kr = sh.baglam_kur(db, "hiç geçmeyen terim")
    assert baglam == "" and kaynaklar == [] and kr == 0


# ------------------------------------------------------------------ uç
def test_api_ask_model_yokken_arama_kaynaklarini_yine_dondurur(client, monkeypatch):
    monkeypatch.setattr(sh, "model_sor",
                        lambda *a, **k: {"yanit": "", "ham": "", "sure_s": 0.1, "hata": "ConnectionRefusedError"})
    r = client.post("/api/ask", json={"q": "GRAFCET"})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is False and "sohbet modeli yok" in j["sebep"]
    assert j["kaynaklar"], "model yoksa da bulunan kaynaklar listelenir"


def test_api_ask_atifli_yanit_dondurur(client, monkeypatch):
    monkeypatch.setattr(sh, "model_sor", lambda soru, baglam, *a, **k: {
        "yanit": "Dizi şeması GRAFCET'tir [FMS200_Z, sayfa 1].",
        "ham": "…", "sure_s": 1.5, "tok": 12, "tok_s": 8.0, "model": "test-model", "url": "http://x"})
    j = client.post("/api/ask", json={"q": "GRAFCET"}).json()
    assert j["ok"] is True and j["atıfsız"] is False
    assert j["atiflar"][0]["doc"] == "FMS200_Z" and j["atiflar"][0]["tanindi"] is True
    assert j["model"] == "test-model" and j["kaynaklar"]


def test_api_ask_uydurma_atif_isaretlenir(client, monkeypatch):
    monkeypatch.setattr(sh, "model_sor", lambda *a, **k: {
        "yanit": "Cevap [OLMAYAN_BELGE, sayfa 9].", "ham": "", "sure_s": 1.0,
        "tok": 5, "tok_s": 5.0, "model": "test-model", "url": "http://x"})
    j = client.post("/api/ask", json={"q": "GRAFCET"}).json()
    assert j["atiflar"][0]["tanindi"] is False, "bağlamda olmayan atıf işaretlenir"


def test_api_ask_bos_soru_400(client):
    assert client.post("/api/ask", json={"q": "  "}).status_code == 400


def test_status_calisma_ani_arka_ucunu_ve_sohbeti_bildirir(client, monkeypatch):
    from fms200_arama import vec as vecmod
    monkeypatch.setattr(vecmod, "runtime_backend", lambda *a, **k: "hashing")
    j = client.get("/api/status").json()
    assert j["embed_calisiyor"] == "hashing"
    assert j["sohbet"]["model"] == "test-model"
    assert "embed_yedek" in j and "uyari" in j
