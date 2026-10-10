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

IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null \
      || hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1)"
PORT="${FMS200_PORT:-8765}"
echo
echo "=============================================================="
echo "  FMS-200 arşivi yayında.  Telefondan / notebook'tan aç:"
echo "        http://$IP:$PORT"
echo "  (aynı wifi ağında olmalı).  Durdurmak için: Ctrl+C"
echo "=============================================================="
FMS200_ROOT="$ARSIV" exec ./.venv/bin/uvicorn fms200_arama.app:app \
    --host 0.0.0.0 --port "$PORT"
