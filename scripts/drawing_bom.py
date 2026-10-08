#!/usr/bin/env python3
"""Çizim sayfalarının KENAR kolonlarındaki parça listesini (BOM) OCR ile çıkarır.

Neden: DeepSeek-OCR tam sayfayı verirken kenar kolonlarındaki dikey metin kutularını
KAÇIRIYOR. Çizimlerin sol/sağ kolonlarında ve alt başlık bloğunda ise gerçek parça
listesi var, örn:

    M.GIRATORIA MSQB50A
    (2x) Tornillo DIN 7991 M12x25 Cinc.
    (2x) Reg.caudal Ref: AS2301E-01-04
    (3x) Det. Magnético Ref: D-A93L
    (2x) Amorti. RBA 1411-X692

Bu betik o bölgeleri kırpıp büyütür ve OCR'lar. [[x,y,x,y]] layout token'ları temizlenir.

Kullanım:
    python3 drawing_bom.py <cizim_klasoru> <cikti_klasoru> [--margin 0.18] [--scale 3]

Not: curl'e base64 görsel komut-satırı argümanı olarak sığmaz (OSError: Argument list
too long) -> istekler urllib ile yapılır.
"""
import argparse
import base64
import io
import json
import os
import re
import time
import urllib.request

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://192.168.1.26:11434")
MODEL = os.environ.get("OCR_MODEL", "deepseek-ocr:3b-bf16")
PROMPT = "<image>\n<|grounding|>Convert the document to markdown. "

_LAYOUT = re.compile(r"\[\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\]\]")
_ETIKET = re.compile(r"^\s*(text|title|sub_title|figure|table|equation|header|footer)\s*$", re.M)


def _anti_loop(t: str) -> str:
    """VLM tekrar döngüsünü kırar (dikey/rotasyonlu kolon metninde sık olur).

    Elektor/pipeline/vision_ocr.py::_clean_vlm_response mantığının kısa hali:
    ardışık birebir satırları ve >4 kez geçen satırları kısaltır.
    """
    satirlar = t.split("\n")
    # ardışık tekrarlar
    out, son, tekrar = [], None, 0
    for s in satirlar:
        st = s.strip()
        if st and st == son:
            tekrar += 1
            if tekrar < 2:
                out.append(s)
            elif tekrar == 2:
                out.append("*(tekrar kısaltıldı)*")
            continue
        tekrar = 0
        son = st or None
        out.append(s)
    # global tekrarlar (>4 kez)
    say = {}
    for l in out:
        s = l.strip()
        if len(s) > 5:
            say[s] = say.get(s, 0) + 1
    fin, gor = [], {}
    for l in out:
        s = l.strip()
        if len(s) > 5 and say.get(s, 0) > 4:
            gor[s] = gor.get(s, 0) + 1
            if gor[s] <= 2:
                fin.append(l)
            elif gor[s] == 3:
                fin.append(f"*( '{s}' tekrarı kısaltıldı)*")
            continue
        fin.append(l)
    return "\n".join(fin)


def strip_layout(t: str) -> str:
    return _anti_loop(_ETIKET.sub("", _LAYOUT.sub("", t or ""))).strip()


def _birlestir(a: str, b: str) -> str:
    """İki OCR çıktısını satır bazında birleştir (a önce, b'de yeni olanlar sonra).

    ÖLÇÜM (sayfa_150 sol kolon): düz yön 'Corea dencado' (yanlış), 90° saat yönü
    'Correa dentada' (doğru) + düzün kaçırdığı '(4x) Tornillo DIN 912 M4x35 Cinc.'
    satırını verdi. İki yön birbirini tamamlar -> birleştirmek geri çağırmayı artırır.
    """
    sa = [l.strip() for l in a.split("\n") if l.strip()]
    sb = [l.strip() for l in b.split("\n") if l.strip()]
    gor = set(l.lower() for l in sa)
    out = list(sa)
    for l in sb:
        if l.lower() not in gor:
            out.append(l)
            gor.add(l.lower())
    return "\n".join(out)


def _ocr_png(png_bytes: bytes, timeout: int = 400) -> str:
    b64 = base64.b64encode(png_bytes).decode()
    pl = {"model": MODEL, "prompt": PROMPT, "images": [b64], "stream": False,
          "keep_alive": "10m",
          "options": {"temperature": 0, "num_predict": 4096,
                      "repeat_penalty": 1.25, "repeat_last_n": 64}}
    req = urllib.request.Request(f"{OLLAMA}/api/generate",
                                 data=json.dumps(pl).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("response", "")
    except Exception:
        return ""


def _png(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--margin", type=float, default=0.20, help="kenar kolon oranı")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    from PIL import Image

    resample = getattr(Image, "Resampling", Image).LANCZOS
    rot270 = getattr(Image, "Transpose", Image).ROTATE_270

    os.makedirs(a.out, exist_ok=True)
    fs = sorted(f for f in os.listdir(a.src) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if a.limit:
        fs = fs[: a.limit]
    for i, f in enumerate(fs, 1):
        stem = os.path.splitext(f)[0]
        dst = os.path.join(a.out, stem + ".txt")
        if os.path.exists(dst) and os.path.getsize(dst) > 30:
            continue
        im = Image.open(os.path.join(a.src, f))
        W, H = im.size
        m = int(W * a.margin)
        # sol kolon + sağ kolon + alt başlık bloğu
        bolgeler = [
            ("sol", (0, 0, m, H)),
            ("sag", (W - m, 0, W, H)),
            ("baslik", (int(W * 0.55), int(H * 0.68), W, H)),
        ]
        parcalar = []
        for ad, box in bolgeler:
            c = im.crop(box)
            c2 = c.resize((c.width * a.scale, c.height * a.scale), resample)
            t = strip_layout(_ocr_png(_png(c2)))
            if len(t) < 15:
                c2 = c.transpose(rot270)   # 90° CW: dikey metin düzelir
                c2 = c2.resize((c2.width * a.scale, c2.height * a.scale), resample)
                t2 = strip_layout(_ocr_png(_png(c2)))
                t = _birlestir(t, t2)
            if t and len(t) > 15:
                parcalar.append(f"--- {ad} ---\n{t}")
        if parcalar:
            open(dst, "w", encoding="utf-8").write(f"# {stem}\n\n" + "\n\n".join(parcalar))
            print(f"  [{i}/{len(fs)}] {stem}: {len(parcalar)} bölge", flush=True)
        else:
            print(f"  [{i}/{len(fs)}] {stem}: BOŞ", flush=True)
    print("BITTI ->", a.out, flush=True)


if __name__ == "__main__":
    main()
