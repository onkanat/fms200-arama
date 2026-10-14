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
    # durum dossiyeleri: kod yönlendirmesi + jenerik fren testleri için
    durum = os.path.join(root, "durum")
    os.makedirs(durum, exist_ok=True)
    open(os.path.join(durum, "FMS204_DURUM.md"), "w", encoding="utf-8").write(
        "# FMS-204 · Mil seçme-besleme\n\n**İstasyon:** 4 · **Kod:** FMS-204 · Yükseklik ölçer mil "
        "seçme modülü, pnömatik silindir ve döner tabla içerir. " * 3)
    open(os.path.join(durum, "MODUL_DURUM_OZET.md"), "w", encoding="utf-8").write(
        "# Modül Durum Dossiyeleri — Özet\n\nHer modül için ayrı dossiye: FMS201 … FMS208. "
        "Mil seçme modülü FMS-204 istasyon 4'tür. " * 3)
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


# ------------------------------------------------------------------ getirim iyileştirmesi
def test_rota_kod_ve_istasyonu_cozer():
    r = sh.rota("FMS-204 modülünde yükseklik ölçer")
    assert r["dossiler"] == {"FMS204_DURUM"} and "FMS-204" in r["kodlar"]
    r2 = sh.rota("EST.6 vida besleme arızası")
    assert r2["est"] == {6} and "FMS-206" in r2["kodlar"] and "FMS206_DURUM" in r2["dossiler"]
    assert sh.rota("GRAFCET nedir")["kodlar"] == set()


def test_kod_yonlendirmesi_ilgili_dossiyeyi_one_alir(client):
    """Ölçülen kusur: 'FMS-204' sorusunda getirim jenerik OZET'i öne alıyordu."""
    baglam, kaynaklar, _ = sh.baglam_kur(appmod.DB, "FMS-204 mil seçme yükseklik ölçer")
    assert kaynaklar, "aday bulunmalı"
    assert kaynaklar[0]["doc"] == "FMS204_DURUM", f"ilk kaynak {kaynaklar[0]['doc']} oldu"


def test_jenerik_dossiyeden_en_cok_bir_dilim(client):
    _, kaynaklar, _ = sh.baglam_kur(appmod.DB, "FMS-204 mil seçme modülü özet")
    jen = [k for k in kaynaklar if k["doc"] in sh._JENERIK]
    assert len(jen) <= 1, "OZET/README/LISTE'den en çok 1 dilim bağlama girer"


def test_gorev_cumlesi_ve_hedef_dokuman(client):
    q = "FMS200_Z dosyasını yeniden yaz"
    assert sh.gorev_mi(q) is True
    assert sh.gorev_mi("GRAFCET nedir") is False
    assert sh.hedef_doc(appmod.DB, q) == "FMS200_Z"
    assert sh.hedef_doc(appmod.DB, "FMS-204 dossisini güncelle") == "FMS204_DURUM"


def test_api_ask_gorev_taslagi_uretir_ve_diske_yazmaz(client, monkeypatch):
    """Görev modu: taslak döner, dosya DEĞİŞMEZ (yazma yalnız kullanıcı onayıyla düzenleyicide)."""
    yol = os.path.join(appmod._root(), "dokuman", "FMS200_Z", "metin", "sayfa_001.txt")
    onceki = open(yol, encoding="utf-8").read()
    yakalanan = {}

    def taklit(soru, baglam, *a, **k):
        yakalanan["gorev"] = k.get("gorev")
        yakalanan["baglam_kr"] = len(baglam)
        return {"yanit": "# FMS-200 Z\n\n## 1. Yeni başlık\n", "ham": "", "sure_s": 2.0,
                "tok": 20, "tok_s": 10.0, "model": "test-model", "url": "http://x"}

    monkeypatch.setattr(sh, "model_sor", taklit)
    j = client.post("/api/ask", json={"q": "FMS200_Z dosyasını yeniden yaz"}).json()
    assert j["ok"] is True and j["gorev"] is True and j["taslak_doc"] == "FMS200_Z"
    assert j["taslak"].startswith("# FMS-200 Z")
    assert yakalanan["gorev"] is True and yakalanan["baglam_kr"] > 0
    assert open(yol, encoding="utf-8").read() == onceki, "taslak üretmek dosyayı YAZMAMALI"


def test_api_ask_model_gecersizse_eski_davranis(client, monkeypatch):
    gelen = {}
    monkeypatch.setattr(sh, "sor", lambda db, q, **k: (gelen.update(k), {"ok": True, "yanit": "x"})[1])
    client.post("/api/ask", json={"q": "soru", "model": "deneme:4b", "ctx": 8192, "k": 3})
    assert gelen["model"] == "deneme:4b" and gelen["ctx"] == 8192 and gelen["topk"] == 3


# ------------------------------------------------------------------ sağlamlık (ölçümde çıkan kusurlar)
def test_atif_ayristirma_fazladan_alanli_atfi_tanir():
    """Ölçümde model `[FMS206_DURUM, sayfa None, dilim 2]` yazdı ve atıf tanınmadı."""
    a = sh.atiflari_ayikla("... [FMS206_DURUM, sayfa None, dilim 2]. Ayrıca [FMS203_DURUM, sayfa 3].")
    assert ("FMS206_DURUM", None) in a and ("FMS203_DURUM", 3) in a


def test_atif_ayristirma_cumleyi_ve_markdown_baglantiyi_atlar():
    a = sh.atiflari_ayikla("[bu bir düz cümle, sayfa 3] ve [https://ornek.com, 1] ve [FMS202_DURUM]")
    assert a == [("FMS202_DURUM", None)]


def test_kaynak_bulunamayinca_yol_gosterir(client, monkeypatch):
    """Ölçümde arşivde olmayan soru boş dönüyordu (çıkmaz sokak). Artık 'bulamadım' + öneri."""
    monkeypatch.setattr(sh, "model_sor", lambda *a, **k: {"yanit": "", "ham": "", "hata": "çağrılmamalı"})
    j = client.post("/api/ask", json={"q": "zzzqqq wwweee"}).json()
    assert j["ok"] is True and j["bos"] is True
    assert "arşivde bulamadım" in j["yanit"].lower()
    assert "daralt" in j["yanit"].lower()


# ------------------------------------------------------------------ çok dillilik + araştırma aracı
def test_dil_varyantlari_tr_soruyu_en_ve_es_acar():
    v = sh.dil_varyantlari("hidrolik pres arızası nasıl bulunur?")
    assert len(v) == 2, "EN ve ES varyantı üretilmeli"
    assert "hydraulic press" in v[0] and "symptom" in v[0]
    assert "prensa hidráulica" in v[1] and "avería" in v[1]
    assert sh.dil_varyantlari("GRAFCET nedir") == [], "sözlükte olmayan terim varyant üretmez"


def test_kaynak_yoksa_arac_da_yol_gosterir(tmp_path):
    root = os.path.join(str(tmp_path), "bos")
    os.makedirs(os.path.join(root, "dokuman", "BOS", "metin"), exist_ok=True)
    db = os.path.join(str(tmp_path), "b.db")
    bi.build(root=root, db=db, verbose=False)
    assert "bulunamadı" in sh._arac_calistir(db, "arastir_arsiv", {"sorgu": "olmayan terim"})
    assert "bilinmeyen araç" in sh._arac_calistir(db, "yok_arac", {})


def test_model_arac_cagrisini_yurutur(client, monkeypatch):
    """Araç destekli model `arastir_arsiv` çağırırsa: araç çalışır, ikinci turda yanıt gelir."""
    cagrilar = []

    def taklit(mesajlar, model, ctx, en_fazla, timeout, url, araclar=False):
        cagrilar.append(mesajlar)
        if len(cagrilar) == 1:
            assert araclar is True, "ilk turda araç tanımı gönderilmeli"
            return {"message": {"content": "", "tool_calls": [{"function": {
                "name": "arastir_arsiv", "arguments": {"sorgu": "GRAFCET istasyon", "k": 2}}}]}}
        return {"message": {"content": "Dizi şeması GRAFCET'tir [FMS200_Z, sayfa 1]."},
                "eval_count": 10, "total_duration": 1_000_000_000}

    monkeypatch.setattr(sh, "_ollama_chat", taklit)
    m = sh.model_sor("GRAFCET nedir?", "--- KAYNAK: FMS200_Z (belge) ---\nmetin", db=appmod.DB, araclar=True)
    assert m["hata"] is None
    assert m["arac_sorgulari"] == ["GRAFCET istasyon"], "araç sorgusu kaydedilmeli"
    assert "GRAFCET" in m["yanit"]
    assert len(cagrilar) == 2
    rol = [x["role"] for x in cagrilar[1]]                 # 2. turda sistem+hatırlatma+araç sonucu
    assert rol[0] == "system" and rol[1] == "system" and "tool" in rol
    assert any("Hatırlatma" in x["content"] for x in cagrilar[1] if x["role"] == "system")


def test_arac_kapaliysa_tek_istek(client, monkeypatch):
    sayac = {"n": 0}

    def taklit(*a, **k):
        sayac["n"] += 1
        return {"message": {"content": "yanıt"}, "eval_count": 5, "total_duration": 1_000_000_000}

    monkeypatch.setattr(sh, "_ollama_chat", taklit)
    m = sh.model_sor("soru", "bağlam", db=appmod.DB, araclar=False)
    assert sayac["n"] == 1 and m["arac_sorgulari"] == []


def test_arac_desteklemeyen_modelde_aracsiz_devam_eder(client, monkeypatch):
    """ÖLÇÜLEN ARIZA: gemma3:4b araç desteklemiyor → ollama 400 döndürüyor ve sohbet tamamen
    düşüyordu. Artık bir kez denenir, destek yoksa araçsız sorulur ve özellik çalışır."""
    sh._ARAC_DESTEK.clear()
    cagri = {"n": 0, "aracli": []}

    def taklit(mesajlar, model, ctx, en_fazla, timeout, url, araclar=False):
        cagri["n"] += 1
        cagri["aracli"].append(araclar)
        if araclar:
            return {"_hata": 'HTTP Error 400: {"error":"… does not support tools"}', "_destek_yok": True}
        return {"message": {"content": "araçsız yanıt [FMS200_Z, sayfa 1]"}, "eval_count": 5,
                "total_duration": 1_000_000_000}

    monkeypatch.setattr(sh, "_ollama_chat", taklit)
    m = sh.model_sor("soru", "bağlam", model="arac-desteklemeyen:1b", db=appmod.DB, araclar=True)
    assert m["hata"] is None and "araçsız yanıt" in m["yanit"]
    assert cagri["aracli"] == [True, False], "önce araçlı denendi, sonra araçsız tekrar"
    assert sh.arac_destegi("arac-desteklemeyen:1b") is False, "destek yok diye not edilmeli"
    # ikinci soru artık doğrudan araçsız gider (tekrar 400 yemez)
    cagri["n"] = 0
    cagri["aracli"].clear()
    sh.model_sor("soru2", "bağlam", model="arac-desteklemeyen:1b", db=appmod.DB, araclar=True)
    assert cagri["aracli"] == [False]
