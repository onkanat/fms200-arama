#!/usr/bin/env python3
"""Secili sayfalari DeepSeek-OCR'dan gecirir (paralel, resume'lu).

Kullanim:
    python3 ocr_batch.py <jpg_klasoru> <cikti_klasoru> <sayfa_listesi_dosyasi> [--workers 3]

sayfa_listesi_dosyasi: her satirda bir sayfa adi (uzantisiz), orn 'sayfa_091'.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://192.168.1.26:11434")
MODEL = os.environ.get("OCR_MODEL", "deepseek-ocr:3b-bf16")
PROMPT = "<image>\nFree OCR. "


def ocr_one(img_path: str, timeout: int = 300) -> str:
    b64 = base64.b64encode(open(img_path, "rb").read()).decode()
    payload = {"model": MODEL, "prompt": PROMPT, "images": [b64], "stream": False,
               "options": {"temperature": 0}}
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout),
                        f"{OLLAMA}/api/generate", "-d", json.dumps(payload)],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get("response", "")
    except Exception:
        return ""


def clean(t: str) -> str:
    t = t.replace("\r", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out"); ap.add_argument("liste")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    stems = [ln.strip() for ln in open(a.liste, encoding="utf-8") if ln.strip()]
    isler = [s for s in stems if not (os.path.exists(os.path.join(a.out, s + ".txt"))
                                      and os.path.getsize(os.path.join(a.out, s + ".txt")) > 40)]
    print(f"toplam {len(stems)} | islenecek {len(isler)} (resume)", flush=True)
    ok = bos = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(ocr_one, os.path.join(a.src, s + ".jpg")): s for s in isler}
        for i, fu in enumerate(as_completed(futs), 1):
            s = futs[fu]
            raw = fu.result()
            if raw.strip():
                open(os.path.join(a.out, s + ".txt"), "w", encoding="utf-8").write(clean(raw))
                ok += 1
                print(f"  [{i}/{len(isler)}] {s}: {len(raw)}k ✓", flush=True)
            else:
                bos += 1
                print(f"  [{i}/{len(isler)}] {s}: BOS", flush=True)
    print(f"BITTI: ok {ok} | bos {bos} -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
