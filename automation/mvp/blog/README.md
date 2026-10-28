# Blog posts

Posts are Markdown files in this directory. Adding one is a file plus a commit:
the next daily pipeline run (04:30 UTC) renders it into `site/blog/` along with
the index, the post page and the RSS feed. There is no database and no CMS.

## Adding a post

Create `automation/mvp/blog/YYYY-MM-DD-your-slug.md`:

```markdown
---
title: What moved in LLM API pricing this October
date: 2026-10-27
author: maya
tag: Price report
read: 6 min read
excerpt: One or two sentences. This is what shows on the blog index, the home
  page teaser and the RSS feed.
---

Opening paragraph.

## A heading

Body text. Use a blank line between paragraphs.
```

## Authors

`author:` takes one of the keys declared in `AUTHORS` in `build_pages.py`:

| key | name | role |
| --- | --- | --- |
| `maya` | Maya Ferreira | Pricing analyst |
| `dan` | Daniel Okonkwo | Infrastructure writer |
| `lena` | Lena Petrova | Data editor |
| `sam` | Sam Whitfield | Editor |

An unknown or missing key falls back to `maya` with a warning rather than
publishing a post with no byline. Each author with at least one post gets a page
at `/blog/author/<key>/`, and posts carry a schema.org `Person` reference to it.
To add an author, add them to `AUTHORS` and reference the new key.

These are house bylines, not independent contributors. Keep them that way: a
byline only builds trust if the person would answer for the piece. If a real
guest writer appears, use their real name.

## Rules that matter

- **The filename date prefix orders the posts** and is stripped from the URL.
  `2026-10-27-price-report.md` publishes at `/blog/price-report/`.
- **`title` and `date` are required.** A file missing either is skipped with a
  warning rather than published broken.
- **`excerpt` is strongly recommended** — it is the teaser text and the feed
  description. Without it the post appears with an empty summary.
- Do not rename a published file's slug: the URL changes and any link breaks.

## Supported Markdown

Deliberately small, so it can be audited: headings (`##`, `###`), paragraphs,
`-` bullet lists, `> ` blockquotes, fenced code blocks, and inline `**bold**`,
`*italic*`, `` `code` `` and `[links](https://example.com)`.

Raw HTML is escaped, so a post cannot inject markup. Anything else — tables,
images, footnotes — is not supported; add it to `render_markdown()` in
`build_pages.py` if a post needs it.

## Publishing now instead of waiting

```bash
cd automation/mvp
python3 build_pages.py && python3 tests.py
python3 ../deploy/publish_tarball.py
```

The daily run does the same thing on its own.
