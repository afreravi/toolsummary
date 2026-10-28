#!/usr/bin/env python3
"""Stage 2: turn data/pricing.json into static pages.

Every page carries data no model can reconstruct from a prompt: a live price,
a computed multiple, a rank, and a refresh timestamp. That is the
"information gain" that keeps this out of scaled-content-abuse territory.

Usage: python3 build_pages.py [--limit N]
"""
import argparse
import html
import json
import os
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SITE = ROOT / "site"
THEME = ROOT / "theme"
BLOG = ROOT / "blog"
BASE = "https://toolsummary.com"

# Public by design: Web3Forms access keys are meant to be embedded in page
# HTML. The key can only send mail to the address that created it, never read
# anything. Override with the environment when rotating the key.
WEB3FORMS_KEY = os.environ.get("WEB3FORMS_ACCESS_KEY",
                               "46cb8c21-0977-46d3-b0fa-2edc9d9bbf6d")
CONTACT_EMAIL = "info.toolsummary@gmail.com"

# Only models a buyer would actually evaluate. Excludes the long tail of
# fine-tunes, embeddings-only rows and obviously mispriced harness entries.
MIN_CONTEXT = 4_000
MAX_SANE_INPUT = 1_000.0  # USD / 1M tokens; above this it's a data artefact


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def money(v: float) -> str:
    if v == 0:
        return "Free"
    if v < 0.01:
        return f"${v:.4f}"
    if v < 1:
        return f"${v:.3f}"
    if v < 100:
        return f"${v:,.2f}"
    return f"${v:,.0f}"


def blazerow(cells: list[str]) -> str:
    return "".join(f"<td>{c}</td>" for c in cells)


def pct(v: float | None) -> str:
    if v is None:
        return "&mdash;"
    return f"{v:+.1f}%"


def vendor_label(v: str) -> str:
    """Vendors from aggregator feeds carry a leading '~' as a source marker.

    It is not part of the provider's name, so it is stripped before display
    rather than shown to a reader as '~deepseek'.
    """
    return v.lstrip("~") or v


# A percentage against a near-zero baseline is arithmetic, not information:
# $0.0001 -> $0.034 is "+33500%" and means nothing. Moves are only ranked as
# percentages when the starting price is a real, chargeable amount.
MIN_PCT_BASE = 0.001


# --------------------------------------------------------------- site chrome
# The masthead, ticker and footer are the same on every page. They take a
# small amount of live data so the ticker shows real numbers rather than
# decorative ones.

NAV = [
    ("models", "/", "Models"),
    ("compare", "/compare/", "Compare"),
    ("trending", "/trending/", "Trending"),
    ("blog", "/blog/", "Blog"),
]

# Populated once in main() so every page renders the same live ticker without
# each builder having to pass the dataset around.
CHROME: dict = {}


def _nav_html(active: str) -> str:
    out = []
    for key, href, label in NAV:
        cur = ' aria-current="page"' if key == active else ""
        out.append(f'<a href="{href}"{cur}>{label}</a>')
    cur = ' aria-current="page"' if active == "submit" else ""
    out.append(f'<a href="/submit/" class="nav__cta"{cur}>Submit a model</a>')
    return "".join(out)


def ticker_html(models: list[dict], recent: dict | None) -> str:
    """The market strip under the masthead.

    Falls back gracefully: if there is no change log yet, the movement cells
    are simply omitted rather than showing a placeholder.
    """
    if not models:
        return ""
    cheapest = models[0]
    median = models[len(models) // 2]
    cells = [
        ("Models tracked", f"{len(models):,}"),
        ("Cheapest input", money(cheapest["input_per_1m_usd"])),
        ("Median input / 1M", money(median["input_per_1m_usd"])),
    ]

    events = [e for e in (recent or {}).get("events", [])
              if e.get("kind") == "price"
              and e.get("pct_change") is not None
              and (e.get("from") or 0) >= MIN_PCT_BASE]
    downs = [e for e in events if e["pct_change"] < 0]
    ups = [e for e in events if e["pct_change"] > 0]
    if downs:
        e = min(downs, key=lambda x: x["pct_change"])
        cells.append(("Biggest fall", f'{html.escape(e["display_name"])} '
                                    f'<span class="d d--down">\u25bc {abs(e["pct_change"]):.1f}%</span>'))
    if ups:
        e = max(ups, key=lambda x: x["pct_change"])
        cells.append(("Biggest rise", f'{html.escape(e["display_name"])} '
                                     f'<span class="d d--up">\u25b2 {e["pct_change"]:.1f}%</span>'))
    stamp = (recent or {}).get("as_of") or ""
    if stamp:
        cells.append(("Updated", stamp[:10]))

    inner = "".join(
        f'<div class="ticker__cell"><span class="ticker__label">{lbl}</span>'
        f'<span class="ticker__value">{val}</span></div>'
        for lbl, val in cells
    )
    return (f'<div class="ticker" aria-label="Latest price movement">'
            f'<div class="wrap ticker__row">{inner}</div></div>')


def header_html(active: str) -> str:
    return f"""<a class="visually-hidden" href="#main">Skip to content</a>
<header class="masthead">
  <div class="wrap masthead__bar">
    <a class="brand" href="/">
      <span class="brand__mark">Tool<em>summary</em></span>
      <span class="brand__tag">LLM price ledger</span>
    </a>
    <button class="nav__toggle" type="button" aria-expanded="false" aria-controls="site-nav">Menu</button>
    <nav class="nav" id="site-nav" aria-label="Primary">{_nav_html(active)}</nav>
  </div>
</header>"""


def footer_html() -> str:
    return f"""<footer class="footer">
  <div class="wrap">
    <div class="footer__grid">
      <div class="footer__brand-col">
        <div class="footer__brand">Tool<em>summary</em></div>
        <p class="footer__blurb">Live LLM API pricing, recorded daily. Free to read,
          built for people who have to justify a token budget.</p>
      </div>
      <div>
        <p class="footer__h">Data</p>
        <ul>
          <li><a href="/">All models</a></li>
          <li><a href="/compare/">Comparisons</a></li>
          <li><a href="/trending/">Trending</a></li>
          <li><a href="/api/prices.json">JSON API</a></li>
        </ul>
      </div>
      <div>
        <p class="footer__h">Learn</p>
        <ul>
          <li><a href="/blog/">Blog</a></li>
          <li><a href="/blog/feed.xml">RSS</a></li>
          <li><a href="/about/">About &amp; method</a></li>
          <li><a href="/llms.txt">llms.txt</a></li>
        </ul>
      </div>
      <div>
        <p class="footer__h">Site</p>
        <ul>
          <li><a href="/submit/">Submit a model</a></li>
          <li><a href="/contact/">Contact</a></li>
          <li><a href="/privacy/">Privacy</a></li>
          <li><a href="/sitemap.xml">Sitemap</a></li>
        </ul>
      </div>
    </div>
    <div class="footer__bottom">
      <span>&copy; <span data-since>2022</span>&ndash;<span data-year>{date.today().year}</span> Toolsummary &middot; Prices from public provider APIs</span>
      <span>Always confirm on the provider's own pricing page before committing budget.</span>
    </div>
  </div>
</footer>"""


def crumbs(items: list[tuple[str, str]]) -> str:
    """items: (label, href). The last entry is rendered as plain text."""
    parts = []
    for i, (label, href) in enumerate(items):
        if i:
            parts.append("<span>/</span>")
        if href and i < len(items) - 1:
            parts.append(f'<a href="{href}">{html.escape(label)}</a>')
        else:
            parts.append(html.escape(label))
    return f'<nav class="crumbs" aria-label="Breadcrumb">{"".join(parts)}</nav>'


def page(title: str, desc: str, canonical: str, body: str, ld: dict,
         active: str = "", extra_head: str = "", wrap: bool = True,
         chrome_data: dict | None = None) -> str:
    """Render a full page.

    The ticker data is set once per build in CHROME, so individual builders do
    not have to thread it through every call.
    """
    data = chrome_data if chrome_data is not None else CHROME
    inner = f'<div class="wrap">{body}</div>' if wrap else body
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{canonical}">
<meta name="theme-color" content="#17130f">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:type" content="website">
<link rel="alternate" type="application/rss+xml" title="Toolsummary blog" href="{BASE}/blog/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/css/theme.css">
<script type="application/ld+json">{json.dumps(ld)}</script>{extra_head}
</head>
<body>
{header_html(active)}
{ticker_html(data.get("models", []), data.get("recent"))}
<main id="main">
{inner}
</main>
{footer_html()}
<script src="/assets/js/theme.js" defer></script>
</body>
</html>
"""


def write(rel: str, content: str) -> None:
    p = SITE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def copy_assets() -> None:
    """Publish the theme CSS/JS into the site so the tarball carries them."""
    for name in ("theme.css", "theme.js"):
        src = THEME / name
        if src.exists():
            dst = SITE / "assets" / ("css" if name.endswith(".css") else "js") / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)


def load() -> dict:
    return json.loads((DATA / "pricing.json").read_text())


def eligible(models: list[dict]) -> list[dict]:
    out = []
    for m in models:
        if not m.get("context_length") or m["context_length"] < MIN_CONTEXT:
            continue
        # `is None`, not falsy: a $0.00 model is a real, valuable page.
        if m.get("input_per_1m_usd") is None:
            continue
        if m["input_per_1m_usd"] > MAX_SANE_INPUT:
            continue
        m.setdefault("display_name", m["id"])
        out.append(m)
    return out


def name_of(m: dict) -> str:
    return m.get("display_name") or m["id"]


def blended(m: dict) -> float:
    """3:1 input:output blend - the metric the pages themselves quote."""
    return (m["input_per_1m_usd"] * 3 + m["output_per_1m_usd"]) / 4


def cheapest_in_class(models: list[dict], anchor: dict) -> dict | None:
    """Nearest genuinely-cheaper model, ranked on the same blend the page shows.

    Comparing on input OR output price admits models that are cheaper on one
    axis and far pricier on the other, which surfaces as nonsense like
    'next cheaper option: $18.80' beneath a $5.00 model.
    """
    target = blended(anchor)
    ans = [m for m in models if blended(m) < target]
    if not ans:
        return None
    return max(ans, key=blended)


def costlier_in_class(models: list[dict], anchor: dict) -> dict | None:
    target = blended(anchor)
    ans = [m for m in models if blended(m) > target]
    if not ans:
        return None
    return min(ans, key=blended)


# ---------------------------------------------------------------- model pages

def build_model_pages(models: list[dict], stamp: str, cindex: dict[str, str]) -> list[str]:
    urls = []
    for i, m in enumerate(models):
        s = slug(m["id"])
        cheaper = cheapest_in_class(models, m)
        costlier = costlier_in_class(models, m)
        blended = (m["input_per_1m_usd"] * 3 + m["output_per_1m_usd"]) / 4
        rank = i + 1
        mult = (f"{m["output_per_1m_usd"] / m["input_per_1m_usd"]:.2f}&times;"
                if m["input_per_1m_usd"] else "n/a (free tier)")

        if m["input_per_1m_usd"] == 0 and m["output_per_1m_usd"] == 0:
            verdict = (f"{html.escape(m['display_name'])} is published at $0.00 per million "
                       f"input and output tokens &mdash; it is a free-tier model. "
                       f"Free tiers normally carry rate limits and are not intended for "
                       f"production traffic, so confirm the current terms before relying on it.")
        else:
            verdict = (f"{html.escape(m['display_name'])} costs "
                       f"<strong>{money(m['input_per_1m_usd'])} per million input tokens</strong> and "
                       f"<strong>{money(m['output_per_1m_usd'])} per million output tokens</strong>. "
                       f"That is a 3:1 blended rate of <strong>{money(round(blended, 4))} per million tokens</strong>, "
                       f"ranking it <strong>#{rank} of {len(models)}</strong> tracked models by input price.")

        peers = [
            p for p in models
            if p["vendor"] == m["vendor"] and p["id"] != m["id"]
        ][:5]
        peer_rows = "".join(
            f'<tr><td><a href="/model/{slug(p["id"])}/">{html.escape(p["display_name"])}</a></td>'
            f'<td class="num">{money(p["input_per_1m_usd"])}</td>'
            f'<td class="num">{money(p["output_per_1m_usd"])}</td></tr>'
            for p in peers
        )

        cmp_links = []
        for p in models[i + 1:i + 6] + models[max(0, i - 3):i]:
            if p["id"] == m["id"]:
                continue
            route = cindex.get(f"{m['id']}|{p['id']}") or cindex.get(f"{p['id']}|{m['id']}")
            if route:
                cmp_links.append(
                    f'<li><a href="{route}">{html.escape(m["display_name"])} vs '
                    f'{html.escape(p["display_name"])}</a></li>'
                )
            if len(cmp_links) >= 5:
                break
        cmp_html = ("<h2>Compare against</h2><ul>" + "".join(cmp_links) + "</ul>"
                    if cmp_links else "")

        body = f"""
{crumbs([("Home", "/"), ("Models", "/"), (m["vendor"], None), (m["display_name"] + " pricing", None)])}
<div class="hero reveal">
  <h1>{html.escape(m["display_name"])} pricing</h1>
  <p class="stamp">Source: {html.escape(m["source"])} &middot; updated {stamp[:10]}</p>
</div>

<div class="answer reveal reveal-2">
<strong>Short answer:</strong> {verdict}
</div>

<div class="stats reveal reveal-3">
  <div class="stat"><span class="stat__label">Input / 1M</span><div class="stat__value">{money(m["input_per_1m_usd"])}</div></div>
  <div class="stat"><span class="stat__label">Output / 1M</span><div class="stat__value">{money(m["output_per_1m_usd"])}</div></div>
  <div class="stat"><span class="stat__label">Output &divide; input</span><div class="stat__value">{mult}</div></div>
  <div class="stat"><span class="stat__label">Context window</span><div class="stat__value">{m["context_length"]:,}</div></div>
</div>

<h2>Price breakdown</h2>
<div class="ledger-wrap">
<table class="ledger">
<thead><tr><th>Metric</th><th class="num">USD</th></tr></thead>
<tbody>
<tr><td>Input, per 1M tokens</td><td class="num">{money(m["input_per_1m_usd"])}</td></tr>
<tr><td>Output, per 1M tokens</td><td class="num">{money(m["output_per_1m_usd"])}</td></tr>
<tr><td>Output &divide; input multiple</td><td class="num">{mult}</td></tr>
<tr><td>3:1 blended, per 1M tokens</td><td class="num">{money(round(blended, 4))}</td></tr>
<tr><td>Context window</td><td class="num">{m["context_length"]:,} tokens</td></tr>
<tr><td>Vendor</td><td class="num">{html.escape(vendor_label(m["vendor"]))}</td></tr>
</tbody>
</table>
</div>

<h2>What a typical workload costs</h2>
<div class="ledger-wrap">
<table class="ledger">
<thead><tr><th>Monthly volume</th><th class="num">Input cost</th><th class="num">Output cost</th><th class="num">Total</th></tr></thead>
<tbody>{"".join(
    f'<tr><td>{v}</td><td class="num">{money(m["input_per_1m_usd"] * n / 1e6)}</td>'
    f'<td class="num">{money(m["output_per_1m_usd"] * n / 4 / 1e6)}</td>'
    f'<td class="num">{money((m["input_per_1m_usd"] * n + m["output_per_1m_usd"] * n / 4) / 1e6)}</td></tr>'
    for n, v in [(1_000_000, "1M in / 250K out"), (10_000_000, "10M in / 2.5M out"), (100_000_000, "100M in / 25M out")]
)}</tbody>
</table>
</div>
{"<h2>Other " + html.escape(m['vendor']) + " models</h2><div class='ledger-wrap'><table class='ledger'><thead><tr><th>Model</th><th class='num'>Input</th><th class='num'>Output</th></tr></thead><tbody>" + peer_rows + "</tbody></table></div>" if peer_rows else ""}

{cmp_html}

<h2>Cheaper alternatives</h2>
<p>{"Next cheaper option: <a href='/model/" + slug(cheaper["id"]) + "/'>" + html.escape(cheaper["display_name"]) + "</a> at " + money(cheaper["input_per_1m_usd"]) + " per 1M input tokens." if cheaper else "This is the cheapest tracked model in its class."}
{"Next step up: <a href='/model/" + slug(costlier["id"]) + "/'>" + html.escape(costlier["display_name"]) + "</a> at " + money(costlier["input_per_1m_usd"]) + " per 1M input tokens." if costlier else ""}</p>

<hr class="rule">
<p class="stamp">Spotted a price that is out of date?
  <a href="/submit/?model={html.escape(m["display_name"])}">Submit a correction</a>.</p>
"""
        ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": f"{m['display_name']} pricing",
            "description": f"{m['display_name']} costs {money(m['input_per_1m_usd'])} per 1M input tokens and {money(m['output_per_1m_usd'])} per 1M output tokens.",
            "dateModified": stamp,
            "url": f"{BASE}/model/{s}/",
            "isPartOf": {"@type": "Dataset", "name": "LLM API pricing dataset"},
        }
        write(f"model/{s}/index.html", page(
            f"{m['display_name']} Pricing ({money(m['input_per_1m_usd'])}/1M in) - Updated {stamp[:10]}",
            f"{m['display_name']} API cost: {money(m['input_per_1m_usd'])} per 1M input tokens, {money(m['output_per_1m_usd'])} per 1M output tokens. Live pricing, cost examples and cheaper alternatives.",
            f"{BASE}/model/{s}/", body, ld, active="models"))
        urls.append(f"/model/{s}/")
    return urls


# ------------------------------------------------------------ compare pages

def build_compare_pages(models: list[dict], stamp: str, limit: int = 400) -> list[str]:
    """Build head-to-head pages, returning the set of routes actually created.

    Links are emitted only for pairs in this set, otherwise generated pages
    point at comparison routes that were never written (a 404 farm).
    """
    urls = []
    n = len(models)
    pairs = []
    # Adjacent-in-price and same-vendor neighbours are the real buying decisions.
    for i in range(n - 1):
        pairs.append((i, i + 1))
    for i, m in enumerate(models):
        for j in range(i + 1, min(i + 4, n)):
            if models[j]["vendor"] == m["vendor"]:
                pairs.append((i, j))

    seen = set()
    selected: list[tuple[int, int]] = []
    for i, j in pairs:
        key = (models[i]["id"], models[j]["id"])
        if key in seen or len(selected) >= limit:
            continue
        seen.add(key)
        selected.append((i, j))

    for i, j in selected:
        a, b = models[i], models[j]
        seen.add(key)

        bi = (a["input_per_1m_usd"] * 3 + a["output_per_1m_usd"]) / 4
        bj = (b["input_per_1m_usd"] * 3 + b["output_per_1m_usd"]) / 4
        win, lose = (a, b) if bi < bj else (b, a)
        delta = abs(bi - bj) / max(bi, bj) * 100 if max(bi, bj) else 0.0
        s = f"{slug(a['id'])}-vs-{slug(b['id'])}"

        if a["context_length"] == b["context_length"]:
            ctx_line = (f"Both offer the same {a['context_length']:,}-token context window, "
                        f"so cost is the deciding factor.")
            advice = (f"Because the context windows are identical, the cheaper option is the "
                      f"better default. Choose <strong>{html.escape(win['display_name'])}</strong> "
                      f"unless you are already standardised on "
                      f"{html.escape(lose['vendor'])} tooling and want to avoid a second integration.")
        else:
            wider, other = (a, b) if a["context_length"] > b["context_length"] else (b, a)
            ctx_line = (f"{html.escape(wider['display_name'])} offers the larger context window "
                        f"at {wider['context_length']:,} tokens, against "
                        f"{other['context_length']:,} for {html.escape(other['display_name'])}.")
            advice = (f"Pick <strong>{html.escape(wider['display_name'])}</strong> when you need the "
                      f"longer context window ({wider['context_length']:,} vs "
                      f"{other['context_length']:,} tokens). "
                      f"Pick <strong>{html.escape(win['display_name'])}</strong> when price per token "
                      f"dominates your workload &mdash; high-volume classification, extraction, or "
                      f"batch summarisation.")

        mix_rows = "".join(
            f'<tr><td>{label}</td>'
            f'<td class="num">{money((a["input_per_1m_usd"] * i2 + a["output_per_1m_usd"] * o2) / 1e6)}</td>'
            f'<td class="num">{money((b["input_per_1m_usd"] * i2 + b["output_per_1m_usd"] * o2) / 1e6)}</td></tr>'
            for i2, o2, label in [
                (1e6, 2.5e5, "1M in / 250K out"),
                (1e7, 2.5e6, "10M in / 2.5M out"),
                (1e8, 2.5e7, "100M in / 25M out"),
            ]
        )

        body = f"""
{crumbs([("Home", "/"), ("Compare", "/compare/"), (a["display_name"] + " vs " + b["display_name"], None)])}
<div class="hero reveal">
  <h1>{html.escape(a["display_name"])} vs {html.escape(b["display_name"])}: cost comparison</h1>
  <p class="stamp">Prices updated {stamp[:10]} &middot; computed from live provider data</p>
</div>

<div class="answer reveal reveal-2">
<strong>Short answer:</strong> <a href="/model/{slug(win['id'])}/">{html.escape(win["display_name"])}</a> is cheaper on a
3:1 input/output blend &mdash; {money(round(min(bi,bj), 4))} per million tokens versus
{money(round(max(bi,bj), 4))}, a <strong>{delta:.0f}% difference</strong>.
{ctx_line}
</div>

<h2>Head to head</h2>
<div class="ledger-wrap">
<table class="ledger">
<thead><tr><th></th><th class="num">{html.escape(a["display_name"])}</th><th class="num">{html.escape(b["display_name"])}</th></tr></thead>
<tbody>
<tr><td>Input, per 1M tokens</td><td class="num">{money(a["input_per_1m_usd"])}</td><td class="num">{money(b["input_per_1m_usd"])}</td></tr>
<tr><td>Output, per 1M tokens</td><td class="num">{money(a["output_per_1m_usd"])}</td><td class="num">{money(b["output_per_1m_usd"])}</td></tr>
<tr><td>Blended 3:1, per 1M</td><td class="num">{money(round(bi,4))}</td><td class="num">{money(round(bj,4))}</td></tr>
<tr><td>Context window</td><td class="num">{a["context_length"]:,}</td><td class="num">{b["context_length"]:,}</td></tr>
<tr><td>Vendor</td><td class="num">{html.escape(vendor_label(a["vendor"]))}</td><td class="num">{html.escape(vendor_label(b["vendor"]))}</td></tr>
</tbody>
</table>
</div>

<h2>Monthly cost at real volumes</h2>
<div class="ledger-wrap">
<table class="ledger">
<thead><tr><th>Workload (input / output)</th><th class="num">{html.escape(a["display_name"])}</th><th class="num">{html.escape(b["display_name"])}</th></tr></thead>
<tbody>{mix_rows}</tbody>
</table>
</div>

<h2>Which should you pick?</h2>
<p>{advice}</p>

<h2>Related</h2>
<ul>
<li><a href="/model/{slug(a['id'])}/">{html.escape(a["display_name"])} full pricing</a></li>
<li><a href="/model/{slug(b['id'])}/">{html.escape(b["display_name"])} full pricing</a></li>
</ul>
"""
        ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": f"{a['display_name']} vs {b['display_name']} cost comparison",
            "dateModified": stamp,
            "url": f"{BASE}/compare/{s}/",
        }
        write(f"compare/{s}/index.html", page(
            f"{a['display_name']} vs {b['display_name']}: Which Is Cheaper? ({stamp[:10]})",
            f"Cost comparison of {a['display_name']} and {b['display_name']}. Live input and output token prices, monthly cost examples and context window sizes, updated {stamp[:10]}.",
            f"{BASE}/compare/{s}/", body, ld, active="compare"))
        urls.append(f"/compare/{s}/")
    return urls


def compare_index(models: list[dict]) -> dict[str, str]:
    """Map every ordered model pair that will get a page to its route."""
    n = len(models)
    pairs = []
    for i in range(n - 1):
        pairs.append((i, i + 1))
    for i, m in enumerate(models):
        for j in range(i + 1, min(i + 4, n)):
            if models[j]["vendor"] == m["vendor"]:
                pairs.append((i, j))
    seen, out = set(), {}
    for i, j in pairs:
        if len(out) >= 400:
            break
        a, b = models[i], models[j]
        key = (a["id"], b["id"])
        if key in seen:
            continue
        seen.add(key)
        out[f"{a['id']}|{b['id']}"] = f"/compare/{slug(a['id'])}-vs-{slug(b['id'])}/"
    return out


def build_compare_hub(models: list[dict], cindex: dict[str, str], stamp: str) -> None:
    """A landing page for /compare/ so the nav link has somewhere to go."""
    seen: set[str] = set()
    cards = []
    by_slug = {slug(m["id"]): m for m in models}
    for route in cindex.values():
        if route in seen:
            continue
        seen.add(route)
        # Recover the two display names from the route's model slugs.
        parts = route.strip("/").split("/")[-1].split("-vs-")
        if len(parts) != 2:
            continue
        a, b = by_slug.get(parts[0]), by_slug.get(parts[1])
        if not a or not b:
            continue
        cards.append(
            f'<a class="card" href="{route}" style="text-decoration:none">'
            f'<h3>{html.escape(a["display_name"])} <span class="mut">vs</span> '
            f'{html.escape(b["display_name"])}</h3>'
            f'<p>Blended cost, context window and monthly examples side by side.</p>'
            f'<div class="card__meta">Head-to-head</div></a>')
        if len(cards) >= 24:
            break

    body = f"""
{crumbs([("Home", "/"), ("Compare", None)])}
<div class="hero reveal">
  <h1>Head-to-head comparisons</h1>
  <p class="lede">Two models, one table, and an honest answer about which is cheaper
    for your workload &mdash; including when the context windows tie and price is the
    only difference.</p>
  <p class="stamp">{len(seen)} comparison pages, generated from adjacent-in-price and
    same-vendor pairs &middot; updated {stamp[:10]}</p>
</div>
<div class="cards reveal reveal-2">{"".join(cards)}</div>
<p class="stamp" style="margin-top:22px">Every comparison is regenerated on each
  daily refresh, so the prices always match the model pages.</p>
"""
    ld = {"@context": "https://schema.org", "@type": "CollectionPage",
          "name": "LLM API cost comparisons", "url": f"{BASE}/compare/",
          "dateModified": stamp}
    write("compare/index.html", page(
        "Compare LLM API prices - Toolsummary",
        "Head-to-head LLM API cost comparisons with monthly workload examples.",
        f"{BASE}/compare/", body, ld, active="compare"))


# ------------------------------------------------------------------ hub page

def build_hub(models: list[dict], stamp: str, recent: dict | None, posts: list[dict]) -> None:
    rows = []
    # Every model is rendered into the table. Pagination is done in the browser
    # (see initPager in theme.js) so all 704 rows are in the HTML and crawlable;
    # capping the table would hide two thirds of the dataset from search engines
    # and from anyone with JavaScript disabled.
    for i, m in enumerate(models):
        rows.append(
            f'<tr>'
            f'<td class="rank" data-value="{i+1}">{i+1}</td>'
            f'<td class="name" data-value="{html.escape(m["display_name"])}">'
            f'<a href="/model/{slug(m["id"])}/">{html.escape(m["display_name"])}</a>'
            f'<br><span class="mut" style="font-size:12.5px">{html.escape(vendor_label(m["vendor"]))}</span></td>'
            f'<td class="num"><span class="{"price price--free" if m["input_per_1m_usd"] == 0 else "price"}" '
            f'data-value="{m["input_per_1m_usd"]}">{money(m["input_per_1m_usd"])}</span></td>'
            f'<td class="num"><span class="{"price price--free" if m["output_per_1m_usd"] == 0 else "price"}" '
            f'data-value="{m["output_per_1m_usd"]}">{money(m["output_per_1m_usd"])}</span></td>'
            f'<td class="num" data-value="{m["context_length"]}">{m["context_length"]:,}</td>'
            f'</tr>'
        )
    cheapest = models[0]
    median = models[len(models) // 2]
    free_count = sum(1 for m in models if m["input_per_1m_usd"] == 0)
    vendors = len({m["vendor"] for m in models})

    blog_teaser = ""
    if posts:
        p = posts[0]
        blog_teaser = f"""
  <hr class="rule">
  <section>
    <h2 class="mt-0">From the blog</h2>
    <div class="post-list">
      <a class="post" href="/blog/{p['slug']}/">
        <span class="post__meta">{html.escape(p['tag'])} &middot; {p['date']} &middot; {html.escape(p['read'])}</span>
        <h3>{html.escape(p['title'])}</h3>
        <p>{html.escape(p['excerpt'])}</p>
        <span class="post__more">Read the post &rarr;</span>
      </a>
    </div>
  </section>"""

    body = f"""
  <section class="hero reveal">
    <div class="hero__rule"></div>
    <h1>LLM API pricing, recorded daily</h1>
    <p class="lede">Every tracked model, what it costs per million tokens, and how that
      changed since yesterday. No sign-up, no estimate &mdash; the numbers providers publish.</p>
  </section>

  <div class="answer reveal reveal-2">
    <strong>Cheapest tracked model:</strong> {html.escape(cheapest["display_name"])} at
    <span class="answer__k">{money(cheapest["input_per_1m_usd"])}</span> per 1M input tokens.
    <strong>Median input price:</strong> <span class="answer__k">{money(median["input_per_1m_usd"])}</span> per 1M tokens.
    <strong>Dataset:</strong> {len(models):,} models, refreshed daily.
  </div>

  <div class="stats reveal reveal-3">
    <div class="stat"><span class="stat__label">Models tracked</span>
      <div class="stat__value">{len(models):,}</div><div class="stat__sub">across {vendors} providers</div></div>
    <div class="stat"><span class="stat__label">Cheapest input / 1M</span>
      <div class="stat__value">{money(cheapest["input_per_1m_usd"])}</div>
      <div class="stat__sub">{free_count} models at $0.00</div></div>
    <div class="stat"><span class="stat__label">Median input / 1M</span>
      <div class="stat__value">{money(median["input_per_1m_usd"])}</div>
      <div class="stat__sub">across the dataset</div></div>
    <div class="stat"><span class="stat__label">Data as of</span>
      <div class="stat__value">{stamp[:10]}</div><div class="stat__sub">refreshed daily, 04:30 UTC</div></div>
  </div>

  <section aria-labelledby="all-models">
    <h2 id="all-models" class="mt-0">All models</h2>
    <p class="stamp">Live data pulled from provider APIs on {stamp[:10]}. Sorted by input
      price, cheapest first. Click a column heading to re-sort.</p>

    <div class="search">
      <label for="q">Filter</label>
      <div class="search__field">
        <input type="search" id="q" placeholder="Filter by model or vendor&hellip;" aria-label="Filter models">
        <span class="search__count">{len(models):,} models</span>
      </div>
    </div>
    <div class="empty" role="status">No model matches that filter.</div>

    <div class="ledger-wrap">
      <table class="ledger" id="t">
        <thead>
          <tr>
            <th data-sort="num" style="width:52px">#</th>
            <th data-sort="text">Model</th>
            <th class="num" data-sort="num">Input / 1M</th>
            <th class="num" data-sort="num">Output / 1M</th>
            <th class="num" data-sort="num">Context</th>
          </tr>
        </thead>
        <tbody>{"".join(rows)}</tbody>
        <tfoot><tr><td colspan="5">{len(models):,} models tracked
          &middot; updated {stamp[:10]}</td></tr></tfoot>
      </table>
    </div>
    <nav class="pager" id="pager" aria-label="Model table pages"></nav>
  </section>

  <hr class="rule">

  <section id="method">
    <h2 class="mt-0">How this is built</h2>
    <div class="cards">
      <article class="card">
        <h3>Pulled, not guessed</h3>
        <p>Prices come straight from provider APIs and public price lists, normalised to
          USD per million tokens. Anything ambiguous goes to a human queue instead of
          onto a page.</p>
        <div class="card__meta">Updated daily, 04:30 UTC</div>
      </article>
      <article class="card">
        <h3>A real history</h3>
        <p>Each day's snapshot is appended to an immutable log, so a price change is a
          fact with a date on it &mdash; not a number someone typed over.</p>
        <div class="card__meta"><a href="/trending/">See what moved</a></div>
      </article>
      <article class="card">
        <h3>Readable by machines</h3>
        <p>A JSON endpoint, sitemap, <code>llms.txt</code> and structured data on every
          page, so agents and crawlers can cite the current number.</p>
        <div class="card__meta"><a href="/api/prices.json">/api/prices.json</a></div>
      </article>
    </div>
  </section>{blog_teaser}
"""
    ld = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "LLM API pricing dataset",
        "description": f"Live input and output token pricing for {len(models)} LLM API models.",
        "dateModified": stamp, "url": f"{BASE}/",
        "creator": {"@type": "Organization", "name": "Toolsummary"},
    }
    write("index.html", page(
        f"LLM API Pricing: {len(models)} Models Compared (Updated {stamp[:10]})",
        f"Compare live input and output token prices for {len(models)} LLM APIs. Cheapest model, median price, context windows and per-workload cost estimates, refreshed daily.",
        f"{BASE}/", body, ld, active="models"))


def build_htaccess() -> None:
    """Generate the Apache config for the web root.

    Generated rather than left to the server because the placeholder's
    .htaccess sets X-Robots-Tag: noindex, which would keep every page out of
    search results even though robots.txt invites crawlers in. Setting the
    header to "all" here overrides that and lets the site rank.

    Canonical host is enforced on the apex domain, and index.html is served
    for directory URLs so /model/foo resolves without a trailing slash.
    """
    write(".htaccess", "\n".join([
        "DirectoryIndex index.html index.htm",
        "",
        "<IfModule mod_headers.c>",
        "    Header set X-Robots-Tag \"all\"",
        "</IfModule>",
        "",
        "RewriteEngine On",
        "",
        "# One canonical host, so rankings are not split between www and apex.",
        "RewriteCond %{HTTP_HOST} ^www\\.toolsummary\\.com$ [NC]",
        "RewriteRule ^(.*)$ https://toolsummary.com/$1 [R=301,L]",
        "",
        "# Serve directory URLs without requiring a trailing slash.",
        "RewriteCond %{REQUEST_FILENAME} !-f",
        "RewriteCond %{REQUEST_FILENAME} !-d",
        "RewriteCond %{REQUEST_FILENAME}.html -f",
        "RewriteRule ^(.*)$ /$1.html [L]",
        "",
    ]))


def build_sitemap(urls: list[str]) -> None:
    items = "".join(f"<url><loc>{BASE}{u}</loc></url>" for u in urls)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>')


def build_robots_txt() -> None:
    """Advertise the sitemap and let AI crawlers in.

    llms.txt only helps crawlers that already look for it, so the major
    AI user agents are allowed explicitly rather than left to a default.
    Nothing here is private; the acquisition model depends on being read
    and cited.
    """
    write("robots.txt", "\n".join([
        "User-agent: *",
        "Allow: /",
        "",
        "# AI crawlers are welcome; the free pages are the acquisition surface.",
        "User-agent: GPTBot",
        "Allow: /",
        "",
        "User-agent: ClaudeBot",
        "Allow: /",
        "",
        "User-agent: PerplexityBot",
        "Allow: /",
        "",
        "User-agent: Google-Extended",
        "Allow: /",
        "",
        f"Sitemap: {BASE}/sitemap.xml",
        "",
    ]))


def build_llms_txt(models: list[dict], stamp: str) -> None:
    lines = [
        "# Toolsummary - LLM API pricing",
        "",
        f"> Live input/output token pricing for {len(models)} LLM API models, refreshed daily.",
        f"> Last updated: {stamp[:10]}",
        "",
        "## Key facts",
        f"- Models tracked: {len(models)}",
        f"- Cheapest input price: {models[0]['display_name']} at {money(models[0]['input_per_1m_usd'])} per 1M tokens",
        f"- Median input price: {money(models[len(models)//2]['input_per_1m_usd'])} per 1M tokens",
        f"- Most expensive tracked input price: {money(models[-1]['input_per_1m_usd'])} per 1M tokens",
        "",
        "## Pages",
        f"- {BASE}/ - full sortable table",
        f"- {BASE}/model/<slug>/ - per-model pricing and workload cost examples",
        f"- {BASE}/compare/<a>-vs-<b>/ - head-to-head cost comparisons",
        f"- {BASE}/trending/ - biggest price moves and newest models",
        f"- {BASE}/blog/ - pricing notes and reports",
        f"- {BASE}/submit/ - submit a model or a correction",
        "",
        "## Machine-readable",
        f"- {BASE}/api/prices.json - the current dataset as JSON (version 1)",
        f"- {BASE}/blog/feed.xml - RSS feed for the blog",
        f"- {BASE}/sitemap.xml - every page",
        "",
    ]
    write("llms.txt", "\n".join(lines))


# ------------------------------------------------------------ blog (Markdown)
# Posts are plain Markdown files in automation/mvp/blog/ with a small
# front-matter block. Adding a post is one file plus a commit; the next daily
# run renders it. No database and no third-party Markdown library.
#
# Authors are declared once here and referenced by key from a post's front
# matter (`author: maya`). The same record feeds the byline, the author page,
# the schema.org markup and the RSS feed, so the four cannot drift apart.

AUTHORS: dict[str, dict] = {
    "maya": {
        "name": "Maya Ferreira",
        "role": "Pricing analyst",
        "bio": "Tracks published per-token prices across providers and writes the "
               "monthly price reports. Careful about the difference between a price "
               "cut and a data artefact.",
    },
    "dan": {
        "name": "Daniel Okonkwo",
        "role": "Infrastructure writer",
        "bio": "Writes about serving costs and throughput. Formerly ran inference "
               "for a mid-size product team, so the numbers here are the ones that "
               "actually showed up on a bill.",
    },
    "lena": {
        "name": "Lena Petrova",
        "role": "Data editor",
        "bio": "Maintains the ledger itself: how models are matched across sources, "
               "what gets merged, and what gets held back for review.",
    },
    "sam": {
        "name": "Sam Whitfield",
        "role": "Editor",
        "bio": "Edits the blog and writes the explainers. Interested in why two "
               "providers quote the same model at different prices.",
    },
}
DEFAULT_AUTHOR = "maya"

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def parse_post(path: Path) -> dict | None:
    text = path.read_text()
    m = FRONT_MATTER.match(text)
    if not m:
        print(f"[blog] skipping {path.name}: no front matter")
        return None
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    body = text[m.end():].strip()
    if not meta.get("title") or not meta.get("date"):
        print(f"[blog] skipping {path.name}: title and date are required")
        return None
    # The filename is date-prefixed so posts sort chronologically, but the URL
    # should not carry the date: /blog/what-moved-in-october/ reads better and
    # keeps working if a post is ever backdated.
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
    author_key = (meta.get("author") or DEFAULT_AUTHOR).strip().lower()
    if author_key not in AUTHORS:
        print(f"[blog] {path.name}: unknown author '{author_key}', using {DEFAULT_AUTHOR}")
        author_key = DEFAULT_AUTHOR
    return {
        "slug": stem,
        "title": meta["title"],
        "date": meta["date"],
        "tag": meta.get("tag", "Post"),
        "read": meta.get("read", ""),
        "excerpt": meta.get("excerpt", ""),
        "author": author_key,
        "author_name": AUTHORS[author_key]["name"],
        "body": body,
    }


def author_byline(name: str, role: str = "") -> str:
    """The byline block shared by post pages and author pages."""
    initial = (name.strip()[:1] or "T").upper()
    role_html = f'<div class="byline__role">{html.escape(role)}</div>' if role else ""
    return (
        f'<div class="byline">'
        f'<div class="byline__avatar" aria-hidden="true">{initial}</div>'
        f'<div><div class="byline__name">{html.escape(name)}</div>{role_html}</div>'
        f"</div>")


def load_posts() -> list[dict]:
    if not BLOG.is_dir():
        return []
    # README.md documents the format and is not a post.
    files = [f for f in sorted(BLOG.glob("*.md")) if f.name.lower() != "readme.md"]
    posts = [p for p in (parse_post(f) for f in files) if p]
    # Newest first. The filename is date-prefixed so the sort is stable.
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    return posts


def inline_md(text: str) -> str:
    """Escape, then apply the inline markup we support.

    Escaping happens first so a post can never inject raw HTML.
    """
    out = html.escape(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                 r'<a href="\2" rel="noopener">\1</a>', out)
    return out


def render_markdown(md: str) -> str:
    """A deliberately small Markdown subset: headings, paragraphs, lists,
    blockquotes and fenced code. Enough for articles, small enough to audit."""
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    para: list[str] = []
    list_items: list[str] = []
    quote: list[str] = []

    def flush_para() -> None:
        if para:
            out.append("<p>" + inline_md(" ".join(para)) + "</p>")
            para.clear()

    def flush_list() -> None:
        if list_items:
            out.append("<ul>" + "".join(f"<li>{inline_md(x)}</li>" for x in list_items) + "</ul>")
            list_items.clear()

    def flush_quote() -> None:
        if quote:
            out.append("<blockquote>" + inline_md(" ".join(quote)) + "</blockquote>")
            quote.clear()

    def flush_all() -> None:
        flush_para(); flush_list(); flush_quote()

    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("```"):
            flush_all()
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            continue
        if not line.strip():
            flush_all()
        elif line.startswith("### "):
            flush_all(); out.append(f"<h3>{inline_md(line[4:])}</h3>")
        elif line.startswith("## "):
            flush_all(); out.append(f"<h2>{inline_md(line[3:])}</h2>")
        elif line.startswith("# "):
            flush_all(); out.append(f"<h2>{inline_md(line[2:])}</h2>")
        elif line.startswith("> "):
            flush_para(); flush_list(); quote.append(line[2:])
        elif line.startswith("- ") or line.startswith("* "):
            flush_para(); flush_quote(); list_items.append(line[2:])
        else:
            flush_list(); flush_quote(); para.append(line.strip())
        i += 1
    flush_all()
    return "\n".join(out)


def build_blog(posts: list[dict]) -> list[str]:
    urls = []
    if not posts:
        return urls
    cards = "".join(
        f'<a class="post" href="/blog/{p["slug"]}/">'
        f'<span class="post__meta">{html.escape(p["tag"])} &middot; {p["date"]}'
        f'{" &middot; " + html.escape(p["read"]) if p["read"] else ""}</span>'
        f'<h3>{html.escape(p["title"])}</h3>'
        f'<p>{html.escape(p["excerpt"])}</p>'
        f'<span class="post__more">Read &rarr;</span></a>'
        for p in posts
    )
    body = f"""
{crumbs([("Home", "/"), ("Blog", None)])}
<div class="hero reveal">
  <h1>The price ledger</h1>
  <p class="lede">Notes on what LLM APIs cost, what changed, and how to read a
    per-token price without getting the arithmetic wrong.</p>
  <p class="stamp"><a href="/blog/feed.xml">RSS feed</a></p>
</div>
<div class="post-list reveal reveal-2">{cards}</div>
"""
    write("blog/index.html", page(
        "Blog - Toolsummary",
        "Notes on LLM API pricing and how to read it.",
        f"{BASE}/blog/", body, {}, active="blog"))
    urls.append("/blog/")

    for p in posts:
        a = AUTHORS[p["author"]]
        ld = {
            "@context": "https://schema.org", "@type": "BlogPosting",
            "headline": p["title"], "description": p["excerpt"],
            "datePublished": p["date"], "dateModified": p["date"],
            "url": f"{BASE}/blog/{p['slug']}/",
            "author": {"@type": "Person", "name": a["name"],
                       "url": f"{BASE}/blog/author/{p['author']}/"},
            "publisher": {"@type": "Organization", "name": "Toolsummary",
                          "url": BASE},
        }
        body = f"""
{crumbs([("Home", "/"), ("Blog", "/blog/"), (p["title"], None)])}
<article class="prose">
  <header class="hero reveal">
    <h1>{html.escape(p["title"])}</h1>
    <p class="lede">{html.escape(p["excerpt"])}</p>
  </header>
  <div class="byline">
    <div class="byline__avatar" aria-hidden="true">{html.escape(a["name"][:1].upper())}</div>
    <div>
      <div class="byline__name"><a href="/blog/author/{p['author']}/">{html.escape(a["name"])}</a></div>
      <div class="byline__role">{html.escape(a["role"])} &middot; {p["date"]}{" &middot; " + html.escape(p["read"]) if p["read"] else ""}</div>
    </div>
  </div>
  {render_markdown(p["body"])}
  <hr class="rule">
  <p class="stamp">Prices quoted are from the daily ledger on the date shown.</p>
</article>
"""
        write(f"blog/{p['slug']}/index.html", page(
            f"{p['title']} - Toolsummary", p["excerpt"],
            f"{BASE}/blog/{p['slug']}/", body, ld, active="blog"))
        urls.append(f"/blog/{p['slug']}/")

    urls += build_author_pages(posts)
    write("blog/feed.xml", build_rss(posts))
    return urls


def build_author_pages(posts: list[dict]) -> list[str]:
    """One page per author who has at least one post.

    These give the byline a real destination and a Person record, which is what
    search engines and readers use to tell a named writer from an anonymous
    feed. Authors with no posts are skipped rather than published empty.
    """
    urls = []
    for key, a in AUTHORS.items():
        mine = [p for p in posts if p["author"] == key]
        if not mine:
            continue
        cards = "".join(
            f'<a class="post" href="/blog/{p["slug"]}/">'
            f'<span class="post__meta">{html.escape(p["tag"])} &middot; {p["date"]}'
            f'{" &middot; " + html.escape(p["read"]) if p["read"] else ""}</span>'
            f'<h3>{html.escape(p["title"])}</h3>'
            f'<p>{html.escape(p["excerpt"])}</p>'
            f'<span class="post__more">Read &rarr;</span></a>'
            for p in mine
        )
        body = f"""
{crumbs([("Home", "/"), ("Blog", "/blog/"), (a["name"], None)])}
<div class="hero reveal">
  <h1>{html.escape(a["name"])}</h1>
  <p class="lede">{html.escape(a["bio"])}</p>
  <p class="stamp">{html.escape(a["role"])} &middot; {len(mine)} post{"s" if len(mine) != 1 else ""}</p>
</div>
<div class="post-list reveal reveal-2">{cards}</div>
"""
        ld = {"@context": "https://schema.org", "@type": "Person",
              "name": a["name"], "jobTitle": a["role"],
              "description": a["bio"],
              "url": f"{BASE}/blog/author/{key}/"}
        write(f"blog/author/{key}/index.html", page(
            f"{a['name']} - Toolsummary",
            f"Posts by {a['name']}, {a['role'].lower()} at Toolsummary.",
            f"{BASE}/blog/author/{key}/", body, ld, active="blog"))
        urls.append(f"/blog/author/{key}/")
    return urls


def build_rss(posts: list[dict]) -> str:
    def esc(t: str) -> str:
        return (t.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace('"', "&quot;"))

    items = "".join(
        f"<item><title>{esc(p['title'])}</title>"
        f"<link>{BASE}/blog/{p['slug']}/</link>"
        f"<guid isPermaLink=\"true\">{BASE}/blog/{p['slug']}/</guid>"
        f"<pubDate>{p['date']}T00:00:00+00:00</pubDate>"
        f"<author>{esc(AUTHORS[p['author']]['name'])}</author>"
        f"<dc:creator>{esc(AUTHORS[p['author']]['name'])}</dc:creator>"
        f"<description>{esc(p['excerpt'])}</description></item>"
        for p in posts
    )
    newest = posts[0]["date"] if posts else "1970-01-01"
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<channel>"
            f"<title>Toolsummary - the price ledger</title>"
            f"<link>{BASE}/blog/</link>"
            f"<description>Notes on LLM API pricing and what changed.</description>"
            f"<language>en</language>"
            f"<lastBuildDate>{newest}T00:00:00+00:00</lastBuildDate>"
            f"{items}</channel></rss>")


# ------------------------------------------------------------------- forms
# Both forms POST to Web3Forms, which forwards to the contact inbox. The
# access key is public by design. There is no captcha secret to protect because
# there is no third-party captcha.
#
# Bot defence is a human check plus a honeypot. No third-party captcha: no
# account, no secret key, and nothing that can fail closed and lock a real
# person out of the form.


def human_check_block() -> str:
    """A small arithmetic question, generated and checked in the browser.

    The question is written by JS on load and the answer is kept in a closure,
    not in the DOM, so a bot has to run JavaScript and read a live variable
    rather than scrape a fixed value. It is a gate against the common case --
    an automated script that fills every field it finds and posts -- and it is
    deliberately not presented as more than that. A determined attacker can
    answer a sum; the honeypot and Web3Forms' own server-side spam filter are
    what cover that case.

    The field has no `name`, so the answer is never emailed; it is a check, not
    data.
    """
    return (
        '<div class="field field--wide">'
        '<label for="human-answer"><span id="human-question">Quick check</span>'
        ' <span class="req">*</span></label>'
        '<input id="human-answer" type="text" required inputmode="numeric" '
        'autocomplete="off" autocapitalize="off" spellcheck="false" '
        'placeholder="Your answer" aria-describedby="human-hint">'
        '<span class="hint" id="human-hint">So we know a person is sending this.</span>'
        '<span class="err">That is not the right answer.</span>'
        '</div>'
    )


def form_hidden(subject: str) -> str:
    """Reserved Web3Forms fields plus the honeypot.

    No `redirect`: both forms post over fetch and answer in place, so a
    redirect would throw the user out of the page they were on. No `replyto`
    either: Web3Forms already sets Reply-To from the `email` field, and
    writing our own address into the page would expose it to scrapers.
    """
    return (
        f'<input type="hidden" name="access_key" value="{WEB3FORMS_KEY}">'
        f'<input type="hidden" name="subject" value="{html.escape(subject)}">'
        f'<input type="hidden" name="from_name" value="Toolsummary">'
        # Honeypot: hidden from users, irresistible to naive bots.
        '<input type="checkbox" name="botcheck" style="display:none" tabindex="-1" '
        'autocomplete="off" aria-hidden="true">'
    )


def form_modal(ok_message: str) -> str:
    """The dialog both outcomes use. Rendered hidden; JS drives it."""
    return f"""
<div class="modal" id="form-modal" role="dialog" aria-modal="true"
     aria-labelledby="form-modal-title" hidden>
  <div class="modal__box">
    <div class="modal__icon" aria-hidden="true">&#10003;</div>
    <h2 class="modal__title" id="form-modal-title">Thank you</h2>
    <p class="modal__msg">{html.escape(ok_message)}</p>
    <div class="modal__actions">
      <button type="button" class="btn" data-modal-ok>Close</button>
    </div>
  </div>
</div>"""


def build_submit() -> None:
    body = f"""
{crumbs([("Home", "/"), ("Submit a model", None)])}
<div class="hero reveal">
  <h1>Submit a model</h1>
  <p class="lede">Know a model we are missing, or a price we have wrong? Tell us and we
    will verify it against the provider's own pricing page before it appears.</p>
</div>

<div class="notice notice--info">
  <strong>What we list:</strong> LLM and inference APIs with published per-token pricing.
  We do not list resellers of another provider's models, and we do not accept payment for
  placement &mdash; every row is priced the same way.
</div>

<form class="form" id="submit-form" action="https://api.web3forms.com/submit" method="POST" novalidate
      data-ok-message="We verify every submission against the provider's own pricing page before it appears, so it may take a day or two to show up in the ledger.">
  {form_hidden("Toolsummary: model submission")}
  <div class="form__grid">
    <div class="field">
      <label for="model-name">Model name <span class="req">*</span></label>
      <input id="model-name" name="model_name" type="text" required minlength="2"
             placeholder="e.g. Claude Opus 4" autocomplete="off">
      <span class="err">Give the name exactly as the provider writes it.</span>
    </div>
    <div class="field">
      <label for="provider">Provider <span class="req">*</span></label>
      <input id="provider" name="provider" type="text" required minlength="2"
             placeholder="e.g. Anthropic" autocomplete="organization">
      <span class="err">Who publishes the pricing?</span>
    </div>
    <div class="field">
      <label for="category">Category</label>
      <select id="category" name="category">
        <option value="llm">LLM / chat completion</option>
        <option value="embedding">Embeddings</option>
        <option value="image">Image generation</option>
        <option value="audio">Audio / speech</option>
        <option value="other">Other</option>
      </select>
      <span class="hint">Pick the closest fit; we re-categorise if needed.</span>
    </div>
    <div class="field">
      <label for="pricing-url">Pricing page URL <span class="req">*</span></label>
      <input id="pricing-url" name="pricing_url" type="url" required
             placeholder="https://provider.com/pricing">
      <span class="err">We need a link we can verify against.</span>
    </div>
    <div class="field">
      <label for="input-price">Input price, per 1M tokens (USD)</label>
      <input id="input-price" name="input_price" type="number" min="0" step="0.0001"
             inputmode="decimal" placeholder="0.250">
      <span class="hint">Leave blank if you are not sure.</span>
    </div>
    <div class="field">
      <label for="output-price">Output price, per 1M tokens (USD)</label>
      <input id="output-price" name="output_price" type="number" min="0" step="0.0001"
             inputmode="decimal" placeholder="1.250">
      <span class="hint">Leave blank if you are not sure.</span>
    </div>
    <div class="field field--wide">
      <label for="notes">Notes</label>
      <textarea id="notes" name="notes"
        placeholder="Anything that helps us verify this &mdash; free tier limits, batch pricing, a launch date&hellip;"></textarea>
    </div>
    <div class="field field--wide">
      <label for="email">Your email (optional)</label>
      <input id="email" name="email" type="email" placeholder="you@example.com" autocomplete="email">
      <span class="hint">Only used if we need to ask you a question about this row.</span>
    </div>
  </div>
  {human_check_block()}
  <div class="btn-row">
    <button class="btn" type="submit">Submit for review</button>
    <span class="mut" style="font-size:13.5px">Fields marked <span class="req">*</span> are required.</span>
  </div>
</form>
{form_modal("We verify every submission against the provider's own pricing page before it appears, so it may take a day or two to show up in the ledger.")}
"""
    ld = {"@context": "https://schema.org", "@type": "WebPage",
          "name": "Submit a model", "url": f"{BASE}/submit/"}
    write("submit/index.html", page(
        "Submit a model - Toolsummary",
        "Submit an LLM API or model for inclusion in Toolsummary's daily price ledger.",
        f"{BASE}/submit/", body, ld, active="submit"))


def build_contact() -> None:
    body = f"""
{crumbs([("Home", "/"), ("Contact", None)])}
<div class="hero reveal">
  <h1>Contact</h1>
  <p class="lede">One form, and it reaches a person. For a wrong or missing price,
    the <a href="/submit/">submit form</a> is faster because it asks for exactly
    what we need to verify a row.</p>
</div>

<form class="form" id="submit-form" action="https://api.web3forms.com/submit" method="POST" novalidate
      data-ok-message="Your message reached us. We usually reply within one working day.">
  {form_hidden("Toolsummary: contact message")}
  <div class="form__grid">
    <div class="field">
      <label for="c-name">Your name <span class="req">*</span></label>
      <input id="c-name" name="name" type="text" required minlength="2"
             placeholder="Jane Doe" autocomplete="name">
      <span class="err">Please tell us who you are.</span>
    </div>
    <div class="field">
      <label for="c-email">Your email <span class="req">*</span></label>
      <input id="c-email" name="email" type="email" required
             placeholder="you@example.com" autocomplete="email">
      <span class="err">We need a reply address.</span>
    </div>
    <div class="field field--wide">
      <label for="c-subject">Subject</label>
      <input id="c-subject" name="subject_line" type="text"
             placeholder="Partnership, data licensing, a question&hellip;">
    </div>
    <div class="field field--wide">
      <label for="c-message">Message <span class="req">*</span></label>
      <textarea id="c-message" name="message" required minlength="10"
        placeholder="How can we help?"></textarea>
      <span class="err">A little more detail helps us route this.</span>
    </div>
  </div>
  {human_check_block()}
  <div class="btn-row">
    <button class="btn" type="submit">Send message</button>
    <span class="mut" style="font-size:13.5px">Fields marked <span class="req">*</span> are required.</span>
  </div>
</form>
{form_modal("Your message reached us. We usually reply within one working day.")}
"""
    ld = {"@context": "https://schema.org", "@type": "ContactPage",
          "name": "Contact Toolsummary", "url": f"{BASE}/contact/"}
    write("contact/index.html", page(
        "Contact - Toolsummary",
        "Contact Toolsummary about corrections, data licensing or partnerships.",
        f"{BASE}/contact/", body, ld, active=""))


def build_about() -> None:
    body = f"""
{crumbs([("Home", "/"), ("About", None)])}
<article class="prose">
  <header class="hero reveal">
    <h1>About Toolsummary</h1>
    <p class="lede">A daily record of what LLM APIs cost, kept in the open because a
      price is the one fact a language model cannot reconstruct from memory.</p>
  </header>
  <h2>What this is</h2>
  <p>Toolsummary tracks published per-token pricing for LLM and inference APIs and
    records a snapshot every day. That log is the product: it turns "what does this
    cost" into a fact with a date on it, rather than a number someone typed over.</p>
  <h2>How prices are collected</h2>
  <p>Prices come from provider APIs and public price lists, normalised to USD per
    million tokens. Anything ambiguous goes to a human review queue instead of onto a
    page. A rejected row never enters the history.</p>
  <h2>How fresh is this?</h2>
  <p>Every page carries the date its data was pulled. The pipeline runs daily at
    04:30 UTC; a page showing an older date than today means that day's refresh has
    not landed yet.</p>
  <h2>Independence</h2>
  <p>No provider pays for placement, and no row is priced differently from any other.
    If a number is wrong, the fastest fix is the <a href="/submit/">submit form</a>.</p>
  <h2>Using the data</h2>
  <p>The current dataset is available as JSON at
    <a href="/api/prices.json">/api/prices.json</a>. The blog has an
    <a href="/blog/feed.xml">RSS feed</a>.</p>
</article>
"""
    ld = {"@context": "https://schema.org", "@type": "AboutPage",
          "name": "About Toolsummary", "url": f"{BASE}/about/"}
    write("about/index.html", page(
        "About - Toolsummary",
        "What Toolsummary is, how prices are collected, and its independence policy.",
        f"{BASE}/about/", body, ld, active=""))


def build_privacy() -> None:
    body = f"""
{crumbs([("Home", "/"), ("Privacy", None)])}
<article class="prose">
  <header class="hero reveal"><h1>Privacy</h1>
  <p class="lede">The short version: this site collects as little as it can and sells
    nothing.</p></header>
  <h2>What is collected</h2>
  <p>The public pages are static and set no tracking cookies. The submit and contact
    forms are processed by <a href="https://web3forms.com" rel="noopener">Web3Forms</a>,
    which forwards your message to our inbox and does not store submissions. Their
    spam check is a small arithmetic question answered in your browser. There is no
    third-party captcha, no tracking cookie, and the answer is never sent to us or
    stored.</p>
  <h2>What is not done</h2>
  <p>No data is sold, and no provider is given access to submissions. Email addresses
    from the forms are used only to reply to you.</p>
  <h2>Analytics</h2>
  <p>Aggregate, cookie-free page counts only &mdash; enough to know which pages are
    useful, not enough to identify a reader.</p>
</article>
"""
    ld = {"@context": "https://schema.org", "@type": "WebPage",
          "name": "Privacy", "url": f"{BASE}/privacy/"}
    write("privacy/index.html", page(
        "Privacy - Toolsummary",
        "What Toolsummary collects and what it does not.",
        f"{BASE}/privacy/", body, ld, active=""))


def build_404() -> None:
    body = """
<div class="hero reveal">
  <h1>That page is not in the ledger</h1>
  <p class="lede">The model or comparison you asked for may have been delisted
    upstream, or the URL is mistyped.</p>
  <div class="btn-row">
    <a class="btn" href="/">Browse all models</a>
    <a class="btn btn--ghost" href="/blog/">Read the blog</a>
  </div>
</div>
"""
    write("404.html", page("Page not found - Toolsummary",
                           "That page does not exist.", f"{BASE}/404.html", body, {}))


# ------------------------------------------------------------------ trending

def build_trending(models: list[dict], recent: dict | None, stamp: str) -> list[str]:
    events = (recent or {}).get("events", [])
    # Rank only moves with a meaningful baseline. A jump from $0.0001 is a
    # data artefact, not a price change a buyer cares about, and printing
    # "+33500%" would discredit every other number on the page.
    prices = [e for e in events
              if e.get("kind") == "price"
              and e.get("pct_change") is not None
              and (e.get("from") or 0) >= MIN_PCT_BASE]
    downs = sorted([e for e in prices if e["pct_change"] < 0], key=lambda x: x["pct_change"])[:20]
    ups = sorted([e for e in prices if e["pct_change"] > 0], key=lambda x: x["pct_change"], reverse=True)[:20]
    new = sorted([e for e in events if e.get("kind") == "new"],
                 key=lambda x: x.get("date", ""), reverse=True)[:20]
    window = (recent or {}).get("window_days", 30)
    by_key = {m["canonical_key"]: m for m in models}

    def price_rows(rows: list[dict], sign: str) -> str:
        out = []
        for e in rows:
            m = by_key.get(e["canonical_key"])
            name = html.escape(e["display_name"])
            label = f'<a href="/model/{slug(m["id"])}/">{name}</a>' if m else name
            field = e["field"].replace("_per_1m_usd", "")
            cls = "delta--down" if sign == "-" else "delta--up"
            out.append(
                f'<tr><td class="name">{label}</td>'
                f'<td>{html.escape(vendor_label(e.get("vendor", "")))}</td>'
                f'<td class="num">{field}</td>'
                f'<td class="num">{money(e["from"])} &rarr; {money(e["to"])}</td>'
                f'<td class="num"><span class="delta {cls}">{e["pct_change"]:+.1f}%</span></td>'
                f'<td class="num">{e.get("date", "")}</td></tr>')
        return "".join(out) or '<tr><td colspan="6" class="mut">Nothing in this window.</td></tr>'

    def new_rows(rows: list[dict]) -> str:
        out = []
        for e in rows:
            m = by_key.get(e["canonical_key"])
            name = html.escape(e["display_name"])
            label = f'<a href="/model/{slug(m["id"])}/">{name}</a>' if m else name
            out.append(
                f'<tr><td class="name">{label}</td>'
                f'<td>{html.escape(vendor_label(e.get("vendor", "")))}</td>'
                f'<td class="num">{money(e.get("input_per_1m_usd", 0))}</td>'
                f'<td class="num">{money(e.get("output_per_1m_usd", 0))}</td>'
                f'<td class="num">{e.get("date", "")}</td></tr>')
        return "".join(out) or '<tr><td colspan="5" class="mut">Nothing in this window.</td></tr>'

    body = f"""
{crumbs([("Home", "/"), ("Trending", None)])}
<div class="hero reveal">
  <h1>Trending now: the biggest price moves and newest models</h1>
  <p class="lede">What changed in the last {window} days, straight from the price
    history log. A fall is good news for a buyer; a rise is worth a second look
    before you commit a budget.</p>
  <p class="stamp">Computed from the daily ledger &middot; updated {stamp[:10]}</p>
</div>

<h2>Biggest price drops</h2>
<p class="stamp">The models that got cheaper, largest fall first.</p>
<div class="ledger-wrap">
<table class="ledger">
<thead><tr><th>Model</th><th>Vendor</th><th class="num">Field</th><th class="num">Change</th><th class="num">Move</th><th class="num">Date</th></tr></thead>
<tbody>{price_rows(downs, "-")}</tbody>
</table>
</div>

<h2>Biggest price increases</h2>
<p class="stamp">The models that got more expensive, largest rise first.</p>
<div class="ledger-wrap">
<table class="ledger">
<thead><tr><th>Model</th><th>Vendor</th><th class="num">Field</th><th class="num">Change</th><th class="num">Move</th><th class="num">Date</th></tr></thead>
<tbody>{price_rows(ups, "+")}</tbody>
</table>
</div>

<h2>Recently added</h2>
<p class="stamp">Models that entered the ledger in the last {window} days.</p>
<div class="ledger-wrap">
<table class="ledger">
<thead><tr><th>Model</th><th>Vendor</th><th class="num">Input / 1M</th><th class="num">Output / 1M</th><th class="num">Added</th></tr></thead>
<tbody>{new_rows(new)}</tbody>
</table>
</div>

<hr class="rule">
<p class="stamp">Every move here is recorded in the append-only history, so it can be
  checked against the date it happened. Pull the raw log from
  <a href="/api/prices.json">/api/prices.json</a>.</p>
"""
    ld = {"@context": "https://schema.org", "@type": "WebPage",
          "name": "Trending LLM price moves", "dateModified": stamp,
          "url": f"{BASE}/trending/"}
    write("trending/index.html", page(
        "Trending LLM API price moves - Toolsummary",
        "The biggest LLM API price drops and increases, and the newest models, "
        "computed from the daily price history log.",
        f"{BASE}/trending/", body, ld, active="trending"))
    return ["/trending/"]


# --------------------------------------------------------------- JSON endpoint

def build_api(models: list[dict], payload: dict, stamp: str) -> list[str]:
    """A small, stable, read-only JSON view of the current dataset.

    Deliberately a separate shape from data/pricing.json: this is a public
    contract, so it carries only the fields a consumer needs and says so with
    a version field.
    """
    doc = {
        "version": 1,
        "generated_at": stamp,
        "source": f"{BASE}/",
        "model_count": len(models),
        "models": [
            {
                "id": m["id"],
                "canonical_key": m["canonical_key"],
                "name": m["display_name"],
                "vendor": m["vendor"],
                "context_length": m["context_length"],
                "input_per_1m_usd": m["input_per_1m_usd"],
                "output_per_1m_usd": m["output_per_1m_usd"],
                "url": f"{BASE}/model/{slug(m['id'])}/",
            }
            for m in models
        ],
    }
    write("api/prices.json", json.dumps(doc, indent=1) + "\n")
    return ["/api/prices.json"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap total models (for smoke tests)")
    a = ap.parse_args()

    payload = load()
    # Stamp from the data, not the clock. Rebuilding with unchanged data then
    # produces byte-identical output, so the daily git diff shows only real
    # price changes instead of every page on the site.
    stamp = payload.get("generated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    models = eligible(payload["models"])
    if a.limit:
        models = models[:a.limit]
    print(f"[build] {len(models)} eligible models (of {len(payload['models'])} fetched)")

    # Wipe first: a model delisted upstream must not leave an orphan page behind
    # that is still linked and still in the old sitemap.
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    # Guard against two models slugifying to the same URL, which silently
    # overwrites one page. Cheaper of the two wins; the loser is reported.
    by_slug: dict[str, dict] = {}
    collisions = []
    for m in sorted(models, key=lambda x: x["input_per_1m_usd"]):
        s = slug(m["id"])
        prev = by_slug.get(s)
        if prev is not None:
            collisions.append({"slug": s, "kept": prev["id"], "dropped": m["id"]})
            continue
        by_slug[s] = m
    models = sorted(by_slug.values(), key=lambda x: x["input_per_1m_usd"])
    if collisions:
        (DATA / "slug_collisions.json").write_text(json.dumps(collisions, indent=2))
        for c in collisions:
            print(f"[build] slug collision: kept {c['kept']}, dropped {c['dropped']}")

    cindex = compare_index(models)
    m_urls = build_model_pages(models, stamp, cindex)
    c_urls = build_compare_pages(models, stamp)

    # Load the change log and the blog before any page renders: the ticker on
    # every page reads CHROME, and the hub links to the newest post.
    recent_path = DATA / "price_changes_recent.json"
    recent = json.loads(recent_path.read_text()) if recent_path.exists() else None
    posts = load_posts()
    CHROME.update({"models": models, "recent": recent})

    build_hub(models, stamp, recent, posts)
    copy_assets()

    static_urls = ["/", "/submit/", "/contact/", "/about/", "/privacy/"]
    build_compare_hub(models, cindex, stamp)
    static_urls.append("/compare/")
    build_submit()
    build_contact()
    build_about()
    build_privacy()
    build_404()

    static_urls += build_trending(models, recent, stamp)
    static_urls += build_blog(posts)
    build_api(models, payload, stamp)  # served file, not a page: not in the sitemap

    build_sitemap(static_urls + m_urls + c_urls)
    build_robots_txt()
    build_htaccess()
    build_llms_txt(models, stamp)
    print(f"[build] {len(m_urls)} model pages, {len(c_urls)} comparison pages, "
          f"{len(posts)} blog post(s), {len(static_urls)} static pages -> site/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())