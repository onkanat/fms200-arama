# FMS-200 Arşivi — Kurulum (Ece'nin notebook'u)

Paket içeriği: **`fms-200/`** (doküman arşivi) · **`fms200-arama/`** (arama motoru + web arayüzü) ·
**`basla.sh`** (tek komut) · bu kılavuz.

---

## 1. Paketi aç

```bash
tar xzf fms200-paket-YYYYMMDD.tar.gz
cd fms200-paket-YYYYMMDD
```

## 2. Başlat

```bash
./basla.sh
```

Bu betik ilk seferde **sanal ortamı kurar** ve **indeksi oluşturur** (birkaç dakika), sonra arşivi
**0.0.0.0:8765** üzerinden yayına açar. Ekrana şunun gibi bir adres yazar:

```
http://192.168.x.y:8765
```

## 3. Gir

- **Notebook'ta:** tarayıcıdan `http://localhost:8765`
- **Telefonda:** `http://192.168.x.y:8765`  (telefon **aynı wifi**'de olmalı)

## 4. Kim ne yaptı (git)

Sağ üstteki **👤** düğmesine basıp **adını yaz**. Bundan sonra her düzenleme o adla **git'e işlenir**.
Geçmişi görmek için (düzenleyicide "son:" notu, ya da terminalde):

```bash
git -C . log --pretty="%ad  %an  %s" --date=short -- fms-200/durum/
```

> Düzenlemeler **Markdown** dosyalarına yapılır (durum dossiyeleri, README, modül listesi).
> Arayüzde bir dossiye gir → **✏️ Düzenle** → editörde yaz → **💾 Kaydet**.

---

## Notlar / sınırlar

- **Semantik arama** (anlam) 768-dim **embedding sunucusu** gerektirir (`nomic-embed-text`).
  Sunucu erişilemezse motor **otomatik olarak yerel (hashing) moda** düşer — **tam metin arama
  (FTS5) her koşulda çalışır**. Embedding sunucusu varsa:
  ```bash
  FMS200_EMBED_URL=http://<sunucu>:11434 FMS200_EMBED_MODEL=nomic-embed-text ./basla.sh
  ```
- **Arşivi güncellediysen** indeksi yenile (arayüzde **⟳ İndeks** düğmesi ya da):
  ```bash
  cd fms200-arama && FMS200_ROOT=../fms-200 .venv/bin/python -m fms200_arama.build_index \
      --root ../fms-200 --db data/fms200.db
  ```
- **Yeni doküman eklemek** için arşiv yapısı: `fms-200/dokuman/<AD>/{metin,ocr_deepseek,jpg}/sayfa_NNN.*`
  (kod deposundaki `README.md` → "Arşiv yapısı").
- Paket **telif** gereği yalnız sizin arşivinizi taşır; SMC belgeleri üçüncü kişilerle **paylaşılmamalı**.
