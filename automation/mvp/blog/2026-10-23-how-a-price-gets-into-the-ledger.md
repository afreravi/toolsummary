---
title: How a price gets into the ledger
date: 2026-10-23
author: lena
tag: Method
read: 5 min read
excerpt: Every model here passed a filter that rejects more rows than it keeps. This is what happens between a provider's pricing page and a row you can sort.
---

Every number on this site arrived through the same pipeline, and that pipeline
throws away more than it publishes. This month it read 3,576 rows from provider
and aggregator sources, rejected 2,115 of them, merged 264 duplicates into models
already tracked, held 87 back for human review, and published 704.

That rejection rate is not a bug. It is the reason the table is worth reading.

## Why so many rows get rejected

A row is rejected when it cannot be trusted to mean one thing. The common cases:

- **No published price.** Some listings describe a model without a per-token
  price - an enterprise tier, a waitlist, or a placeholder. Without a price there
  is no row.
- **Not an LLM inference API.** The sources carry image models, embedding models,
  rerankers and speech models alongside chat models. They are real products, but
  they do not belong in a per-token comparison.
- **Unparseable or contradictory prices.** A listing that gives a price in a unit
  we cannot normalise, or two sources that disagree, goes to review rather than
  into the table on a coin flip.
- **Resellers.** A provider reselling another provider's model at its own margin
  is not a distinct price for the underlying model, and listing it would show the
  same model twice at different numbers with no explanation.

## Why 264 rows became one

The same model appears under different names across sources. DeepSeek V4 Pro and a
vendor-prefixed variant are the same model, priced the same way. Merging is what
stops the table from being 900 rows of 600 models.

Merging is done on a canonical key derived from the vendor and model name, not on
the display string, because display names drift. When two sources disagree on a
price for the same canonical model, the row is not silently averaged - the
disagreement is recorded and the model is held for review. Averaging two prices
would invent a number that no provider charges.

## What held for review means

87 models are in the review queue right now. They are real models with plausible
prices, but something about the row did not pass cleanly: an ambiguous unit, a
source conflict, or a name that could not be matched with confidence.

They stay out of the published table until a person looks. This is a deliberate
trade: the site is smaller than it could be, and every row in it can be defended
against the provider's own pricing page.

## The daily record

Once a row is published it is not overwritten. Each run appends today's price to
the history, so a change is a comparison between two dated observations rather
than an edit. That is what makes a price report possible at all - you cannot
report what moved if you only ever keep the latest number.

The raw current dataset is published at /api/prices.json. It carries the same
numbers as the table, with the caveat that a price is only as good as the source
it came from, and sources change without notice. Always confirm on the provider's
own pricing page before you commit budget.
