# FMS-200 Hibrit Arama

**SMC FMS-200** (esnek otomasyon/mekatronik eğitim hücresi) dokümantasyon arşivi için
**taşınabilir, yerel, ağsız çalışan** hibrit arama motoru ve Türkçe web arayüzü.

- **Lexical:** SQLite **FTS5** (`bm25`), aksan-duyarsız (`remove_diacritics 2`) → ş→s, ı→i, á→a
- **Semantic:** 768-dim hashing vektör + cosine (0-token, sunucu gerekmez)
- **Fusion:** **RRF** (Reciprocal Rank Fusion, k=60)
- **Normalizasyon:** Scribd/OCR çıktısındaki harf-aralı boşlukları onarır (`"o c h o p"`→`ochop`)
- **Arayüz:** Tek sayfa, CDN'siz; arama satırı + sonuç listesi + sayfa metni/görseli görüntüleyici

> Bu depo **kodu** taşır; telif hakkı SMC'ye ait **belgeleri taşımaz**. Arşivini kendin oluşturursun.

---

## Hızlı başlangıç

```bash
git clone <bu-depo> fms200-arama && cd fms200-arama
python3 -m venv .venv && .venv/bin/python -m pip install -e ".[web,dev]"

# Arşivini indeksle (aşağıdaki "Arşiv yapısı"na bak)
.venv/bin/python -m fms200_arama.build_index --root /yol/fms-200 --db data/fms200.db

# Komut satırından ara
.venv/bin/python -m fms200_arama.search "GRAFCET"
.venv/bin/python -m fms200_arama.search "rodamiento estación" --lang es

# Web arayüzü
FMS200_ROOT=/yol/fms-200 .venv/bin/uvicorn fms200_arama.app:app --host 127.0.0.1 --port 8765
# tarayıcı: http://127.0.0.1:8765
```

---

## Arşiv yapısı (indeksleyici bunu bekler)

```
fms-200/
├── dokuman/<DOKUMAN_ADI>/
│   ├── metin/sayfa_001.txt        # Scribd metin katmanı (harf aralı olabilir)
│   ├── ocr_deepseek/sayfa_001.txt # (tercih edilir) DeepSeek-OCR temiz metni
│   ├── ocr_metin/sayfa_001.txt    # (alternatif) tesseract çıktısı
│   └── sayfalar/sayfa_001.jpg     # sayfa görseli (metin/semalar/ de olur)
├── dokuman/*.txt                  # katalog metinleri
├── yazilim/*.txt
└── README.md
```

**Metin önceliği:** `ocr_deepseek/` > `ocr_metin/` > `metin/`. Aynı sayfa numarası için
en üstteki kaynak kazanır — böylece OCR ile temizlenmiş metin otomatik öne geçer.

---

## OCR ile temizlik (opsiyonel ama önerilir)

Scribd'ten gelen metinler harf arası boşluklu olabilir ve tesseract bazı sayfalarda
gürültülüdür. **DeepSeek-OCR** (Ollama) ile temiz markdown çıkarılır:

```bash
python3 scripts/ocr_deepseek.py <jpg_klasoru> <cikti_klasoru>   # tek klasör
python3 scripts/ocr_batch.py <jpg_klasoru> <cikti_klasoru> <sayfa_listesi.txt> --workers 3
```

Varsayılan sunucu `http://192.168.1.26:11434`, model `deepseek-ocr:3b-bf16`
(ortam değişkeniyle değiştirilir: `OLLAMA_HOST_URL`, `OCR_MODEL`).

---

## Test

```bash
.venv/bin/python -m pytest tests/ -q      # 29 test
```

---

## Sınırlar

- Hashing vektör **semantik değil** (soft-lexical); ağsız/0-token çalışsın diye böyle.
  İstenirse `fms200_arama/vec.py::embed` yerine bir embedding sunucusu takılır (arayüz aynı).
- PDF/görsel OCR **bu depoda yok**; yalnız çıkarılmış `*.txt` indekslenir. OCR betikleri `scripts/`.
- Kaba dil tespiti (`tr/en/es/de/fr`) anahtar-kelime tabanlıdır.

## Lisans

Kod: MIT. SMC belgeleri bu depoda **yoktur** ve SMC'nin telif hakkına tabidir.
