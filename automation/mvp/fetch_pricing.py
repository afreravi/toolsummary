#!/usr/bin/env python3
"""Stage 1: fetch live LLM pricing data from free public APIs.

Produces data/pricing.json - the single source of truth every other stage reads.
No API keys required.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

SOURCES = {
    "openrouter": "https://openrouter.ai/api/v1/models",
    "litellm": (
        "https://raw.githubusercontent.com/BerriAI/litellm/main/"
        "model_prices_and_context_window.json"
    ),
}


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "toolsummary-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def per_million(value: str | None) -> float | None:
    """OpenRouter quotes USD per token; convert to USD per 1M tokens."""
    if value in (None, "", "-1"):
        return None
    try:
        return round(float(value) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


def normalise(openrouter: dict, litellm: dict) -> list[dict]:
    rows: dict[str, dict] = {}

    for m in openrouter.get("data", []):
        pricing = m.get("pricing") or {}
        prompt = per_million(pricing.get("prompt"))
        completion = per_million(pricing.get("completion"))
        if prompt is None or completion is None:
            continue
        rows[m["id"]] = {
            "id": m["id"],
            "name": m.get("name") or m["id"],
            "vendor": m["id"].split("/")[0],
            "context_length": m.get("context_length"),
            "input_per_1m_usd": prompt,
            "output_per_1m_usd": completion,
            "modality": (m.get("architecture") or {}).get("modality"),
            "source": "openrouter",
        }

    # LiteLLM fills gaps for first-party models that OpenRouter does not proxy.
    for key, v in litellm.items():
        if not isinstance(v, dict) or key == "sample_spec":
            continue
        if key in rows:
            continue
        inp = v.get("input_cost_per_token")
        out = v.get("output_cost_per_token")
        if not inp or not out:
            continue
        rows[key] = {
            "id": key,
            "name": key,
            "vendor": v.get("litellm_provider") or key.split("/")[0],
            "context_length": v.get("max_input_tokens") or v.get("max_tokens"),
            "input_per_1m_usd": per_million(inp),
            "output_per_1m_usd": per_million(out),
            "modality": v.get("mode"),
            "source": "litellm",
        }

    return sorted(rows.values(), key=lambda r: r["input_per_1m_usd"])


def main() -> int:
    raw, missing = {}, []
    for name, url in SOURCES.items():
        try:
            raw[name] = fetch(url)
            print(f"[fetch] {name}: ok")
        except Exception as e:  # keep going, a partial refresh beats no refresh
            print(f"[fetch] {name}: FAILED ({e})", file=sys.stderr)
            missing.append(name)

    if not raw:
        print("[fetch] every source failed - aborting", file=sys.stderr)
        return 1

    models = normalise(raw.get("openrouter", {}), raw.get("litellm", {}))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_count": len(models),
        "failed_sources": missing,
        "models": models,
    }
    (DATA / "pricing.json").write_text(json.dumps(payload, indent=2))
    print(f"[fetch] wrote {len(models)} models -> data/pricing.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
