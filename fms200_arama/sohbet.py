"""Sohbet (RAG) katmanı: aramadan bağlam kurar, **yerel** model ucundan yanıtlı-takipli cevap alır.

Akış:  soru → hibrit arama (ilk k sayfa) → sayfa metninden dilimler (süzgeçli) → yerel sohbet
ucuna (ollama `/api/chat`, OpenAI-uyumlu değil) istek → yanıt + `[belge, sayfa N]` atıfları.

Ortam değişkenleri:
  FMS200_CHAT_URL    varsayılan: http://127.0.0.1:11434 (**yerel**; gömme ucundan bağımsız —
                     gömme başka makinede olabilir, sohbet modeli yerelde olmalı)
  FMS200_CHAT_MODEL  varsayılan: gemma3:4b   (düşünmeyen model — ölçüm: bkz. arşiv planı)
  FMS200_CHAT_CTX    bağlam penceresi (varsayılan 4096; 8 GB makinede yükseltme)
  FMS200_CHAT_MAX    en fazla üretilecek token (varsayılan 600)
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
    "Kaynakta yanıt yoksa yalnızca \"arşivde bulamadım\" yaz."
)

ATIF_RE = re.compile(r"\[([^\[\]]+?)\s*[·,]\s*(?:sayfa\s*)?(\d+|[^-)\]·,]+?)\s*\]")

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
    """Hibrit aramadan bağlam kurar. Süzgeç: metinsiz sayfa atılır, belge başına en çok 2 dilim,
    sorgu terimi geçmeyen dilimler (yeterli aday varsa) atılır."""
    terimler = [t for t in re.split(r"\W+", (q or "").lower()) if len(t) > 3]
    isabetler = se.search(q, db=db, limit=max(1, topk), doc=doc, mode=mode)
    con = sqlite3.connect(db)
    try:
        aday = []
        for r in isabetler:
            metin, etiket, gorsel = _sayfa_metni(con, r["doc"], r["page"])
            if len(metin.strip()) < 80:                 # etiket-only/görsel sayfa bağlama girmez
                continue
            for no, d in enumerate(dilimle(metin)):
                aday.append({"isabet": sum(d.lower().count(t) for t in terimler),
                             "kr": len(d), "doc": r["doc"], "page": r["page"], "dilim": no,
                             "metin": d, "etiket": etiket, "gorsel": gorsel})
    finally:
        con.close()
    pozitif = [a for a in aday if a["isabet"] > 0]
    havuz = sorted(pozitif if len(pozitif) >= 3 else aday, key=lambda x: -x["isabet"])
    sec, kaynaklar, toplam, sayac = [], [], 0, {}
    for a in havuz:
        if sayac.get(a["doc"], 0) >= 2 or toplam + a["kr"] > butce_kr:
            continue
        sec.append(f"--- KAYNAK: {a['doc']} · sayfa {a['page']} · dilim {a['dilim']} ---\n{a['metin']}")
        kaynaklar.append({k: a[k] for k in ("doc", "page", "dilim", "kr", "isabet", "etiket", "gorsel")})
        sayac[a["doc"]] = sayac.get(a["doc"], 0) + 1
        toplam += a["kr"]
        if len(sec) >= 5 or toplam > butce_kr * 0.9:
            break
    return "\n\n".join(sec), kaynaklar, toplam


# ------------------------------------------------------------------ model çağrısı
def temizle(yanit: str) -> str:
    """Düşünme izini atar: `_KAPALI` işaretinden sonrası nihai yanıttır."""
    if not yanit:
        return ""
    return (yanit.split(_KAPALI)[-1] if _KAPALI in yanit else yanit).strip()


def atiflari_ayikla(yanit: str) -> list[tuple[str, int | None]]:
    """`[belge, sayfa 12]` → (belge, 12). Sayfa yoksa (belge, None). Tekrarlar atılır, sıra korunur."""
    out, gorulen = [], set()
    for d, p in ATIF_RE.findall(yanit or ""):
        d = d.strip()
        if not d:
            continue
        sayfa = int(p) if (p or "").strip().isdigit() else None
        if (d, sayfa) in gorulen:
            continue
        gorulen.add((d, sayfa))
        out.append((d, sayfa))
    return out


def model_sor(soru: str, baglam: str, url: str | None = None, model: str | None = None,
              ctx: int | None = None, en_fazla: int | None = None,
              timeout: float | None = None) -> dict:
    """Yerel sohbet ucuna tek istek. Döner: {yanit, ham, sure_s, tok, tok_s, hata}."""
    global SON_HATA
    url0, model0, ctx0, mx0, to0 = cfg()
    url = (url or url0).rstrip("/")
    model = model or model0
    ctx = ctx or ctx0
    en_fazla = en_fazla or mx0
    timeout = timeout or to0
    govde = {"model": model, "stream": False, "think": False,
             "messages": [{"role": "system", "content": SISTEM},
                          {"role": "user", "content": f"SORU: {soru}\n\nKAYNAKLAR:\n{baglam}"}],
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


def sor(db: str, q: str, doc: str | None = None, topk: int = 5, mode: str = "hybrid") -> dict:
    """Tam akış. Model yoksa bile **kaynaklar** döner (`ok: False` + `sebep`); arayüz yalnız aramayı gösterir."""
    q = (q or "").strip()
    if not q:
        return {"ok": False, "sebep": "soru boş", "yanit": "", "kaynaklar": [], "atiflar": []}
    baglam, kaynaklar, kr = baglam_kur(db, q, doc=doc, topk=topk, mode=mode)
    if not baglam:
        return {"ok": False, "sebep": "arşivde bu soruya kaynak bulunamadı",
                "yanit": "", "kaynaklar": [], "atiflar": [], "baglam_kr": 0}
    m = model_sor(q, baglam)
    if m.get("hata"):
        return {"ok": False, "sebep": f"sohbet modeli yok ({m['hata']}) — yalnız arama",
                "yanit": "", "kaynaklar": kaynaklar, "atiflar": [], "baglam_kr": kr}
    atiflar = []
    for d1, p1 in atiflari_ayikla(m["yanit"]):
        kaynak = next((k for k in kaynaklar if k["doc"].lower() == d1.lower()
                       and (p1 is None or k["page"] == p1)), None)
        if kaynak is None:
            kaynak = next((k for k in kaynaklar if k["doc"].lower() == d1.lower()), None)
        atiflar.append({"doc": d1, "page": p1, "tanindi": bool(kaynak),
                        "etiket": (kaynak or {}).get("etiket", ""),
                        "gorsel": (kaynak or {}).get("gorsel", "")})
    return {"ok": True, "yanit": m["yanit"], "atiflar": atiflar, "kaynaklar": kaynaklar,
            "baglam_kr": kr, "model": m.get("model"), "url": m.get("url"),
            "sure_s": m.get("sure_s"), "tok": m.get("tok"), "tok_s": m.get("tok_s"),
            "atıfsız": not atiflar}


def durum() -> dict:
    """Arayüz/durum ucu için: yapılandırma + son hata (ağ çağrısı YAPMAZ)."""
    url, model, ctx, mx, _ = cfg()
    return {"url": url, "model": model, "ctx": ctx, "en_fazla": mx,
            "son_hata": SON_HATA, "hazir": SON_HATA is None}
