#!/usr/bin/env bash
# FMS-200 arşivini servis eder (Ece'nin notebook'u). TEK KOMUT:  ./basla.sh
#
# Yaptığı: sanal ortam kurar → indeks yoksa kurar → 0.0.0.0:8765'te yayına açar.
# Telefon ve notebook'lar aynı wifi'deyken verilen adresten girer.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ARSIV="${FMS200_ARSIV:-$HERE/fms-200}"
KOD="$HERE/fms200-arama"
cd "$KOD"

if [ ! -d .venv ]; then
  echo "→ sanal ortam kuruluyor (.venv)…"
  python3 -m venv .venv
  ./.venv/bin/python -m pip install -q --upgrade pip
  ./.venv/bin/python -m pip install -q fastapi "uvicorn[standard]" markdown pymupdf numpy
fi

if [ ! -f data/fms200.db ]; then
  echo "→ ilk indeks kuruluyor (birkaç dakika sürebilir)…"
  FMS200_ROOT="$ARSIV" ./.venv/bin/python -m fms200_arama.build_index \
      --root "$ARSIV" --db data/fms200.db
fi

# Sohbet (💬 Sor) için YEREL model gerekir: ollama + gemma3:4b. Yoksa yalnız sohbet susar, ARAMA çalışır.
# (Ev ağındaysan uygulama kendiliğinden ECE_PC'deki büyük modele geçer; bu adım okul/çevrimdışı içindir.)
if command -v ollama >/dev/null 2>&1; then
  if ! ollama list 2>/dev/null | grep -qE "^gemma3:4b"; then
    echo "→ sohbet modeli eksik: gemma3:4b indiriliyor (~3,4 GB, internet gerekir)…"
    ollama pull gemma3:4b || echo "  ⚠️  indirilemedi — sohbet kapalı olur, arama/arayüz tam çalışır."
  fi
else
  echo "ℹ️  ollama bulunamadı: 💬 Sor (sohbet) kapalı olur; arama ve arayüz tam çalışır."
  echo "    Sohbet istersen: https://ollama.com indir → 'ollama pull gemma3:4b'"
fi

IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null \
      || hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1)"
PORT="${FMS200_PORT:-8765}"
echo
echo "=============================================================="
echo "  FMS-200 arşivi yayında.  Telefondan / notebook'tan aç:"
echo "        http://$IP:$PORT"
echo "  (aynı wifi ağında olmalı).  Durdurmak için: Ctrl+C"
echo "  Sohbet: ev ağındaysan otomatik ECE_PC (35B) · değilse yerel gemma3:4b"
echo "=============================================================="
FMS200_ROOT="$ARSIV" exec ./.venv/bin/uvicorn fms200_arama.app:app \
    --host 0.0.0.0 --port "$PORT"
