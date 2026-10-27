# Toolsummary strategy — market read

Research date: 2026-10-26. Sources are the competitors' own live pages, probed
directly. Written by an AI agent; treat every figure as something to re-verify
before it drives a spending decision.

## The uncomfortable finding first

The earlier version of this document said daily price history was table stakes
but that "interpretation" was still an open gap. Having now read the
competitors properly, that is too optimistic on both counts.

**The niche is crowded, and one competitor has already built this exact plan.**
`llm-cost.io` ships a price-changes tracker, a weekly report, a free model
list, cheapest-for-coding guides, a batch-pricing page, a direct-vs-router
page, an agent-cost page, a calculator, an RSS feed, a 96 KB `llms.txt`, and a
free "Agent Data API" with no API key. It runs a Pro tier at $9/month with a $6
founding rate. Its `/changes/` page diffs daily snapshots and states the
comparison window explicitly ("comparing snapshot 2026-09-26 → 2026-10-25, 63
daily snapshots collected").

That is the plan in this document, already executed, by someone with a 63
snapshot head start. Our own history currently holds **4 snapshot dates**
(2026-10-09 → 2026-10-26). On the "dated history is the moat" thesis we are not
close to competitive, and every day of delay widens the gap.

## 1. Who is actually in this space

Probed live on 2026-10-26:

| Site | What it ships | Notes |
|---|---|---|
| llm-cost.io | `/changes/` (63 snapshots), `/report/` weekly, `/free/`, `/guides/cheapest-coding/`, `/mcp/`, `/batch-pricing/`, `/direct-vs-router/`, `/agent-cost/`, `/calculator/`, `/llms.txt`, RSS | Closest competitor. Free Agent Data API, Pro $9/mo |
| benchlm.ai | Pricing comparison + calculator, "update ledger", token price index | Ranks #1 for "llm api pricing" |
| costgoat.com | `/compare/llm-api`, `/pricing/<vendor>-api`, `/bill-shock`, `/monitor/*`, cost calculators | Broad beyond LLMs (AWS, SaaS, domains) |
| llmpricing.dev | 1,300+ models, 232+ providers, 13 languages, `/api` | i18n from day one |
| tokeven.com | `/pricing-history`, `/models`, `/compare`, `/cost`, `/docs`, `/intelligence`, paid `/pricing` | AI cost optimizer framing |
| aipricinghub.com | `/price-changes/` | Thin, but owns the phrase |
| claudearchive.com | `/pricing-history/`, `/deprecations/`, `/migration-map/`, `/release-ledger/`, `/sources/` | Claude-only, but very deep |
| clawrouters.com | Router product + pricing guides + cost calculator | Content as acquisition for a router |
| pricepertoken.com | Price history + charts + paid MCP | Blocks bots (403); cited in earlier research |
| models.dev | Open API: 232 providers, 8,940 models | Free upstream data source |

Also ranking on the money queries: llmpricecheck.com, llmapi.pro,
inventivehq.com, comparedge.com, simplifai.tools, aicost.tools, llmcosthub.com,
kickllm.com, leanlm.ai, aispendcalc.com, costperprompt.com, aimodelwatch.dev.

That is roughly twenty sites on "LLM API pricing". Treat any plan whose pitch is
"nobody covers X" as unverified until the SERP is checked.

## 2. models.dev is the upstream, and it is free

`https://models.dev/api.json` returns 232 providers and **8,940 models** with
`cost: {input, output, cache_read}` per model, plus context limits and
modalities. We track 701. It is open, unauthenticated, and already the source
many smaller tools build on.

Two consequences:

- **Do not compete on breadth.** 701 vs 8,940 is not a race worth entering.
- **Consume it.** Merging models.dev would add `cache_read` — a field we do not
  have at all — and close most of the coverage gap for free.

## 3. Where our data actually stands

| Measure | Value |
|---|---|
| Models in `pricing.json` | 701 |
| History rows / snapshot dates | 2,693 / **4** (2026-10-09 → 2026-10-26) |
| Models with more than one observation | 664 |
| Change events | 887 (711 new, 148 price, 18 context, 10 delisted) |
| Significant changes (>20%) | 96 |
| Pages built | 1,102 (701 model + 400 compare + root) |
| Cache / batch price fields | **none** |
| Models not on OpenRouter | 405 of 701 |

The last row is the interesting one. We merge LiteLLM, so 405 of our models do
not appear on OpenRouter — and the OpenRouter-only competitors therefore cannot
cover them. That is a genuine differentiator.

**But it is currently junk.** Our "extra" models include entries like
`au.anthropic.claude-fable-5` and `au.anthropic.claude-opus-5-5` — LiteLLM's
Azure/Bedrock-prefixed duplicates of the same underlying models. Publishing 405
pages for them would generate near-duplicate content, which is worse than not
publishing them. Deduplicate before treating this as an asset.

## 4. The own-goal worth fixing first

We collect price history and **publish none of it**. A rendered model page
contains zero occurrences of "history", "changed", or "previous". We hold 2,693
rows and 887 change events and show the visitor a single "as of" date.

This is the cheapest available win: the data is already on disk, the transform
is deterministic, and no new source is needed. It does not make us competitive
with 63 snapshots on day one, but the only way to get to 63 is to start
publishing.

## 5. Low-hanging content ideas, ranked

Ordered by (unclaimed × derivable from data we have). Note the honest caveat in
section 6.

1. **Per-model history and change pages** — `/model/<slug>/history` and
   `/changes/<date>`. Pure derivation from `price_history.jsonl` and
   `price_changes.jsonl`. **Claimed by llm-cost.io and aipricinghub**, so this is
   parity work, not differentiation — but it is the foundation everything else
   cites, and it compounds daily.
2. **Cost-per-task / workload pages** — "what an AI agent costs per month",
   "RAG pipeline monthly cost", "support chatbot cost". Our model pages already
   render a "what a typical workload costs" section; this generalises it into
   named, realistic workloads with the arithmetic shown. This is the thinnest
   area across the competitive set.
3. **Migration and deprecation pages** — "X was delisted, here is what to move
   to and what it costs". We log `delisted` events (10 so far). claudearchive
   does this for Claude only; cross-vendor is open.
4. **Bill-shock / price-increase pages** — we log 84 increases. costgoat has
   `/bill-shock`, so this is partly claimed, but the query intent ("why did my
   bill go up") is strong and the content is a direct derivation.
5. **Direct vs router** — genuinely useful, but llm-cost.io and costgoat both
   cover it, and doing it well needs endpoint-level data we do not collect.

Ideas 2 and 3 are the best combination of unclaimed and buildable today.

## 6. What I could not verify

Search-engine probing stopped returning results partway through this research —
control queries that had returned hits began returning zero, which is
rate-limiting, not a genuine absence of competitors. **The "unclaimed" claims in
section 5 are therefore weaker than they look.** Queries such as "llm api cache
pricing discount" and "batch api discount llm pricing" returned a full page of
established sites, which suggests the long tail is more contested than the
zero-result queries implied. Re-run this against a real keyword tool with volume
data before committing to a content bet.

## 7. The 90% automation split

The split in the earlier draft holds, and is the part of the plan that is
genuinely working.

**Deterministic, no LLM (target: >90% of pages, near-zero marginal cost):**
history tables, change pages, cheapest-for-X, increase/delist lists, workload
cost pages, sitemap, `robots.txt`, `llms.txt`, JSON/RSS output. Runs daily.

**LLM, the 10%:** a one-sentence "what this means" on *significant* changes
only. That is 96 events across the whole dataset so far — on a quiet day, zero
calls. Guardrail stands: the LLM never authors a number, only comments on
figures the deterministic stage computed and QA-checked.

## 8. What I would do first

1. **Publish the site.** 1,102 pages are built and QA-clean and the live domain
   serves a staging placeholder. Nothing else matters until `/sitemap.xml` and
   `/robots.txt` return 200.
2. **Ship the history we already collect** onto the model pages. Cheapest real
   win, and it starts the compounding clock.
3. **Deduplicate the 405 non-OpenRouter models** before publishing pages for
   them. Merging models.dev would also add `cache_read`.
4. **Pick the workload-cost angle** (idea 2) as the differentiation bet, after
   validating it with real keyword data.
5. **Accept the honest risk:** llm-cost.io has a 63-snapshot lead, a free MCP,
   and the same price point. A head-on "pricing site" race is likely a loss.
   The defensible position is non-OpenRouter coverage plus workload economics —
   not "we also have price history".

## 9. Legacy domain note

`toolsummary.com` is indexed, but the indexed URLs are dead:
`/ai-tools/aggregator/theresanaiforthat`, `/category/ai-tools/finance/`,
`/page/2/` and similar all return 404. Those are soft 404s burning whatever
legacy signal the domain has. They need explicit redirects (to the closest new
page, or a 410 if there is no honest match).

Separately, third-party directories describe toolsummary as an AI *tool
directory* (creati.ai, vanetools, whattheai, toolstory.ai), not a pricing
resource. There is a brand mismatch to manage: the domain's existing
associations do not reinforce the new positioning.
