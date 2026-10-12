#!/usr/bin/env bash
# FMS-200 projesini taşınabilir bir pakete çevirir (Ece'nin notebook'u için).
# Kullanım:  scripts/paketle.sh [çıktı_dizini]      (varsayılan: ~/MacAir/dist)
set -euo pipefail
ARSIV="${FMS200_ARSIV:-$HOME/MacAir/fms-200}"
KOD="${FMS200_KOD:-$(cd "$(dirname "$0")/.." && pwd)}"
CIKTI="${1:-$HOME/MacAir/dist}"
AD="fms200-paket-$(date +%Y%m%d)"
GEC="$(mktemp -d)"; H="$GEC/$AD"
mkdir -p "$H" "$CIKTI"

echo "→ arşiv kopyalanıyor (ağır/geçici öğeler hariç)"
rsync -a --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
      --exclude '.karantina' --exclude '.pytest_cache' --exclude '.DS_Store' \
      "$ARSIV/" "$H/fms-200/"

echo "→ kod + arayüz kopyalanıyor"
rsync -a --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
      --exclude '.pytest_cache' --exclude '.DS_Store' \
      "$KOD/" "$H/fms200-arama/"

# DB'nin mtime'ını arşiv kopyasından YENİ yap: /api/status'taki 'bayat' bayrağı, arşivdeki en yeni
# dosya mtime'ı ile DB mtime'ını karşılaştırır. Kopyalama arşiv dosyalarını tazelediği için paket
# ilk açılışta yanlış 'bayat:true' gösteriyordu (11-12 Eki 2026 paket denemesinde görüldü).
[ -f "$H/fms200-arama/data/fms200.db" ] && touch "$H/fms200-arama/data/fms200.db"

echo "→ başlatma betiği + kılavuz"
cp "$KOD/scripts/basla.sh" "$H/basla.sh"; chmod +x "$H/basla.sh"
cp "$KOD/KURULUM.md" "$H/KURULUM.md"

# Git YALNIZ metin/kod izler (kim ne değiştirdi). Büyük ikili dosyalar girmez → paket şişmez.
cat > "$H/.gitignore" <<'GI'
# büyük ikili dosyalar sürüm kontrolüne girmez (yalnız .md/.py/.sh/.txt izlenir)
*.pdf
*.jpg
*.jpeg
*.png
*.webp
*.heic
*.tif
*.mp4
*.zip
*.tar.gz
__pycache__/
.venv/
.pytest_cache/
data/*.db
.DS_Store
GI

echo "→ git deposu (kim ne yaptı kaydı buradan tutulur)"
git -C "$H" init -q
git -C "$H" config user.name "FMS-200"
git -C "$H" config user.email "${FMS200_GIT_EPOSTA:-fms200@yerel}"
git -C "$H" add -A
git -C "$H" -c user.name="Hermes-MacAir" -c user.email="hermes-macair@macair.local" \
    commit -q -m "FMS-200 paketi $(date +%Y-%m-%d) — arşiv + arama motoru + modül dossiyeleri"

echo "→ paketleniyor…"
tar -C "$GEC" -czf "$CIKTI/$AD.tar.gz" "$AD"
rm -rf "$GEC"
printf "✅ paket: %s  (%s)\n" "$CIKTI/$AD.tar.gz" "$(du -h "$CIKTI/$AD.tar.gz" | cut -f1)"
echo "   → Ece'nin notebook'una kopyala (USB / AirDrop / scp), aç ve: tar xzf, sonra ./basla.sh"
