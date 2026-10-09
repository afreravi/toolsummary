#!/usr/bin/env python3
"""Stage 2.5 - price history.

Appends every run's prices to an append-only log so that "what did this model
cost last month" becomes answerable. This is the one output of the pipeline
that cannot be regenerated: a day not recorded is a day gone forever, and no
competitor can backfill it either.

History starts empty. Snapshots accumulate from the first run onward.

Outputs:
  data/price_history.jsonl      - one row per (date, canonical_key)
  data/price_changes.jsonl      - one row per detected event
  data/price_changes_recent.json - last 30 days, for the site and API

Idempotent: re-running on the same data date replaces that date's rows rather
than duplicating them, so a rebuild never corrupts the log.

Usage: python3 track_history.py
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

HISTORY = DATA / "price_history.jsonl"
CHANGES = DATA / "price_changes.jsonl"
RECENT = DATA / "price_changes_recent.json"

# Below this, a difference is float noise or a rounding change upstream.
CHANGE_THRESHOLD_PCT = 0.5
# Above this, a human should look before the page is trusted.
SIGNIFICANT_PCT = 20.0
RECENT_WINDOW_DAYS = 30

TRACKED = ("input_per_1m_usd", "output_per_1m_usd", "context_length")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # A partial write is worth skipping, never worth crashing the build.
            print(f"[history] WARNING: skipped corrupt line in {path.name}", file=sys.stderr)
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


def snapshot_date(payload: dict) -> str:
    """The data's own date, not the clock: keeps rebuilds reproducible."""
    raw = payload.get("generated_at") or ""
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc).date().isoformat()
    except ValueError:
        return datetime.now(timezone.utc).date().isoformat()


def snapshot_rows(payload: dict, day: str) -> list[dict]:
    rows = []
    for m in payload["models"]:
        rows.append({
            "date": day,
            "canonical_key": m["canonical_key"],
            "id": m["id"],
            "display_name": m["display_name"],
            "vendor": m["vendor"],
            "input_per_1m_usd": m["input_per_1m_usd"],
            "output_per_1m_usd": m["output_per_1m_usd"],
            "context_length": m.get("context_length"),
            "source": m.get("source"),
        })
    return sorted(rows, key=lambda r: r["canonical_key"])


def pct_change(old: float | None, new: float | None) -> float | None:
    """Relative change, or None when it is undefined.

    A move from zero has no meaningful percentage: "free -> $0.05" is not
    "+100%". Reporting it as one would render a false figure on a price-history
    chart, and ~40 free models make that a live case, not a hypothetical.
    """
    if old is None or new is None or old == 0:
        return None
    return round((new - old) / old * 100.0, 2)


def diff_snapshots(prev: dict[str, dict], curr: dict[str, dict], day: str) -> list[dict]:
    """Events between the previous snapshot and today's.

    Three kinds, kept distinct rather than flattened together:
      new      - first time we have seen this model
      price    - a tracked field moved beyond the threshold
      delisted - it was present last time and is gone now
    """
    events: list[dict] = []

    for key, now in curr.items():
        before = prev.get(key)
        if before is None:
            events.append({
                "date": day, "kind": "new", "canonical_key": key,
                "display_name": now["display_name"], "vendor": now["vendor"],
                "input_per_1m_usd": now["input_per_1m_usd"],
                "output_per_1m_usd": now["output_per_1m_usd"],
                "significant": False,
            })
            continue

        for field in TRACKED:
            old, new = before.get(field), now.get(field)
            if old is None or new is None or old == new:
                continue
            # Context length is a fact, not a price: report the delta, never a %.
            if field == "context_length":
                events.append({
                    "date": day, "kind": "context", "canonical_key": key,
                    "display_name": now["display_name"], "vendor": now["vendor"],
                    "field": field, "from": old, "to": new,
                    "pct_change": None, "direction": "increase" if new > old else "decrease",
                    "significant": False,
                })
                continue

            pct = pct_change(old, new)
            # pct is None only when the baseline was zero, which is always notable.
            if pct is not None and abs(pct) < CHANGE_THRESHOLD_PCT:
                continue
            events.append({
                "date": day, "kind": "price", "canonical_key": key,
                "display_name": now["display_name"], "vendor": now["vendor"],
                "field": field, "from": old, "to": new, "pct_change": pct,
                "direction": "increase" if new > old else "decrease",
                "significant": pct is None or abs(pct) > SIGNIFICANT_PCT,
            })

    for key, before in prev.items():
        if key not in curr:
            events.append({
                "date": day, "kind": "delisted", "canonical_key": key,
                "display_name": before["display_name"], "vendor": before["vendor"],
                "input_per_1m_usd": before["input_per_1m_usd"],
                "output_per_1m_usd": before["output_per_1m_usd"],
                "significant": False,
            })

    return sorted(events, key=lambda e: (e["kind"], e["canonical_key"], e.get("field") or ""))


def latest_before(history: list[dict], day: str) -> dict[str, dict]:
    """Most recent snapshot strictly before `day`, keyed by canonical_key."""
    prior = [r for r in history if r["date"] < day]
    if not prior:
        return {}
    newest = max(r["date"] for r in prior)
    return {r["canonical_key"]: r for r in prior if r["date"] == newest}


def main() -> int:
    payload = json.loads((DATA / "pricing.json").read_text())
    day = snapshot_date(payload)

    history = read_jsonl(HISTORY)
    todays = snapshot_rows(payload, day)
    prev = latest_before(history, day)

    events = diff_snapshots(prev, {r["canonical_key"]: r for r in todays}, day)

    # Replace this date's rows wholesale, then append. Re-running the same data
    # date is therefore a no-op instead of a duplicate, and a re-run today
    # cannot see today as its own "previous" snapshot.
    kept = [r for r in history if r["date"] != day]
    write_jsonl(HISTORY, sorted(kept + todays, key=lambda r: (r["date"], r["canonical_key"])))

    known = read_jsonl(CHANGES)
    kept_events = [e for e in known if e["date"] != day]
    write_jsonl(CHANGES, sorted(kept_events + events,
                                key=lambda e: (e["date"], e["kind"],
                                               e["canonical_key"], e.get("field") or "")))

    cutoff = (date.fromisoformat(day) - timedelta(days=RECENT_WINDOW_DAYS)).isoformat()
    recent = [e for e in kept_events + events if e["date"] >= cutoff]
    RECENT.write_text(json.dumps({
        "generated_at": payload.get("generated_at"),
        "as_of": day,
        "window_days": RECENT_WINDOW_DAYS,
        "counts": {
            "price": sum(1 for e in recent if e["kind"] == "price"),
            "new": sum(1 for e in recent if e["kind"] == "new"),
            "delisted": sum(1 for e in recent if e["kind"] == "delisted"),
            "context": sum(1 for e in recent if e["kind"] == "context"),
            "significant": sum(1 for e in recent if e.get("significant")),
        },
        "events": recent,
    }, indent=2))

    dates = sorted({r["date"] for r in kept + todays})
    prices = [e for e in events if e["kind"] == "price"]

    print(f"[history] date={day} tracked={len(todays)} days_on_record={len(dates)}")
    print(f"[history] this run: {len(prices)} price changes, "
          f"{sum(1 for e in events if e['kind'] == 'new')} new, "
          f"{sum(1 for e in events if e['kind'] == 'delisted')} delisted")
    for e in prices[:10]:
        if e["pct_change"] is None:
            # from == 0 here: a percentage would be meaningless.
            pct = "was free"
        else:
            pct = f"{'+' if e['direction'] == 'increase' else ''}{e['pct_change']}%"
        flag = "  <-- SIGNIFICANT" if e["significant"] else ""
        print(f"[history]   {e['display_name']}: {e['field']} "
              f"{e['from']} -> {e['to']} ({pct}){flag}")
    if len(prices) > 10:
        print(f"[history]   ... {len(prices) - 10} more")
    print(f"[history] history -> {HISTORY.name}, changes -> {CHANGES.name}, recent -> {RECENT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
