#!/usr/bin/env python3
"""Generate the static theme-preview pages.

This is a *review artifact*, not the production build. It renders the new
"Price Ledger" theme around dummy data so the look and feel can be inspected
without touching the live pipeline. The real site is built by
automation/mvp/build_pages.py; the header/footer/CSS here are what would be
moved into that template.

    python3 theme-preview/build_preview.py

Writes plain HTML into theme-preview/ next to assets/css and assets/js.
"""
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://toolsummary.com"

# --------------------------------------------------------------------- data
# A small slice of realistic rows. Enough to show sorting, filtering, the
# free-tier styling and the delta column.
MODELS = [
    ("Flint V1.0", "Recursive", 0.0, 0.0, 262144, "flat"),
    ("Nemotron 3.5 Super VL", "NVIDIA", 0.0, 0.0, 1000000, "flat"),
    ("DeepSeek V4.1 Flash Fast", "Coralbricks", 0.010, 1.20, 1048576, "down"),
    ("Qwen 2.5 Coder 7B", "Nebius", 0.010, 0.030, 32768, "flat"),
    ("GPT OSS 20B", "Darkbloom", 0.015, 0.070, 131072, "down"),
    ("Llama 3.2 11B Vision", "Lambda", 0.015, 0.025, 131072, "flat"),
    ("DeepSeek Flash Latest", "DeepSeek", 0.017, 0.600, 1048576, "down"),
    ("Granite 4.0 H Micro", "Cloudflare", 0.017, 0.112, 131000, "flat"),
    ("Llama Guard 3 8B", "Nebius", 0.020, 0.060, 128000, "up"),
    ("Qwen 2 VL 7B Instruct", "Nebius", 0.020, 0.060, 131072, "flat"),
    ("Ling 3.0 Flash", "InclusionAI", 0.021, 0.063, 262144, "down"),
    ("Hermes 3 8B", "Lambda", 0.025, 0.040, 131072, "flat"),
    ("Llama 3.2 1B Instruct", "Meta", 0.027, 0.201, 60000, "flat"),
    ("Mistral Nemo", "Mistral", 0.029, 0.030, 131072, "down"),
    ("Qwen 3.7 Flash", "Qwen", 0.030, 0.130, 1000000, "down"),
    ("Nova Micro", "Amazon", 0.035, 0.140, 128000, "flat"),
    ("Command R7B", "Cohere", 0.037, 0.150, 128000, "up"),
    ("Mercury 2.5", "Inception", 0.040, 0.150, 260000, "flat"),
    ("Ministral 3B", "Vercel", 0.040, 0.040, 128000, "flat"),
    ("GLM Flash Latest", "Z.ai", 0.042, 0.085, 1048576, "down"),
    ("Trinity Mini", "Together", 0.045, 0.150, 128000, "flat"),
    ("Claude Haiku 5.5", "Anthropic", 0.050, 0.250, 1000000, "down"),
    ("Solar Mini 4", "Upstage", 0.050, 0.200, 524288, "flat"),
    ("Gemma 3 4B It", "Google", 0.050, 0.100, 131072, "down"),
    ("Llama 3.1 8B Instruct", "Meta", 0.050, 0.080, 131072, "flat"),
    ("LFM 2.5 24B A2B", "Liquid", 0.050, 0.700, 128000, "up"),
    ("Minimax M2", "Minimax", 0.255, 1.02, 204800, "down"),
    ("DeepSeek Chat", "DeepSeek", 0.257, 1.03, 163840, "down"),
    ("Qwen 3.5 27B", "Qwen", 0.260, 2.60, 262144, "flat"),
    ("Minimax M2.7", "Minimax", 0.300, 1.20, 204800, "up"),
    ("GLM 5.2", "Z.ai", 0.034, 7.00, 1048576, "down"),
    ("Claude Opus 4", "Anthropic", 5.00, 25.00, 200000, "flat"),
    ("GPT-5.4", "OpenAI", 4.00, 16.00, 400000, "down"),
    ("Gemini 3.1 Pro", "Google", 2.50, 15.00, 1048576, "down"),
]

POSTS = [
    {
        "slug": "llm-api-pricing-changes-october-2026",
        "title": "What moved in LLM API pricing this October",
        "date": "2026-10-27",
        "read": "6 min read",
        "tag": "Price report",
        "excerpt": "DeepSeek cut output prices by up to 82% on its Flash line, while a "
                   "handful of smaller models quietly went the other way. Here is the "
                   "month in five charts and what it means if you are budgeting tokens.",
        "body": [
            ("p", "Every day this site records what each tracked model costs per million "
                  "input and output tokens. That log is now long enough to see a month "
                  "clearly, so this is the first of a recurring price report."),
            ("h2", "The headline: output tokens got cheaper, fast"),
            ("p", "DeepSeek's Flash line led the month, with output prices falling by "
                  "72\u201382% on several entries. That is the single largest move we "
                  "have recorded, and it drags the whole blended cost of a "
                  "chat-style workload down with it."),
            ("quote", "A model is only cheap for your workload if its input:output "
                      "ratio matches how you actually use it. A 20:1 output price is "
                      "irrelevant if you mostly send, not generate."),
            ("h2", "The counter-move nobody advertised"),
            ("p", "Not everything fell. A handful of smaller models raised prices, "
                  "which is usually a sign of a capacity crunch or a graduation out "
                  "of a promotional tier. Those are the rows worth a second look "
                  "before you commit a budget to them."),
            ("h2", "How to read the tables on this site"),
            ("p", "Prices are per million tokens, in USD, exactly as the provider "
                  "publishes them. The blended figure weights input to output 3:1, "
                  "which is a common chat workload, but your own ratio is the one "
                  "that matters. Use the comparison pages to put two candidates "
                  "side by side at your real volumes."),
            ("h2", "What is coming next"),
            ("p", "The plan is a weekly digest with the largest movers, and a "
                  "public history endpoint so you can pull the raw log yourself. "
                  "Until then, the daily table is the source of truth."),
        ],
    },
]

# ------------------------------------------------------------------ helpers


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


def slug(text: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def delta_html(kind: str) -> str:
    if kind == "down":
        return '<span class="delta delta--down" title="price fell since last snapshot">\u25bc 3.2%</span>'
    if kind == "up":
        return '<span class="delta delta--up" title="price rose since last snapshot">\u25b2 1.4%</span>'
    return '<span class="delta delta--flat">\u2014</span>'


def price_cell(v: float, kind: str) -> str:
    cls = "price price--free" if v == 0 else "price"
    return f'<td class="num"><span class="{cls}" data-value="{v}">{money(v)}</span>{delta_html(kind)}</td>'


def header(active: str) -> str:
    def cls(name: str) -> str:
        return ' aria-current="page"' if name == active else ""

    return f"""<a class="visually-hidden" href="#main">Skip to content</a>
<header class="masthead">
  <div class="wrap masthead__bar">
    <a class="brand" href="/">
      <span class="brand__mark">Tool<em>summary</em></span>
      <span class="brand__tag">LLM price ledger</span>
    </a>
    <button class="nav__toggle" type="button" aria-expanded="false" aria-controls="site-nav">Menu</button>
    <nav class="nav" id="site-nav" aria-label="Primary">
      <a href="/"{cls("models")}>Models</a>
      <a href="/compare/"{cls("compare")}>Compare</a>
      <a href="/blog/"{cls("blog")}>Blog</a>
      <a href="/submit/" class="nav__cta"{cls("submit")}>Submit a tool</a>
    </nav>
  </div>
</header>
<div class="ticker" aria-label="Latest price movement">
  <div class="wrap ticker__row">
    <div class="ticker__cell"><span class="ticker__label">Models tracked</span><span class="ticker__value">704</span></div>
    <div class="ticker__cell"><span class="ticker__label">Cheapest input</span><span class="ticker__value">Free</span></div>
    <div class="ticker__cell"><span class="ticker__label">Median input / 1M</span><span class="ticker__value">$0.400</span></div>
    <div class="ticker__cell"><span class="ticker__label">Biggest fall</span><span class="ticker__value">DeepSeek V4 Pro <span class="d d--down">\u25bc 7.8%</span></span></div>
    <div class="ticker__cell"><span class="ticker__label">Biggest rise</span><span class="ticker__value">DeepSeek V4.1 Flash <span class="d d--up">\u25b2 150%</span></span></div>
    <div class="ticker__cell"><span class="ticker__label">Updated</span><span class="ticker__value">2026-10-27</span></div>
  </div>
</div>"""


def footer() -> str:
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
          <li><a href="/sitemap.xml">Sitemap</a></li>
          <li><a href="/llms.txt">llms.txt</a></li>
        </ul>
      </div>
      <div>
        <p class="footer__h">Learn</p>
        <ul>
          <li><a href="/blog/">Blog</a></li>
          <li><a href="/blog/llm-api-pricing-changes-october-2026/">Latest price report</a></li>
          <li><a href="/#method">Methodology</a></li>
        </ul>
      </div>
      <div>
        <p class="footer__h">Site</p>
        <ul>
          <li><a href="/submit/">Submit a tool</a></li>
          <li><a href="/about/">About</a></li>
          <li><a href="/contact/">Contact</a></li>
          <li><a href="/privacy/">Privacy</a></li>
        </ul>
      </div>
    </div>
    <div class="footer__bottom">
      <span>\u00a9 <span data-year>2026</span> Toolsummary \u00b7 Prices from public provider APIs</span>
      <span>Always confirm on the provider's own pricing page before committing budget.</span>
    </div>
  </div>
</footer>"""


def shell(title: str, desc: str, canonical: str, active: str, body: str,
          ld: dict | None = None) -> str:
    ld = ld or {}
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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/css/theme.css">
<script type="application/ld+json">{json.dumps(ld)}</script>
</head>
<body>
{header(active)}
<main id="main">
{body}
</main>
{footer()}
<script src="/assets/js/theme.js" defer></script>
</body>
</html>
"""


def write(rel: str, content: str) -> None:
    p = HERE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    print("wrote", p.relative_to(HERE))


# ------------------------------------------------------------------- pages


def build_home() -> None:
    rows = []
    for i, (name, vendor, inp, out, ctx, kind) in enumerate(MODELS):
        rows.append(
            f'<tr>'
            f'<td class="rank" data-value="{i+1}">{i+1}</td>'
            f'<td class="name"><a href="/model/{slug(name)}/">{html.escape(name)}</a>'
            f'<br><span class="mut" style="font-size:12.5px">{html.escape(vendor)}</span></td>'
            f'{price_cell(inp, kind)}'
            f'{price_cell(out, kind)}'
            f'<td class="num" data-value="{ctx}">{ctx:,}</td>'
            f'</tr>'
        )
    body = f"""<div class="wrap">
  <section class="hero reveal">
    <div class="hero__rule"></div>
    <h1>LLM API pricing, recorded daily</h1>
    <p class="lede">Every tracked model, what it costs per million tokens, and how that
      changed since yesterday. No sign-up, no estimate \u2014 the numbers providers publish.</p>
  </section>

  <div class="answer reveal reveal-2">
    <strong>Cheapest tracked model:</strong> Flint V1.0 at <span class="answer__k">Free</span> per 1M input tokens.
    <strong>Median input price:</strong> <span class="answer__k">$0.400</span> per 1M tokens.
    <strong>Dataset:</strong> 704 models, refreshed daily.
  </div>

  <div class="stats reveal reveal-3">
    <div class="stat"><span class="stat__label">Models tracked</span>
      <div class="stat__value">704</div><div class="stat__sub">across 48 providers</div></div>
    <div class="stat"><span class="stat__label">Cheapest input / 1M</span>
      <div class="stat__value">Free</div><div class="stat__sub">17 models at $0.00</div></div>
    <div class="stat"><span class="stat__label">Median input / 1M</span>
      <div class="stat__value">$0.400</div><div class="stat__sub">down from $0.42 last month</div></div>
    <div class="stat"><span class="stat__label">Days on record</span>
      <div class="stat__value">42</div><div class="stat__sub">history since Sep 2026</div></div>
  </div>

  <section aria-labelledby="all-models">
    <h2 id="all-models" class="mt-0">All models</h2>
    <p class="stamp">Live data pulled from provider APIs on 2026-10-27. Sorted by input
      price, cheapest first. Click any column to re-sort.</p>

    <div class="search">
      <label for="q">Filter</label>
      <div class="search__field">
        <input type="search" id="q" placeholder="Filter by model or vendor\u2026" aria-label="Filter models">
        <span class="search__count">34 models</span>
      </div>
    </div>
    <div class="empty" role="status">No model matches that filter.</div>

    <div class="ledger-wrap">
      <table class="ledger" id="t">
        <caption>Showing a 34-model sample for theme review. The live table carries all 704.</caption>
        <thead>
          <tr>
            <th data-sort="num" style="width:52px">#</th>
            <th data-sort="text">Model</th>
            <th class="num" data-sort="num">Input / 1M</th>
            <th class="num" data-sort="num">Output / 1M</th>
            <th class="num" data-sort="num">Context</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
        <tfoot>
          <tr><td colspan="5">34 of 704 models shown \u00b7 updated 2026-10-27 04:30 UTC</td></tr>
        </tfoot>
      </table>
    </div>
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
          fact with a date on it \u2014 not a number someone typed over.</p>
        <div class="card__meta">42 days on record</div>
      </article>
      <article class="card">
        <h3>Readable by machines</h3>
        <p>Sitemap, <code>llms.txt</code> and structured data on every page, so agents and
          crawlers can cite the current number.</p>
        <div class="card__meta">Dataset schema.org markup</div>
      </article>
    </div>
  </section>

  <hr class="rule">

  <section>
    <h2 class="mt-0">From the blog</h2>
    <div class="post-list">
      <a class="post" href="/blog/llm-api-pricing-changes-october-2026/">
        <span class="post__meta">Price report \u00b7 2026-10-27 \u00b7 6 min read</span>
        <h3>What moved in LLM API pricing this October</h3>
        <p>DeepSeek cut output prices by up to 82% on its Flash line, while a handful of
          smaller models quietly went the other way.</p>
        <span class="post__more">Read the report \u2192</span>
      </a>
    </div>
  </section>
</div>"""
    ld = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "LLM API pricing dataset",
        "description": "Live input and output token pricing for 704 LLM API models.",
        "dateModified": "2026-10-27T04:30:00+00:00", "url": f"{BASE}/",
        "creator": {"@type": "Organization", "name": "Toolsummary"},
    }
    write("index.html", shell(
        "LLM API Pricing: 704 Models Compared (Updated 2026-10-27)",
        "Compare live input and output token prices for 704 LLM APIs. Cheapest model, "
        "median price, context windows and per-workload cost estimates, refreshed daily.",
        f"{BASE}/", "models", body, ld))


def build_submit() -> None:
    body = """<div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span>Submit a tool</nav>
  <div class="hero reveal">
    <h1>Submit a tool</h1>
    <p class="lede">Know a model or API we are missing, or a price we have wrong? Tell us
      and we will verify it against the provider's own pricing page before it appears.</p>
  </div>

  <div class="notice notice--info">
    <strong>What we list:</strong> LLM and inference APIs with published per-token pricing.
    We do not list resellers of another provider's models, and we do not accept payment for
    placement \u2014 every row is priced the same way.
  </div>

  <div id="submit-done" class="notice" hidden role="status">
    <strong>Thanks \u2014 that is queued.</strong> A human checks each submission against the
    provider's pricing page. You will not get an automated reply, but accepted rows appear
    in the daily refresh.
  </div>

  <form class="form" id="submit-form" novalidate>
    <div class="form__grid">
      <div class="field">
        <label for="tool-name">Tool or model name <span class="req">*</span></label>
        <input id="tool-name" name="tool-name" type="text" required minlength="2"
               placeholder="e.g. Claude Opus 4" autocomplete="off">
        <span class="err">Give the name exactly as the provider writes it.</span>
      </div>

      <div class="field">
        <label for="vendor">Provider <span class="req">*</span></label>
        <input id="vendor" name="vendor" type="text" required minlength="2"
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
        <input id="pricing-url" name="pricing-url" type="url" required
               placeholder="https://provider.com/pricing">
        <span class="err">We need a link we can verify against.</span>
      </div>

      <div class="field">
        <label for="input-price">Input price, per 1M tokens (USD)</label>
        <input id="input-price" name="input-price" type="number" min="0" step="0.0001"
               inputmode="decimal" placeholder="0.250">
        <span class="hint">Leave blank if you are not sure.</span>
      </div>

      <div class="field">
        <label for="output-price">Output price, per 1M tokens (USD)</label>
        <input id="output-price" name="output-price" type="number" min="0" step="0.0001"
               inputmode="decimal" placeholder="1.250">
        <span class="hint">Leave blank if you are not sure.</span>
      </div>

      <div class="field field--wide">
        <label for="notes">Notes</label>
        <textarea id="notes" name="notes"
          placeholder="Anything that helps us verify this \u2014 free tier limits, batch pricing, a launch date\u2026"></textarea>
      </div>

      <div class="field field--wide">
        <label for="email">Your email (optional)</label>
        <input id="email" name="email" type="email" placeholder="you@example.com"
               autocomplete="email">
        <span class="hint">Only used if we need to ask you a question about this row.</span>
      </div>
    </div>

    <div class="btn-row">
      <button class="btn" type="submit">Submit for review</button>
      <span class="mut" style="font-size:13.5px">Fields marked <span class="req">*</span> are required.</span>
    </div>
  </form>
</div>"""
    write("submit/index.html", shell(
        "Submit a tool - Toolsummary",
        "Submit an LLM API or model for inclusion in Toolsummary's daily price ledger.",
        f"{BASE}/submit/", "submit", body))


def build_blog_index() -> None:
    cards = "".join(
        f'<a class="post" href="/blog/{p["slug"]}/">'
        f'<span class="post__meta">{p["tag"]} \u00b7 {p["date"]} \u00b7 {p["read"]}</span>'
        f'<h3>{html.escape(p["title"])}</h3>'
        f'<p>{html.escape(p["excerpt"])}</p>'
        f'<span class="post__more">Read \u2192</span></a>'
        for p in POSTS
    )
    body = f"""<div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span>Blog</nav>
  <div class="hero reveal">
    <h1>The price ledger</h1>
    <p class="lede">Notes on what LLM APIs cost, what changed, and how to read a
      per-token price without getting the arithmetic wrong.</p>
  </div>

  <div class="post-list reveal reveal-2">{cards}</div>

  <p class="stamp" style="margin-top:22px">One post so far \u2014 this is a placeholder for
    the theme review.</p>
</div>"""
    write("blog/index.html", shell(
        "Blog - Toolsummary", "Notes on LLM API pricing and how to read it.",
        f"{BASE}/blog/", "blog", body))


def build_blog_post() -> None:
    p = POSTS[0]
    blocks = []
    for kind, text in p["body"]:
        if kind == "h2":
            blocks.append(f"<h2>{html.escape(text)}</h2>")
        elif kind == "quote":
            blocks.append(f"<blockquote>{html.escape(text)}</blockquote>")
        else:
            blocks.append(f"<p>{html.escape(text)}</p>")
    body = f"""<div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span><a href="/blog/">Blog</a><span>/</span>Price report</nav>
  <article class="prose">
    <header class="hero reveal">
      <h1>{html.escape(p["title"])}</h1>
      <p class="lede">{html.escape(p["excerpt"])}</p>
    </header>
    <div class="byline">
      <div class="byline__avatar">T</div>
      <div>
        <div class="byline__name">The Toolsummary desk</div>
        <div class="byline__role">{p["date"]} \u00b7 {p["read"]}</div>
      </div>
    </div>
    {''.join(blocks)}
    <hr class="rule">
    <p class="stamp">This is a placeholder post for the theme review. The figures are
      illustrative; the live site reads them from the daily price log.</p>
  </article>
</div>"""
    ld = {
        "@context": "https://schema.org", "@type": "BlogPosting",
        "headline": p["title"], "datePublished": p["date"],
        "dateModified": p["date"], "url": f"{BASE}/blog/{p['slug']}/",
        "author": {"@type": "Organization", "name": "Toolsummary"},
    }
    write(f"blog/{p['slug']}/index.html", shell(
        f"{p['title']} - Toolsummary", p["excerpt"],
        f"{BASE}/blog/{p['slug']}/", "blog", body, ld))


def build_model_pages() -> None:
    """One page per sample model, so every link in the table resolves."""
    for name, vendor, inp, out, ctx, _kind in MODELS:
        blended = (inp * 3 + out) / 4
        mult = f"{out / inp:.2f}&times;" if inp else "n/a (free tier)"
        if inp == 0 and out == 0:
            verdict = (f"{html.escape(name)} is published at $0.00 per million input and "
                       f"output tokens &mdash; it is a free-tier model. Free tiers normally "
                       f"carry rate limits and are not intended for production traffic, so "
                       f"confirm the current terms before relying on it.")
        else:
            verdict = (f"{html.escape(name)} costs <strong>{money(inp)} per million input "
                       f"tokens</strong> and <strong>{money(out)} per million output "
                       f"tokens</strong>. That is a 3:1 blended rate of "
                       f"<strong>{money(round(blended, 4))} per million tokens</strong>.")
        body = f"""<div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span><a href="/">Models</a><span>/</span>{html.escape(vendor)}</nav>
  <div class="hero reveal">
    <h1>{html.escape(name)} pricing</h1>
    <p class="stamp">Source: {html.escape(vendor)} &middot; updated 2026-10-27</p>
  </div>

  <div class="answer reveal reveal-2">
    <strong>Short answer:</strong> {verdict}
  </div>

  <div class="stats reveal reveal-3">
    <div class="stat"><span class="stat__label">Input / 1M</span><div class="stat__value">{money(inp)}</div></div>
    <div class="stat"><span class="stat__label">Output / 1M</span><div class="stat__value">{money(out)}</div></div>
    <div class="stat"><span class="stat__label">Output \u00f7 input</span><div class="stat__value">{mult}</div></div>
    <div class="stat"><span class="stat__label">Context window</span><div class="stat__value">{ctx:,}</div></div>
  </div>

  <h2>Price breakdown</h2>
  <div class="ledger-wrap">
    <table class="ledger">
      <thead><tr><th>Metric</th><th class="num">Value</th></tr></thead>
      <tbody>
        <tr><td>Input, per 1M tokens</td><td class="num">{money(inp)}</td></tr>
        <tr><td>Output, per 1M tokens</td><td class="num">{money(out)}</td></tr>
        <tr><td>Output \u00f7 input multiple</td><td class="num">{mult}</td></tr>
        <tr><td>3:1 blended, per 1M tokens</td><td class="num">{money(round(blended, 4))}</td></tr>
        <tr><td>Context window</td><td class="num">{ctx:,} tokens</td></tr>
        <tr><td>Vendor</td><td class="num">{html.escape(vendor)}</td></tr>
      </tbody>
    </table>
  </div>

  <h2>What a typical workload costs</h2>
  <div class="ledger-wrap">
    <table class="ledger">
      <thead><tr><th>Monthly volume</th><th class="num">Input cost</th><th class="num">Output cost</th><th class="num">Total</th></tr></thead>
      <tbody>
        <tr><td>1M in / 250K out</td><td class="num">{money(inp * 1e6 / 1e6)}</td><td class="num">{money(out * 2.5e5 / 1e6)}</td><td class="num">{money((inp * 1e6 + out * 2.5e5) / 1e6)}</td></tr>
        <tr><td>10M in / 2.5M out</td><td class="num">{money(inp * 1e7 / 1e6)}</td><td class="num">{money(out * 2.5e6 / 1e6)}</td><td class="num">{money((inp * 1e7 + out * 2.5e6) / 1e6)}</td></tr>
        <tr><td>100M in / 25M out</td><td class="num">{money(inp * 1e8 / 1e6)}</td><td class="num">{money(out * 2.5e7 / 1e6)}</td><td class="num">{money((inp * 1e8 + out * 2.5e7) / 1e6)}</td></tr>
      </tbody>
    </table>
  </div>

  <h2>Cheaper alternatives</h2>
  <p>Every price here is recomputed on the daily refresh, so this page always reflects
    the provider's current published rate.</p>
</div>"""
        ld = {
            "@context": "https://schema.org", "@type": "WebPage",
            "name": f"{name} pricing", "dateModified": "2026-10-27T04:30:00+00:00",
            "url": f"{BASE}/model/{slug(name)}/",
            "isPartOf": {"@type": "Dataset", "name": "LLM API pricing dataset"},
        }
        write(f"model/{slug(name)}/index.html", shell(
            f"{name} Pricing ({money(inp)}/1M in) - Updated 2026-10-27",
            f"{name} API cost: {money(inp)} per 1M input tokens, {money(out)} per 1M "
            f"output tokens. Live pricing, cost examples and cheaper alternatives.",
            f"{BASE}/model/{slug(name)}/", "models", body, ld))


PAIRS = [
    ("Claude Opus 4", "GPT-5.4", "claude-opus-4-vs-gpt-5-4"),
    ("Claude Opus 4", "Gemini 3.1 Pro", "claude-opus-4-vs-gemini-3-1-pro"),
    ("DeepSeek Chat", "Minimax M2", "deepseek-chat-vs-minimax-m2"),
    ("Mistral Nemo", "Llama 3.2 1B Instruct", "mistral-nemo-vs-llama-3-2-1b-instruct"),
    ("Qwen 3.5 27B", "GLM Flash Latest", "qwen-3-5-27b-vs-glm-flash-latest"),
    ("Nova Micro", "Command R7B", "nova-micro-vs-command-r7b"),
]


def _model_by_name(name: str):
    for m in MODELS:
        if m[0] == name:
            return m
    return None


def build_compare_pages() -> None:
    for x, y, s in PAIRS:
        ma, mb = _model_by_name(x), _model_by_name(y)
        if not ma or not mb:
            continue
        an, av, ai, ao, ac, _ = ma
        bn, bv, bi_, bo, bc, _ = mb
        bi = (ai * 3 + ao) / 4
        bj = (bi_ * 3 + bo) / 4
        win, lose = (ma, mb) if bi < bj else (mb, ma)
        delta = abs(bi - bj) / max(bi, bj) * 100 if max(bi, bj) else 0.0
        wider, other = (ma, mb) if ac > bc else (mb, ma)
        ctx_line = (f"Both offer the same {ac:,}-token context window, so cost is the "
                    f"deciding factor.") if ac == bc else (
                    f"{html.escape(wider[0])} offers the larger context window at "
                    f"{wider[4]:,} tokens, against {other[4]:,} for {html.escape(other[0])}.")
        advice = (f"Because the context windows are identical, the cheaper option is the "
                  f"better default. Choose <strong>{html.escape(win[0])}</strong> unless you "
                  f"are already standardised on {html.escape(lose[1])} tooling.") if ac == bc else (
                  f"Pick <strong>{html.escape(wider[0])}</strong> when you need the longer "
                  f"context window ({wider[4]:,} vs {other[4]:,} tokens). "
                  f"Pick <strong>{html.escape(win[0])}</strong> when price per token dominates "
                  f"your workload &mdash; high-volume classification, extraction, or batch "
                  f"summarisation.")
        body = f"""<div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span><a href="/compare/">Compare</a><span>/</span>{html.escape(an)} vs {html.escape(bn)}</nav>
  <div class="hero reveal">
    <h1>{html.escape(an)} vs {html.escape(bn)}: cost comparison</h1>
    <p class="stamp">Prices updated 2026-10-27 &middot; computed from live provider data</p>
  </div>

  <div class="answer reveal reveal-2">
    <strong>Short answer:</strong> <a href="/model/{slug(win[0])}/">{html.escape(win[0])}</a>
    is cheaper on a 3:1 input/output blend &mdash; {money(round(min(bi,bj), 4))} per million
    tokens versus {money(round(max(bi,bj), 4))}, a <strong>{delta:.0f}% difference</strong>.
    {ctx_line}
  </div>

  <h2>Head to head</h2>
  <div class="ledger-wrap">
    <table class="ledger">
      <thead><tr><th></th><th class="num">{html.escape(an)}</th><th class="num">{html.escape(bn)}</th></tr></thead>
      <tbody>
        <tr><td>Input, per 1M tokens</td><td class="num">{money(ai)}</td><td class="num">{money(bi_)}</td></tr>
        <tr><td>Output, per 1M tokens</td><td class="num">{money(ao)}</td><td class="num">{money(bo)}</td></tr>
        <tr><td>Blended 3:1, per 1M</td><td class="num">{money(round(bi,4))}</td><td class="num">{money(round(bj,4))}</td></tr>
        <tr><td>Context window</td><td class="num">{ac:,}</td><td class="num">{bc:,}</td></tr>
        <tr><td>Vendor</td><td class="num">{html.escape(av)}</td><td class="num">{html.escape(bv)}</td></tr>
      </tbody>
    </table>
  </div>

  <h2>Monthly cost at real volumes</h2>
  <div class="ledger-wrap">
    <table class="ledger">
      <thead><tr><th>Workload (in / out)</th><th class="num">{html.escape(an)}</th><th class="num">{html.escape(bn)}</th></tr></thead>
      <tbody>
        <tr><td>1M in / 250K out</td><td class="num">{money((ai*1e6+ao*2.5e5)/1e6)}</td><td class="num">{money((bi_*1e6+bo*2.5e5)/1e6)}</td></tr>
        <tr><td>10M in / 2.5M out</td><td class="num">{money((ai*1e7+ao*2.5e6)/1e6)}</td><td class="num">{money((bi_*1e7+bo*2.5e6)/1e6)}</td></tr>
        <tr><td>100M in / 25M out</td><td class="num">{money((ai*1e8+ao*2.5e7)/1e6)}</td><td class="num">{money((bi_*1e8+bo*2.5e7)/1e6)}</td></tr>
      </tbody>
    </table>
  </div>

  <h2>Which should you pick?</h2>
  <p>{advice}</p>

  <h2>Related</h2>
  <ul>
    <li><a href="/model/{slug(an)}/">{html.escape(an)} full pricing</a></li>
    <li><a href="/model/{slug(bn)}/">{html.escape(bn)} full pricing</a></li>
  </ul>
</div>"""
        write(f"compare/{s}/index.html", shell(
            f"{an} vs {bn}: Which Is Cheaper? (2026-10-27)",
            f"Cost comparison of {an} and {bn}. Live input and output token prices, "
            f"monthly cost examples and context window sizes, updated 2026-10-27.",
            f"{BASE}/compare/{s}/", "compare", body))


def build_compare_index() -> None:
    cards = "".join(
        f'<a class="card" href="/compare/{s}/" style="text-decoration:none">'
        f'<h3>{html.escape(x)} <span class="mut">vs</span> {html.escape(y)}</h3>'
        f'<p>Blended cost, context window and monthly examples side by side.</p>'
        f'<div class="card__meta">Head-to-head</div></a>'
        for x, y, s in PAIRS
    )
    body = f"""<div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span>Compare</nav>
  <div class="hero reveal">
    <h1>Head-to-head comparisons</h1>
    <p class="lede">Two models, one table, and an honest answer about which is cheaper
      for your workload \u2014 including when the context windows tie and price is the only
      difference.</p>
  </div>
  <div class="cards reveal reveal-2">{cards}</div>
  <p class="stamp" style="margin-top:22px">6 of 400 comparison pages. The live set is
    generated from adjacent-in-price and same-vendor pairs.</p>
</div>"""
    write("compare/index.html", shell(
        "Compare LLM API prices - Toolsummary",
        "Head-to-head LLM API cost comparisons with monthly workload examples.",
        f"{BASE}/compare/", "compare", body))


def build_404() -> None:
    body = """<div class="wrap">
  <div class="hero reveal">
    <h1>That page is not in the ledger</h1>
    <p class="lede">The model or comparison you asked for may have been delisted
      upstream, or the URL is mistyped.</p>
    <div class="btn-row">
      <a class="btn" href="/">Browse all models</a>
      <a class="btn btn--ghost" href="/blog/">Read the blog</a>
    </div>
  </div>
</div>"""
    write("404.html", shell("Page not found - Toolsummary",
                            "That page does not exist.", f"{BASE}/404.html", "", body))


def build_simple_pages() -> None:
    """About / Contact / Privacy, so no nav link dead-ends in the review."""
    about = """<div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span>About</nav>
  <article class="prose">
    <header class="hero reveal">
      <h1>About Toolsummary</h1>
      <p class="lede">A daily record of what LLM APIs cost, kept in the open because a
        price is the one fact a language model cannot reconstruct from memory.</p>
    </header>
    <div class="byline">
      <div class="byline__avatar">T</div>
      <div><div class="byline__name">The Toolsummary desk</div>
      <div class="byline__role">Independent \u00b7 no sponsored placement</div></div>
    </div>
    <h2>What this is</h2>
    <p>Toolsummary tracks published per-token pricing for LLM and inference APIs and
      records a snapshot every day. That log is the product: it turns "what does this
      cost" into a fact with a date on it, rather than a number someone typed over.</p>
    <h2>How prices are collected</h2>
    <p>Prices come from provider APIs and public price lists, normalised to USD per
      million tokens. Anything ambiguous goes to a human review queue instead of onto a
      page. A rejected row never enters the history.</p>
    <h2>Independence</h2>
    <p>No provider pays for placement, and no row is priced differently from any other.
      If a number is wrong, the fastest fix is the submit form.</p>
    <h2>Corrections</h2>
    <p>Spotted a stale price? <a href="/submit/">Send it in</a> with the provider's own
      pricing page and it will be checked on the next refresh.</p>
  </article>
</div>"""

    contact = """<div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span>Contact</nav>
  <div class="hero reveal">
    <h1>Contact</h1>
    <p class="lede">One form, and it reaches a person.</p>
  </div>
  <div class="cards">
    <article class="card">
      <h3>Corrections and data</h3>
      <p>The fastest route for a wrong or missing price is the submit form \u2014 it asks
        for exactly what is needed to verify a row.</p>
      <div class="card__meta"><a href="/submit/">Open the submit form</a></div>
    </article>
    <article class="card">
      <h3>Everything else</h3>
      <p>Partnerships, data licensing, or a question about the history log.</p>
      <div class="card__meta">hello@toolsummary.com</div>
    </article>
  </div>
</div>"""

    privacy = """<div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span>Privacy</nav>
  <article class="prose">
    <header class="hero reveal"><h1>Privacy</h1>
    <p class="lede">The short version: this site collects as little as it can and sells
      nothing.</p></header>
    <h2>What is collected</h2>
    <p>The public pages are static and read no cookies for tracking. If you use the
      submit form, the details you enter are used only to verify the row you sent.</p>
    <h2>What is not done</h2>
    <p>No data is sold, and no provider is given access to submissions. Email addresses
      from the submit form are used only to ask a clarifying question.</p>
    <h2>Analytics</h2>
    <p>Aggregate, cookie-free page counts only \u2014 enough to know which pages are useful,
      not enough to identify a reader.</p>
  </article>
</div>"""

    write("about/index.html", shell("About - Toolsummary",
        "What Toolsummary is, how prices are collected, and its independence policy.",
        f"{BASE}/about/", "", about))
    write("contact/index.html", shell("Contact - Toolsummary",
        "How to reach Toolsummary about corrections, data or partnerships.",
        f"{BASE}/contact/", "", contact))
    write("privacy/index.html", shell("Privacy - Toolsummary",
        "What Toolsummary collects and what it does not.", f"{BASE}/privacy/", "", privacy))


def build_served_files() -> None:
    """sitemap.xml and llms.txt so the footer links resolve in the preview."""
    routes = ["/", "/compare/", "/blog/", "/blog/llm-api-pricing-changes-october-2026/",
              "/submit/", "/about/", "/contact/", "/privacy/"]
    for name, *_ in MODELS:
        routes.append(f"/model/{slug(name)}/")
    for _x, _y, s in PAIRS:
        routes.append(f"/compare/{s}/")
    items = "".join(f"<url><loc>{BASE}{u}</loc></url>" for u in routes)
    write("sitemap.xml",
          f'<?xml version="1.0" encoding="UTF-8"?>\n'
          f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>')
    write("llms.txt", "\n".join([
        "# Toolsummary - LLM API pricing",
        "",
        "> Live input/output token pricing for 704 LLM API models, refreshed daily.",
        "> Last updated: 2026-10-27",
        "",
        "## Key facts",
        "- Models tracked: 704",
        "- Cheapest input price: Flint V1.0 at Free per 1M tokens",
        "- Median input price: $0.400 per 1M tokens",
        "",
        "## Pages",
        f"- {BASE}/ - full sortable table",
        f"- {BASE}/model/<slug>/ - per-model pricing and workload cost examples",
        f"- {BASE}/compare/<a>-vs-<b>/ - head-to-head cost comparisons",
        f"- {BASE}/blog/ - pricing notes and reports",
        f"- {BASE}/submit/ - submit a tool or a correction",
        "",
    ]))


def main() -> int:
    build_home()
    build_submit()
    build_blog_index()
    build_blog_post()
    build_compare_index()
    build_compare_pages()
    build_model_pages()
    build_simple_pages()
    build_served_files()
    build_404()
    print("\nPreview written. Serve it with:")
    print(f"  python3 -m http.server 8080 --directory {HERE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
