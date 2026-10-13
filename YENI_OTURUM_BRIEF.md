# YENİ OTURUM BRİEFİ — FMS-200 DEV

> Yeni oturumda **ilk mesaj** olarak bunu oku: `~/Git/fms200-arama/YENI_OTURUM_BRIEF.md`.
> Bu dosya, temiz bir oturumun 800 mesaj okumadan işe devam edebilmesi için var.
> (Güncelleme: 13 Eki 2026 — önceki FMS-200 oturumu arşive alındı, ayrıntı §"Devir durumu".)

## Nerede çalışıyoruz
- **Kod deposu:** `~/Git/fms200-arama` — **`dev` dalındayız.** Durum (13 Eki, ölçüldü):
  - `dev` temiz, HEAD **`0b8acfe`** = `origin/dev` (`git ls-remote` ile doğrulandı).
  - `main` = **SABİT sürüm** **`fe3d4e0`** = `origin/main`. **`dev` merge EDİLMİŞ durumda**
    (main ⊇ dev; main'in dev'e göre 2 ek commit'i: `4a71b21` v0.2-sabit birleşmesi + `fe3d4e0` paketle.sh mtime düzeltmesi).
  - Etiketler: `v0.1-sabit` → `d15fe36` · `v0.2-sabit` → `fe3d4e0`. Kural dosyası: `DALLAR.md`.
  - **Günlük iş `dev`'e** gider; `main`'e yalnız parlatma bitince merge + etiket (ayrıntı: skill).
- **Arşiv (+ veri):** `~/MacAir` (git: `~/MacAir`; uzak `git@pi2b01.local:macair.git`, `main` = `cac211e` = `origin/main`;
  etiketler `sabit-2026-10-10`, `sabit-2026-10-12`). **Uyarı:** ağaçta **başka oturumların commit'lenmemiş**
  değişiklikleri var (`delinux01-*.md`, `filo-desktop-konsolu.md`, `isci-model/*`) → `git add -A` **yok**,
  yalnız kendi dosyalarını ekle, yabancı değişiklikleri raporla/sahiplenme.
- **Skill (bu işin ansiklopedisi):** `fms-200-arsiv` — **ilk iş bunu yükle** (`skill_view(name='fms-200-arsiv')`).

## Çalışan servis — ŞU AN KAPALI (13 Eki ölçüldü: 8765'te uvicorn yok) → ayağa kaldır:
```bash
cd ~/Git/fms200-arama && FMS200_ROOT=~/MacAir/fms-200 \
  FMS200_EMBED_URL=http://192.168.1.26:11434 FMS200_EMBED_MODEL=nomic-embed-text \
  .venv/bin/uvicorn fms200_arama.app:app --host 0.0.0.0 --port 8765 --reload
```
- Arayüz: MacAir `http://127.0.0.1:8765` · telefon/notebook (wifi) `http://192.168.1.10:8765`
- Açılış doğrulaması: `/api/status` → **1119 kayıt · 138 etiket** beklenir.
- **Ölçülen indeks durumu** (sunucu kapalıyken `data/fms200.db`'den, 13 Eki): sayfa **1119**, etiketli **138**;
  `meta`: `embed_backend=server`, `embed_model=nomic-embed-text`, `embed_dim=768`.
- **`bayat` tuzağı:** DB mtime **10 Eki 19:22**; o tarihten sonra *indekslenen* kaynaklarda değişiklik yok →
  indeks gerçekte taze. `/api/status` `bayat:true` derse kaynağı **indekslenmeyen** dosyalardır
  (ör. `fms-200/oturum-arsivi/*`, `arastirma/*.py`) — önce neyin değiştiğine bak.

## Devir durumu (13 Eki)
- Önceki oturum **`20261010_174427_1d1394`** ("FMS-200") arşive alındı:
  transcript `~/MacAir/fms-200/oturum-arsivi/` altına export edildi (MD **790 mesaj** + JSONL 4,4 MB,
  `manifest.jsonl`'e işlendi) ve Hermes oturum listesinden **arşive** çekildi (pin kaldırıldı → otomatik arşiv muafiyeti yok).
- 8 modül dossiyesi + özet: `~/MacAir/fms-200/durum/FMS201..208_DURUM.md` + `MODUL_DURUM_OZET.md` +
  `ANNEXA_ARIZA_TABLOLARI.md` (10 Eki 19:06).
- Etiketleme: **138 sayfa** (Annex B 27 · Annex C 13 · Annex E 41 · teknik belge ekleri 39 · GRAFCET 13 · PLC 5);
  `label` + FTS `labeltext`; betikler `arastirma/*_etiketle.py` (dry-run varsayılan, `--uygula`).
- **Paketler** (`~/MacAir/dist/`): `fms200-paket-20261010.tar.gz` (337,9 MB) — **DONDURULMUŞ**, `dist/OKU.md`:
  yeniden üretme/üzerine yazma · `fms200-paket-20261012.tar.gz` (341,5 MB, 12 Eki 22:27) — hangi etiket
  setiyle üretildiği ve doğrulandığı `OKU.md`'de **yazılı değil** (aşağıdaki 1. iş).

## Sıradaki iş (birini seç / kullanıcı söyler)
1. **12 Eki paketinin durumu:** etiket setini/doğrulamasını teyit et → `dist/OKU.md`'ye işle.
   Dondurulmuş 10 Eki dosyasına **dokunma**; taze paket gerekiyorsa **yeni ad/konum** + etiket.
2. **Yeni döküman geldikçe:** arşive koy → `durum/` + `arastirma/` betikleriyle işle → **⟳ İndeks**
   (ya da `build_index`) → gerekirse `modul_durum.py FMS-20x` → **`etiketli` sayısını doğrula**.
3. **Yeni şema/çizim seti gelirse:** antet kırp → vision/OCR → ilgili `*_etiketle.py --uygula` → reindex
   → `etiketli` sayısını karşılaştır.
4. **Lab'a gidince** dossiyelerin §5 "gerçek durum" tablolarını bulgularla doldur
   (EST.3/4/5/7 elektrik şeması eksikliği ve EST.7/8 arıza tablosu eksikliği lab'da teyit edilecek).
5. Parlatma listesi **kapandı** (`PARLATMA_NOTLARI.md` — yeni iş eklenmez, madde durumları orada).

## Paket / Ece kopyası
- Kural: paket DB'yi taşır → her etiket/indeks işinden sonra paket **bayatlar**; sürüm notunda hangi
  etiket setiyle üretildiği yazılır. **Yayınlanan paket dondurulmuştur** — yeni paket **yeni ad/konum** ile.
- Ece'nin notebook'u: `tar xzf …`, sonra `./basla.sh` (0.0.0.0:8765), kılavuz `KURULUM.md`.

## Değişmezler
- **Ölçmeden "yapıldı" deme:** test (`pytest`, 51 test), `curl` HTTP 200, uzak commit hash'i, DB sayımı kanıt sayılır.
- **Sıra:** ana iş → parlatma turu → `dev` pürüzsüz → `main` merge + etiket → paket (**EN SON**).
- **Reindeksten sonra etiket sayısını karşılaştır** (`build_index` etiketleri korur: `c1cb3b9`).
- Büyük üretilmiş ikililer repoya **girmez** (`.gitignore`).
