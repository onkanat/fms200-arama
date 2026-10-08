#!/usr/bin/env python3
"""Secili sayfalari DeepSeek-OCR'dan gecirir (paralel, resume'lu).

PROMPT MODLARI (resmi README: github.com/deepseek-ai/DeepSeek-OCR, "Prompts examples"):
  doc    : "<image>\\n<|grounding|>Convert the document to markdown. "  <- VARSAYILAN
           Belge/tablo/liste yapisi + baslik hiyerarsisi (##, ####) korunur.
           Ham cikti [[x1,y1,x2,y2]] layout token'lari icerir; varsayilan clean() siler.
  plain  : "<image>\\nFree OCR. "   layoutsuz; duz metin, hiyerarsi YOK.
  figure : "<image>\\nParse the figure. "   sekil/diyagram aciklamasi.
  image  : "<image>\\n<|grounding|>OCR this image. "   tek gorsel.

Kullanim:
    python3 ocr_batch.py <jpg_klasoru> <cikti_klasoru> <sayfa_listesi_dosyasi> [--workers 3] [--mode doc|plain]

sayfa_listesi_dosyasi: her satirda bir sayfa adi (uzantisiz), orn 'sayfa_091'.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    if strip:
        t = strip_layout(t)
    t = t.replace("\r", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def ocr_one(img_path: str, prompt: str, timeout: int = 400, num_predict: int = 8192) -> str:
    b64 = base64.b64encode(open(img_path, "rb").read()).decode()
    payload = {"model": MODEL, "prompt": prompt, "images": [b64], "stream": False,
               "options": {"temperature": 0, "num_predict": num_predict}}
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout),
                        f"{OLLAMA}/api/generate", "-d", json.dumps(payload)],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get("response", "")
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out"); ap.add_argument("liste")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--mode", default="doc", choices=list(MODLAR), help="prompt modu (varsayilan: doc)")
    ap.add_argument("--raw", action="store_true", help="layout token'larini silmeden sakla")
    a = ap.parse_args()
    prompt = MODLAR[a.mode]
    os.makedirs(a.out, exist_ok=True)
    stems = [ln.strip() for ln in open(a.liste, encoding="utf-8") if ln.strip()]
    isler = [s for s in stems if not (os.path.exists(os.path.join(a.out, s + ".txt"))
                                      and os.path.getsize(os.path.join(a.out, s + ".txt")) > 40)]
    print(f"mode={a.mode} | toplam {len(stems)} | islenecek {len(isler)} (resume)", flush=True)
    ok = bos = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(ocr_one, os.path.join(a.src, s + ".jpg"), prompt): s for s in isler}
        for i, fu in enumerate(as_completed(futs), 1):
            s = futs[fu]
            raw = fu.result()
            if raw.strip():
                open(os.path.join(a.out, s + ".txt"), "w", encoding="utf-8").write(clean(raw, strip=not a.raw))
                ok += 1
                print(f"  [{i}/{len(isler)}] {s}: {len(raw)}k ✓", flush=True)
            else:
                bos += 1
                print(f"  [{i}/{len(isler)}] {s}: BOS", flush=True)
    print(f"BITTI: ok {ok} | bos {bos} -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
