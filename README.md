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
| `automation/automation_main.py` | Daily OpenHands automation entrypoint (cron, no LLM, publishes over SFTP) |
| `automation/ROADMAP.md` | What is built, what is stubbed, and the phase-by-phase plan |
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
[fetch]   wrote 3838 models -> data/pricing.json
[gate]    3838 in -> 672 published (2518 rejected, 85 to review)
[history] date=2026-10-09 tracked=672 days_on_record=1
[build]   672 model pages, 400 comparison pages -> site/
[qa]      pages=1073 models=672 broken_links=0 placeholder_leak=0
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
