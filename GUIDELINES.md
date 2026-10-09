# Tool Build Guidelines (read fresh on every run)

> **Important:** This file is read from `main` at the start of every automation run.
> Update it anytime — changes automatically apply from the next daily run onward.

1. **Bootstrap 4.6** for HTML structure. (CDN: `https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css` + the matching JS bundle.)
2. **SEO title & description** — generate a unique, SEO-friendly `<title>` and `<meta name="description">` following current SEO standards (description targeting ~150–160 chars, natural keyword use, no stuffing).
3. **No dark theme** — always a light, clean, accessible color scheme.
4. **Reference vibe**: keep the layout rhythm, spacing and tone calm, text-first and readable. Adapt, don't copy.
5. **Unique content** — include a unique, plagiarism-free, human-like informational article of **~800–1000 words** on the page (below or around the interactive tool). Integrate relevant **secondary keywords** naturally to build **E-E-A-T** (author bio, accurate facts, sources where relevant, FAQ section, last-updated date).
6. **Originality per tool** — every tool must be genuinely distinct in voice, structure, and design (no reused boilerplate). Do not duplicate another tool's title, slug, or article.
7. **Theme primary color** — use `#60089c` as the theme primary color and its color variants to build the page theme.
8. **Disclaimer** — add a disclaimer for each tool.
9. **Interactive graph/chart** — add an interactive graph/chart in the result or within content, if possible.

## How the queue works
- `tools-queue.txt` holds one tool idea per line. The first unconsumed line (not starting with `[done]`) gets built next.
- Optional per-tool note after a pipe: `Tool Name | note for the builder`.
- After building, rewrite that line to `[done] Tool Name` and commit it in the same PR.

## Build checklist (before you commit)
- [ ] New tool files created (this repo uses `index.html`, `style.css`, `script.js` at the root)
- [ ] Unique `<title>` + `<meta name="description">` (~150–160 chars)
- [ ] Light theme only; Bootstrap 4.6 CDN; responsive viewport
- [ ] Article length ≈800–1000 words (verify by count; trim/extend if outside)
- [ ] Vanilla JS tool logic works + handles invalid/edge input gracefully
- [ ] No copied content; no reused article/voice from previous tools
- [ ] README.md updated to describe the current state
