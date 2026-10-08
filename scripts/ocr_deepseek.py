#!/usr/bin/env python3
"""DeepSeek-OCR (.26:11434) ile bir klasordeki sayfa gorsellerini metne cevirir.

Neden: Scribd'ten gelen metinler harf-arali bozuk ("TECHNICA L DESCRIPTION") ve
tesseract cikitisi bazi sayfalarda gurultulu. DeepSeek-OCR temiz markdown uretir.

PROMPT MODLARI (resmi README: github.com/deepseek-ai/DeepSeek-OCR, "Prompts examples"):
  doc    : "<image>\\n<|grounding|>Convert the document to markdown. "  <- VARSAYILAN
           Belge/tablo/liste yapisi + baslik hiyerarsisi (##, ####) korunur.
           Cikti ham halde [[x1,y1,x2,y2]] layout koordinat token'lari icerir; clean() siler.
  plain  : "<image>\\nFree OCR. "   layoutsuz; duz metin, hiyerarsi YOK.
  figure : "<image>\\nParse the figure. "   sekil/diyagram aciklamasi.
  image  : "<image>\\n<|grounding|>OCR this image. "   tek gorsel (belge degil).

Kullanim:
    python3 ocr_deepseek.py <jpg_klasoru> <cikti_klasoru> [--mode doc|plain|figure|image]
    python3 ocr_deepseek.py <src> <out> --raw      # layout token'larini silmeden sakla
    python3 ocr_deepseek.py <src> <out> --limit 5  # ilk 5 sayfa

Ozellikler:
  - RESUME: var olan (>40B) cikti dosyalarini atlar.
  - num_predict=8192 (resmi ayar): uzun/tablolu sayfalarda kirpma olmaz.
  - Basarisiz sayfa icin bos dosya YAZMAZ.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import time

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://192.168.1.26:11434")
MODEL = os.environ.get("OCR_MODEL", "deepseek-ocr:3b-bf16")

MODLAR = {
    "doc":    "<image>\n<|grounding|>Convert the document to markdown. ",
    "plain":  "<image>\nFree OCR. ",
    "figure": "<image>\nParse the figure. ",
    "image":  "<image>\n<|grounding|>OCR this image. ",
}

_LAYOUT = re.compile(r"\[\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\]\]")
_ETIKET = re.compile(r"^\s*(text|title|sub_title|figure|table|equation|header|footer|page_number|formula)\s*$", re.M)


def strip_layout(t: str) -> str:
    """<|grounding|> cikisindaki layout token'larini sil; baslik/metin yapisini koru."""
    t = _LAYOUT.sub("", t)
    t = _ETIKET.sub("", t)
    return t


def clean(t: str, strip=True) -> str:
    """Coklu bos satirlari tek; bosluklari sikistir; (varsa) layout token'larini sil."""
    if strip:
        t = strip_layout(t)
    t = t.replace("\r", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def ocr_one(img_path: str, prompt: str, timeout: int = 400, num_predict: int = 8192) -> str:
    b64 = base64.b64encode(open(img_path, "rb").read()).decode()
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0, "num_predict": num_predict},
    }
    r = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), f"{OLLAMA}/api/generate", "-d", json.dumps(payload)],
        capture_output=True, text=True,
    )
    try:
        return json.loads(r.stdout).get("response", "")
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="jpg klasoru")
    ap.add_argument("out", help="cikti klasoru")
    ap.add_argument("--mode", default="doc", choices=list(MODLAR), help="prompt modu (varsayilan: doc)")
    ap.add_argument("--prompt", default=None, help="ozel prompt (--mode'u gecersiz kilar)")
    ap.add_argument("--raw", action="store_true", help="layout token'larini silmeden sakla")
    ap.add_argument("--limit", type=int, default=0, help="0 = hepsi")
    ap.add_argument("--timeout", type=int, default=400)
    a = ap.parse_args()

    prompt = a.prompt if a.prompt else MODLAR[a.mode]
    os.makedirs(a.out, exist_ok=True)
    jpgs = sorted(f for f in os.listdir(a.src) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if a.limit:
        jpgs = jpgs[: a.limit]
    toplam = len(jpgs)
    yeni = atlanan = hata = 0
    print(f"mode={a.mode} | prompt={prompt!r}", flush=True)
    for i, f in enumerate(jpgs, 1):
        stem = os.path.splitext(f)[0]
        dst = os.path.join(a.out, f"{stem}.txt")
        if os.path.exists(dst) and os.path.getsize(dst) > 40:
            atlanan += 1
            continue
        t0 = time.time()
        raw = ocr_one(os.path.join(a.src, f), prompt, timeout=a.timeout)
        dt = time.time() - t0
        if not raw.strip():
            hata += 1
            print(f"  [{i}/{toplam}] {f}: BOS ({dt:.0f}s) — atlandi, tekrar denenecek", flush=True)
            continue
        open(dst, "w", encoding="utf-8").write(clean(raw, strip=not a.raw))
        yeni += 1
        print(f"  [{i}/{toplam}] {f}: {len(raw)} k -> {stem}.txt ({dt:.0f}s)", flush=True)
    print(f"OCR bitti: yeni {yeni} | atlanan {atlanan} | bos/hata {hata} -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
