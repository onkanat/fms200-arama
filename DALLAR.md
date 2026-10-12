# Dallar (branch) kuralı — fms200-arama

| Dal | Anlam | Kural |
|---|---|---|
| `main` | **SABİT sürüm** | Ece'nin notebook'undaki paketle eşleşir. Buraya **yalnız stabilize olmuş** iş girer (dev'den merge) + sürüm etiketi (`vX.Y-sabit`). Doğrudan commit **yok**. |
| `dev` | **Geliştirme** | Günlük iş burada: yeni doküman/modül, arayüz, indeks, dossiye güncellemeleri. |

## Akış

1. `dev`'de çalış, commit et.
2. Testler geçsin: `.venv/bin/python -m pytest -q`
3. Stabilize olunca:
   ```bash
   git switch main && git merge --no-ff dev
   git tag vX.Y-sabit && git push origin main --tags
   ```
4. Yeni paket: `scripts/paketle.sh` → Ece'nin notebook'una kopyala.

## Notlar

- **Sunucu hangi daldaysan onu servis eder** (`--reload`). Paket üretmeden önce `git status` **temiz** olmalı.
- Arşiv (`~/MacAir/fms-200`) bu deponun **dışında** yaşar; dal değişimi arşivi etkilemez (arşiv tarafı monorepo, orada dal yerine **etiket** kullanılıyor: `sabit-2026-10-10`).
- Etiketler: `v0.1-sabit` (ilk sabit sürüm) — `main` üzerinde.
