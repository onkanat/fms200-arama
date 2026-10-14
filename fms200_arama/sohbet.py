"""Sohbet (RAG) katmanı: aramadan bağlam kurar, **yerel** model ucundan yanıtlı-takipli cevap alır.

Akış:  soru → hibrit arama (ilk k sayfa) → **getirim iyileştirmeleri** (modül kodu yönlendirmesi,
belge çeşitliliği, jenerik dossiye freni) → sayfa metninden dilimler → yerel sohbet ucuna istek →
yanıt + `[belge, sayfa N]` atıfları. Görev cümlelerinde ("... dosyasını yeniden yaz") **taslak**
üretir; diske yazmaz — kullanıcı düzenleyicide onaylayıp kaydeder.

Ortam değişkenleri:
  FMS200_CHAT_URL    varsayılan: http://127.0.0.1:11434 (**yerel**; gömme ucundan bağımsız —
                     gömme başka makinede olabilir, sohbet modeli yerelde olmalı)
  FMS200_CHAT_MODEL  varsayılan: gemma3:4b   (düşünmeyen model — ölçüm: bkz. arşiv planı)
  FMS200_CHAT_CTX    bağlam penceresi (varsayılan 4096; 8 GB makinede yükseltme)
  FMS200_CHAT_MAX    en fazla üretilecek token (varsayılan 600; görev modunda 1400)
  FMS200_CHAT_TIMEOUT saniye (varsayılan 120)

**Neden `think=False`:** qwen3 gibi "düşünen" modellerde çıktı bütçesi muhakemeye gidip nihai yanıt
hiç gelmiyor (ölçüldü: 700 token'da bile yanıt yok). Düşünme bloğu yine de gelirse `_KAPALI`
işaretinden sonrası alınır.
"""
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request

from . import search as se

_KAPALI = "<" + "/think" + ">"          # literal yazılmaz (araç/şablon katmanı yiyebiliyor)

SISTEM = (
    "Sen SMC FMS-200 eğitim seti doküman arşivinin asistanısın. Yalnızca sana verilen KAYNAK "
    "dilimlerini kullan; dış bilgi katma. Yanıtı TÜRKÇE yaz.\n"
    "KURAL: Önce 2-4 cümlelik yanıtı yaz, sonra kullandığın her bilgi için atıf ver.\n"
    "ATIF BIÇİMİ (birebir): [belge, sayfa <numara>]   — örnek: [FMS203_DURUM, sayfa 3]\n"
    "Kaynakta yanıt yoksa yalnızca \"arşivde bulamadım\" yaz. Soru belirsizse (hangi devre, hangi "
    "modül?) önce hangi belge/şema olduğunu sor."
)

SISTEM_GOREV = (
    "Sen SMC FMS-200 arşivinin teknik yazıcısısın. Sana bir dökümanın MEVCUT içeriği verilecek.\n"
    "Görev: istenen değişikliği uygulayıp dökümanı **baştan sona Markdown olarak** yeniden yaz.\n"
    "Kurallar: (1) verilen içerikte olmayan bilgiyi UYDURMA; eksik gördüğün yere "
    "`<!-- eksik: ... -->` notu koy. (2) Başlık yapısını ve tabloları koru. (3) Yalnızca Markdown "
    "döndür; açıklama/ön söz yazma. (4) Türkçe yaz."
)

ATIF_RE = re.compile(r"\[([^\[\]]+?)\s*[·,]\s*(?:sayfa\s*)?(\d+|[^-)\]·,]+?)\s*\]")
_KOD_RE = re.compile(r"FMS[\s\-_]?(\d{3})", re.I)          # "FMS-204", "FMS204"
_EST_RE = re.compile(r"(?:EST|istasyon|İstasyon)[\s\.\-]*(\d)", re.I)
_JENERIK = {"MODUL_DURUM_OZET", "MODUL_LISTESI", "README"}  # dizin dossiyeleri: fren
_GOREV_RE = re.compile(r"(yeniden\s+yaz|baştan\s+yaz|güncelle|düzenle|taslak|kısalt|özetle)", re.I)

SON_HATA = None                          # son sohbet çağrısı hatası (durum için)


def cfg() -> tuple[str, str, int, int, float]:
    # Sohbet ucu **varsayılan olarak YEREL**tir (okul/çevrimdışı senaryosunun şartı); gömme ucu
    # başka makinede olabilir, bu yüzden FMS200_EMBED_URL'e DÜŞÜLMEZ. Uzak model kullanmak
    # isteniyorsa FMS200_CHAT_URL açıkça verilir.
    url = (os.environ.get("FMS200_CHAT_URL") or "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("FMS200_CHAT_MODEL", "gemma3:4b")
    try:
        ctx = int(os.environ.get("FMS200_CHAT_CTX", "4096"))
        mx = int(os.environ.get("FMS200_CHAT_MAX", "600"))
        to = float(os.environ.get("FMS200_CHAT_TIMEOUT", "120"))
    except ValueError:                                          # pragma: no cover
        ctx, mx, to = 4096, 600, 120.0
    return url, model, max(512, ctx), max(64, mx), to


# ------------------------------------------------------------------ yönlendirme
def rota(q: str) -> dict:
    """Sorudaki modül/istasyon kodlarını çözer.

    Döner: {"dossiler": {"FMS204_DURUM"}, "kodlar": {"FMS-204"}, "est": {4}}.
    Neden: ölçüldü — "FMS-204 ..." diye sorulduğunda getirim ilgili dossiyeyi değil jenerik
    OZET/README/MODUL_LISTESI sayfalarını bağlama koyuyor, model de yanlış dosyayı atıflıyordu.
    """
    kodlar, est = set(), set()
    for k in _KOD_RE.findall(q or ""):
        kodlar.add(f"FMS-{k}")
    for e in _EST_RE.findall(q or ""):
        est.add(int(e))
        kodlar.add(f"FMS-20{e}")
    dossiler = {f"FMS{k[4:]}_DURUM" for k in kodlar if re.fullmatch(r"FMS-20[1-8]", k)}
    return {"dossiler": dossiler, "kodlar": kodlar, "est": est}


def gorev_mi(q: str) -> bool:
    """Soru bir **yazma/güncelleme görevi** mi ('dossiyi yeniden yaz' gibi)?"""
    return bool(_GOREV_RE.search(q or ""))


def hedef_doc(db: str, q: str) -> str | None:
    """Görev cümlesinin hedef dökümanı: koddan dossiye, yoksa addan indekse."""
    r = rota(q)
    if r["dossiler"]:
        return sorted(r["dossiler"])[0]
    aday = re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b", q or "")
    if aday:
        con = sqlite3.connect(db)
        try:
            for a in aday:
                if con.execute("SELECT 1 FROM pages WHERE doc=? LIMIT 1", (a,)).fetchone():
                    return a
        finally:
            con.close()
    return None


# ------------------------------------------------------------------ bağlam kurma
def dilimle(metin: str, boy: int = 1300, ortusme: int = 200) -> list[str]:
    """Uzun sayfa metnini örtüşen pencerelere böler (durum dossiyeleri 30 bin kr'ya çıkabiliyor)."""
    if not metin:
        return []
    out, i = [], 0
    while i < len(metin):
        out.append(metin[i:i + boy])
        i += max(1, boy - ortusme)
    return out[:4]


def _sayfa_metni(con: sqlite3.Connection, doc: str, page) -> tuple[str, str, str]:
    """(metin, etiket, görsel_yolu) — `page` None olabilir (dossier .md'leri)."""
    row = con.execute(
        "SELECT text, label, image_path FROM pages WHERE doc=? AND (page=? OR (? IS NULL AND page IS NULL))",
        (doc, page, page)).fetchone()
    if not row:
        return "", "", ""
    return (row[0] or "", row[1] or "", row[2] or "")


def baglam_kur(db: str, q: str, doc: str | None = None, topk: int = 5,
               butce_kr: int = 6500, mode: str = "hybrid") -> tuple[str, list[dict], int]:
    """Bağlam kurar. **Getirim iyileştirmeleri:**

    1. **Modül kodu yönlendirmesi:** soruda `FMS-20x` / `EST.n` varsa o dossiye ve kodun geçtiği
       etiketli çizimler öne alınır (+3/+2); ayrıca kodla ek arama yapılır.
    2. **Belge çeşitliliği:** ilk turda belge başına 1 dilim, yer kalırsa ikinci turda 2.'si.
    3. **Jenerik dossiye freni:** OZET/README/MODUL_LISTESI toplam en çok 1 dilim, en sonda (-2).
    4. Metinsiz (etiket-only/görsel) sayfa bağlama girmez; sorgu terimi geçmeyen dilim düşer.
    """
    terimler = [t for t in re.split(r"\W+", (q or "").lower()) if len(t) > 3]
    yon = rota(q)
    isabetler = se.search(q, db=db, limit=max(1, topk), doc=doc, mode=mode)
    con = sqlite3.connect(db)
    try:
        # (1) Modül kodu yönlendirmesi: soruda FMS-20x/EST.n varsa o dossiye **doğrudan** alınır.
        # Ölçüldü: puanlama yetmiyordu — dossiye arama sonucuna hiç girmeyince +puan işe yaramıyor.
        if yon["dossiler"] and not doc:
            var = {r[0] for r in con.execute("SELECT DISTINCT doc FROM pages").fetchall()}
            zaten = {(r["doc"], r["page"]) for r in isabetler}
            for d in sorted(yon["dossiler"] & var):
                if (d, None) not in zaten:
                    isabetler.insert(0, {"doc": d, "page": None, "onem_ek": 6})
        aday = []
        for r in isabetler:
            metin, etiket, gorsel = _sayfa_metni(con, r["doc"], r["page"])
            if len(metin.strip()) < 80:                 # etiket-only/görsel sayfa bağlama girmez
                continue
            onem = r.get("onem_ek", 0)
            if r["doc"] in yon["dossiler"] or any(
                    k.replace("FMS-", "FMS").lower() in r["doc"].lower() for k in yon["kodlar"]):
                onem += 3                                            # kod yönlendirmesi
            if any(k in (etiket or "") for k in yon["kodlar"]):
                onem += 2                                            # etiketli çizim eşleşmesi
            if r["doc"] in _JENERIK:
                onem -= 2                                            # jenerik dossiye freni
            for no, d in enumerate(dilimle(metin)):
                aday.append({"isabet": sum(d.lower().count(t) for t in terimler) + onem,
                             "kr": len(d), "doc": r["doc"], "page": r["page"], "dilim": no,
                             "metin": d, "etiket": etiket, "gorsel": gorsel,
                             "jenerik": r["doc"] in _JENERIK})
    finally:
        con.close()
    pozitif = [a for a in aday if a["isabet"] > 0]
    havuz = sorted(pozitif if len(pozitif) >= 3 else aday, key=lambda x: (-x["isabet"], x["jenerik"]))
    sec, kaynaklar, toplam, sayac, jen = [], [], 0, {}, 0
    for tur in (1, 2):                      # 1. tur: belge başına 1 dilim → 2. tur: ikinci dilim
        for a in havuz:
            if len(sec) >= 5 or toplam > butce_kr * 0.9:
                break
            if sayac.get(a["doc"], 0) >= tur:
                continue
            if a["jenerik"] and jen >= 1:                        # jenerikten en çok 1 dilim
                continue
            if toplam + a["kr"] > butce_kr:
                continue
            sec.append((f"--- KAYNAK: {a['doc']} · sayfa {a['page']} ---" if a["page"] is not None
                        else f"--- KAYNAK: {a['doc']} (belge) ---") + f"\n{a['metin']}")
            kaynaklar.append({k: a[k] for k in ("doc", "page", "dilim", "kr", "isabet", "etiket", "gorsel")})
            sayac[a["doc"]] = sayac.get(a["doc"], 0) + 1
            if a["jenerik"]:
                jen += 1
            toplam += a["kr"]
    return "\n\n".join(sec), kaynaklar, toplam


# ------------------------------------------------------------------ model çağrısı
def temizle(yanit: str) -> str:
    """Düşünme izini atar: `_KAPALI` işaretinden sonrası nihai yanıttır."""
    if not yanit:
        return ""
    return (yanit.split(_KAPALI)[-1] if _KAPALI in yanit else yanit).strip()


def atiflari_ayikla(yanit: str) -> list[tuple[str, int | None]]:
    """Atıfları ayrıştırır: `[FMS203_DURUM, sayfa 12]` → ("FMS203_DURUM", 12).

    Sağlam olması gerekiyor: model `[FMS206_DURUM, sayfa None, dilim 2]` gibi fazladan alan da
    yazıyor (ölçümde atıf bu yüzden tanınmadı). Kural: köşeli parantezin ilk alanı **belge adı**
    (boşluksuz, 3-60 kr, en az 3 alfanümerik), sonraki alanlardan ilk sayı = sayfa.
    """
    out, gorulen = [], set()
    for ic in re.findall(r"\[([^\[\]]+)\]", yanit or ""):
        alanlar = [p.strip() for p in ic.split(",")]
        if not alanlar or not alanlar[0]:
            continue
        doc = alanlar[0]
        if not re.fullmatch(r"[A-Za-z0-9_\-]{3,60}", doc):     # cümle/URL/etiket değil, belge adı
            continue
        if sum(c.isalnum() for c in doc) < 3:
            continue
        sayfa = None
        for p in alanlar[1:]:                       # önce "sayfa ..." alanı (varsa) — "dilim N" sayılmaz
            if re.match(r"sayfa\b", p, re.I):
                m = re.search(r"\d+", p)
                sayfa = int(m.group()) if m else None
                break
        else:                                      # "sayfa" etiketi yoksa ilk sayı yeter
            for p in alanlar[1:]:
                m = re.search(r"\d+", p)
                if m:
                    sayfa = int(m.group())
                    break
        if (doc, sayfa) in gorulen:
            continue
        gorulen.add((doc, sayfa))
        out.append((doc, sayfa))
    return out


def model_sor(soru: str, baglam: str, url: str | None = None, model: str | None = None,
              ctx: int | None = None, en_fazla: int | None = None,
              timeout: float | None = None, gorev: bool = False) -> dict:
    """Yerel sohbet ucuna tek istek. Döner: {yanit, ham, sure_s, tok, tok_s, hata}."""
    global SON_HATA
    url0, model0, ctx0, mx0, to0 = cfg()
    url = (url or url0).rstrip("/")
    model = model or model0
    ctx = ctx or ctx0
    en_fazla = en_fazla or mx0
    timeout = timeout or to0
    kullanici = (f"GÖREV: {soru}\n\nMEVCUT İÇERİK:\n{baglam}" if gorev
                 else f"SORU: {soru}\n\nKAYNAKLAR:\n{baglam}")
    govde = {"model": model, "stream": False, "think": False,
             "messages": [{"role": "system", "content": SISTEM_GOREV if gorev else SISTEM},
                          {"role": "user", "content": kullanici}],
             "options": {"num_ctx": ctx, "temperature": 0.2, "num_predict": en_fazla},
             "keep_alive": "5m"}
    req = urllib.request.Request(f"{url}/api/chat", data=json.dumps(govde).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
        SON_HATA = f"{type(e).__name__}: {str(e)[:120]}"
        return {"yanit": "", "ham": "", "sure_s": round(time.time() - t0, 1), "hata": SON_HATA}
    SON_HATA = None
    ham = (d.get("message") or {}).get("content") or ""
    if not ham and (d.get("message") or {}).get("thinking"):        # bazı modeller düşünmeyi ayrı verir
        ham = d["message"]["thinking"]
    n = d.get("eval_count") or 0
    sure = (d.get("total_duration") or 0) / 1e9 or (time.time() - t0)
    return {"yanit": temizle(ham), "ham": ham, "sure_s": round(time.time() - t0, 1),
            "tok": n, "tok_s": round(n / sure, 1) if sure else None, "model": model, "url": url}


def _atif_esle(yanit: str, kaynaklar: list[dict]) -> list[dict]:
    """Atıfları bağlamdaki kaynaklarla eşler; eşleşmeyen atıf `tanindi:false` (uydurma uyarısı)."""
    atiflar = []
    for d1, p1 in atiflari_ayikla(yanit):
        kaynak = next((k for k in kaynaklar if k["doc"].lower() == d1.lower()
                       and (p1 is None or k["page"] == p1)), None)
        if kaynak is None:
            kaynak = next((k for k in kaynaklar if k["doc"].lower() == d1.lower()), None)
        atiflar.append({"doc": d1, "page": p1, "tanindi": bool(kaynak),
                        "etiket": (kaynak or {}).get("etiket", ""),
                        "gorsel": (kaynak or {}).get("gorsel", "")})
    return atiflar


def _gorev_metni(db: str, doc: str, butce_kr: int = 9000) -> str:
    """Hedef dökümanın tam metni (taslak üretimi için)."""
    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT page, text FROM pages WHERE doc=? ORDER BY (page IS NULL), page",
                            (doc,)).fetchall()
    finally:
        con.close()
    parcalar, toplam = [], 0
    for page, metin in rows:
        m = metin or ""
        if toplam + len(m) > butce_kr:
            m = m[:max(0, butce_kr - toplam)]
        parcalar.append((f"[sayfa {page}] " if page is not None else "") + m)
        toplam += len(m)
        if toplam >= butce_kr:
            break
    return "\n\n".join(parcalar)


def _bos_yanit(db: str, q: str) -> dict:
    """Hiç kaynak bulunamazsa: net 'bulamadım' + **en yakın belgeler** (model gerekmez, deterministik).

    Neden: ölçümde "S7-1200 nasıl programlanır" gibi arşivde olmayan sorular 0,3 sn'de boş dönüyordu —
    kullanıcı için çıkmaz sokak. Artık ne bulunamadığı yazılır ve neyin bulunabileceği önerilir.
    """
    oneriler = []
    try:
        for mod in ("lexical", "hybrid"):
            for r in se.search(q, db=db, limit=6, mode=mod):
                if r["doc"] not in oneriler:
                    oneriler.append(r["doc"])
            if oneriler:
                break
    except Exception:                                           # pragma: no cover
        pass
    yanit = "Bu sorunun yanıtı arşivdeki kaynaklarda bulunamadı — **arşivde bulamadım**."
    if oneriler:
        yanit += " Yakın olabilecek belgeler: " + ", ".join(oneriler[:5]) + "."
    yanit += (" Soruyu belirli bir modül/istasyon (ör. FMS-203 · EST.3) ya da belge adıyla "
              "daraltırsanız arayabilirim.")
    return {"ok": True, "yanit": yanit, "atiflar": [], "kaynaklar": [], "atıfsız": True,
            "bos": True, "oneriler": oneriler[:5], "sure_s": 0.0}


def sor(db: str, q: str, doc: str | None = None, topk: int = 5, mode: str = "hybrid",
        model: str | None = None, ctx: int | None = None, en_fazla: int | None = None) -> dict:
    """Tam akış. Model yoksa bile **kaynaklar** döner (`ok: False` + `sebep`).

    Görev cümlesi ("... yeniden yaz") + hedef döküman varsa **taslak** üretir (`taslak`,`taslak_doc`);
    **diske yazmaz** — kullanıcı düzenleyicide onaylar (git kaydı orada oluşur).
    """
    q = (q or "").strip()
    if not q:
        return {"ok": False, "sebep": "soru boş", "yanit": "", "kaynaklar": [], "atiflar": []}

    hedef = hedef_doc(db, q) if gorev_mi(q) else None
    if hedef:
        icerik = _gorev_metni(db, hedef)
        if not icerik:
            return {"ok": False, "sebep": f"{hedef} boş/okunamadı", "yanit": "",
                    "kaynaklar": [], "atiflar": [], "taslak_doc": hedef}
        # Görev modu uzun sürer (tüm döküman bağlamda): ayrı, daha geniş zaman aşımı.
        try:
            to_gorev = float(os.environ.get("FMS200_CHAT_TIMEOUT_GOREV", "300"))
        except ValueError:                                        # pragma: no cover
            to_gorev = 300.0
        m = model_sor(q, icerik, model=model, ctx=ctx, en_fazla=en_fazla or 1400,
                      gorev=True, timeout=to_gorev)
        if m.get("hata"):
            return {"ok": False, "sebep": f"sohbet modeli yok ({m['hata']}) — yalnız arama",
                    "yanit": "", "kaynaklar": [], "atiflar": [], "taslak_doc": hedef}
        return {"ok": True, "gorev": True, "taslak": m["yanit"], "taslak_doc": hedef,
                "yanit": m["yanit"], "atiflar": [], "kaynaklar": [], "atıfsız": True,
                "model": m.get("model"), "url": m.get("url"), "sure_s": m.get("sure_s"),
                "tok": m.get("tok"), "tok_s": m.get("tok_s")}

    baglam, kaynaklar, kr = baglam_kur(db, q, doc=doc, topk=topk, mode=mode)
    if not baglam:
        return _bos_yanit(db, q)
    m = model_sor(q, baglam, model=model, ctx=ctx, en_fazla=en_fazla)
    if m.get("hata"):
        return {"ok": False, "sebep": f"sohbet modeli yok ({m['hata']}) — yalnız arama",
                "yanit": "", "kaynaklar": kaynaklar, "atiflar": [], "baglam_kr": kr}
    return {"ok": True, "yanit": m["yanit"], "atiflar": _atif_esle(m["yanit"], kaynaklar),
            "kaynaklar": kaynaklar, "baglam_kr": kr, "model": m.get("model"), "url": m.get("url"),
            "sure_s": m.get("sure_s"), "tok": m.get("tok"), "tok_s": m.get("tok_s"),
            "atıfsız": not atiflari_ayikla(m["yanit"])}


def durum() -> dict:
    """Arayüz/durum ucu için: yapılandırma + son hata (ağ çağrısı YAPMAZ)."""
    url, model, ctx, mx, _ = cfg()
    return {"url": url, "model": model, "ctx": ctx, "en_fazla": mx,
            "son_hata": SON_HATA, "hazir": SON_HATA is None}
