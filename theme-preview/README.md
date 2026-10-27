# Theme preview — "Price Ledger"

A static mock-up of the new look and feel for toolsummary.com, for review only.
It is **not** wired into the pipeline: the live site is still built by
`automation/mvp/build_pages.py`. Nothing here deploys.

## View it

```bash
python3 -m http.server 8080 --directory theme-preview
# open http://localhost:8080
```

Or rebuild the HTML first (it is generated, so edit the generator, not the HTML):

```bash
python3 theme-preview/build_preview.py
```

## The design direction

An **editorial data-broadsheet**: warm paper instead of cold white, ink rules
that carry the layout, a characterful serif (Fraunces) for headlines, and
monospace (IBM Plex Mono) for every number so prices line up column-wise like a
ledger. The idea is that a pricing site should look like a record of prices, not
like a generic SaaS landing page.

- **Masthead** — dark bar, serif wordmark, primary nav, and a *Submit a tool*
  button as the one call to action.
- **Price ticker** — the signature element: a market-style strip under the
  masthead carrying models tracked, cheapest/median price, and the biggest mover
  of the day. This is the thing a visitor should remember.
- **Tables** — real ledger styling: sticky header, tabular figures, row
  hover, up/down deltas, free tiers in green.
- **Stats strip** — four headline numbers as a ruled grid.
- **Footer** — dark, four columns (brand, Data, Learn, Site).

## What is mocked

Only the chrome and layout are real. The data is a 34-model sample in
`build_preview.py`; model and comparison pages are generated from that sample so
every link resolves. Header, footer, CSS and JS are the parts that would move
into `build_pages.py`.

## Pages included

| Route | What it shows |
|---|---|
| `/` | Home: hero, answer box, stats, full filterable + sortable table, blog teaser |
| `/model/<name>/` | Model detail: price breakdown, workload costs (one per sample model) |
| `/compare/` | Comparison index |
| `/compare/<a>-vs-<b>/` | Head-to-head comparison (6 samples) |
| `/blog/` | Blog index with one placeholder post |
| `/blog/llm-api-pricing-changes-october-2026/` | The placeholder post |
| `/submit/` | **Submit a tool** — the form you asked for, with validation |
| `/about/`, `/contact/`, `/privacy/` | Supporting pages so no nav link dead-ends |
| `/404.html` | Not-found page |

## The submit form

`/submit/` collects: tool name, provider, category, pricing-page URL, optional
input/output prices, notes, optional email. Required fields are marked and
validated in the browser; submitting shows a confirmation and does not send
anywhere yet (there is no backend on a static site).

## Files

```
theme-preview/
├── build_preview.py      # the generator — edit this, not the HTML
├── assets/css/theme.css  # the whole design system, token-driven
├── assets/js/theme.js    # nav, table filter/sort, form validation (no deps)
└── *.html, model/, compare/, blog/, submit/, ...   # generated
```

## Before this ships

1. Move the header, footer and `<link>` tags from `build_preview.py` into the
   `page()` template in `automation/mvp/build_pages.py`.
2. Copy `theme.css` and `theme.js` into the site build (they would be written to
   `site/assets/`).
3. Add `/submit/` and `/blog/` as generated routes, and decide where form posts
   go (a static host needs an endpoint or a form service).
4. Keep the QA gate passing: one `<h1>` per page, no broken internal links, no
   template placeholders.
