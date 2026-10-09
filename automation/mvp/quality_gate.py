#!/usr/bin/env python3
"""Stage 1.5 - the quality gate.

Raw aggregator data is dirty: the same model appears under several provider
prefixes, some rows are internal harness artefacts, and some names are raw IDs.
This stage canonicalises, deduplicates and rejects, then writes the exact diff
a human needs to review.

Outputs:
  data/pricing.json      - rewritten in place, clean
  data/review_queue.json - rows a human must approve before they get a page
  data/quality_report.md - what changed and why
"""
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# Provider resale prefixes / SDK harness entries that are not buying decisions.
NOISE_PREFIXES = (
    "openrouter/", "wandb/", "azure_ai/", "azure/", "vertex_ai/", "bedrock/",
    "databricks/", "watsonx/", "together/", "fireworks_ai/", "groq/",
    "deepinfra/", "perplexity/", "cerebras/", "sambanova/", "novita/",
    "hyperbolic/", "anyscale/", "replicate/", "ai21/", "voyage/",
    "text-embedding", "computer-use", "gpt-3.5", "gpt-4-0", "gpt-4-3",
)
# Resale marketplaces and aggregator harnesses: these list someone else's model
# under their own prefix, so a page for them competes with the first-party page
# and duplicates the price.
RESALE_VENDORS = {
    "aihubmix", "openrouter", "wandb", "azure", "azure_ai", "vertex_ai",
    "bedrock", "databricks", "watsonx", "together", "fireworks_ai", "groq",
    "deepinfra", "perplexity", "cerebras", "sambanova", "novita", "hyperbolic",
    "anyscale", "replicate", "ai21", "voyage", "moonshot", "openai",
}
MIN_CONTEXT = 4_000
MAX_SANE_INPUT = 1_000.0
NOISE_EXACT = {"sample_spec", "ft:gpt-4o", "ft:gpt-4", "ft:gpt-3.5", "ft:gpt-3.5-turbo", "babbage-002", "davinci-002"}

# Bedrock-style identifiers: 'us.anthropic.claude-...', 'meta.llama3-1-405b',
# 'ai21.j2-ultra-v1', 'amazon.nova-micro-v1:0'.
BEDROCK_ID = re.compile(r"^(global|us|eu|jp|apac|sa|ca|me|af|cn|il)\.[a-z0-9]", re.I)
DOTTED_VENDOR = re.compile(r"^(anthropic|meta|amazon|cohere|mistral|ai21|stability|writer|deepseek|openai|nvidia|google|qwen|minimax|moonshotai|moonshot|zai|z-ai|alibaba|baidu|tencent|ibm|microsoft|xai|x-ai|sberbank|gigachat)\.[a-z0-9]", re.I)
VERSION_SUFFIX = re.compile(r":\d+$")

# Brands we want human-readable labels for.
BRANDS = {
    "gpt": "GPT", "llm": "LLM", "ai": "AI", "oss": "OSS", "vl": "VL",
    "api": "API", "moe": "MoE", "r1": "R1", "v3": "V3", "v2": "V2",
    "glm": "GLM", "qwen": "Qwen", "llama": "Llama", "mistral": "Mistral",
    "gemma": "Gemma", "phi": "Phi", "claude": "Claude", "gemini": "Gemini",
    "deepseek": "DeepSeek", "nemotron": "Nemotron", "grok": "Grok",
    "command": "Command", "kimi": "Kimi", "yi": "Yi", "mpt": "MPT",
    "dbrx": "DBRX", "smaug": "Smaug", "tulu": "Tulu", "olmo": "OLMo",
}
# Aggregator routing suffixes, not part of the product name.
ROUTE_SUFFIX = re.compile(r":(free|nitro|extended|thinking|online|batch|floor)$")
# Release dates embedded in model IDs: 20250514, 2024-11-01, 09-2025.
DATE_TOKEN = re.compile(r"\b(20\d{2}[-_.]?\d{2}[-_.]?\d{2}|\d{2}[-_.]20\d{2})\b")
CLOUD_VERSION = re.compile(r"[-_]?v\d+(:\d+)?$", re.I)
# Only this family is conventionally written with a hyphen before its version.
HYPHENATED = {"gpt": "GPT", "gptoss": "GPT-OSS"}


def base_name(model_id: str) -> str:
    """Strip any provider prefix so resold copies collapse to one key."""
    return model_id.split("/")[-1].lower()


def canonical_key(model_id: str) -> str:
    """Identity of the underlying model, ignoring snapshot and routing noise.

    'gpt-5-nano' and 'gpt-5-nano-2025-08-07' are the same product at the same
    price; publishing both creates a self-competing duplicate pair.
    """
    raw = base_name(model_id)
    raw = ROUTE_SUFFIX.sub("", raw)
    raw = re.sub(r"^~+", "", raw)
    raw = CLOUD_VERSION.sub("", raw)
    raw = DATE_TOKEN.sub("-", raw)
    raw = re.sub(r"-(preview|latest)$", "", raw)
    return re.sub(r"-{2,}", "-", raw).strip("-")


def display_name(model_id: str) -> str:
    """'openai/gpt-5-nano' -> 'GPT-5 Nano'; 'claude-sonnet-4-5-20250514' -> 'Claude Sonnet 4.5'.

    Cosmetic, but it drives the title tag and breadcrumb, so it has to read
    like the product name a person would type.
    """
    raw = base_name(model_id)
    raw = ROUTE_SUFFIX.sub("", raw)
    raw = CLOUD_VERSION.sub("", raw)
    raw = DATE_TOKEN.sub(" ", raw)

    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)*", raw, re.I)
    parts: list[str] = []
    for tok in tokens:
        if re.fullmatch(r"\d+(?:\.\d+)*", tok):
            prev_is_word = bool(parts) and not re.search(r"[\d.]$", parts[-1])
            # '4-5' in claude-sonnet-4-5 is a single version, not two words.
            if parts and re.fullmatch(r"\d", tok) and re.search(r"\d$", parts[-1]):
                parts[-1] = f"{parts[-1]}.{tok}"
            elif prev_is_word and parts[-1].lower() in HYPHENATED:
                parts[-1] = f"{parts[-1]}-{tok}"
            # Single-letter alpha prefix glues to its version: 'n2.5' -> 'N2.5'.
            elif prev_is_word and re.fullmatch(r"[A-Za-z]", parts[-1]):
                parts[-1] = f"{parts[-1]}{tok}"
            else:
                parts.append(tok)
            continue
        if tok.lower() in HYPHENATED:
            parts.append(HYPHENATED[tok.lower()])
        elif tok.lower() in BRANDS:
            parts.append(BRANDS[tok.lower()])
        else:
            parts.append(tok[:1].upper() + tok[1:])
    return " ".join(parts).strip() or model_id


def vendor_of(model_id: str) -> str:
    v = model_id.split("/")[0] if "/" in model_id else (model_id.split("-")[0])
    return v


def is_noise(m: dict) -> str | None:
    i = m["id"]
    low = i.lower()
    if i in NOISE_EXACT or i.lower().startswith("ft:"):
        return "known non-model artefact"
    if any(low.startswith(p) for p in NOISE_PREFIXES):
        return "provider resale duplicate or SDK harness entry"
    vendor = low.split("/")[0]
    if vendor in RESALE_VENDORS:
        return "resale marketplace listing of another vendor's model"
    # Dotted cloud namespace can sit after a marketplace prefix, e.g.
    # 'oci/openai.gpt-5-nano' or 'us.anthropic.claude-...'.
    last = low.split("/")[-1]
    if BEDROCK_ID.match(i) or BEDROCK_ID.match(last) or DOTTED_VENDOR.match(last):
        return "cloud-marketplace identifier, not a buyer-facing model name"
    if not re.search(r"[a-z]", low):
        return "no alphabetic model name"
    return None


def near_duplicate(a: dict, b: dict, threshold: float = 0.93) -> bool:
    """Two rows are a probable duplicate only if names are similar AND prices agree.

    Name similarity alone flags 'Llama 3.1 8B' against 'Llama 3.1 70B', which are
    genuinely different products. Resold copies of one model carry the same price.
    """
    if SequenceMatcher(None, a["canonical_key"], b["canonical_key"]).ratio() < threshold:
        return False
    pa = a["input_per_1m_usd"] * 3 + a["output_per_1m_usd"]
    pb = b["input_per_1m_usd"] * 3 + b["output_per_1m_usd"]
    if pa == 0 and pb == 0:
        return True
    hi = max(pa, pb)
    return hi > 0 and abs(pa - pb) / hi <= 0.10


def main() -> int:
    payload = json.loads((DATA / "pricing.json").read_text())
    before = payload["models"]

    kept, rejected, canonical = [], [], []
    for m in before:
        reason = is_noise(m)
        if reason:
            rejected.append({**m, "reason": reason})
            continue
        m["display_name"] = display_name(m["id"])
        m["vendor"] = vendor_of(m["id"])
        m["canonical_key"] = canonical_key(m["id"])
        canonical.append(m)

    # Collapse the same canonical model listed by more than one aggregator.
    groups: dict[str, list[dict]] = defaultdict(list)
    for m in canonical:
        groups[m["canonical_key"]].append(m)

    for key, rows in groups.items():
        if len(rows) == 1:
            kept.append(rows[0])
            continue
        # Prefer the OpenRouter row (first-party, live) then the lowest input price.
        rows.sort(key=lambda r: (r["source"] != "openrouter", r["input_per_1m_usd"]))
        winner = rows[0]
        winner["merged_from"] = sorted({r["id"] for r in rows[1:]})
        kept.append(winner)

    # Ambiguous near-duplicates and unusable rows go to a human queue rather
    # than being auto-published. Context filtering lives here, not in the page
    # builder, so the dataset and the rendered site always agree.
    review, final = [], []
    seen: list[dict] = []
    for m in kept:
        if not m.get("context_length") or m["context_length"] < MIN_CONTEXT:
            review.append({
                "candidate": m["id"], "candidate_name": m["display_name"],
                "input_per_1m_usd": m["input_per_1m_usd"],
                "possible_duplicate_of": None,
                "possible_duplicate_name": None,
                "confidence": None,
                "reason": "missing or too-small context window",
            })
            continue
        if m["input_per_1m_usd"] > MAX_SANE_INPUT:
            review.append({
                "candidate": m["id"], "candidate_name": m["display_name"],
                "input_per_1m_usd": m["input_per_1m_usd"],
                "possible_duplicate_of": None,
                "possible_duplicate_name": None,
                "confidence": None,
                "reason": "input price above plausibility threshold",
            })
            continue
        clash = next((s for s in seen if near_duplicate(m, s)), None)
        if clash:
            review.append({
                "candidate": m["id"], "candidate_name": m["display_name"],
                "input_per_1m_usd": m["input_per_1m_usd"],
                "possible_duplicate_of": clash["id"],
                "possible_duplicate_name": clash["display_name"],
                "confidence": round(SequenceMatcher(None, m["canonical_key"], clash["canonical_key"]).ratio(), 3),
                "reason": "possible duplicate",
            })
            continue
        seen.append(m)
        final.append(m)

    final.sort(key=lambda r: r["input_per_1m_usd"])

    payload["models"] = final
    payload["model_count"] = len(final)
    payload["quality"] = {
        "input_rows": len(before),
        "rejected": len(rejected),
        "merged": sum(1 for m in final if m.get("merged_from")),
        "queued_for_review": len(review),
        "published": len(final),
    }
    payload["models"] = final
    (DATA / "pricing.json").write_text(json.dumps(payload, indent=2))
    (DATA / "review_queue.json").write_text(json.dumps(review, indent=2))

    q = payload["quality"]
    lines = [
        "# Quality gate report",
        "",
        f"- Input rows from aggregators: **{q['input_rows']}**",
        f"- Rejected as noise / resale duplicates: **{q['rejected']}**",
        f"- Merged duplicates collapsed to one page: **{q['merged']}**",
        f"- Routed to human review queue: **{q['queued_for_review']}**",
        f"- Published with data-derived pages: **{q['published']}**",
        "",
        "## Rejection reasons",
    ]
    reasons: dict[str, int] = defaultdict(int)
    for r in rejected:
        reasons[r["reason"]] += 1
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")
    (DATA / "quality_report.md").write_text("\n".join(lines) + "\n")

    print(f"[gate] {len(before)} in -> {len(final)} published "
          f"({len(rejected)} rejected, {len(review)} to review)")
    print(f"[gate] wrote data/quality_report.md and data/review_queue.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
