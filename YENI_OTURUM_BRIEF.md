# YENİ OTURUM BRİEFİ — FMS-200 DEV

> Yeni oturumda **ilk mesaj** olarak bunu oku: `~/Git/fms200-arama/YENI_OTURUM_BRIEF.md`.
> Bu dosya, temiz bir oturumun 800 mesaj okumadan işe devam edebilmesi için var.

## Nerede çalışıyoruz
- **Kod deposu:** `~/Git/fms200-arama` — **`dev` dalındayız.**
  - `main` = **SABİT sürüm** (Ece'nin paketiyle eşleşir, etiket **`v0.2-sabit`** — sunum sonrası 11 Eki 2026 birleştirmesi) → **dokunma**.
  - Kural dosyası: `DALLAR.md`.
- **Arşiv (+ veri):** `~/MacAir/fms-200` (git: `~/MacAir`; uzak depo `git@pi2b01.local:macair.git`, etiket `sabit-2026-10-10`).
- **Skill (bu işin ansiklopedisi):** `fms-200-arsiv` — **ilk iş bunu yükle** (`skill_view(name='fms-200-arsiv')`).
  Kaynak: mimari, boru hattı, editör+git, paketleme, modül dossiyesi, tuzaklar hepsi orada.

## Çalışan servis
```bash
# (durdurulmuşsa) ayağa kaldır:
cd ~/Git/fms200-arama && FMS200_ROOT=~/MacAir/fms-200 \
  FMS200_EMBED_URL=http://192.168.1.26:11434 FMS200_EMBED_MODEL=nomic-embed-text \
  .venv/bin/uvicorn fms200_arama.app:app --host 0.0.0.0 --port 8765 --reload
```
- Arayüz: MacAir `http://127.0.0.1:8765` · **telefon/notebook (wifi) `http://192.168.1.10:8765`**
- Durum: `/api/status` · indeks **1119 kayıt**, **138 etiket**, `bayat:false`.

## Bu oturumda nerede kaldık
- 8 modül (FMS-201…208) için **durum dossiyeleri** yazıldı: `~/MacAir/fms-200/durum/FMS20x_DURUM.md` (+ `MODUL_DURUM_OZET.md`).
- Arayüz: markdown render düzeltildi + **✏️ Düzenle** (Markdown editör) + her kayıt **git'e yazar adıyla** işleniyor (`/api/save`, `/api/history`).
- `dev`/`main` ayrıldı; **sunum sonrası `dev` → `main` birleştirildi** + `v0.2-sabit` etiketi + paket yenilendi.
- **ETİKETLEME (10 Eki): 138 sayfa** — Annex B 27 · Annex C 13 · Annex E 41 · teknik belge çizim ekleri 39
  (AnnexE + 111 ofseti, doğrulandı) · GRAFCET sayfaları 13 · PLC program sayfaları 5.
  TR/EN/ES çok dilli, `label` + FTS `labeltext`. Betikler: `arastirma/annexbc_etiketle.py`,
  `annexE_etiketle.py` (`--td`), `kod_sayfalari_etiketle.py` (hepsi dry-run varsayılan, `--uygula`, `--sadece`).
- **Kritik hata düzeltildi (bu repoda):** `build_index.build()` etiketleri `DELETE FROM pages`'ten sonra
  okuyordu → her reindeks **tüm etiketleri siliyordu**; ayrıca etiket FTS'e hiç yazılmıyordu. Düzeltildi
  (`c1cb3b9`), regresyon testleri eklendi (**51 test**). **Kural: reindeksten sonra `etiketli` sayısını karşılaştır.**
- **Parlatma turu yapıldı** (10 Eki): etiket güncellenince eski terim düşüyor (ayrı `labeltext` kolonu),
  `norm()` X/Y/Z istisnası, `bayat` yalnız indekslenen kaynaklara bakıyor, etiket eşleşmesi sıralamada öne
  geçti (bm25 8× ağırlık + hibrit RRF bonusu), arayüzde 🏷 rozeti. Liste DONDURULDU.
- **AnnexA arıza tabloları** vision ile okundu → `durum/ANNEXA_ARIZA_TABLOLARI.md` (EST.1–6, 65 kayıt:
  semptom → **kırık bileşen + Xn/Yn**); dossilerin §4'ü bu tabloyla beslendi. **EST.7/8 tablosu arşivde yok.**

## Sıradaki iş (birini seç / kullanıcı söyler)
1. **Yeni döküman geldikçe:** arşive koy → `durum/` + `arastirma/` betikleriyle işle → **⟳ İndeks** (ya da `build_index`) → gerekirse `modul_durum.py FMS-20x`.
2. **Yeni şema/çizim seti gelirse:** antet kırp → vision/OCR → ilgili `*_etiketle.py --uygula` → reindex
   → `etiketli` sayısını doğrula.
3. **Lab'a gidince** dossiyelerin §5 "gerçek durum" tablolarını bulgularla doldurmak
   (EST.3/4/5/7 elektrik şeması eksikliği ve EST.7/8 arıza tablosu eksikliği lab'da teyit edilecek).
4. **Parlatma listesi kapandı** (`PARLATMA_NOTLARI.md` — yeni iş eklenmez, madde durumları orada).

## Paket / Ece kopyası
- **Yeni paket:** `~/MacAir/dist/fms200-paket-<tarih>.tar.gz` — **138 etiketli DB** ile üretildi ve
  temiz dizine açılıp çalıştırılarak doğrulandı (bkz. `PARLATMA_NOTLARI` / commit mesajı).
- Ece'nin notebook'u: `tar xzf …`, sonra `./basla.sh` (0.0.0.0:8765), kılavuz `KURULUM.md`.
- **Kural:** paket DB'yi taşır → her etiket/indeks işinden sonra paket **bayatlar**; sürüm notunda
  hangi etiket setiyle üretildiği yazılır.

## Değişmezler
- Ölçmeden "yapıldı" deme: test (`pytest`), `curl` HTTP 200, uzak commit hash'i kanıt sayılır.
- İş bitince: `dev`'e commit → stabilize olunca `main`'e merge + etiket → `scripts/paketle.sh`.
- Büyük üretilmiş ikililer repoya **girmez** (`.gitignore`).

