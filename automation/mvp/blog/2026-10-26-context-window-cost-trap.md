---
title: The context window is a pricing decision
date: 2026-10-26
author: dan
tag: Infrastructure
read: 6 min read
excerpt: Long context is not free, and it is not priced the way most people assume. Here is what a large window actually costs on a real workload.
---

A model with a one-million-token context window looks like a capability upgrade.
In practice it is a pricing decision, and an easy one to get wrong, because the
cost of a long window does not show up where you expect.

The ledger tracks context length next to price, and the two are not correlated in
the way intuition suggests. Some of the cheapest models on the page carry very
large windows. Some expensive ones cap out at 128,000. Window size is a separate
axis from price per token, and treating it as a feature you get "for free" is how
budgets go sideways.

## Where the cost actually lands

Two mechanisms matter. The first is that context is paid for on every request, not
once. If your application sends a 200,000-token preamble on each call, you are
billed for 200,000 input tokens every time, whether or not the model uses them.
Retrieval that stuffs a window "because it fits" is not free; it is a per-request
charge that scales with traffic.

The second is attention cost. Longer inputs are slower and more expensive to
process, and some providers price tiers by length or degrade throughput as the
window fills. A model that is cheap at 4,000 tokens of input may behave very
differently at 400,000, in latency as well as in dollars.

## A worked comparison

Suppose you are summarising 300,000-token documents. You need a window that
accepts them, which rules out most of the table immediately. Of the models that
qualify, you now compare on the columns that matter for this job: input price,
because you are almost all input, and context, because that is the gate.

Take a model at $0.25 per million input with a sufficient window, against one at
$0.10 with the same window. Per document:

- At $0.25: 0.3 x $0.25 = **$0.075 per document**
- At $0.10: 0.3 x $0.10 = **$0.030 per document**

Across 100,000 documents a month that is $7,500 versus $3,000. Same job, same
window, more than double the cost - purely from the input column that people
skim past when they see "long context" on a feature list.

## What to do about it

Filter by the window you actually need, then sort by price within that set. Do not
sort by price and then discover the window is too small, and do not assume a big
window is a reason to pay more per token.

For long-document work, chunking is usually cheaper than a giant window. Splitting
a 300,000-token document into 30 chunks of 10,000 and summarising hierarchically
lets you use a cheaper model, and it often produces a better summary because the
model is not trying to hold an entire book in mind at once. The large window is a
convenience, not an optimisation.

## The one case for paying more

There is a genuine reason to pay for a large window: work where the document
cannot be chunked without losing the point. Whole-repository reasoning, or a
contract where clause 40 depends on clause 3, is not decomposable. When the task
truly needs the whole thing in view at once, the large window is worth its price.

The mistake is paying that price for work that does not need it. Most
summarisation, most extraction, most question answering over a document set can be
chunked, and the models that can do it are on the cheaper end of the ledger.
