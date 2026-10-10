# YENİ OTURUM BRİEFİ — FMS-200 DEV

> Yeni oturumda **ilk mesaj** olarak bunu oku: `~/Git/fms200-arama/YENI_OTURUM_BRIEF.md`.
> Bu dosya, temiz bir oturumun 800 mesaj okumadan işe devam edebilmesi için var.

## Nerede çalışıyoruz
- **Kod deposu:** `~/Git/fms200-arama` — **`dev` dalındayız.**
  - `main` = **SABİT sürüm** (Ece'nin paketiyle eşleşir, etiket `v0.1-sabit`) → **dokunma**.
  - Kural dosyası: `DALLAR.md`.
- **Arşiv (+ veri):** `~/MacAir/fms-200` (git: `~/MacAir`, etiket `sabit-2026-10-10`).
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
- Durum: `/api/status` · indeks **1118 kayıt**.

## Bu oturumda nerede kaldık
- 8 modül (FMS-201…208) için **durum dossiyeleri** yazıldı: `~/MacAir/fms-200/durum/FMS20x_DURUM.md` (+ `MODUL_DURUM_OZET.md`).
- Arayüz: markdown render düzeltildi + **✏️ Düzenle** (Markdown editör) + her kayıt **git'e yazar adıyla** işleniyor (`/api/save`, `/api/history`).
- **Paket:** `~/MacAir/dist/fms200-paket-20261010.tar.gz` (322M) → Ece'nin notebook'u (`./basla.sh`, kılavuz `KURULUM.md`).
- `dev`/`main` ayrıldı, `v0.1-sabit` etiketlendi; GitHub'a push'lu.
- **ÇİZİM İNDEKSİ ETİKETLENDİ (10 Eki):** Annex B (27) + Annex C (13) + Annex E (41) = **81 sayfa**,
  `label` + FTS'te, TR/EN/ES çok dilli. Betikler: `~/MacAir/fms-200/arastirma/annexbc_etiketle.py`,
  `annexE_etiketle.py` (dry-run varsayılan, `--uygula`, `--sadece`). Antet okuma kanıtları:
  `arastirma/annex{b,c,E}_antet_okumalari.json` · AnnexE düzeltme tablosu: `arastirma/annexE_esleme_duzeltme.md`.
- **Kritik hata bulundu ve düzeltildi (bu repoda):** `build_index.build()` etiketleri `DELETE FROM pages`'ten
  sonra okuyordu → **her reindeks tüm etiketleri siliyordu** (81'i gitti) + etiket hiç FTS'e yazılmıyordu.
  Düzeltildi (`c1cb3b9`), `tests/test_build_index.py` regresyonu eklendi (45 test).
  **Kural: reindeksten sonra `etiketli` sayısını karşılaştır.**
- **Bekleyen küçük işler:** `~/MacAir/fms-200/arastirma/PARLATMA_NOTLARI.md` (11 madde) — parlatma turu.

## Sıradaki iş (birini seç / kullanıcı söyler)
1. **Yeni döküman geldikçe:** arşive koy → `durum/` + `arastirma/` betikleriyle işle → **⟳ İndeks** (ya da `build_index`) → gerekirse `modul_durum.py FMS-20x`.
2. ~~Annex B/C şemalarının istasyon sayfalarını elle işaretlemek~~ → **yapıldı (10 Eki)**; kalan:
   yeni şema/çizim seti gelirse aynı deseni uygula (antet kırp → vision → `*_etiketle.py --uygula`).
3. **Lab'a gidince** dossiyelerin §5 "gerçek durum" tablolarını bulgularla doldurmak.
4. **Parlatma turu** — `PARLATMA_NOTLARI.md` maddeleri; **parlatma bitmeden `main`'e merge / paket YOK.**

## Paket / Ece kopyası (kullanıcı kararı, 10 Eki 2026)
- **Ece'nin kopyası en son güncellenir (≈5 gün sonra).** Şu anki kopyada yalnız **sunum** yapılıyor.
- Yani: parlatmalar → `dev` pürüzsüz → **sonra** `scripts/paketle.sh` (+ gerekiyorsa `main` merge/etiket).
- Mevcut `.tar.gz` **81 etiketsiz** DB içerir; paketi yeniden üretmeden "Ece çizimleri modül adıyla arıyor"
  diye raporlama.


## Değişmezler
- Ölçmeden "yapıldı" deme: test (`pytest`), `curl` HTTP 200, uzak commit hash'i kanıt sayılır.
- İş bitince: `dev`'e commit → stabilize olunca `main`'e merge + etiket → `scripts/paketle.sh`.
- Büyük üretilmiş ikililer repoya **girmez** (`.gitignore`).
