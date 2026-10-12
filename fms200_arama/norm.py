"""Metin normalizasyonu ve kaba dil tespiti.

Scribd / OCR çıktıları harf arası boşluk üretebilir:  "TECHNICA L DESCRIPTION",
"F M S 2 0 0".  Bu yüzden tek karakterli alfanümerik token'ları **önceki** token'a
yapıştırırız: "TECHNICA"+"L" -> "TECHNICAL"; "F"+"M"+"S"+"2"+"0"+"0" -> "FMS200".
"""
import re

# Dil tespiti desenleri — ayırt edici (ortak İngilizce kelimeler hariç tutuldu)
_ES = re.compile(r'\b(estaci[oó]n|p[aá]gina|neum[aá]t|rodamiento|pr[aá]ctica|sistema d|manual de)\b', re.I)
_TR = re.compile(r'\b(istasyon|sistem|i[cç]in|kullan[ıi]m|montaj|ba[ğg]lant[ıi]|ayar)\b', re.I)
_DE = re.compile(r'\b(und|der|die|das|montage|betriebsanleitung|schaltung)\b', re.I)
_FR = re.compile(r'\b(les|syst[eè]me|montage|notice|r[eé]glage|avec le)\b', re.I)
_EN = re.compile(r'\b(the|and|system|station|module|with|from|manual|training)\b', re.I)


def norm(t: str) -> str:
    """Arama metni: NBSP temizle, tek-karakter token'ları öncekine yapıştır, boşluk sıkıştır.

    İstisna: **X / Y / Z** tek başına bir eksen etiketi olabilir ("servo sürücü X ekseni");
    bunlar birleştirilmez, yoksa `sürücüX` gibi bozuk token oluşur (2026-10-10).
    """
    t = (t or "").replace("\xa0", " ")
    out = []
    for tk in t.split(" "):
        if not tk:
            continue
        if len(tk) == 1 and tk.isalnum() and out and tk.upper() not in ("X", "Y", "Z"):
            out[-1] += tk          # önceki token'a yapıştır
        else:
            out.append(tk)
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def detect_lang(t: str) -> str:
    """Kaba dil tespiti: tr / es / de / fr / en / ??."""
    s = norm(t)[:4000]
    for tag, rx in (("es", _ES), ("tr", _TR), ("de", _DE), ("fr", _FR), ("en", _EN)):
        if rx.search(s):
            return tag
    return "??"
