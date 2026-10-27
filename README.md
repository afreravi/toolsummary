# toolsummary.com — Market research, competitive analysis, and a working automation

Prepared 2026-09-21. AI-generated analysis; verify anything you intend to act on.

## The headline

Your bottleneck is not ideas, it is **content type**. `toolsummary.com` is a WordPress site
(a Rank Math PRO + Rate My Post install on Hostinger) that is currently dark: the homepage
returns 200, but the sample of inner pages checked — `/about-us`, `/submit-ai-tool`, `/albus/` —
all return 404. An archived copy of the homepage shows ~31 category links, i.e. a general
"AI tools directory" structure.

That structure is a directory of *tools*, competing head-on with Toolify and There's An AI
For That. It is the hardest version of this idea to win, and re-running it is the fastest way
to lose again.

The fix keeps the topic (AI tools) but changes the content type to something a language model
cannot summarise away: **live pricing data about the AI tools themselves**. That is 90%
automatable because it is a deterministic data transform, not a writing task.

## What is in this repo

| Path | What it is |
|---|---|
| `automation/mvp/` | **Working, tested pipeline.** Fetches live LLM pricing, cleans it, records daily price history, builds pages, runs 40+ QA assertions |
| `automation/mvp/track_history.py` | Append-only price log. The only output that cannot be regenerated |
| `automation/cron/main.py` | Daily OpenHands automation entrypoint (cron, no LLM): clone → pipeline → commit → push → publish |
| `automation/deploy/publish_tarball.py` | Publishes the built site as one tarball and extracts it on the host |
| `automation/ROADMAP.md` | What is built and the phase-by-phase plan |
| `automation/DATA_PRODUCT_SPEC.md` | Spec for the paid API + MCP server |
| `RELAUNCH_PLAN.md` | Current-stack audit of toolsummary.com and the phased relaunch plan |

## Prove the automation works

```bash
cd automation/mvp
python3 run_pipeline.py     # ~40s: fetch -> clean -> record history -> build -> QA
python3 -m http.server 8080 --directory site
# then open http://localhost:8080
```

Current output on a real run:

```
[fetch]   wrote 3576 models -> data/pricing.json
[gate]    3576 in -> 704 published (2115 rejected, 87 to review)
[history] date=2026-10-27 tracked=704 days_on_record=...
[build]   704 model pages, 400 comparison pages, 1 blog post(s), 9 static pages -> site/
[qa]      pages=1113 models=704 broken_links=0 placeholder_leak=0
[qa]      all checks passed
```

## Price history: handle with care

`data/price_history.jsonl` and `data/price_changes.jsonl` are append-only records of
what every model cost on each date. **They cannot be regenerated.** A day not
recorded is permanently lost, and no competitor can be caught up to on it either.

- Never add them to `.gitignore`
- Never delete them to "clean up"
- They are written after the quality gate, so a rejected row can never enter the log
- Re-running on the same data date replaces that date's rows rather than
  duplicating them, so a rebuild cannot corrupt the log
