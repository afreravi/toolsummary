# Data product spec — LLM pricing API + MCP server

Status: **spec only, nothing built.** Written 2026-09-21. AI-generated; verify pricing and program terms before acting.

## 1. What this is, and what it is not

**Is:** a small data product that serves live and historical LLM API pricing to two kinds of buyer — a
human via the website, and an *agent* via an MCP server and REST API. The website is the
acquisition channel; the API/MCP is the revenue.

**Is not:** a media site, an ad play, or a competitor to Artificial Analysis on head terms. Do not
build benchmark/evaluation data — that is their moat and it costs real money to produce.

### Why the agent buyer is the real opportunity

Ref (a documentation-search MCP) reached *hundreds of paying subscribers within three months* at
$9/month for 1,000 credits (~$0.009/search), with Tavily and Exa charging ~$0.01/search as the
market anchor. That establishes a price point for "an agent needs a lookup mid-task."

Pricing data fits that shape well: small, factual, cheap to serve, and needed at decision time
("which model can I afford for this workload?"). Pricepertoken already ships a paid MCP, which
validates demand — and is also a warning that the window is not wide open.

### Non-goals

- No display advertising, ever. Developer traffic plus low pageviews makes it structurally wrong.
- No benchmark/leaderboard data. No evals. No scraped review content.
- No per-token pricing of *our* service. See §6 for why.

## 2. Architecture

```
OpenRouter ─┐
LiteLLM    ─┴─► fetch_pricing.py ─► quality_gate.py ─► pricing.json
                                                          │
                                          ┌───────────────┼───────────────┐
                                          ▼               ▼               ▼
                                  price_history.json  build_pages.py   serve_api.py
                                   (append-only)      (free site)      (paid: REST + MCP)
                                                                          │
                                                              ┌───────────┴───────────┐
                                                              ▼                       ▼
                                                        meter (KV store)      change alerts
```

One dataset, three consumers. The free site and the paid API must never diverge — same
`pricing.json`, same `canonical_key` identity, so a page and an API answer agree.

## 3. Data layer — price history (build this first)

**Why first:** you cannot backfill it. Every day without recording is history you will never have.
It is also the only asset here a vendor's own page cannot replicate, and the thing a competitor
cannot copy retroactively.

### New file: `data/price_history.jsonl` (append-only, one JSON object per model per run)

```json
{"date": "2026-09-21", "id": "openai/gpt-5-nano", "canonical_key": "gpt-5-nano",
 "input_per_1m_usd": 0.05, "output_per_1m_usd": 0.4, "context_length": 400000,
 "vendor": "openai", "source": "openrouter"}
```

### New file: `data/price_changes.jsonl` (derived, one row per detected change)

```json
{"date": "2026-09-21", "canonical_key": "gpt-5-nano", "display_name": "GPT-5 Nano",
 "field": "input_per_1m_usd", "from": 0.25, "to": 0.05,
 "pct_change": -80.0, "direction": "decrease", "vendor": "openai"}
```

### Rules

| Concern | Decision |
|---|---|
| Append frequency | Once per successful pipeline run, keyed by date |
| Idempotency | Re-running on the same date replaces that date's row, never duplicates |
| Change threshold | Record any change >0.5% to avoid float noise; flag >20% as `significant: true` |
| Deletions | If a model vanishes upstream, record `{"delisted": true}` rather than dropping it |
| Identity | Join on `canonical_key`, not `id` — the id changes with routing suffixes |

### New pipeline stage: `track_history.py`

Runs after `quality_gate.py`, before `build_pages.py`. Reads `pricing.json`, appends to both
history files, writes `data/price_changes_recent.json` (last 30 days) for the site and API.

### Backfill reality

**There is no history today.** The dataset starts empty. Options, in order of honesty:

1. **Start recording now.** Zero cost, no backfill. Best option.
2. Backfill from the Wayback Machine's snapshots of provider pricing pages — feasible for a
   handful of major models only, low confidence, do not present as authoritative.
3. Do not fake it. A wrong history chart is worse than no history chart.

## 4. API surface (REST, JSON)

Versioned at `/v1`. All responses include `data_as_of` and `source`.

| Endpoint | Purpose |
|---|---|
| `GET /v1/models` | List/filter: `?vendor=&max_input_price=&min_context=&modality=` |
| `GET /v1/models/{canonical_key}` | Full record + `merged_from` aliases |
| `GET /v1/compare?models=a,b,c` | Side-by-side, cheapest flag, % delta |
| `GET /v1/estimate` | `?model=&input_tokens=&output_tokens=&calls=` → cost |
| `GET /v1/cheapest` | `?max_input_price=&min_context=&modality=` → best fit |
| `GET /v1/changes` | `?since=2026-09-01&significant=true` |
| `GET /v1/history/{canonical_key}` | Time series for charting |
| `POST /v1/alerts` | Register a webhook for price-change events (paid tier) |

Design notes: mirror the free site's answers exactly; support `?format=md` for LLM consumption;
return 404 with a `did_you_mean` list on unknown keys; keep the whole surface read-only except
alerts.

## 5. MCP server surface (the paid wedge)

Transport: stdio (local) and streamable HTTP (hosted, authenticated by API key).

| Tool | Purpose |
|---|---|
| `list_models` | Filtered list, token-cheap summary form by default |
| `get_model_price` | One model, exact current price |
| `compare_models` | Head-to-head for 2–5 models |
| `estimate_cost` | Cost for a stated workload — the highest-value call |
| `cheapest_for` | Constrained best-fit ("cheapest with 200k+ context") |
| `price_changes` | What moved since a date |
| `price_history` | Time series for a model |

**Design rules that matter:**

- **Return compact payloads.** An agent calling `list_models` should not receive 662 full records
  into its context window. Default to `{key, name, in, out}` and offer `detail=true`.
- **Be idempotent and cheap to re-call.** Agents loop and retry. See §6.
- **State the as-of date in every response** so the agent can judge staleness.
- **Never hallucinate-adjacent.** If a model is unknown, return a clear miss plus close matches,
  not a guess.

## 6. Metering and billing

### The trap to avoid

Agents are bad at being economical — they retry and re-query. A naive per-call meter charges the
customer for the agent's inefficiency, which breeds resentment and churn. Mitigations, all
non-negotiable:

1. **Never bill errors, retries of identical queries, or 4xx responses.**
2. **Dedupe identical requests** within a 60-second window per key — bill once.
3. **Bill the call, not the tokens.** Our serving cost is negligible; metering tokens would
   invent a cost that doesn't exist.
4. **Show the meter in real time** so nobody is surprised at month end.

### Tiers (anchored to the ~$0.01/call market)

| Tier | Price | Included | Notes |
|---|---|---|---|
| Free | $0 | 200 calls/day, no key | Public dataset; keeps the site's traffic funnel intact |
| Pro | $19/mo | 5,000 calls/mo | Card, self-serve. The volume tier most buyers land on |
| Team | $49/mo | 25,000 calls/mo + change webhooks | Alerts are the reason teams upgrade |
| Enterprise | Custom | Unlimited + SLA + history export | Only pursue inbound; do not build sales motion yet |

Overage at $0.004/call. State persistence via the automation KV store, not local files.

**Pricing is a hypothesis.** Ref's $9/1,000-credits is the closest comparable, but they sell
documentation search. Our willingness-to-pay is unproven — see §10.

## 7. Distribution and launch

1. **Free site first.** No paid tier until the site has organic traffic — the site *is* the funnel.
2. **Publish to MCP directories.** PulseMCP is confirmed as a listing surface; Smithery and the
   official registry need checking at build time.
3. **Ship the client packages** (`pip install toolsummary-pricing`, `npx toolsummary-mcp`) so
   install is one line.
4. **Keep `llms.txt` current** — already generated by `build_pages.py`. This is free agent
   discovery and most competitors neglect it.
5. **Launch the price-change newsletter** with the history feature. It is the only channel here
   that compounds and the only one that doesn't depend on ranking.
6. **Then** open the paid tier, with the newsletter and site as proof of freshness.

## 8. Build phases

| Phase | Work | Rough effort |
|---|---|---|
| 0 | `track_history.py` + append-only files + idempotency | 1–2 days |
| 1 | History/changes pages on the free site | 2–3 days |
| 2 | `serve_api.py` REST over `pricing.json` + history, no auth | 3–5 days |
| 3 | MCP server (stdio first), published to PyPI/npm | 3–5 days |
| 4 | Metering, API keys, Stripe, hosted HTTP MCP | 1–2 weeks |
| 5 | Change webhooks + newsletter automation | 1 week |

Phases 0–1 are worth doing regardless of whether the paid tier ever ships — they improve the free
site on their own. Phases 2–5 are bets.

## 9. Success metrics and kill criteria

**Leading (weeks 1–8):** history accumulating daily without gaps; MCP install count; free-tier
calls/day; newsletter subscribers.

**Revenue gate (month 6):** 25+ paying subscribers ≈ $500/mo. Below 10 paying subscribers with
1,000+ monthly free-tier calls means the data is wanted but not worth paying for — kill the paid
tier and keep the free site.

**Hard kill:** if the free site has not cleared ~5,000 monthly organic sessions by month 9, the
funnel does not exist and the paid tier has no path. Stop.

## 10. Risks and open questions

| Risk | Severity | Note |
|---|---|---|
| Willingness to pay is unproven | **High** | Model prices are public. We sell aggregation, history, freshness, and agent-readability — a convenience, not a necessity. This is the whole bet |
| History starts at zero | **High** | Competitors who record today beat us forever. Mitigated only by starting now |
| Incumbents add history | Medium | Artificial Analysis and pricepertoken could ship it; we cannot out-spend them |
| AI answers absorb the query | **High** | "How much does GPT-5 cost" is answered inline. Long-tail and history pages are the defence |
| MCP monetization infra is immature | Medium | x402/Nevermined/Apify exist but are early; Stripe-with-API-keys is the boring reliable path |
| Data source dependency | Medium | OpenRouter + LiteLLM are our whole supply. One blocking change breaks the pipeline |
| Free-tier abuse | Low | Rate-limit by IP and require keys beyond the free allowance |

### The question to answer before phase 4

Talk to five developers or platform teams and ask what they currently do to track model costs.
If the answer is "we check the vendor page once a quarter," the pain is too small to pay for and
the paid tier should not be built. Do this **before** writing billing code.

## 11. Immediate next action

Phase 0, today. `track_history.py` is roughly a day's work, costs nothing to run, and every day of
delay is permanently lost data. Everything else in this spec can wait; that cannot.
