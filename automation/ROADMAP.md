# Automation roadmap & skeleton

Status legend: **[built]** works and is tested · **[stub]** wired but needs a credential or decision from you · **[planned]** not written yet.

## What runs today

```
cron "Toolsummary pricing refresh" (daily 04:30 UTC, no LLM)
      │
      ▼
automation/cron/main.py ──[built]── clone → pipeline → commit → push → publish
      │
      ├─ run_pipeline.py ────────────[built]── 5 stages, aborts on any failure
      │       ├─ fetch_pricing.py ───[built]── OpenRouter + LiteLLM  → data/pricing.json
      │       ├─ quality_gate.py ────[built]── filter/merge/queue    → 704 publishable
      │       ├─ track_history.py ───[built]── append-only price log
      │       ├─ build_pages.py ─────[built]── 1,104 HTML pages      → site/
      │       └─ tests.py ───────────[built]── 30+ assertions; non-zero exit = no publish
      │
      ├─ review_digest.md ──────────[built]── what the human reads (the 10%)
      ├─ publish_tarball.py ────────[built]── one tarball, one tar -xzf on the host
      └─ fire_callback() ───────────[built]── marks the run done in OpenHands
```

## File skeleton

```
automation/
├── ROADMAP.md               # this file
├── cron/
│   ├── main.py              # [built]  scheduled entrypoint, no LLM
│   └── README.md            # [built]  what the run does and its failure policy
├── deploy/
│   ├── publish_tarball.py   # [built]  the publisher the daily run calls
│   └── package_site.py      # [built]  builds the downloadable archive + manifest
└── mvp/
    ├── run_pipeline.py      # [built]   84 LOC — stage runner + digest
    ├── fetch_pricing.py     # [built]  114 LOC — pull + normalise sources
    ├── quality_gate.py      # [built]  278 LOC — the trust layer
    ├── track_history.py     # [built]  append-only price log
    ├── build_pages.py       # [built]  517 LOC — render model + compare pages
    ├── tests.py             # [built]  136 LOC — QA gate
    ├── data/
    │   ├── pricing.json         # canonical dataset (the artifact that matters)
    │   ├── price_history.jsonl  # append-only — irreplaceable
    │   ├── price_changes.jsonl  # append-only — irreplaceable
    │   ├── quality_report.md    # counts + rejection reasons
    │   ├── review_queue.json    # rows needing a human
    │   └── review_digest.md     # daily summary
    └── site/                # generated output — never hand-edited
```

## Phase 1 — data spine **[built, done]**

The only part that matters long-term: a clean, reproducible dataset.

- 3,576 raw rows from two aggregators → 704 publishable
- Rejection is explicit and counted, never silent: 2,115 rejected across resale duplicates, cloud-marketplace IDs, marketplace listings, and non-model artefacts
- 264 duplicates merged with the survivor recording `merged_from`
- 87 ambiguous rows routed to a human queue instead of guessed at
- Builds are idempotent — same data in, byte-identical HTML out

## Phase 2 — page generation **[built, done]**

- 704 model pages: price breakdown, blended cost, 3 workload scenarios, same-vendor peers, cheaper/costlier neighbours
- 400 comparison pages: head-to-head, % delta, conditional advice that is honest when context windows tie
- `sitemap.xml`, `llms.txt`, internal hub

## Phase 3 — deploy **[built, done]**

`automation/deploy/publish_tarball.py` publishes the built site over SFTP using
the secrets stored in OpenHands:

| Secret | Holds |
|---|---|
| `TOOLSUMMARY_SFTP_HOST` | bare hostname |
| `TOOLSUMMARY_SFTP_USER` | SSH account name |
| `TOOLSUMMARY_SFTP_PASSWORD` | account password (the older `TOOLSUMMARY_SFTP_KEY` name is a password too) |
| `TOOLSUMMARY_SFTP_PORT` | SSH port |
| `TOOLSUMMARY_SFTP_PATH` | remote web root (`.../domains/toolsummary.com/public_html`) |

A publish failure does not fail the run — the snapshot is already pushed, so a
stale site is recoverable tomorrow and a credential gap can never take the site
down or lose a day's prices.

## Phase 4 — the cron **[built, registered]**

One automation is registered: **"Toolsummary pricing refresh"**, cron
`30 4 * * *` UTC, entrypoint `python3 main.py`, tarball uploaded from
`automation/cron/`. No LLM preset, because this task is deterministic.

## Phase 5 — expand **[planned]**

Add sources one at a time, each behind the same quality gate:

1. Google AI / Vertex, Azure OpenAI price lists (flat HTML tables)
2. Anthropic, Mistral, Cohere direct pricing pages
3. A price-history table so "dropped 30% this week" pages exist — the genuinely defensible asset, since it compounds and no competitor has it
4. Non-LLM tool pricing (image, video, voice) once the LLM set is stable

## The 90% / 10% split, stated plainly

| Automated | Human |
|---|---|
| Fetching every source | Approving the 87 queued rows |
| Filtering, merging, deduping | Spot-checking any >20% price move |
| Rendering all 1,104 pages | Writing the occasional editorial piece |
| QA (30+ assertions) | Deciding to add a new source |
| Publishing + sitemap | Handling a provider's takedown request |
| Daily digest | |

Measured: the run is ~40 seconds of compute and one markdown summary to skim. That is the 90%.
