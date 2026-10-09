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
    NON_PAGE = ("/sitemap.xml", "/llms.txt")  # served files, not generated routes
    for p in pages:
        html = p.read_text()
        # Strip <style>/<script> first: CSS contains 'text-decoration:none'
        # and JS contains 'undefined', which are not template leaks.
        visible = re.sub(r"<style.*?</style>|<script.*?</script>", "", html, flags=re.S)
        if "{{" in visible or "None" in visible or "nan." in visible.lower():
            placeholder_leak += 1
        if html.count("<h1>") != 1:
            check(False, f"page must have exactly one h1: {p}")

        for link in re.findall(r'href="(/[^"#]*)"', html):
            if link in NON_PAGE:
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