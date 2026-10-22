# dorker — Discovery Engine untuk Resource AI Publik

> **Status: Proof of Concept.** Dibuat untuk membuktikan satu tesis: *dorking
> dari server tidak bisa mengandalkan search engine HTML, tapi bisa dilakukan
> lewat structured API platform.* Semua angka di README ini hasil pengukuran
> nyata dari VPS datacenter, bukan asumsi.

Cari resource AI yang **memang dipublikasikan gratis/terbuka**: free tier resmi,
gateway OpenAI-compatible terdokumentasi, dataset terbuka, mirror bobot model,
list proxy publik, dan awesome-list.

Dua mode:

| Mode | Fungsi |
|---|---|
| `gen` | Cetak dork siap tempel ke Google/Bing (tanpa request) |
| `run` | Jalankan discovery lewat API yang andal dari server |

---

## Kenapa tidak pakai Google/DDG langsung?

Diuji dari VPS ini (IP datacenter), semua search engine HTML memblokir:

| Engine | Hasil uji |
|---|---|
| DuckDuckGo HTML | `202` challenge (juga saat lewat proxy residensial) |
| Mojeek | `200` tapi body = "JavaScript is required to complete this challenge" |
| SearX (searx.be) | `200` tapi body = "Verifying your browser…" |

Jadi `run` memakai API yang benar-benar jalan dari server:

| Source | Butuh key? | Status uji | Kegunaan |
|---|---|---|---|
| `github` | token (auto dari `gh`) | ✅ 92 hasil/5 query | repo & file AI publik — paling produktif |
| `hf` | tidak | ✅ jalan | dataset & model HuggingFace |
| `archive` | tidak | ✅ exact URL | verifikasi snapshot Wayback |
| `brave` | `BRAVE_API_KEY` | opsional | web search (2.000 query/bln gratis) |
| `google` | `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | opsional | web search (100/hari gratis) |
| `ddg` | tidak | ⚠️ sering captcha | best-effort |

Dork Google-style tetap tersedia lewat `gen` — tempel manual di browser.

---

## Instalasi

```bash
python3 -m venv .venv
.venv/bin/pip install requests
```

Token GitHub otomatis diambil dari `gh auth` (`~/.config/gh/hosts.yml`), atau set:

```bash
export GITHUB_TOKEN=ghp_xxx
```

---

## Kategori

```bash
./dorker.py categories
```

```
Kategori             Var       google  github    hf  arch  Deskripsi
free_providers       -              9       6     1     0  Free tier / free credit provider AI resmi
openai_compatible    -              6       5     0     0  Gateway OpenAI-compatible terdokumentasi publik
datasets             topic          8       2     1     0  Dataset AI terbuka
models               model          5       3     1     0  Bobot model & mirror publik
proxies              -              5       4     0     0  Sumber list proxy publik
awesome_lists        -              5       5     0     0  Kurasi / awesome-list API AI gratis
self_audit           domain         6       1     0     0  Audit eksposur domain sendiri
```

---

## Mode `gen` — dork untuk tempel manual

```bash
# Google-style dork (default)
./dorker.py gen --category free_providers

# GitHub search syntax
./dorker.py gen --source github --all

# Butuh variabel
./dorker.py gen --category datasets --topic "medical imaging"
./dorker.py gen --category self_audit --domain example.com
```

Contoh output `--category datasets --topic "medical imaging"`:

```
site:huggingface.co/datasets medical imaging
site:kaggle.com/datasets medical imaging
site:zenodo.org medical imaging dataset
filetype:parquet medical imaging dataset
```

---

## Mode `run` — discovery otomatis

```bash
# GitHub: awesome-list API AI gratis
./dorker.py run --source github --category awesome_lists --limit 30

# HuggingFace: dataset
./dorker.py run --source hf --category datasets --topic "medical imaging" --hf-type datasets

# HuggingFace: bobot model
./dorker.py run --source hf --category models --model qwen --hf-type models

# Multi-sumber sekaligus
./dorker.py run --source github --source hf --category models --model qwen --hf-type models

# Verifikasi snapshot Wayback untuk URL spesifik
./dorker.py run --source archive --category proxies \
  --url "raw.githubusercontent.com/ShiftyTR/Proxy-List/master/proxy.txt"

# Semua kategori, satu sumber
./dorker.py run --source github --all --limit 20

# Opsional: web search ber-key
export BRAVE_API_KEY=xxx
./dorker.py run --source brave --category free_providers
```

Opsi `run`:

| Flag | Default | Keterangan |
|---|---|---|
| `--source` | wajib | ulangi untuk multi-sumber |
| `--limit` | 30 | hasil per query |
| `--delay` | 2.0 | jeda antar query (detik) — jaga rate limit |
| `--hf-type` | `datasets` | `datasets` atau `models` |
| `--url` | – | wajib untuk `--source archive` |
| `--proxy` | – | hanya berguna untuk `ddg` |

---

## Output

Setiap `run` menulis 3 file ke `out/`:

```
out/<kategori>_<timestamp>.jsonl   # satu JSON per baris
out/<kategori>_<timestamp>.csv     # rapi untuk spreadsheet
out/<kategori>_<timestamp>.md      # laporan: domain teratas + daftar hasil
```

Field: `category, source, query, title, url, snippet, extra, domain`

Contoh baris JSONL:

```json
{"category":"models","source":"hf","query":"qwen","title":"Qwen/Qwen3-8B",
 "url":"https://huggingface.co/models/Qwen/Qwen3-8B",
 "snippet":"text-generation, license:apache-2.0","extra":"dl 1200000 | like 850",
 "domain":"huggingface.co"}
```

---

## Catatan rate limit

- **GitHub search**: 30 req/menit (terautentikasi), 10/menit (anonim). `--delay 2` aman.
- **HuggingFace**: longgar, `--delay 1` cukup.
- **Internet Archive CDX**: exact URL cepat; wildcard luas (`domain/*`) timeout/503 — karena itu `archive` dibatasi ke `--url`.
- **Brave**: free tier 2.000 query/bulan, 1 req/detik.

---

## Batas penggunaan

Tool ini menyasar resource yang **dipublikasikan untuk dipakai publik**: free tier
resmi, repo open-source, dataset berlisensi terbuka, list proxy publik.

Bukan untuk memindai server/inference endpoint orang yang tidak sengaja terbuka.
Memakai endpoint pihak lain tanpa izin = unauthorized use. Untuk kasus itu,
pakai kategori `self_audit` pada domain milik sendiri.

---

## Struktur

```
dorker/
├── dorker.py         # CLI utama (gen + run), 7 kategori × 6 sumber
├── run.sh            # wrapper (auto pakai .venv kalau ada)
├── requirements.txt  # requests
├── README.md
├── LICENSE           # MIT
└── out/              # hasil run (gitignored)
```

## Hasil pengukuran PoC

Semua dijalankan dari VPS datacenter dengan `--delay 3`:

| Perintah | Hasil |
|---|---|
| `run --source github --category awesome_lists --limit 20` | 92 hasil unik / 5 query |
| `run --source github --category proxies --limit 12` | 35 hasil unik / 4 query |
| `run --source github --source hf --category models --model qwen` | 32 hasil unik / 2 domain |
| `run --source hf --category datasets --topic "medical imaging"` | 8 dataset, lengkap dengan lisensi |
| `run --source archive --url <url>` | 1 snapshot ditemukan |

Kesimpulan PoC: **search engine HTML = jalan buntu dari server** (3 engine, semua
gagal dengan `200`/`202` palsu), sementara **structured API = hasil nyata** dengan
latensi wajar dan tanpa captcha.
