# Automation roadmap & skeleton

Status legend: **[built]** works and is tested · **[stub]** wired but needs a credential or decision from you · **[planned]** not written yet.

## What runs today

```
cron (daily 06:00)
      │
      ▼
automation_main.py  ──[built]── orchestrates, reports, publishes
      │
      ├─ run_pipeline.py ────────────[built]── 4 stages, aborts on any failure
      │       ├─ fetch_pricing.py ───[built]── OpenRouter + LiteLLM  → data/pricing.json
      │       ├─ quality_gate.py ────[built]── filter/merge/queue    → 662 publishable
      │       ├─ build_pages.py ─────[built]── 1,063 HTML pages      → site/
      │       └─ tests.py ───────────[built]── 30+ assertions; non-zero exit = no publish
      │
      ├─ review_digest.md ──────────[built]── what the human reads (the 10%)
      ├─ publish() ─────────────────[stub]─── needs SFTP secrets
      └─ fire_callback() ───────────[built]── marks the run done in OpenHands
```

## File skeleton

```
automation/
├── ROADMAP.md               # this file
├── REVIEW.md                # [planned] the 10% human checklist
├── automation_main.py       # [built]  139 LOC — cron entrypoint, no LLM
└── mvp/
    ├── run_pipeline.py      # [built]   84 LOC — stage runner + digest
    ├── fetch_pricing.py     # [built]  114 LOC — pull + normalise sources
    ├── quality_gate.py      # [built]  278 LOC — the trust layer
    ├── build_pages.py       # [built]  517 LOC — render model + compare pages
    ├── tests.py             # [built]  136 LOC — QA gate
    ├── data/
    │   ├── pricing.json         # canonical dataset (the artifact that matters)
    │   ├── quality_report.md    # counts + rejection reasons
    │   ├── review_queue.json    # rows needing a human
    │   └── review_digest.md     # daily summary
    └── site/                # generated output — never hand-edited
```

## Phase 1 — data spine **[built, done]**

The only part that matters long-term: a clean, reproducible dataset.

- 3,769 raw rows from two aggregators → 662 publishable
- Rejection is explicit and counted, never silent: 1,936 resale duplicates, 252 cloud-marketplace IDs, 187 marketplace listings, 16 non-model artefacts
- 241 duplicates merged with the survivor recording `merged_from`
- 97 ambiguous rows routed to a human queue instead of guessed at
- Builds are idempotent — same data in, byte-identical HTML out

## Phase 2 — page generation **[built, done]**

- 662 model pages: price breakdown, blended cost, 3 workload scenarios, same-vendor peers, cheaper/costlier neighbours
- 400 comparison pages: head-to-head, % delta, conditional advice that is honest when context windows tie
- `sitemap.xml`, `llms.txt`, internal hub

## Phase 3 — deploy **[stub — needs your input]**

`publish()` in `automation_main.py` is written and calls `rsync --delete` over SSH, but it needs three secrets stored in OpenHands:

| Secret | Example |
|---|---|
| `TOOLSUMMARY_SFTP_HOST` | `your-server.hostinger.com` |
| `TOOLSUMMARY_SFTP_USER` | `u123456789` |
| `TOOLSUMMARY_SFTP_KEY` | private key contents |

Missing secrets do not break the run — publish is skipped and reported, so a credential gap can never take the site down.

## Phase 4 — register the cron **[stub — needs your go-ahead]**

One API call creates it. No LLM preset, because this task is deterministic:

```bash
curl -X POST "${OPENHANDS_HOST}/api/automation/v1/preset/prompt" \
  -H "Authorization: Bearer ${OPENHANDS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"name":"Toolsummary pricing refresh",
       "prompt":"Run the pricing pipeline",
       "trigger":{"type":"cron","schedule":"0 6 * * *","timezone":"UTC"}}'
```

## Phase 5 — expand **[planned]**

Add sources one at a time, each behind the same quality gate:

1. Google AI / Vertex, Azure OpenAI price lists (flat HTML tables)
2. Anthropic, Mistral, Cohere direct pricing pages
3. A price-history table so "dropped 30% this week" pages exist — the genuinely defensible asset, since it compounds and no competitor has it
4. Non-LLM tool pricing (image, video, voice) once the LLM set is stable

## The 90% / 10% split, stated plainly

| Automated | Human |
|---|---|
| Fetching every source | Approving the 97 queued rows |
| Filtering, merging, deduping | Spot-checking any >20% price move |
| Rendering all 1,063 pages | Writing the occasional editorial piece |
| QA (30+ assertions) | Deciding to add a new source |
| Publishing + sitemap | Handling a provider's takedown request |
| Daily digest | |

Measured: the run is ~40 seconds of compute and one markdown summary to skim. That is the 90%.
