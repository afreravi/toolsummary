# Toolsummary — competitive analysis and content plan

Research date: 2026-10-26. Every competitor figure below was counted from that
site's own live `sitemap.xml` on that date, not quoted from a third party.
`models.dev` figures come from `https://models.dev/api.json`. Written by an AI
agent; re-verify before spending money on any of it.

Companion to `docs/market.md`, which covers positioning. This document is the
measured content gap.

## 1. The finding that changes the plan

`docs/market.md` recommended workload/cost pages as the differentiation bet and
called them "the thinnest area across the competitive set". Counting the live
sitemaps, that is no longer true, and the comparison space is far more
saturated than it appeared.

| Site | Total URLs | Comparison pages | Workload/cost pages | History pages |
|---|---|---|---|---|
| benchlm.ai | **290,874** | **288,429** | 2 | 1 |
| tokeven.com | 7,044 | 3,846 | **2,937** | 94 |
| llm-cost.io | 2,767 | 2,179 | 11 | 1 |
| aipricinghub.com | 1,902 | 51 | 11 | **741** |
| llmpricing.dev | 1,142 | 20 | 14 | 0 |
| costgoat.com | 115 | 16 | 0 | 0 |
| llmpricecheck.com | 77 | 0 | 0 | 0 |

Three conclusions:

1. **Do not build comparison pages as a growth play.** benchlm.ai alone has
   288,429 of them. At 400 we would be a rounding error competing on the most
   commoditised page type on the internet. Keep the ones already built as
   internal navigation; do not invest in more.
2. **Workload/cost pages are now contested.** tokeven.com ships 2,937 and
   llm-cost.io has a `/scenario/` set. The window market.md identified has
   closed in the last few weeks.
3. **History is the only category where the leader is not unbeatable.**
   aipricinghub.com has 741 history pages, tokeven.com 94, llm-cost.io 1,
   benchlm.ai 1. Nobody has an insurmountable lead, and we hold history we
   currently publish nowhere.

## 2. The one genuine gap: cache and batch economics

Counting URLs by topic across all seven sites:

| Content type | Sites covering it | Max URLs on any one site |
|---|---|---|
| Comparison | 6 of 7 | 288,429 |
| Model page | 5 of 7 | 992 |
| Embedding | 3 of 7 | 4,566 |
| Benchmarks | 3 of 7 | 792 |
| **Cache / prompt caching** | **2 of 7** | **2** |
| **Migration** | **1 of 7** | **2** |
| **Deprecation** | **1 of 7** | **13** |

Cache pricing is covered by two sites with two pages between them. Nobody has a
per-model cache page. This is a real, specific, unclaimed content type — and it
matters because prompt caching is a 75–90% discount that most teams do not
model, so the query intent ("what does cached input cost") is commercial.

`models.dev` already serves the data, for free, unauthenticated:

| Field | Models covered (of 8,940) |
|---|---|
| `cost.cache_read` | **6,206** |
| `cost.cache_write` | 1,964 |
| `cost.tiers` (context-size tiered pricing) | present |

Our dataset has **no cache field at all**, and tracks 701 models against their
8,940. Per market.md's conclusion, breadth is not worth racing — but cache
pricing is a wedge into the one page type that is not yet contested.

## 3. What we already have and do not publish

This is the cheapest available win, and it is larger than market.md recorded.

| Asset | Held | Published |
|---|---|---|
| Price history rows | 2,693 | **nothing** |
| Snapshot dates | 4 (2026-10-09 → 10-26) | nothing |
| Price-change events | 148 (78 up, 70 down) | nothing |
| Delisted events | 10 | nothing |
| Significant changes (>20%) | 96 | nothing |
| Vendors | 111 | nothing |
| Free models | 18 | nothing |

A rendered model page contains one occurrence of "as of" and **zero** of
"history", "changed", or "previous". We collect a daily price log and show the
visitor a single date.

## 4. Ranked content plan

Ordered by (unclaimed × derivable from data we have or can get free). The
automation split from market.md holds: everything below is deterministic and
costs no LLM tokens.

### Tier 1 — build now, zero new sources

1. **Per-model price-history pages** — `/model/<slug>/history/`. Derived from
   `price_history.jsonl`. 701 pages, zero marginal cost, compounds daily. This
   is the foundation every other page cites, and it is the only way to close a
   4-snapshot gap to aipricinghub's 741: start publishing.
2. **Change-event pages** — `/changes/<date>/`, plus `/changes/` index and RSS.
   Derived from `price_changes.jsonl`. 4 dates today, one more per day.
   Increases and decreases as separate, filterable lists.
3. **Cache-pricing pages** — `/cache-pricing/` hub plus per-model cache tables.
   Requires merging `cost.cache_read` from models.dev, which is a free
   upstream. **This is the differentiation bet**: 2 pages of competition
   across the entire set.
4. **Vendor pages** — 111 vendors already in `pricing.json`, no page for any of
   them. Derived entirely from data on disk.

### Tier 2 — build next, one free upstream merge

5. **Context-tier pricing pages** — models.dev `cost.tiers` gives the
   price-per-context-window bands. Nobody in the set surfaces these, and they
   are where large-context bills actually go wrong. 401 of our models claim
   ≥200k context, so the tier question is live for most of the catalogue.
6. **Free-LLM pages** — 18 free models today. Small, but "free LLM API" is
   high-intent and llm-cost.io has a `/free/` page, so treat it as parity.
7. **Deprecation / migration pages** — 10 delisted events, one competitor
   (benchlm, 13 pages). Cross-vendor migration is genuinely open, but the
   dataset is thin at 10 events. Build the template now, let it fill.

### Tier 3 — deliberately not built

8. **More comparison pages.** The existing 400 stay as internal links. Adding
   more competes with 288,429 pages on the lowest-value page type available.
9. **Direct-vs-router, calculator, bill-shock.** Claimed by llm-cost.io and
   costgoat; each needs data we do not collect.

## 5. The 90% automation split, concretely

| Stage | Mechanism | Pages/day | LLM cost |
|---|---|---|---|
| History + change pages | Deterministic from `price_history.jsonl` | ~5 new, 700 rebuilt | none |
| Cache + tier tables | Deterministic from models.dev merge | 700 rebuilt | none |
| Vendor pages | Deterministic from `pricing.json` | 111 rebuilt | none |
| "What this means" note | LLM, on >20% changes only | 0–3 | ~0 calls on a quiet day |
| Daily digest | Deterministic | 1 | none |

Over 95% of pages are pure derivation. The LLM writes only the one-sentence
annotation on significant changes — 96 events in the entire dataset so far,
frequently zero on a given day. The guardrail stands: the LLM never authors a
number, only comments on figures the deterministic stage computed and QA
checked.

## 6. What is genuinely blocking this

Not content ideas. The domain serves a staging placeholder:

```
https://toolsummary.com/           200  "Toolsummary — staging" + noindex,nofollow
https://toolsummary.com/robots.txt 404
https://toolsummary.com/sitemap.xml 404
```

1,102 pages are built, QA-clean, and unreachable. The publish automation's hang
is fixed and verified locally (a stalled host now fails in 90s instead of
hanging, and 1002 files upload in 2.7s), but the fix is unpushed and untested
against the real host. Until `/robots.txt` and `/sitemap.xml` return 200, none
of the content plan compounds.

Legacy indexed URLs (`/ai-tools/aggregator/*`, `/category/*`, `/page/2/`) return
404 and burn whatever domain authority exists. They need explicit redirects to
the closest new page, or a 410 where there is no honest match.

## 7. Honest risks

- **aipricinghub has 741 history pages to our 4 snapshot dates.** They can
  generate history for models they have never observed by backfilling from
  upstream sources; we cannot. Publishing daily is the only remedy, and it
  starts paying only once it has run for months.
- **The cache-pricing gap may be a gap because the demand is small**, not
  because nobody thought of it. Validate with a keyword tool that returns
  volume before making it the primary bet. The SERP evidence here is
  structural (URL counts), not volume.
- **Search probing was rate-limited partway through this research.** Counts
  from sitemaps are reliable; any claim about what ranks for a given query is
  not. benchlm.ai's 290k sitemap in particular suggests aggressive programmatic
  generation that may or may not be indexed.
- **The domain's existing associations are a directory, not a pricing
  resource** (market.md §9). The rebrand cost is real and not counted above.
