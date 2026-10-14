# YENİ OTURUM BRİEFİ — FMS-200 DEV

> Yeni oturumda **ilk mesaj** olarak bunu oku: `~/Git/fms200-arama/YENI_OTURUM_BRIEF.md`.
> Bu dosya, temiz bir oturumun 800 mesaj okumadan işe devam edebilmesi için var.
> (Güncelleme: 13 Eki 2026 — önceki FMS-200 oturumu arşive alındı, ayrıntı §"Devir durumu".)

## ECE · Sohbet (RAG) + Okul senaryosu — 14 Eki 2026'da yazıldı, UÇ SEÇİMİ tamamlandı
- **Plan + tüm ölçümler:** `~/MacAir/fms-200/arastirma/ECE_SOHBET_OKUL_PLANI.md` (§"Tur 4–7" en güncel:
  ölçüm düzenekleri aynı dizinde: `sohbet_olcum.py`, `sohbet_olcum2.py`, `sohbet_altin_set.json` (15 soru),
  `sohbet_olcum_sonuclari.jsonl`).
- **Özellik (kodda):** `POST /api/ask` + arayüzde **💬 Sor** + tıklanabilir atıflar (bağlamda olmayan atıf
  **turuncu** = uydurma uyarısı) + atıfsız yanıta **koddan kaynak ekleme** + çok dilli sorgu açılımı
  (TR→EN+ES) + araç `arastir_arsiv` (iki çağrı biçimi de tanınır) + görev modu **taslak** (diske yazmaz).
- **UÇ SEÇİMİ AĞ-DUYARLI (`uc()`, kullanıcı kararı 14 Eki):** `FMS200_CHAT_URL` verilmezse ev ağı ölçülür
  (TCP + 60 sn önbellek): **ev ağında** → ECE_PC `192.168.1.26:11435` · `qwen3.6:35b-a3b-coding-mtp-q4_K_M` ·
  **think AÇIK** · **bağlam sınırı yok** (`num_ctx` gönderilmez) · bütçe 3000; **ev ağı yoksa** → yerel
  **`gemma3:4b`** · think kapalı · 4096. `/api/status → sohbet.{mod, think, ev_agi}`. **Ece hiçbir şey ayarlamaz.**
- **Kural — `think=true` bütçesiz açılmaz:** ölçüldü, 600 token bütçede üretimin tamamı muhakemeye gitti ve
  **yanıt 0 kr** döndü; think açıkken bütçe ≥3000 (maliyet 26–68 sn/yanıt ↔ kapalıyken 0,2–15,7 sn).
  **Düşünme metni ASLA yanıt yerine konmaz.**
- **Ölçülmüş model tablosu (sıkı ölçüt):** ECE_PC 35B **15/15** ✅ (ev) · `gemma3:4b` **14/15** ✅ (okul) ·
  `qwen3:4b` ❌ · 1B ❌ (0 atıf) · `nemotron-3-nano:4b` ❌ (atıf zayıf + araştırma **0/6 araç çağrısı**,
  uydurma atıf) · MLX ⚠️ (hız eşit, bellek yüksek). **gemma4'ün küçük sürümü YOK** (`1b`/`4b` 404).
- **Test:** `pytest` **87 geçiyor**. **Getirim hazır:** yerel `nomic-embed-text` = uzaktakiyle birebir aynı
  → okulda/çevrimdışı **arama tam çalışır**. Sohbet modeli yoksa özellik susar, arama bloke olmaz.
- **Açık kalemler:** P2 okul paketinin sahada denenmesi (Ece'de `basla.sh`) · P4 `KURULUM.md` + örnek sorular ·
  bağlam bütçesi/gecikme dengesi (8 GB makine swap'e giriyor) · kullanıcı nemotron'da ısrar ederse
  araç çağrısını zorlayan ek iş gerekir.

## Nerede çalışıyoruz
- **Kod deposu:** `~/Git/fms200-arama` — **`dev` dalındayız.** Kural dosyası: `DALLAR.md`.
  - `main` = **SABİT sürüm** (`v0.3-sabit`, 14 Eki 2026: sohbet/RAG + uç seçimi + README/KURULUM güncel).
  - Etiketler: `v0.1-sabit` · `v0.2-sabit` · **`v0.3-sabit`**. Günlük iş `dev`'e; `main`'e yalnız parlatma
    bitince merge + etiket (ayrıntı: skill). Her iş sonunda uzak hash `git ls-remote origin refs/heads/dev`
    ile doğrulanır.
- **Arşiv (+ veri):** `~/MacAir` (uzak `git@pi2b01.local:macair.git`). **Uyarı:** ağaçta **başka oturumların
  commit'lenmemiş** değişiklikleri var (`delinux01-*.md`, `filo-desktop-konsolu.md`, `isci-model/*`) →
  `git add -A` **yok**, yalnız kendi dosyalarını ekle, yabancı değişiklikleri raporla/sahiplenme.
- **Paket kaydı:** `~/MacAir/dist/OKU.md` (sha256 + boyut; paketler **DONDURULMUŞ** — üzerine yazılmaz,
  taze paket yeni ad ile). Geçerli paket: `fms200-paket-20261014.tar.gz`.
- **Skill (bu işin ansiklopedisi):** `fms-200-arsiv` — **ilk iş bunu yükle** (`skill_view(name='fms-200-arsiv')`).

## Çalışan servis — sohbet ucu ARTIK OTOMATİK (14 Eki)
```bash
cd ~/Git/fms200-arama && FMS200_ROOT=~/MacAir/fms-200 \
  FMS200_EMBED_URL=http://192.168.1.26:11434 FMS200_EMBED_MODEL=nomic-embed-text \
  .venv/bin/uvicorn fms200_arama.app:app --host 0.0.0.0 --port 8765 --reload
```
- **Sohbet için env VERİLMEZ:** `uc()` ev ağını ölçer → evde ECE_PC 35B (think açık, sınırsız bağlam),
  okulda yerel `gemma3:4b`. Doğrulama: `/api/status → sohbet.{mod, model, think, ev_agi}`.
- Arayüz: MacAir `http://127.0.0.1:8765` · telefon/notebook (wifi) `http://192.168.1.10:8765`
- Açılış doğrulaması: `/api/status` → **1119 kayıt · 138 etiket** beklenir.
- **`bayat` tuzağı:** `/api/status` `bayat:true` derse kaynağı **indekslenmeyen** dosyalardır
  (ör. `fms-200/oturum-arsivi/*`, `arastirma/*.py`) — önce neyin değiştiğine bak.

## Devir durumu (14 Eki)
- Etiketleme: **138 sayfa** (Annex B 27 · Annex C 13 · Annex E 41 · teknik belge ekleri 39 · GRAFCET 13 · PLC 5);
  `label` + FTS `labeltext`; betikler `arastirma/*_etiketle.py` (dry-run varsayılan, `--uygula`).
- **Paketler** (`~/MacAir/dist/`, ayrıntı + sha256: `dist/OKU.md`): `fms200-paket-20261010.tar.gz`
  (337,9 MB, **etiketsiz** DB) **DONDURULMUŞ** · `fms200-paket-20261012.tar.gz` (341,5 MB) **DONDURULMUŞ**
  (doğrulandı: DB 1119/138, uçlar 200) · **`fms200-paket-20261014.tar.gz` = güncel sürüm (v0.3-sabit)**.

## Sıradaki iş (birini seç / kullanıcı söyler)
1. **Paketi Ece'de sahada dene:** indir → `tar xzf` → `./basla.sh` → 💬 Sor; sonucu bu brief'e yaz.
2. **Yeni döküman geldikçe:** arşive koy → `durum/` + `arastirma/` betikleriyle işle → **⟳ İndeks**
   (ya da `build_index`) → gerekirse `modul_durum.py FMS-20x` → **`etiketli` sayısını doğrula**.
3. **Yeni şema/çizim seti gelirse:** antet kırp → vision/OCR → ilgili `*_etiketle.py --uygula` → reindex
   → `etiketli` sayısını karşılaştır.
4. **Lab'a gidince** dossiyelerin §5 "gerçek durum" tablolarını bulgularla doldur
   (EST.3/4/5/7 elektrik şeması eksikliği ve EST.7/8 arıza tablosu eksikliği lab'da teyit edilecek).
5. **Sohbet kalitesi:** bağlam bütçesi/gecikme dengesi (8 GB makinede swap) — ölçerek ilerle.
6. Parlatma listesi **kapandı** (`PARLATMA_NOTLARI.md` — yeni iş eklenmez, madde durumları orada).

## Paket / Ece kopyası
- Kural: paket DB'yi taşır → her etiket/indeks işinden sonra paket **bayatlar**; sürüm notunda hangi
  etiket setiyle üretildiği yazılır. **Yayınlanan paket dondurulmuştur** — yeni paket **yeni ad/konum** ile.
- Ece'nin notebook'u: `tar xzf …`, sonra `./basla.sh` (0.0.0.0:8765, sohbet modelini yoksa indirir),
  kılavuz `KURULUM.md`.

## Değişmezler
- **Ölçmeden "yapıldı" deme:** test (`pytest`, **87 test**), `curl` HTTP 200, uzak commit hash'i, DB sayımı kanıt sayılır.
- **Sıra:** ana iş → parlatma turu → `dev` pürüzsüz → `main` merge + etiket → paket (**EN SON**).
- **Reindeksten sonra etiket sayısını karşılaştır** (`build_index` etiketleri korur: `c1cb3b9`).
- Büyük üretilmiş ikililer repoya **girmez** (`.gitignore`).
