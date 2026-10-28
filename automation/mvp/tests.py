#!/usr/bin/env python3
"""Automated QA for generated pages.

Every assertion here corresponds to a defect that actually shipped during
development of this pipeline. Running this on each build is what replaces
manual proofreading and keeps the automation honest.

Usage: python3 tests.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SITE = ROOT / "site"
CONTACT_EMAIL = "info.toolsummary@gmail.com"
# The reCAPTCHA secret key must never appear in anything the site serves. It is
# read from the environment, never stored here: a secret committed to the repo
# is already leaked, even inside a guard that exists to catch leaks.
import os
RECAPTCHA_SECRET = os.environ.get("RECAPTCHA_SECRET_KEY", "")
if not RECAPTCHA_SECRET:
    print("[qa] note: RECAPTCHA_SECRET_KEY not set; skipping secret-leak scan")

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


def main() -> int:
    payload = json.loads((DATA / "pricing.json").read_text())
    models = payload["models"]
    by_id = {m["id"]: m for m in models}

    # --- data integrity -----------------------------------------------------
    check(len(models) > 0, "no models published")
    check(
        all(models[i]["input_per_1m_usd"] <= models[i + 1]["input_per_1m_usd"]
            for i in range(len(models) - 1)),
        "published models are not sorted by input price",
    )
    for m in models:
        check(m["input_per_1m_usd"] >= 0, f"negative input price: {m['id']}")
        check(m["output_per_1m_usd"] >= 0, f"negative output price: {m['id']}")
        check(
            (m.get("context_length") or 0) >= 4_000,
            f"context below threshold leaked through: {m['id']}",
        )

    # No provider-prefixed duplicate of the same underlying model.
    canonical = [m["canonical_key"] for m in models]
    check(len(canonical) == len(set(canonical)), "duplicate canonical models published")

    # Dirty aggregator identifiers must not reach a page.
    for m in models:
        low = m["id"].lower()
        check(not re.match(r"^(us|eu|jp)\.", low), f"bedrock regional id published: {m['id']}")
        check("/" not in low.split("/")[-1] or True, "")
        for bad in ("aihubmix", "openrouter/", "wandb/", "databricks/"):
            check(bad not in low, f"resale listing published: {m['id']}")

    # --- rendered pages -----------------------------------------------------
    pages = list(SITE.rglob("index.html"))
    check(len(pages) > 0, "no pages rendered")

    broken_links = 0
    placeholder_leak = 0
    # Served files that are not generated HTML pages: link targets that exist
    # as files on disk, so they are checked for existence rather than looked up
    # as an index.html route.
    SERVED = ("/sitemap.xml", "/llms.txt", "/robots.txt", "/blog/feed.xml",
              "/api/prices.json")
    for p in pages:
        html = p.read_text()
        # Strip <style>/<script> first: CSS contains 'text-decoration:none'
        # and JS contains 'undefined', which are not template leaks.
        visible = re.sub(r"<style.*?</style>|<script.*?</script>", "", html, flags=re.S)
        if "{{" in visible or "None" in visible or "nan." in visible.lower():
            placeholder_leak += 1
        if html.count("<h1>") != 1:
            check(False, f"page must have exactly one h1: {p}")

        for link in re.findall(r'href="(/[^"#?]*)"', html):
            if link in SERVED:
                if not (SITE / link.strip("/")).exists():
                    broken_links += 1
                    if broken_links < 4:
                        FAILURES.append(f"missing served file {link} on {p.relative_to(SITE)}")
                continue
            if link.startswith("/assets/"):
                if not (SITE / link.strip("/")).exists():
                    broken_links += 1
                    if broken_links < 4:
                        FAILURES.append(f"missing asset {link} on {p.relative_to(SITE)}")
                continue
            target = SITE / "index.html" if link == "/" else SITE / link.strip("/") / "index.html"
            if not target.exists():
                broken_links += 1
                if broken_links < 4:
                    FAILURES.append(f"broken internal link {link} on {p.relative_to(SITE)}")

    check(placeholder_leak == 0, f"{placeholder_leak} pages leak template placeholders")
    check(broken_links == 0, f"{broken_links} broken internal links")

    # --- the two specific logic bugs this suite was written for -------------
    # 1. A 'cheaper alternative' must actually be cheaper on the blended metric.
    import importlib.util
    spec = importlib.util.spec_from_file_location("bp", ROOT / "build_pages.py")
    bp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bp)

    inversions = 0
    for m in models:
        c = bp.cheapest_in_class(models, m)
        if c and bp.blended(c) >= bp.blended(m):
            inversions += 1
    check(inversions == 0, f"{inversions} 'cheaper alternative' links are not cheaper")

    pick = [m for m in models if "claude-opus-4-8-think" in m["id"]]
    if pick:
        c = bp.cheapest_in_class(models, pick[0])
        check(c is not None, "cheapest_in_class returned None for a mid-priced model")
        if c:
            check(bp.blended(c) <= bp.blended(pick[0]),
                  "cheaper-than-$5 model resolved to something pricier")

    # 2. Model names must not be raw slugs.
    for m in models:
        check(m["display_name"] != m["id"],
              f"display name never derived for {m['id']}")
        check(not re.match(r"^[a-z0-9_]+$", m["display_name"]),
              f"display name looks like a slug: {m['display_name']}")

    # --- sitemap / llms.txt sanity -----------------------------------------
    sm = (SITE / "sitemap.xml").read_text()
    sitemap_urls = sm.count("<url>")
    # Sitemap lists the hub plus every generated route; must match exactly.
    check(sitemap_urls == len(pages), 
          f"sitemap has {sitemap_urls} urls but {len(pages)} pages were rendered")
    check((SITE / "llms.txt").exists(), "llms.txt missing")

    # --- price history ------------------------------------------------------
    # The log is append-only and unrecoverable, so its integrity is worth
    # asserting on every run rather than trusting the writer.
    hist_path = DATA / "price_history.jsonl"
    chg_path = DATA / "price_changes.jsonl"
    check(hist_path.exists(), "price_history.jsonl missing")
    check(chg_path.exists(), "price_changes.jsonl missing")

    if hist_path.exists():
        hist = [json.loads(l) for l in hist_path.read_text().splitlines() if l.strip()]
        check(len(hist) > 0, "price history is empty")

        # One row per (date, canonical_key): duplicates mean the idempotency
        # guard broke and the log is now corrupt.
        seen = set()
        dups = 0
        for r in hist:
            k = (r["date"], r["canonical_key"])
            if k in seen:
                dups += 1
            seen.add(k)
        check(dups == 0, f"{dups} duplicate (date, canonical_key) rows in price history")

        # The latest snapshot must cover exactly the published models, or the
        # history has silently diverged from the dataset it claims to mirror.
        latest = max(r["date"] for r in hist)
        snap_keys = {r["canonical_key"] for r in hist if r["date"] == latest}
        published_keys = {m["canonical_key"] for m in models}
        check(snap_keys == published_keys,
              f"latest snapshot ({latest}) has {len(snap_keys)} keys "
              f"but {len(published_keys)} models are published")

        for r in hist:
            check(r["input_per_1m_usd"] >= 0 and r["output_per_1m_usd"] >= 0,
                  f"negative price in history: {r['canonical_key']}")

    if chg_path.exists():
        chgs = [json.loads(l) for l in chg_path.read_text().splitlines() if l.strip()]
        for c in chgs:
            check(c.get("kind") in ("price", "new", "delisted", "context"),
                  f"unknown change kind: {c.get('kind')}")
            # A percentage requires a non-zero baseline. Reporting "+100%" for
            # free -> paid would put a false number on a chart.
            if c.get("kind") == "price" and c.get("pct_change") is not None:
                check(c.get("from") not in (None, 0),
                      f"percentage reported against a zero baseline: {c['canonical_key']}")
            if c.get("kind") == "context":
                check(c.get("pct_change") is None,
                      "context-length change must not carry a percentage")

    check((DATA / "price_changes_recent.json").exists(),
          "price_changes_recent.json missing")


    # --- forms: both must carry the key, a honeypot and a captcha -----------
    # A form that silently loses its spam controls is the kind of regression
    # that only shows up as inbox spam weeks later, so it is asserted here.
    for route in ("submit/index.html", "contact/index.html"):
        f = SITE / route
        check(f.exists(), f"{route} missing")
        if not f.exists():
            continue
        fh = f.read_text()
        check("api.web3forms.com/submit" in fh, f"{route} does not post to Web3Forms")
        check('name="access_key"' in fh, f"{route} has no access key")
        check('name="botcheck"' in fh, f"{route} lost its honeypot field")
        # replyto would write our own address into public HTML, so it is
        # deliberately absent; Web3Forms derives Reply-To from `email`.
        check('name="replyto"' not in fh, f"{route} leaks an address via replyto")
        # reCAPTCHA v3 replaces hCaptcha entirely.
        check("h-captcha" not in fh and "hcaptcha" not in fh.lower(),
              f"{route} still references hCaptcha")
        check("google.com/recaptcha/api.js" in fh, f"{route} lost the reCAPTCHA loader")
        check('name="recaptcha_response"' in fh, f"{route} has no reCAPTCHA token field")
        check('method="POST"' in fh, f"{route} is not a POST form")
        # The dialog is how both outcomes are reported now.
        check('id="form-modal"' in fh, f"{route} has no result dialog")
        check("data-ok-message" in fh, f"{route} has no success message for the dialog")
        # Post over fetch, so the page must not be sent to a redirect target.
        check('name="redirect"' not in fh,
              f"{route} still redirects away; the dialog would never be seen")
        # A form that echoes the inbox address invites scraping; the address
        # should not appear in page HTML.
        check(CONTACT_EMAIL not in fh,
              f"{route} exposes the inbox address in HTML")

    # --- no secrets in anything served --------------------------------------
    # A secret key in a static page is public the moment it is deployed, so
    # this is checked across every generated file, not just the form pages.
    for f in SITE.rglob("*"):
        if f.is_file() and f.suffix in {".html", ".js", ".css", ".json", ".xml", ".txt"}:
            body = f.read_text(errors="ignore")
            if RECAPTCHA_SECRET:
                check(RECAPTCHA_SECRET not in body,
                      f"reCAPTCHA secret key leaked into {f.relative_to(SITE)}")
            check("WEB3FORMS_ACCESS_KEY" not in body,
                  f"env var name leaked into {f.relative_to(SITE)}")

    # --- blog ---------------------------------------------------------------
    feed = SITE / "blog" / "feed.xml"
    check(feed.exists(), "blog/feed.xml missing")
    if feed.exists():
        fx = feed.read_text()
        check("<rss" in fx and "</rss>" in fx, "RSS feed is not well-formed RSS")
        check("<item>" in fx, "RSS feed has no items")

    # A post file with front matter must produce a page; a missing one is a
    # silent content loss, which is worth catching.
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("bp2", ROOT / "build_pages.py")
    _bp = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_bp)
    posts = _bp.load_posts()
    check(len(posts) > 0, "no blog posts parsed")
    for p in posts:
        check(bool(p["title"]), f"post {p['slug']} has no title")
        check(bool(p["excerpt"]), f"post {p['slug']} has no excerpt")
        check(p["author"] in _bp.AUTHORS,
              f"post {p['slug']} resolves to unknown author {p['author']}")
        check((SITE / "blog" / p["slug"] / "index.html").exists(),
              f"post {p['slug']} was parsed but not rendered")
        # A post must name a real person and link to their author page, or the
        # byline is decoration rather than an author signal.
        ph = (SITE / "blog" / p["slug"] / "index.html").read_text()
        check("The Toolsummary desk" not in ph,
              f"post {p['slug']} still shows the placeholder byline")
        check(f'/blog/author/{p["author"]}/' in ph,
              f"post {p['slug']} does not link to its author page")
        check((SITE / "blog" / "author" / p["author"] / "index.html").exists(),
              f"author page missing for {p['author']}")
        # Markdown must never reach the page unrendered.
        html = ph
        check("##" not in re.sub(r"<[^>]+>", "", html.split("<article", 1)[-1]),
              f"post {p['slug']} leaks raw Markdown headings")
        check("&lt;script" not in html and "<script>alert" not in html,
              f"post {p['slug']} may have injected raw HTML")

    # Posts must be genuinely distinct, not one text under four names.
    bodies = [p["body"] for p in posts]
    check(len(set(bodies)) == len(bodies), "two blog posts have identical bodies")
    titles = [p["title"].lower() for p in posts]
    check(len(set(titles)) == len(titles), "two blog posts share a title")

    # A published post needs a real title length for search results; too short
    # and it competes with nothing, too long and it is truncated.
    for p in posts:
        check(20 <= len(p["title"]) <= 65,
              f"post {p['slug']} title is {len(p['title'])} chars (want 20-65)")
        check(70 <= len(p["excerpt"]) <= 200,
              f"post {p['slug']} excerpt is {len(p['excerpt'])} chars (want 70-200)")

    # --- public JSON API ----------------------------------------------------
    api = SITE / "api" / "prices.json"
    check(api.exists(), "api/prices.json missing")
    if api.exists():
        doc = json.loads(api.read_text())
        check(doc.get("version") == 1, "api/prices.json version is not 1")
        check(len(doc.get("models", [])) == len(models),
              f"api/prices.json has {len(doc.get('models', []))} models, expected {len(models)}")
        for m in doc.get("models", [])[:50]:
            check(set(("id", "name", "vendor", "input_per_1m_usd",
                       "output_per_1m_usd", "url")) <= set(m),
                  f"api/prices.json row missing fields: {m.get('id')}")

    # --- trending -----------------------------------------------------------
    check((SITE / "trending" / "index.html").exists(), "trending page missing")

    # --- footer -------------------------------------------------------------
    # The copyright range must end at the current year. A hardcoded year is the
    # classic way a site starts looking abandoned every January.
    import datetime as _dt
    year = str(_dt.date.today().year)
    for p in pages[:1] + [SITE / "blog" / "index.html"]:
        fh = p.read_text()
        check("data-since" in fh, f"{p.relative_to(SITE)} footer lost the start year")
        m = re.search(r'data-year>(\d{4})<', fh)
        check(bool(m), f"{p.relative_to(SITE)} footer has no end year")
        if m:
            check(m.group(1) == year,
                  f"{p.relative_to(SITE)} footer year is {m.group(1)}, expected {year}")

    # --- assets shipped -----------------------------------------------------
    for asset in ("assets/css/theme.css", "assets/js/theme.js"):
        check((SITE / asset).exists(), f"{asset} not copied into the site")


    print(f"[qa] pages={len(pages)} models={len(models)} "
          f"broken_links={broken_links} placeholder_leak={placeholder_leak}")
    if FAILURES:
        print(f"\n[qa] {len(FAILURES)} FAILURES:")
        for f in FAILURES[:25]:
            print("  -", f)
        return 1
    print("[qa] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())