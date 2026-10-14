# FMS-200 Hibrit Arama + Sohbet

**SMC FMS-200** (esnek otomasyon/mekatronik eğitim hücresi) dokümantasyon arşivi için
**taşınabilir, yerel, ağsız çalışabilen** hibrit arama motoru, **atıflı sohbet (RAG)** katmanı ve
Türkçe web arayüzü.

| | |
|---|---|
| **Sürüm** | `v0.3-sabit` (14 Eki 2026) |
| **Test** | 87 test (`pytest`) |
| **Durum** | `dev` günlük iş · `main` sabit sürüm · paket `dist/` (Ece'nin notebook'u) |

- **Lexical:** SQLite **FTS5** (`bm25`), aksan-duyarsız (`remove_diacritics 2`) → ş→s, ı→i, á→a
- **Semantic:** **768-dim gömme** (varsayılan: `nomic-embed-text` sunucusu) · sunucu yoksa
  **hashing** yedeğine düşer (0-token, ağsız çalışır)
- **Fusion:** **RRF** (Reciprocal Rank Fusion, k=60) + etiket bonusu
- **Etiketleme:** sayfa bazında (`label` + ayrı FTS `labeltext` kolonu; etiket 8× ağırlık)
- **Sohbet:** 💬 Sor → arşivden bağlam → **atıflı** yanıt; model yoksa arama yine çalışır
- **Normalizasyon:** Scribd/OCR harf-aralı boşlukları onarır (`"o c h o p"`→`ochop`)
- **Arayüz:** Tek sayfa, CDN'siz; arama + görüntüleyici + Markdown düzenleme (git'li çok kullanıcı)

> Bu depo **kodu** taşır; telif hakkı SMC'ye ait **belgeleri taşımaz**. Arşivini kendin oluşturursun.

---

## 💬 Sohbet (RAG) — arama sonrası soru sorma

Aramadan sonra belgeler hakkında soru sorulur; yanıt **yalnız verilen bağlamdan** üretilir ve her bilgi
`[belge, sayfa N]` ile atıflandırılır (arayüzde **tıklanabilir**; bağlamda bulunmayan atıf **turuncu**
"bu atıf bağlamda yok" rozetiyle işaretlenir).

**Akış:** soru → hibrit arama → getirim iyileştirmeleri (modül kodu yönlendirmesi, belge çeşitliliği,
jenerik dossiye freni) → sayfa **metninden** dilimler → model → atıflı yanıt.

- **Atıf disiplini:** model atıf koymayı unutursa kaynakları **kod** ekler (uydurma riski sıfır).
- **Çok dillilik:** sorgu TR→EN+ES açılır (`hidrolik pres` = `hydraulic press` = `prensa hidráulica`);
  yanıt **sorunun dilinde** verilir.
- **Arşivde olmayan soru:** deterministik *"arşivde bulamadım + yakın belgeler + daraltma önerisi"*
  (çıkmaz sokak yok). Arşivde var olan ama tam karşılığı olmayan konularda model **ne bulunduğunu** söyler.
- **Araç (ajan araması):** model araç destekliyorsa `arastir_arsiv` ile ek arama yapar (en çok 2 tur);
  desteklemeyen modelde araç otomatik kapanır (sohbet düşmez). İki çağrı biçimi de tanınır
  (`function` sarmalı ve düz `name`/`arguments`, ayrıca `<tool_call>` metni).
- **Görev cümlesi** (*"… dosyasını yeniden yaz"*): **taslak** üretilir, **diske yazılmaz** → arayüzde
  "✏️ Düzenleyicide aç"; git kaydı yalnız **💾 Kaydet** denirse oluşur.

### Uç seçimi — ağ-duyarlı (Ece hiçbir şey ayarlamaz)

`FMS200_CHAT_URL` **verilmezse** uç, ağ ölçümüyle seçilir:

| Ortam | Uç · model | think | Bağlam |
|---|---|---|---|
| **Ev ağında** (ECE_PC erişilebilir) | `192.168.1.26:11435` · `qwen3.6:35b-a3b-coding-mtp-q4_K_M` | **açık** | **sınır yok** (sunucudaki model ayarı) |
| **Ev ağı yok (okul)** | yerel `gemma3:4b` | kapalı | 4096 |

- Ölçüm **TCP denemesi + 60 sn önbellek** → istek başına gecikme yok. `FMS200_CHAT_URL` açıkça
  verilirse "elle" modu (ölçüm/deneme) kullanılır.
- **`think=true` bütçeyi yer:** ölçüldü — 600 token bütçeyle üretimin tamamı muhakemeye gitti ve
  **yanıt 0 kr** döndü. Bu yüzden think açıkken bütçe 3000'dir ve **düşünme metni yanıt yerine konmaz**.
- Durum ucunda görünür: `/api/status → sohbet.{mod, think, ev_agi, ctx, en_fazla, arac_destek}`.

### Ölçülmüş model tablosu (sıkı ölçüt: zorunlu/any/yasak + bağlamda **tanınan** atıf)

| Model | Skor | Süre | Not |
|---|---|---|---|
| `qwen3.6:35b-a3b-coding-mtp-q4_K_M` (ECE_PC) | **15/15** | 0,2–15,7 sn (think kapalı) · 26–68 sn (açık) · 18–90 tok/s | ev modu |
| `gemma3:4b` (yerel, 8 GB M2) | **14/15** | 20–130 sn · 1,5–11 tok/s | okul modu |
| `qwen3:4b` (düşünen) | ❌ | 61–141 sn | bütçe muhakemeye gidiyor |
| 1B sınıfı (`gemma3:1b`) | ❌ 0 atıf | — | uydurma |
| `nemotron-3-nano:4b` | ❌ 2/14 | — | atıf disiplini zayıf; araştırma testi **0/6 araç çağrısı**, uydurma atıf |
| MLX (mlx-lm) | ⚠️ | hız eşit, bellek daha yüksek | tek runtime = ollama |

Yeni model adayı **bu setle ölçülür**, sonra seçilir (düzenek: arşivde `arastirma/sohbet_olcum*.py`).

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

# Web arayüzü (arama + 💬 Sor)
FMS200_ROOT=/yol/fms-200 .venv/bin/uvicorn fms200_arama.app:app --host 127.0.0.1 --port 8765
# tarayıcı: http://127.0.0.1:8765
```

Sohbet için yerel model (ağsız çalışsın diye): `ollama pull gemma3:4b` (~3,4 GB).
Model yoksa **arama bozulmaz** — `/api/ask` `ok:false` + kaynak listesi döner, arayüz bunu söyler.

---

## Uçlar (HTTP API)

| Uç | İş |
|---|---|
| `GET /api/status` | kayıt/etiketli sayısı · `bayat` · gömme arka ucu (`embed`, `embed_calisiyor`) · **sohbet** (mod/think/model) |
| `GET /api/search` | arama (`q`, `doc`, `k`, `mode=lexical|semantic|hybrid`, `lang`) |
| `POST /api/ask` | **sohbet**: `{q, doc?, k?, mode?, model?, ctx?, en_fazla?, araclar?}` → atıflı yanıt |
| `GET /api/page` · `GET /api/file` | sayfa metni (markdown) · sayfa görseli |
| `GET /api/docs` · `POST /api/label` | döküman listesi · sayfa etiketi yaz |
| `GET /api/raw` · `POST /api/save` · `GET /api/history` | düzenlenebilir metin · kaydet (git commit) · geçmiş |
| `POST /api/reindex` | indeksi yenile (**etiketli** sayısını sonra karşılaştır) |

### Ortam değişkenleri

| Değişken | Varsayılan | Not |
|---|---|---|
| `FMS200_ROOT` | — | arşiv kökü |
| `FMS200_EMBED_URL` / `FMS200_EMBED_MODEL` | — / `nomic-embed-text` | gömme sunucusu; yoksa hashing |
| `FMS200_CHAT_URL` / `FMS200_CHAT_MODEL` | *(ağ ölçümü)* / `gemma3:4b` | açıkça verilirse "elle" modu |
| `FMS200_EV_URL` / `FMS200_EV_MODEL` | `http://192.168.1.26:11435` / 35B coding | **ev ağında** kullanılır |
| `FMS200_YEREL_URL` / `FMS200_YEREL_MODEL` | `http://127.0.0.1:11434` / `gemma3:4b` | **ev ağı yoksa** |
| `FMS200_CHAT_THINK` | `0` (kapalı) | **Ölçüldü:** açıkken aynı soru 81–240 sn ve boş/kesik yanıt; kapalıyken 0,2–15,7 sn ve 15/15. Açılırsa bütçe otomatik 8000 |
| `FMS200_CHAT_CTX` | `4096` (`0` = sınır yok) | ev modunda **gönderilmez** (sunucu ayarı) |
| `FMS200_CHAT_MAX` | ev: `3000` (`think=1` ise `8000`) · yerel: `600` | en fazla üretilecek token |
| `FMS200_CHAT_BUTCE` · `_DILIM` · `_DILIM_SAYI` · `_SEC` | ev: `24000` kr · `2000` kr · `6` · `8` | **bağlam bütçesi** (yerel: 6500 · 1300 · 4 · 5). Büyük model + tablolu belgeler için ölçülerek büyütüldü |
| `FMS200_CHAT_KEEP_ALIVE` | ev: `30m` · yerel: `5m` | modeli sıcak tut — boşalınca ilk soru 22 GB yeniden yükleme yüzünden **2-3 dk** sürüyordu |
| `FMS200_CHAT_TIMEOUT` / `FMS200_CHAT_TIMEOUT_GOREV` | 120/600 · 300 | saniye |
| `FMS200_CHAT_TOOLS` | `1` | `0` → ajan araması kapalı |

---

## Arşiv yapısı (indeksleyici bunu bekler)

```
fms-200/
├── dokuman/<DOKUMAN_ADI>/
│   ├── metin/sayfa_001.txt        # Scribd metin katmanı (harf aralı olabilir)
│   ├── ocr_deepseek/sayfa_001.txt # (tercih edilir) DeepSeek-OCR temiz metni
│   ├── ocr_metin/sayfa_001.txt    # (alternatif) tesseract çıktısı
│   └── sayfalar/sayfa_001.jpg     # sayfa görseli (metin/semalar/ de olur)
├── durum/FMS20x_DURUM.md          # modül durum dossiyeleri (indekslenir, arayüzde düzenlenir)
├── dokuman/*.txt · yazilim/*.txt
└── *.md                           # kökteki tüm .md indekslenir
```

**Metin önceliği:** `en_iyi/` > `ocr_deepseek/` > `ocr_deepseek_plain/` > `ocr_metin/` > `metin/`.
Aynı sayfa için en üstteki kaynak kazanır (OCR temiz metni otomatik öne geçer).

---

## OCR ile temizlik (opsiyonel ama önerilir)

```bash
python3 scripts/ocr_deepseek.py <jpg_klasoru> <cikti_klasoru>   # tek klasör
python3 scripts/ocr_batch.py <jpg_klasoru> <cikti_klasoru> <sayfa_listesi.txt> --workers 3
```

Varsayılan sunucu `http://192.168.1.26:11434`, model `deepseek-ocr:3b-bf16`
(`OLLAMA_HOST_URL`, `OCR_MODEL` ile değiştirilir).

---

## Test

```bash
.venv/bin/python -m pytest tests/ -q      # 87 test (ağ yok: model çağrısı monkeypatch ile taklit)
```

---

## Paket (Ece'nin notebook'u)

```bash
scripts/paketle.sh                        # ~/MacAir/dist/fms200-paket-YYYYMMDD.tar.gz
```

Paket: arşiv + kod + **hazır DB (1119 kayıt / 138 etiket)** + taze git + `basla.sh` + `KURULUM.md`.
**Yayınlanan paket dondurulmuştur** — taze paket her zaman **yeni ad** ile üretilir, üzerine yazılmaz;
kayıt `dist/OKU.md`'de (sha256 + boyut). Hedefte:

```bash
tar xzf fms200-paket-YYYYMMDD.tar.gz && cd fms200-paket-YYYYMMDD && ./basla.sh
```

`basla.sh` venv'i kurar, indeks yoksa kurar, **sohbet modeli (`gemma3:4b`) yoksa indirmeyi dener**
(internet gerekir), sonra `0.0.0.0:8765`'te yayına açar. Ayrıntı: **`KURULUM.md`**.

---

## Sınırlar

- Hashing vektör (gömme sunucusu yoksa) **semantik değil** (soft-lexical); ağsız/0-token çalışsın diye böyle.
- PDF/görsel OCR **bu depoda yok**; yalnız çıkarılmış `*.txt` indekslenir (OCR betikleri `scripts/`).
- Kaba dil tespiti (`tr/en/es/de/fr`) anahtar-kelime tabanlıdır.
- Sohbet modelinin **kalitesi modele bağlıdır**: ölçülmüş modeller yukarıdaki tabloda; model yoksa
  özellik susar, arama çalışır.

## Lisans

Kod: MIT. SMC belgeleri bu depoda **yoktur** ve SMC'nin telif hakkına tabidir.
