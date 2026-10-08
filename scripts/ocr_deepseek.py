#!/usr/bin/env python3
"""DeepSeek-OCR (.26:11434) ile bir klasordeki sayfa gorsellerini metne cevirir.

Neden: Scribd'ten gelen metinler harf-arali bozuk ("TECHNICA L DESCRIPTION") ve
tesseract cikitisi bazi sayfalarda gurultulu. DeepSeek-OCR temiz markdown uretir.

Kullanim:
    python3 ocr_deepseek.py <jpg_klasoru> <cikti_klasoru> [--prompt "Free OCR. "] [--limit N]
    # ornek:
    python3 ocr_deepseek.py \\
        ~/MacAir/fms-200/dokuman/FMS200_TECHNICAL_DESCRIPTION_152s/sayfalar \\
        ~/MacAir/fms-200/dokuman/FMS200_TECHNICAL_DESCRIPTION_152s/ocr_deepseek

Ozellikler:
  - RESUME: var olan cikti dosyalarini atlar (tekrar calistirilabilir).
  - Her sayfa icin ham cikti + temiz (satir ici bosluk sikistirilmis) saklanir.
  - Basarisiz sayfa icin bos dosya YAZMAZ; tekrar denemek icin loglar.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://192.168.1.26:11434")
MODEL = os.environ.get("OCR_MODEL", "deepseek-ocr:3b-bf16")
PROMPT = "<image>\nFree OCR. "


def ocr_one(img_path: str, timeout: int = 300) -> str:
    b64 = base64.b64encode(open(img_path, "rb").read()).decode()
    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0},
    }
    r = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), f"{OLLAMA}/api/generate", "-d", json.dumps(payload)],
        capture_output=True, text=True,
    )
    try:
        return json.loads(r.stdout).get("response", "")
    except Exception:
        return ""


def clean(t: str) -> str:
    """Coklu bos satirlari tek; bosluklari sikistir; kenar bosluklari temizle."""
    t = t.replace("\r", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="jpg klasoru")
    ap.add_argument("out", help="cikti klasoru")
    ap.add_argument("--limit", type=int, default=0, help="0 = hepsi")
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    jpgs = sorted(f for f in os.listdir(a.src) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if a.limit:
        jpgs = jpgs[: a.limit]
    toplam = len(jpgs)
    yeni = atlanan = hata = 0
    for i, f in enumerate(jpgs, 1):
        stem = os.path.splitext(f)[0]
        dst = os.path.join(a.out, f"{stem}.txt")
        if os.path.exists(dst) and os.path.getsize(dst) > 40:
            atlanan += 1
            continue
        t0 = time.time()
        raw = ocr_one(os.path.join(a.src, f), timeout=a.timeout)
        dt = time.time() - t0
        if not raw.strip():
            hata += 1
            print(f"  [{i}/{toplam}] {f}: BOS ({dt:.0f}s) — atlandi, tekrar denenecek", flush=True)
            continue
        open(dst, "w", encoding="utf-8").write(clean(raw))
        yeni += 1
        print(f"  [{i}/{toplam}] {f}: {len(raw)} k -> {stem}.txt ({dt:.0f}s)", flush=True)
    print(f"OCR bitti: yeni {yeni} | atlanan {atlanan} | bos/hata {hata} -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
