#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dorker.py — Discovery engine untuk resource AI publik.

Dua mode:
  1. gen  -> cetak dork siap tempel ke Google/Bing (klasik)
  2. run  -> jalankan discovery lewat API yang andal dari server

Sumber (source):
  github   GitHub repo search (butuh GITHUB_TOKEN atau gh CLI)   <- paling produktif
  hf       HuggingFace Hub API (datasets & models, tanpa key)
  archive  Internet Archive CDX (pola URL / arsip, tanpa key)
  brave    Brave Search API (butuh BRAVE_API_KEY)
  google   Google Programmable Search (butuh GOOGLE_API_KEY + GOOGLE_CSE_ID)
  ddg      DuckDuckGo HTML (best-effort; sering captcha dari IP datacenter)

Fokus resource yang MEMANG publik & gratis:
  free tier resmi, gateway OpenAI-compatible terdokumentasi, dataset terbuka,
  mirror bobot model, list proxy publik, awesome-list.

Contoh:
  ./dorker.py categories
  ./dorker.py gen  --source google --category free_providers
  ./dorker.py gen  --source github --all
  ./dorker.py run  --source github --category awesome_lists --limit 30
  ./dorker.py run  --source hf --category datasets --topic "medical imaging"
  ./dorker.py run  --source github --source hf --category models --model qwen
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Butuh 'requests': pip install requests")

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "out"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36")


# ---------------------------------------------------------------------------
# Katalog kategori: query per sumber
# ---------------------------------------------------------------------------
CATEGORIES: dict[str, dict] = {
    "free_providers": {
        "label": "Free tier / free credit provider AI resmi",
        "vars": [],
        "dorks": [
            '"free API" "OpenAI compatible" "no credit card" llm',
            '"free tier" "chat completions" api llm -site:github.com',
            'intitle:"free api" deepseek "api key"',
            '"free credits" "api key" llm provider signup',
            '"no credit card required" api llm free',
            '"free forever" api llm inference',
            'site:openrouter.ai free models',
            '"free plan" "api key" "chat completions"',
            '"trial credits" llm api free signup',
        ],
        "github": [
            '"free api" llm in:description,readme stars:>50',
            '"free tier" llm api in:readme stars:>30',
            '"no credit card" llm api in:readme',
            'free-llm-api in:name,description',
            'llm-api-list free in:description',
            '"free credits" llm in:readme',
        ],
        "hf": ["free api"],
        "archive": [],
    },
    "openai_compatible": {
        "label": "Gateway OpenAI-compatible terdokumentasi publik",
        "vars": [],
        "dorks": [
            '"OpenAI compatible" "base URL" gateway free tier',
            '"base_url" "/v1" "openai-compatible" documentation',
            '"drop-in replacement" "OpenAI API" gateway',
            'intitle:"API reference" "chat/completions" free tier',
            '"compatible with the OpenAI API" free inference',
            '"api base" openai gateway self-hosted docs',
        ],
        "github": [
            '"openai-compatible" gateway in:description',
            '"openai compatible" proxy in:description stars:>100',
            '"drop-in replacement" openai in:description stars:>100',
            '"openai compatible endpoint" in:readme',
            'llm-gateway openai-compatible in:name,description',
        ],
        "hf": [],
        "archive": [],
    },
    "datasets": {
        "label": "Dataset AI terbuka",
        "vars": ["topic"],
        "dorks": [
            'site:huggingface.co/datasets {topic}',
            'site:kaggle.com/datasets {topic}',
            'site:zenodo.org {topic} dataset',
            'site:data.gov {topic}',
            'filetype:parquet {topic} dataset',
            'filetype:jsonl {topic} dataset',
            '"{topic}" dataset "CC-BY" OR "MIT" download',
            'site:github.com {topic} dataset release',
        ],
        "github": [
            '{topic} dataset in:name,description stars:>20',
            '{topic} dataset license:mit in:readme',
        ],
        "hf": ["{topic}"],
        "archive": [],
    },
    "models": {
        "label": "Bobot model & mirror publik",
        "vars": ["model"],
        "dorks": [
            'site:huggingface.co {model} gguf',
            'site:huggingface.co {model} safetensors',
            '"{model}" gguf mirror download',
            '"{model}" quantized release github',
            '"{model}" "apache-2.0" OR "mit" weights',
        ],
        "github": [
            '{model} gguf in:name,description',
            '{model} quantized in:readme',
            '{model} weights release in:description',
        ],
        "hf": ["{model}"],
        "archive": [],
    },
    "proxies": {
        "label": "Sumber list proxy publik",
        "vars": [],
        "dorks": [
            'site:raw.githubusercontent.com "socks5://" proxy list',
            '"free proxy list" "socks5" api json',
            'filetype:txt "socks5://" "http://" proxy list',
            '"proxy list" "updated every" github raw',
            '"free proxy" api endpoint json no key',
        ],
        "github": [
            'proxy-list in:name stars:>200',
            'free-proxy in:name,description stars:>100',
            'proxy-scraper checker in:description stars:>50',
            '"socks5" proxy list in:readme stars:>100',
        ],
        "hf": [],
        # archive = snapshot verifier (pakai --url), bukan discovery
        "archive": [],
    },
    "awesome_lists": {
        "label": "Kurasi / awesome-list API AI gratis",
        "vars": [],
        "dorks": [
            'site:github.com "awesome" free llm api list',
            'site:github.com awesome-llm OR awesome-ai free api',
            '"curated list" free AI API github',
            '"list of free" LLM API providers github',
            '"free ai apis" list 2026',
        ],
        "github": [
            'awesome llm in:name stars:>500',
            'awesome ai api in:name,description',
            'awesome free api in:name,description',
            'awesome-llm-api in:name',
            'free llm list in:readme stars:>100',
        ],
        "hf": [],
        "archive": [],
    },
    "self_audit": {
        "label": "Audit eksposur domain sendiri (butuh --domain)",
        "vars": ["domain"],
        "dorks": [
            'site:{domain} filetype:env',
            'site:{domain} intitle:"index of"',
            'site:{domain} ext:sql OR ext:bak OR ext:log',
            'site:{domain} inurl:admin OR inurl:dashboard',
            'site:{domain} "api_key" OR "apikey" OR "secret"',
            'site:{domain} inurl:"/.git"',
        ],
        "github": ['{domain} in:readme'],
        "hf": [],
        "archive": [],
    },
}

DORK_SOURCES = ("google", "github", "hf", "archive")
RUN_SOURCES = ("github", "hf", "archive", "brave", "google", "ddg")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass
class Hit:
    category: str
    source: str
    query: str
    title: str
    url: str
    snippet: str = ""
    extra: str = ""
    domain: str = ""

    def __post_init__(self):
        if not self.domain and self.url:
            try:
                self.domain = urllib.parse.urlsplit(self.url).netloc.lower()
            except Exception:
                self.domain = ""


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------
def build_queries(category: str, source: str, variables: dict | None = None) -> list[str]:
    spec = CATEGORIES.get(category)
    if not spec:
        raise KeyError(f"Kategori tidak dikenal: {category}")

    key = "dorks" if source in ("brave", "google", "ddg") else source
    raw = spec.get(key) or []
    if not raw:
        return []

    variables = variables or {}
    missing = [v for v in spec.get("vars", []) if not variables.get(v)]
    if missing:
        raise ValueError(
            f"Kategori '{category}' butuh: " + ", ".join("--" + m for m in missing)
        )

    out = []
    for tpl in raw:
        q = tpl
        for k, v in variables.items():
            q = q.replace("{" + k + "}", v)
        out.append(q.strip())
    return out


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def get(url: str, *, params=None, headers=None, timeout=25, proxy=None):
    h = {"User-Agent": UA, "Accept": "application/json, text/html;q=0.9,*/*;q=0.8"}
    if headers:
        h.update(headers)
    proxies = {"http": proxy, "https": proxy} if proxy else None

    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=h, timeout=timeout, proxies=proxies)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 502, 503):
                wait = 5 * (attempt + 1)
                print(f"    [{r.status_code}] tunggu {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"    [HTTP {r.status_code}] {url[:70]}", file=sys.stderr)
            return r
        except requests.RequestException as e:
            print(f"    [{type(e).__name__}] {str(e)[:70]}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# Source: GitHub
# ---------------------------------------------------------------------------
def github_token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    for p in (Path.home() / ".config" / "gh" / "hosts.yml",
              Path.home() / "AppData" / "Roaming" / "GitHub CLI" / "hosts.yml"):
        if p.exists():
            m = re.search(r"oauth_token:\s*(\S+)",
                          p.read_text(encoding="utf-8", errors="ignore"))
            if m:
                return m.group(1)
    return ""


def search_github(query: str, limit: int = 30, **_kw) -> list[Hit]:
    tok = github_token()
    headers = {"Accept": "application/vnd.github+json"}
    if tok:
        headers["Authorization"] = f"token {tok}"
    else:
        print("    [!] tanpa token GitHub - rate limit 10/menit", file=sys.stderr)

    r = get("https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc",
                    "per_page": min(limit, 50)},
            headers=headers)
    if r is None or r.status_code != 200:
        return []

    hits = []
    for it in r.json().get("items", []):
        hits.append(Hit(
            category="", source="github", query=query,
            title=it.get("full_name", ""),
            url=it.get("html_url", ""),
            snippet=(it.get("description") or "")[:300],
            extra=(f"star {it.get('stargazers_count', 0)} | "
                   f"{it.get('language') or '-'} | "
                   f"upd {str(it.get('pushed_at', ''))[:10]}"),
        ))
    return hits


# ---------------------------------------------------------------------------
# Source: HuggingFace
# ---------------------------------------------------------------------------
def search_hf(query: str, limit: int = 30, hf_type: str = "datasets", **_kw) -> list[Hit]:
    kind = "datasets" if hf_type == "datasets" else "models"
    r = get(f"https://huggingface.co/api/{kind}",
            params={"search": query, "limit": min(limit, 50),
                    "sort": "downloads", "direction": "-1"})
    if r is None or r.status_code != 200:
        return []

    hits = []
    for it in r.json():
        rid = it.get("id", "")
        tags = ", ".join([t for t in (it.get("tags") or [])
                          if not t.startswith("region:")][:5])
        hits.append(Hit(
            category="", source="hf", query=query,
            title=rid, url=f"https://huggingface.co/{kind}/{rid}",
            snippet=tags or (it.get("pipeline_tag") or ""),
            extra=f"dl {it.get('downloads', 0)} | like {it.get('likes', 0)}",
        ))
    return hits


# ---------------------------------------------------------------------------
# Source: Internet Archive CDX
# ---------------------------------------------------------------------------
def search_archive(query: str, limit: int = 30, **_kw) -> list[Hit]:
    """Snapshot verifier: cek arsip Wayback untuk URL spesifik.

    Wildcard luas (`domain/*`) membuat CDX timeout/503, jadi mode default
    adalah exact match. Prefix hanya dipakai kalau query diakhiri '/'.
    """
    params = {"url": query, "output": "json", "limit": min(limit, 100),
              "collapse": "urlkey", "fl": "original,timestamp,mimetype"}
    if query.endswith("/"):
        params["matchType"] = "prefix"

    r = get("https://web.archive.org/cdx/search/cdx", params=params, timeout=45)
    if r is None or r.status_code != 200:
        return []

    try:
        rows = r.json()
    except Exception:
        return []
    if not rows or len(rows) < 2:
        return []

    hits = []
    for row in rows[1:]:
        if len(row) < 3:
            continue
        original, ts, mime = row[0], row[1], row[2]
        hits.append(Hit(
            category="", source="archive", query=query,
            title=original, url=original,
            snippet=f"archived {ts[:8]} | {mime}",
            extra=ts[:8],
        ))
    return hits


# ---------------------------------------------------------------------------
# Source: Brave / Google / DDG
# ---------------------------------------------------------------------------
def search_brave(query: str, limit: int = 20, proxy=None, **_kw) -> list[Hit]:
    key = os.environ.get("BRAVE_API_KEY", "")
    if not key:
        print("    [!] BRAVE_API_KEY kosong", file=sys.stderr)
        return []
    r = get("https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(limit, 20)},
            headers={"Accept": "application/json", "X-Subscription-Token": key},
            proxy=proxy)
    if r is None or r.status_code != 200:
        return []
    return [Hit(category="", source="brave", query=query,
                title=it.get("title", ""), url=it.get("url", ""),
                snippet=(it.get("description") or "")[:300])
            for it in r.json().get("web", {}).get("results", [])]


def search_google(query: str, limit: int = 10, proxy=None, **_kw) -> list[Hit]:
    key = os.environ.get("GOOGLE_API_KEY", "")
    cx = os.environ.get("GOOGLE_CSE_ID", "")
    if not key or not cx:
        print("    [!] GOOGLE_API_KEY / GOOGLE_CSE_ID kosong", file=sys.stderr)
        return []
    r = get("https://www.googleapis.com/customsearch/v1",
            params={"key": key, "cx": cx, "q": query, "num": min(limit, 10)},
            proxy=proxy)
    if r is None or r.status_code != 200:
        return []
    return [Hit(category="", source="google", query=query,
                title=it.get("title", ""), url=it.get("link", ""),
                snippet=(it.get("snippet") or "")[:300])
            for it in r.json().get("items", [])]


DDG_REDIRECT = re.compile(r"uddg=([^&]+)")


def search_ddg(query: str, limit: int = 20, proxy=None, **_kw) -> list[Hit]:
    r = get("https://html.duckduckgo.com/html/",
            params={"q": query, "kl": "us-en"}, proxy=proxy, timeout=30)
    if r is None or r.status_code != 200:
        return []
    if "result__a" not in r.text:
        print("    [!] DDG: challenge/captcha - pakai sumber github/hf atau --proxy residensial",
              file=sys.stderr)
        return []

    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                         r.text, re.S):
        href = m.group(1).replace("&amp;", "&")
        u = DDG_REDIRECT.search(href)
        url = urllib.parse.unquote(u.group(1)) if u else (
            "https:" + href if href.startswith("//") else href)
        if not url.startswith("http"):
            continue
        out.append(Hit(category="", source="ddg", query=query,
                       title=re.sub(r"<[^>]+>", "", m.group(2)).strip(), url=url))
        if len(out) >= limit:
            break
    return out


SOURCES = {
    "github": search_github,
    "hf": search_hf,
    "archive": search_archive,
    "brave": search_brave,
    "google": search_google,
    "ddg": search_ddg,
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_source(source: str, queries: list[str], *, limit: int, delay: float,
               proxy: str | None, hf_type: str) -> list[Hit]:
    fn = SOURCES[source]
    hits: list[Hit] = []
    seen: set[str] = set()

    for i, q in enumerate(queries, 1):
        print(f"\n[{i}/{len(queries)}] ({source}) {q}")
        raw = fn(q, limit=limit, proxy=proxy, hf_type=hf_type)

        new = 0
        for h in raw:
            key = h.url.rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            hits.append(h)
            new += 1
        print(f"    {len(raw)} hasil, {new} baru")
        time.sleep(delay)

    return hits


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def export(hits: list[Hit], tag: str) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = OUT_DIR / f"{tag}_{time.strftime('%Y%m%d_%H%M%S')}"
    fields = ["category", "source", "query", "title", "url", "snippet", "extra", "domain"]

    p_jsonl = base.with_suffix(".jsonl")
    with p_jsonl.open("w", encoding="utf-8") as f:
        for h in hits:
            f.write(json.dumps(asdict(h), ensure_ascii=False) + "\n")

    p_csv = base.with_suffix(".csv")
    with p_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for h in hits:
            w.writerow(asdict(h))

    by_dom: dict[str, int] = {}
    for h in hits:
        by_dom[h.domain] = by_dom.get(h.domain, 0) + 1
    top = sorted(by_dom.items(), key=lambda kv: -kv[1])[:30]

    p_md = base.with_suffix(".md")
    with p_md.open("w", encoding="utf-8") as f:
        f.write(f"# Dork Report - {tag}\n\n")
        f.write(f"- Hasil unik: **{len(hits)}**\n")
        f.write(f"- Domain unik: **{len(by_dom)}**\n")
        f.write(f"- Sumber: {', '.join(sorted({h.source for h in hits}))}\n")
        f.write(f"- Waktu: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Domain teratas\n\n| Domain | Hit |\n|---|---|\n")
        for d, c in top:
            f.write(f"| {d} | {c} |\n")
        f.write("\n## Hasil\n")
        cur = None
        for h in hits:
            if h.category != cur:
                cur = h.category
                f.write(f"\n### {cur}\n\n")
            f.write(f"- [{h.title or h.url}]({h.url})")
            if h.extra:
                f.write(f" - `{h.extra}`")
            f.write(f"  \n  _{h.source}_ | `{h.query}`\n")
            if h.snippet:
                f.write(f"  > {h.snippet[:220]}\n")

    return {"jsonl": p_jsonl, "csv": p_csv, "md": p_md}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_categories(_a):
    print(f"\n{'Kategori':<20} {'Var':<8} {'google':>7} {'github':>7} {'hf':>5} {'arch':>5}  Deskripsi")
    print("-" * 100)
    for n, s in CATEGORIES.items():
        v = ",".join(s.get("vars", [])) or "-"
        print(f"{n:<20} {v:<8} {len(s.get('dorks', [])):>7} {len(s.get('github', [])):>7} "
              f"{len(s.get('hf', [])):>5} {len(s.get('archive', [])):>5}  {s['label']}")
    print()


def _vars(a) -> dict:
    return {k: getattr(a, k) for k in ("topic", "model", "domain")
            if getattr(a, k, None)}


def cmd_gen(a):
    cats = list(CATEGORIES) if a.all else [a.category]
    sources = a.source or ["google"]
    total = 0
    for src in sources:
        print(f"\n{'=' * 78}\n  SUMBER: {src}\n{'=' * 78}")
        for c in cats:
            try:
                qs = build_queries(c, src, _vars(a))
            except (KeyError, ValueError) as e:
                print(f"[!] {e}", file=sys.stderr)
                continue
            if not qs:
                continue
            print(f"\n### {c} - {CATEGORIES[c]['label']}\n")
            for q in qs:
                print(q)
                total += 1
    print(f"\n# total {total} query\n")


def cmd_run(a):
    cats = list(CATEGORIES) if a.all else [a.category]
    proxy = a.proxy or os.environ.get("DORKER_PROXY")
    all_hits: list[Hit] = []

    for src in a.source:
        for c in cats:
            try:
                qs = build_queries(c, src, _vars(a))
            except (KeyError, ValueError) as e:
                print(f"[!] {e}", file=sys.stderr)
                continue

            # archive = snapshot verifier: butuh --url, bukan query template
            if src == "archive":
                if not getattr(a, "url", None):
                    print(f"[i] archive butuh --url <url>; kategori '{c}' dilewati",
                          file=sys.stderr)
                    continue
                qs = [a.url]

            if not qs:
                continue

            print(f"\n{'=' * 78}\n  {src} :: {c} - {CATEGORIES[c]['label']} "
                  f"({len(qs)} query)\n{'=' * 78}")
            hits = run_source(src, qs, limit=a.limit or 30, delay=a.delay,
                              proxy=proxy, hf_type=a.hf_type)
            for h in hits:
                h.category = c
            all_hits.extend(hits)

    if not all_hits:
        print("\n[!] Tidak ada hasil.\n")
        return

    tag = "all" if a.all else a.category
    paths = export(all_hits, tag)
    print(f"\n{'=' * 78}")
    print(f"  {len(all_hits)} hasil unik dari {len({h.domain for h in all_hits})} domain")
    print(f"  jsonl : {paths['jsonl']}")
    print(f"  csv   : {paths['csv']}")
    print(f"  report: {paths['md']}")
    print(f"{'=' * 78}\n")


def main():
    ap = argparse.ArgumentParser(
        description="Discovery engine untuk resource AI publik",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("Sumber: github (token), hf (no key), archive (no key), "
                "brave/google (butuh key), ddg (sering captcha)."),
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("categories", help="daftar kategori").set_defaults(func=cmd_categories)

    g = sub.add_parser("gen", help="cetak dork saja (tanpa request)")
    g.add_argument("--category", default="free_providers")
    g.add_argument("--all", action="store_true")
    g.add_argument("--source", action="append", choices=DORK_SOURCES,
                   help="ulangi untuk beberapa sumber (default: google)")
    g.add_argument("--topic")
    g.add_argument("--model")
    g.add_argument("--domain")
    g.set_defaults(func=cmd_gen)

    r = sub.add_parser("run", help="jalankan discovery")
    r.add_argument("--category", default="free_providers")
    r.add_argument("--all", action="store_true")
    r.add_argument("--source", action="append", choices=RUN_SOURCES, required=True,
                   help="ulangi untuk beberapa sumber")
    r.add_argument("--topic")
    r.add_argument("--model")
    r.add_argument("--domain")
    r.add_argument("--hf-type", default="datasets", choices=["datasets", "models"])
    r.add_argument("--limit", type=int, default=30, help="hasil per query (default 30)")
    r.add_argument("--delay", type=float, default=2.0, help="jeda antar query (detik)")
    r.add_argument("--proxy", help="proxy http://user:pass@host:port (untuk ddg)")
    r.add_argument("--url", help="URL spesifik untuk --source archive (snapshot lookup)")
    r.set_defaults(func=cmd_run)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
