# Toolsummary strategy — market read

Research date: 2026-10-09. Sources are the competitors' own live pages.

## The uncomfortable finding first

The plan assumed daily price history is an open niche that would become a moat
with time. It is not open. Several competitors already publish it:

| Site | Price history | MCP server | Notes |
|---|---|---|---|
| pricepertoken.com | yes, charts + `/pricing-history` | yes, announced | tracks 610+ models, daily updates from OpenRouter |
| benchlm.ai | yes, "update ledger" + token price index | yes (free tier 1,000 reads/mo) | 783 models, per-change dated records |
| costgoat.com | live pricing + value scores | no | 374+ APIs, benchmark-driven value ranking |
| models.dev / llm-prices.com | partial | some | aggregator-shaped |

So "we have history" is table stakes, not differentiation. What is still thin
across all of them is **interpretation**: none of them explain what a price
change *means* for a given workload. They show a chart and stop.

That gap is where the content strategy should aim, and it has a useful property:
it is derived from the data we already collect daily.

## What the incumbents are weak at

Reading their pages, the consistent weaknesses are:

1. **No dated, citable record per change.** benchlm has an index and a ledger
   but the per-model pages don't state "input price was X on date Y, changed to
   Z on date W" in a form you'd cite or that a search engine can match to a
   specific query.
2. **No long-tail pairing.** They cover "cheapest LLM API". Nobody covers
   "Gemini 2.5 Flash vs GPT-5.4 nano price per million tokens for 100k input /
   20k output", which is how people actually search when budgeting.
3. **No "did it get more expensive" pages.** Price cuts get blog posts. Price
   *increases* and silent deprecations get far less coverage, and those are the
   queries with intent ("why did my bill go up").
4. **Aggregator price ≠ direct price.** The same model differs across
   endpoints. A page that says which route is cheapest for a model is
   genuinely useful and nobody does it well.

## Low-hanging content that can actually rank

Ordered by (search intent × ease × automation fit). All of these are generated
from `data/price_history.jsonl` plus `pricing.json` — no new data source needed.

1. **Per-model price-history pages** (`/model/<slug>/history`). One page per
   model, dated table of every recorded change, "as of" line. These are the
   pages the pipeline already half-produces. Long-tail, low competition per
   page, and they compound: every day we run, the page gets another row and
   more unique content. ~666 pages today.

2. **"Price change" event pages** (`/changes/2026-10-09`). One page per day
   something moved, listing what moved and by how much. Evergreen URLs, and
   they naturally target "<model> price change" queries. Generated from
   `price_changes.jsonl`, which we already write.

3. **Head-to-head cost calculators** (`/compare/<a>-vs-<b>-cost`). Not just a
   price table — a "what does this cost for *my* workload" answer with the
   arithmetic shown. The existing 400 comparison pages are the seed; adding the
   workload arithmetic is what makes them different from the incumbents.

4. **"Cheapest model for X" pages** (`/cheapest/coding`, `/cheapest/long-context`,
   `/cheapest/vision`). Qualified cheapest-questions. The qualification (task
   class, context floor) is what keeps these out of the wall-to-wall generic
   competition for "cheapest LLM API".

5. **Price-increase / deprecation pages** (`/increases`, `/deprecated`). Low
   competition, high intent, and nobody covers them well. Directly derived from
   `kind: price` events with `direction: increase` and `kind: delisted`.

Do **1 and 2 first**: they are pure derivations of data already on disk, they
add a new page every single day without any new work, and they are the pages
that accumulate the thing competitors can't backfill — our own dated record.

## The 90% automation story

The pipeline already produces the data. The automation gap is turning data into
pages, and that is a deterministic transform — no LLM needed.

Avatars of the split:

- **Deterministic (no LLM, near-zero marginal cost):** history tables, change
  pages, cheapest-for-X rankings, increase/delist lists, sitemap, JSON API.
  This is ~90% of the page count and it should stay non-LLM. It already runs
  daily and now commits itself (see `automation/cron/`).
- **LLM (the 10%):** a short "what this means" paragraph on the change pages,
  and the monthly trend summary. One LLM call per *changed* model per day, not
  per page. On a quiet day that is zero calls.

Guardrail: the LLM must never author a number. It comments on figures the
deterministic stage computed and QA-checked, which keeps a hallucination from
becoming a mispriced page.

## Monetization read

- **AdSense: poor fit.** Low-RPM traffic (developers, ad-blockers) on
  high-volume pages. Thin pages also risk rejection under thin-content policy.
  Not worth optimizing for.
- **API/MCP subscription: the credible product.** The competing MCP servers are
  free, so the paid tier has to sell something they don't: dated history with
  provenance, and change events. BenchLM's free 1,000 reads/month sets the
  price anchor. A low single-digit $/month tier with a real free tier is the
  realistic shape.
- **Affiliate: plausible but not primary.** GPU clouds and inference providers
  have affiliate programs. Only worth it once the pages rank.

The honest ordering is: traffic from citable history pages → free MCP to build
habit → paid tier for history + change events. The ad network is not part of it.

## What is already done

- Daily pricing pipeline, deterministic, self-committing to `main`.
- 666 models tracked with a daily append-only price log.
- 1,067 pages built and QA-gated per run.
- Price-change detection with a "significant" flag at the >20% threshold.
