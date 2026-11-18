#!/usr/bin/env bash
# GELİŞTİRME/TEST sunucusu — **bizim kopya** (kullanıcı kararı, 18 Kas 2026).
#
# Sohbet modeli: Precision 5820'deki **strata** (OpenAI-uyumlu, `qwen3.8-flash-next`, 262K bağlam).
# Gömme: yerel ollama `nomic-embed-text` — strata'da `/v1/embeddings` YOK (ölçüldü: 404).
#
# Ece'nin kopyasında BU DOSYA kullanılmaz; orada `basla.sh` var ve uç ev/okul ağına göre otomatik
# seçilir. Buradaki `FMS200_STRATA_URL` verilmediğinde kod eskisi gibi ev ağı → yerel sırasına düşer.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

export FMS200_ROOT="${FMS200_ROOT:-$HOME/MacAir/fms-200}"
export FMS200_EMBED_URL="${FMS200_EMBED_URL:-http://127.0.0.1:11434}"
export FMS200_EMBED_MODEL="${FMS200_EMBED_MODEL:-nomic-embed-text}"
export FMS200_STRATA_URL="${FMS200_STRATA_URL:-http://192.168.1.105:8080}"
export FMS200_STRATA_MODEL="${FMS200_STRATA_MODEL:-qwen3.8-flash-next}"
# strata düşünmeyi varsayılan AÇIK yapar; kod `chat_template_kwargs.enable_thinking` ile kapatır.
export FMS200_CHAT_THINK="${FMS200_CHAT_THINK:-0}"
PORT="${FMS200_PORT:-8765}"

if [ ! -x .venv/bin/uvicorn ]; then
  echo "→ sanal ortam yok: python3 -m venv .venv && .venv/bin/python -m pip install -e \".[web,dev]\""
  exit 1
fi

# Ön kontrol: strata ayakta mı? Değilse kod ev/yerel moda düşer — sessiz sürpriz olmasın.
if curl -sf -m 3 "${FMS200_STRATA_URL}/health" >/dev/null 2>&1; then
  echo "✔ strata ayakta: ${FMS200_STRATA_URL} · ${FMS200_STRATA_MODEL}"
else
  echo "⚠️  strata yanıt vermiyor (${FMS200_STRATA_URL}) — kod ev ağı → yerel sırasına düşecek."
  echo "    (WSL2 distro kapalıysa strata susar; bkz. skill 'strata' notu.)"
fi

echo "→ http://127.0.0.1:${PORT}  ·  durum: /api/status (sohbet.mod / .api / .strata_agi)"
exec .venv/bin/uvicorn fms200_arama.app:app --host 0.0.0.0 --port "$PORT" --reload
