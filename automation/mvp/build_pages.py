#!/usr/bin/env python3
"""Stage 2: turn data/pricing.json into static pages.

Every page carries data no model can reconstruct from a prompt: a live price,
a computed multiple, a rank, and a refresh timestamp. That is the
"information gain" that keeps this out of scaled-content-abuse territory.

Usage: python3 build_pages.py [--limit N]
"""
import argparse
import shutil
import json
import re
import html
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SITE = ROOT / "site"
BASE = "https://toolsummary.com"

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


def page(title: str, desc: str, canonical: str, body: str, ld: dict) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:type" content="website">
<script type="application/ld+json">{json.dumps(ld)}</script>
<style>
:root{{--fg:#111;--mut:#666;--line:#e3e3e3;--acc:#0b5fff;--bg:#fff}}
*{{box-sizing:border-box}}
body{{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--fg);background:var(--bg)}}
header,main,footer{{max-width:1000px;margin:0 auto;padding:0 20px}}
header{{padding-top:28px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
header a{{color:var(--fg);text-decoration:none;font-weight:700;font-size:19px}}
main{{padding:28px 0 60px}}
h1{{font-size:30px;line-height:1.25;margin:0 0 8px}}
h2{{font-size:20px;margin:34px 0 10px}}
a{{color:var(--acc)}}
table{{border-collapse:collapse;width:100%;margin:16px 0;font-size:15px}}
th,td{{border-bottom:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top}}
th{{background:#fafafa;font-weight:600;white-space:nowrap}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.mut{{color:var(--mut)}}
.stamp{{font-size:13px;color:var(--mut);margin-top:4px}}
.answer{{background:#f6f8ff;border-left:3px solid var(--acc);padding:12px 16px;margin:18px 0;border-radius:0 4px 4px 0}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;padding:0;list-style:none}}
.cards li{{border:1px solid var(--line);border-radius:6px;padding:12px 14px}}
footer{{border-top:1px solid var(--line);padding:20px;color:var(--mut);font-size:14px}}
input[type=search]{{width:100%;padding:11px 14px;font-size:16px;border:1px solid var(--line);border-radius:6px}}
</style>
</head>
<body>
<header><a href="/">Toolsummary</a> <span class="mut">&middot; LLM pricing data</span></header>
<main>
{body}
</main>
<footer>
<p class="stamp">Prices are pulled from public provider APIs. Data as of <time datetime="{ld['dateModified']}">{ld['dateModified'][:10]}</time>. Always confirm on the provider's own pricing page before committing budget.</p>
<p><a href="/">All models</a> &middot; <a href="/sitemap.xml">Sitemap</a> &middot; <a href="/llms.txt">llms.txt</a></p>
</footer>
</body>
</html>
"""


def write(rel: str, content: str) -> None:
    p = SITE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


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
<h1>{html.escape(m["display_name"])} pricing</h1>
<p class="stamp">Source: {m["source"]} &middot; updated {stamp[:10]}</p>

<div class="answer">
<strong>Short answer:</strong> {verdict}
</div>

<h2>Price breakdown</h2>
<table>
<tr><th>Metric</th><th class="num">USD</th></tr>
<tr><td>Input, per 1M tokens</td><td class="num">{money(m["input_per_1m_usd"])}</td></tr>
<tr><td>Output, per 1M tokens</td><td class="num">{money(m["output_per_1m_usd"])}</td></tr>
<tr><td>Output ÷ input multiple</td><td class="num">{mult}</td></tr>
<tr><td>3:1 blended, per 1M tokens</td><td class="num">{money(round(blended, 4))}</td></tr>
<tr><td>Context window</td><td class="num">{m["context_length"]:,} tokens</td></tr>
</table>

<h2>What a typical workload costs</h2>
<table>
<tr><th>Monthly volume</th><th class="num">Input cost</th><th class="num">Output cost</th><th class="num">Total</th></tr{"".join(
    f'<tr><td>{v}</td><td class="num">{money(m["input_per_1m_usd"] * n / 1e6)}</td>'
    f'<td class="num">{money(m["output_per_1m_usd"] * n / 4 / 1e6)}</td>'
    f'<td class="num">{money((m["input_per_1m_usd"] * n + m["output_per_1m_usd"] * n / 4) / 1e6)}</td></tr>'
    for n, v in [(1_000_000, "1M in / 250K out"), (10_000_000, "10M in / 2.5M out"), (100_000_000, "100M in / 25M out")]
)}</table>
{"<h2>Other " + html.escape(m['vendor']) + " models</h2><table><tr><th>Model</th><th class='num'>Input</th><th class='num'>Output</th></tr>" + peer_rows + "</table>" if peer_rows else ""}

{cmp_html}

<h2>Cheaper alternatives</h2>
<p>{"Next cheaper option: <a href='/model/" + slug(cheaper["id"]) + "/'>" + html.escape(cheaper["display_name"]) + "</a> at " + money(cheaper["input_per_1m_usd"]) + " per 1M input tokens." if cheaper else "This is the cheapest tracked model in its class."}
{"Next step up: <a href='/model/" + slug(costlier["id"]) + "/'>" + html.escape(costlier["display_name"]) + "</a> at " + money(costlier["input_per_1m_usd"]) + " per 1M input tokens." if costlier else ""}</p>
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
            f"{BASE}/model/{s}/", body, ld))
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
<h1>{html.escape(a["display_name"])} vs {html.escape(b["display_name"])}: cost comparison</h1>
<p class="stamp">Prices updated {stamp[:10]} &middot; computed from live provider data</p>

<div class="answer">
<strong>Short answer:</strong> <a href="/model/{slug(win['id'])}/">{html.escape(win["display_name"])}</a> is cheaper on a
3:1 input/output blend &mdash; {money(round(min(bi,bj), 4))} per million tokens versus
{money(round(max(bi,bj), 4))}, a <strong>{delta:.0f}% difference</strong>.
{ctx_line}
</div>

<h2>Head to head</h2>
<table>
<tr><th></th><th>{html.escape(a["display_name"])}</th><th>{html.escape(b["display_name"])}</th></tr>
<tr><td>Input, per 1M tokens</td><td class="num">{money(a["input_per_1m_usd"])}</td><td class="num">{money(b["input_per_1m_usd"])}</td></tr>
<tr><td>Output, per 1M tokens</td><td class="num">{money(a["output_per_1m_usd"])}</td><td class="num">{money(b["output_per_1m_usd"])}</td></tr>
<tr><td>Blended 3:1, per 1M</td><td class="num">{money(round(bi,4))}</td><td class="num">{money(round(bj,4))}</td></tr>
<tr><td>Context window</td><td class="num">{a["context_length"]:,}</td><td class="num">{b["context_length"]:,}</td></tr>
<tr><td>Vendor</td><td class="num">{html.escape(a["vendor"])}</td><td class="num">{html.escape(b["vendor"])}</td></tr>
</table>

<h2>Monthly cost at real volumes</h2>
<table>
<tr><th>Workload (input / output)</th><th>{html.escape(a["display_name"])}</th><th>{html.escape(b["display_name"])}</th></tr>
{mix_rows}
</table>

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
            f"{BASE}/compare/{s}/", body, ld))
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


# ------------------------------------------------------------------ hub page

def build_hub(models: list[dict], stamp: str) -> None:
    rows = "".join(
        f'<tr><td>{i+1}</td><td><a href="/model/{slug(m["id"])}/">{html.escape(m["display_name"])}</a></td>'
        f'<td class="num">{money(m["input_per_1m_usd"])}</td>'
        f'<td class="num">{money(m["output_per_1m_usd"])}</td>'
        f'<td class="num">{m["context_length"]:,}</td></tr>'
        for i, m in enumerate(models[:300])
    )
    body = f"""
<h1>LLM API pricing: {len(models)} models compared</h1>
<p class="stamp">Live data pulled from provider APIs on {stamp[:10]}. Sorted by input price, cheapest first.</p>
<div class="answer">
<strong>Cheapest tracked model:</strong> {html.escape(models[0]["display_name"])} at {money(models[0]["input_per_1m_usd"])} per 1M input tokens.
<strong>Median input price:</strong> {money(models[len(models)//2]["input_per_1m_usd"])} per 1M tokens.
<strong>Dataset:</strong> {len(models)} models, refreshed daily.
</div>
<input type="search" id="q" placeholder="Filter by model or vendor..." aria-label="Filter models">
<table id="t">
<thead><tr><th>#</th><th>Model</th><th class="num">Input / 1M</th><th class="num">Output / 1M</th><th class="num">Context</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<script>
const q=document.getElementById('q'),rs=[...document.querySelectorAll('#t tbody tr')];
q.addEventListener('input',()=>{{const v=q.value.toLowerCase();rs.forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(v));}});
</script>
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
        f"{BASE}/", body, ld))


def build_sitemap(urls: list[str]) -> None:
    items = "".join(f"<url><loc>{BASE}{u}</loc></url>" for u in urls)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>')


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
        "",
    ]
    write("llms.txt", "\n".join(lines))


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
    build_hub(models, stamp)
    build_sitemap(["/"] + m_urls + c_urls)
    build_llms_txt(models, stamp)
    print(f"[build] {len(m_urls)} model pages, {len(c_urls)} comparison pages -> site/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())