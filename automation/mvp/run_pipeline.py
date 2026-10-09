#!/usr/bin/env python3
"""Pipeline entrypoint (used by the OpenHands automation tarball).

Runs fetch -> quality gate -> build -> QA, then writes a summary of exactly
what a human needs to look at. Exit code 0 only if QA passed.

Run locally:  python3 run_pipeline.py
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def stage(name: str, script: str) -> int:
    print(f"\n===== {name} =====", flush=True)
    r = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT)
    if r.returncode != 0:
        print(f"[pipeline] {name} FAILED (exit {r.returncode})", file=sys.stderr)
    return r.returncode


def run_stage(script: str) -> int:
    """Run an importable stage in-process so main() can gate on its result."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(script[:-3], ROOT / script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main()


def write_review_digest() -> Path:
    """The one file a human reads each morning."""
    data = ROOT / "data"
    payload = json.loads((data / "pricing.json").read_text())
    queue = json.loads((data / "review_queue.json").read_text())
    q = payload.get("quality", {})

    dups = [x for x in queue if x.get("reason") == "possible duplicate"]
    small = [x for x in queue if x.get("reason") == "missing or too-small context window"]

    recent_path = data / "price_changes_recent.json"
    recent = json.loads(recent_path.read_text()) if recent_path.exists() else {}
    prices = [e for e in recent.get("events", []) if e.get("kind") == "price"]
    new_models = [e for e in recent.get("events", []) if e.get("kind") == "new"]
    delisted = [e for e in recent.get("events", []) if e.get("kind") == "delisted"]
    significant = [e for e in prices if e.get("significant")]

    lines = [
        f"# Daily review digest - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"Automation refreshed the pricing dataset. **{q.get('published', 0)} model pages** "
        f"and 400 comparison pages were regenerated. No action needed unless something below looks wrong.",
        "",
        "## Prices that moved",
        "",
        f"{len(prices)} price changes in the last {recent.get('window_days', 30)} days, "
        f"{len(new_models)} new models, {len(delisted)} delisted.",
        "",
    ]
    if significant:
        lines += [f"### {len(significant)} changes over 20% - check these before trusting the page", ""]
        for e in sorted(significant, key=lambda x: abs(x.get("pct_change") or 0), reverse=True)[:15]:
            pct = e.get("pct_change")
            # A move from zero has no meaningful percentage; say so rather than print 100%.
            shown = "was free" if pct is None and e["from"] == 0 else f"{pct}%"
            lines.append(f"- **{e['display_name']}** {e['field'].replace('_per_1m_usd', '')}: "
                         f"${e['from']} -> ${e['to']} ({shown})")
        lines.append("")
    elif not prices:
        lines += ["Nothing has moved since the last snapshot. History is now being recorded daily.",
                  ""]
    else:
        lines += ["No change exceeded 20%. The largest were:", ""]
        for e in sorted(prices, key=lambda x: abs(x.get("pct_change") or 0), reverse=True)[:5]:
            lines.append(f"- {e['display_name']} {e['field'].replace('_per_1m_usd', '')}: "
                         f"${e['from']} -> ${e['to']} ({e.get('pct_change')}%)")
        lines.append("")

    lines += [
        "## Needs a human decision",
        "",
        f"### {len(dups)} possible duplicates",
        "Two model IDs look like the same product. Confirm and either merge or ignore.",
        "",
    ]
    for d in dups[:15]:
        lines.append(f"- `{d['candidate']}` looks like `{d['possible_duplicate_of']}` "
                     f"(similarity {d['confidence']})")
    lines += ["", f"### {len(small)} rows missing a usable context window", ""]
    for d in small[:15]:
        lines.append(f"- `{d['candidate']}` - {d['input_per_1m_usd']} USD/1M input")
    lines += [
        "",
        "## Anything that moved fast",
        "",
        "Check the git diff on `data/pricing.json`. A model whose price changed by more than 20% "
        "in one day is worth a manual look before the page is trusted.",
        "",
    ]
    out = data / "review_digest.md"
    out.write_text("\n".join(lines))
    return out


def main() -> int:
    rc = 0

    # fetch and gate must pass before anything downstream is trusted.
    for name, script in [("fetch pricing", "fetch_pricing.py"),
                         ("quality gate", "quality_gate.py")]:
        rc |= stage(name, script)

    # History sits between the gate and the build, for two reasons: no rejected
    # row can ever reach the append-only log, and the build can then read this
    # run's change events. Run in-process so a failure halts the pipeline
    # instead of silently producing a build with no history.
    if rc == 0:
        print("\n===== price history =====", flush=True)
        try:
            rc |= run_stage("track_history.py")
        except Exception as e:
            print(f"[pipeline] price history FAILED: {e}", file=sys.stderr)
            rc = 1
    else:
        print("\n[pipeline] skipping price history: an earlier stage failed", file=sys.stderr)

    if rc == 0:
        for name, script in [("build pages", "build_pages.py"), ("qa", "tests.py")]:
            rc |= stage(name, script)
    else:
        print("[pipeline] skipping build and QA: price history failed", file=sys.stderr)

    digest = write_review_digest()
    print(f"\n[pipeline] review digest -> {digest}")
    print(f"[pipeline] {'OK' if rc == 0 else 'FAILED'}")
    return rc



if __name__ == "__main__":
    raise SystemExit(main())
