"""Sohbet (RAG) katmanı testleri — ağ YOK: model çağrısı monkeypatch ile taklit edilir."""
import json
import os

import pytest
from fastapi.testclient import TestClient

from fms200_arama import app as appmod
from fms200_arama import build_index as bi
from fms200_arama import sohbet as sh

_GERCEK_EV_AGI_VAR = sh.ev_agi_var          # autouse fixture bunu taklit eder; önbellek testi gerçeğini kurar


@pytest.fixture(autouse=True)
def _yerel_mod(monkeypatch):
    """Testler GERÇEK ağa çıkmasın: ev ağı ölçümü sabitlenir (varsayılan: ev ağı yok → yerel mod).

    `uc()` normalde `192.168.1.26:11435`'e TCP denemesi yapar; testlerde bu deterministik olmalı.
    """
    monkeypatch.delenv("FMS200_CHAT_URL", raising=False)
    monkeypatch.setattr(sh, "ev_agi_var", lambda *a, **k: False)
    return False


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

    def taklit(mesajlar, model, ctx, en_fazla, timeout, url, araclar=False, think=False):
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


def test_uc_ev_modu(monkeypatch):
    """EV AĞINDA → ECE_PC 35B · bağlam sınırı YOK · **think varsayılan KAPALI**.
    Ölçüm (14 Eki): think=true 81–240 sn ve boş/kesik yanıt; think=false 0,2–15,7 sn ve 15/15."""
    monkeypatch.setattr(sh, "ev_agi_var", lambda *a, **k: True)
    u = sh.uc()
    assert u["mod"] == "ev" and u["url"] == sh.EV_URL and u["model"] == sh.EV_MODEL
    assert u["think"] is False and u["ctx"] is None and u["en_fazla"] == 3000


def test_ev_modu_think_acilirsa_butce_de_yukselir(monkeypatch):
    """`FMS200_CHAT_THINK=1`: think açılır **ve** bütçe 8000'e çıkar (yoksa muhakeme yanıtı kesiyor)."""
    monkeypatch.setattr(sh, "ev_agi_var", lambda *a, **k: True)
    monkeypatch.setenv("FMS200_CHAT_THINK", "1")
    u = sh.uc()
    assert u["think"] is True and u["en_fazla"] == 8000


def test_uc_yerel_modu(monkeypatch):
    """EV AĞI YOK → yerel küçük model, think kapalı, 4096 bağlam (8 GB makine şartı)."""
    monkeypatch.setattr(sh, "ev_agi_var", lambda *a, **k: False)
    u = sh.uc()
    assert u["mod"] == "yerel" and u["model"] == sh.YEREL_MODEL and u["think"] is False
    assert u["ctx"] == 4096 and u["en_fazla"] == 600


def test_uc_elle_override(monkeypatch):
    """FMS200_CHAT_URL açıkça verilirse dokunulmaz (ölçüm/deneme yolu); think env'den gelir."""
    monkeypatch.setenv("FMS200_CHAT_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("FMS200_CHAT_MODEL", "elle-model")
    monkeypatch.setenv("FMS200_CHAT_THINK", "1")
    monkeypatch.setattr(sh, "ev_agi_var", lambda *a, **k: True)
    u = sh.uc()
    assert u["mod"] == "elle" and u["model"] == "elle-model" and u["think"] is True


def test_ev_agi_olcumu_onbellekli(monkeypatch):
    """Ağ ölçümü 60 sn önbelleklenir → istek başına gecikme olmaz; sayım kanıtı."""
    sayac = {"n": 0}

    def taklit(url, timeout=1.5):
        sayac["n"] += 1
        return True

    monkeypatch.setattr(sh, "ev_agi_var", _GERCEK_EV_AGI_VAR)      # fixture taklidini gerçekle değiştir
    monkeypatch.setattr(sh, "_tcp_acik", taklit)
    monkeypatch.setattr(sh, "_EV_ONBELLEK", {"zaman": 0.0, "var": False})
    assert sh.ev_agi_var() is True and sh.ev_agi_var() is True
    assert sayac["n"] == 1, "ikinci çağrı önbellekten gelmeli"


def test_ollama_chat_govdesi_think_ve_baglam_siniri(monkeypatch):
    """think gövdeye geçer; ctx None ise num_ctx GÖNDERİLMEZ (sunucu ayarı geçerli)."""
    yakalanan: dict = {}

    class _R:
        def read(self):
            return json.dumps({"message": {"content": "ok"}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        yakalanan.clear()
        yakalanan.update(json.loads(req.data.decode()))
        return _R()

    monkeypatch.setattr(sh.urllib.request, "urlopen", urlopen)
    sh._ollama_chat([{"role": "user", "content": "x"}], "m", None, 100, 10, "http://x", think=True)
    assert yakalanan["think"] is True and "num_ctx" not in yakalanan["options"]
    sh._ollama_chat([{"role": "user", "content": "x"}], "m", 4096, 100, 10, "http://x", think=False)
    assert yakalanan["think"] is False and yakalanan["options"]["num_ctx"] == 4096


def test_dusunme_metni_yanit_yerine_konmaz(monkeypatch):
    """Ölçüldü (35B + think=true, 600 bütçe): yanıt 0 kr, üretim `thinking`'e gitti.
    Ham muhakeme kullanıcıya GÖSTERİLMEZ; net bir uyarı döner."""
    monkeypatch.setattr(sh, "_ollama_chat", lambda *a, **k: {
        "message": {"content": "", "thinking": "ADIM ADIM MUHAKEME: önce şunu düşünelim " * 40},
        "eval_count": 600, "total_duration": 1_000_000_000})
    m = sh.model_sor("soru", "bağlam")
    assert "MUHAKEME" not in m["yanit"], "düşünme metni yanıt olarak dönmemeli"
    assert m["bos"] is True and m["dusunme_kr"] > 0
    assert "düşünme bütçesini tüketti" in m["yanit"]


def test_dusunme_butcesi_yetmezse_dusunmesiz_tekrar_sorulur(monkeypatch):
    """ÖLÇÜLDÜ (14 Eki, 35B + think=true + 3000 token): üretimin tamamı muhakemeye gitti →
    aynı soruda 81 sn boş, 98 sn 31 karakter ('Verilen kaynaklara göre FMS-2'), 240 sn dolgun.
    Kullanıcı bunu 'dondu' görüyor. Çare: kısa/boş yanıtta **bir kez** düşünmesiz sor."""
    monkeypatch.setattr(sh, "uc", lambda: {"url": "http://x", "model": "m", "think": True,
                                            "ctx": None, "en_fazla": 3000, "timeout": 60,
                                            "mod": "ev"})
    cagrilar: list[bool] = []

    def taklit(mesajlar, model, ctx, en_fazla, timeout, url, araclar=False, think=False):
        cagrilar.append(think)
        if think:                                                      # düşünen tur: kesik yanıt
            return {"message": {"content": "Verilen kaynaklara göre FMS-2",
                                "thinking": "uzun muhakeme " * 200},
                    "eval_count": 3000, "total_duration": 2_000_000_000}
        return {"message": {"content": "FMS-203 hidrolik pres 3. istasyondadır [FMS203_DURUM, sayfa 1]."},
                "eval_count": 40, "total_duration": 1_000_000_000}

    monkeypatch.setattr(sh, "_ollama_chat", taklit)
    m = sh.model_sor("FMS-203 nedir?", "bağlam")
    assert cagrilar == [True, False], "önce düşünen, sonra düşünmesiz sorulmalı"
    assert m["think_yedek"] is True
    assert "3. istasyondadır" in m["yanit"] and "FMS-2  " not in m["yanit"]


def test_yeterli_yanitta_tekrar_sorulmaz(monkeypatch):
    monkeypatch.setattr(sh, "uc", lambda: {"url": "http://x", "model": "m", "think": True,
                                           "ctx": None, "en_fazla": 3000, "timeout": 60, "mod": "ev"})
    cagrilar: list[bool] = []

    def taklit(mesajlar, model, ctx, en_fazla, timeout, url, araclar=False, think=False):
        cagrilar.append(think)
        return {"message": {"content": "FMS-203 hidrolik pres 3. istasyondadır. " * 4},
                "eval_count": 60, "total_duration": 1_000_000_000}

    monkeypatch.setattr(sh, "_ollama_chat", taklit)
    m = sh.model_sor("FMS-203 nedir?", "bağlam")
    assert cagrilar == [True] and m["think_yedek"] is False, "yeterli yanıtta ikinci istek olmamalı"


def test_durum_uc_bilgisi_verir(client):
    """Durum ucu: hangi modda, hangi model, think açık mı — ECE hiçbir şey ayarlamadan görünür."""
    d = sh.durum()
    assert d["mod"] == "yerel" and d["think"] is False
    assert d["model"] == "test-model", "FMS200_CHAT_MODEL verilirse yerel model adı o olur"
    j = client.get("/api/status").json()["sohbet"]
    assert j["mod"] == "yerel" and j["think"] is False and "en_fazla" in j


def test_atifsiz_yanita_kaynak_kod_ekler(client, monkeypatch):
    """Ölçüldü: içerik doğru ama atıf yok (Q6). Modelden istemek yerine kaynakları KOD ekler."""
    monkeypatch.setattr(sh, "model_sor", lambda *a, **k: {
        "yanit": "Rulman modülü manuelde s.92, s.94, s.96 sayfalarında anlatılıyor.",
        "ham": "", "sure_s": 2.0, "tok": 20, "tok_s": 10.0, "model": "test-model", "url": "http://x",
        "hata": None, "arac_sorgulari": []})
    j = client.post("/api/ask", json={"q": "Rulman seçme-besleme modülü manuelde hangi sayfalarda?"}).json()
    assert j["ok"] is True and j["atif_eklendi"] is True
    assert j["atiflar"][0]["tanindi"] is True, "kod eklenen kaynak tanınmalı"
    assert "Kaynaklar:" in j["yanit"] and j["atıfsız"] is False


def test_atifli_yanitsa_dokunulmaz(client, monkeypatch):
    monkeypatch.setattr(sh, "model_sor", lambda *a, **k: {
        "yanit": "Cevap [FMS200_Z, sayfa 1].", "ham": "", "sure_s": 1.0, "tok": 5, "tok_s": 5.0,
        "model": "test-model", "url": "http://x", "hata": None, "arac_sorgulari": []})
    j = client.post("/api/ask", json={"q": "GRAFCET nedir?"}).json()
    assert j["atif_eklendi"] is False and "Kaynaklar:" not in j["yanit"]


def test_metin_bicimli_arac_cagrisi_da_yurutulur(client, monkeypatch):
    """ÖLÇÜLDÜ (nemotron-3-nano:4b): araç çağrısını `tool_calls` yerine METİN olarak yazıyor
    (`<tool_call><function=arastir_arsiv>{"sorgu": "..."}`). Bu biçim de yürütülmeli."""
    c = sh._metin_arac_cagrilari('<tool_call>\n<function=arastir_arsiv>{"sorgu": "GRAFCET dizi"}')
    assert c and c[0]["function"]["name"] == "arastir_arsiv"
    assert c[0]["function"]["arguments"]["sorgu"] == "GRAFCET dizi"
    assert sh._metin_arac_cagrilari("düz yanıt, araç yok") == []
    assert "<tool_call>" not in sh._arac_bloklarini_temizle('<tool_call>x</tool_call> Sonuç: 6 kayıt.')

    cagri = {"n": 0}

    def taklit(mesajlar, model, ctx, en_fazla, timeout, url, araclar=False, think=False):
        cagri["n"] += 1
        if cagri["n"] == 1:
            return {"message": {"content": '<tool_call>\n<function=arastir_arsiv>{"sorgu": "GRAFCET"}'}}
        return {"message": {"content": "Kaynakta 6 kayıt var [FMS200_Z, sayfa 1]."},
                "eval_count": 8, "total_duration": 1_000_000_000}

    monkeypatch.setattr(sh, "_ollama_chat", taklit)
    m = sh.model_sor("kaç kayıt?", "bağlam", db=appmod.DB, araclar=True)
    assert m["arac_sorgulari"] == ["GRAFCET"] and "6 kayıt" in m["yanit"]
    assert "<tool_call>" not in m["yanit"]


def test_duz_bicimli_tool_call_da_calisir(client, monkeypatch):
    """ÖLÇÜLDÜ (nemotron-3-nano:4b): çağrıyı düz biçimde döndürüyor
    `{"index":0,"name":"arastir_arsiv","arguments":{"sorgu":"hidrolik pres"}}` — `function` sarmalayıcısı YOK."""
    cagri = {"n": 0}

    def taklit(mesajlar, model, ctx, en_fazla, timeout, url, araclar=False, think=False):
        cagri["n"] += 1
        if cagri["n"] == 1:
            return {"message": {"content": "", "tool_calls": [
                {"index": 0, "name": "arastir_arsiv", "arguments": {"sorgu": "GRAFCET istasyon"}}]}}
        assert any(m.get("role") == "tool" and "KAYNAK" in (m.get("content") or "")
                   for m in mesajlar), "araç sonucu bağlam olarak eklenmeli"
        return {"message": {"content": "6 kayıt var [FMS200_Z, sayfa 1]."},
                "eval_count": 8, "total_duration": 1_000_000_000}

    monkeypatch.setattr(sh, "_ollama_chat", taklit)
    m = sh.model_sor("kaç kayıt?", "bağlam", db=appmod.DB, araclar=True)
    assert m["arac_sorgulari"] == ["GRAFCET istasyon"], "düz biçimli çağrı yürütülmeli"
    assert "6 kayıt" in m["yanit"]


def test_arac_desteklemeyen_modelde_aracsiz_devam_eder(client, monkeypatch):
    """ÖLÇÜLEN ARIZA: gemma3:4b araç desteklemiyor → ollama 400 döndürüyor ve sohbet tamamen
    düşüyordu. Artık bir kez denenir, destek yoksa araçsız sorulur ve özellik çalışır."""
    sh._ARAC_DESTEK.clear()
    cagri = {"n": 0, "aracli": []}

    def taklit(mesajlar, model, ctx, en_fazla, timeout, url, araclar=False, think=False):
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
