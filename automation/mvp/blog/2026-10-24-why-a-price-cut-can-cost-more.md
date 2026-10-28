---
title: Why a 50% price cut can still cost you more
date: 2026-10-24
author: maya
tag: Explainer
read: 6 min read
excerpt: A cheaper input price is not the same as a cheaper bill. The ratio of input to output tokens decides which number actually matters for your workload.
---

A provider announces a 50% cut on input tokens and the headline writes itself. But
if your workload is output-heavy, that cut may barely move your bill, while a
modest rise on the output side quietly costs you more than you saved.

The two prices are not interchangeable. Most workloads consume far more input
tokens than output tokens, but output tokens usually cost several times more per
million. Those two facts pull in opposite directions, and the balance between
them is the whole game.

## The ratio is the thing

Every workload has an input-to-output ratio. A summarisation job might read
20,000 tokens and write 500, which is 40:1. A code assistant might read 4,000 and
write 1,200, closer to 3:1. A chat product sits somewhere between.

Work out your ratio once and the comparison stops being ambiguous. Multiply your
input volume by the input price, your output volume by the output price, and add
them. That total is the only number that matters. A model with the cheapest input
price on the page is frequently not the cheapest model for your ratio.

## A worked example

Take two models from the ledger. One charges $0.25 per million input and $1.25 per
million output. Another charges $0.50 input and $0.60 output. The first looks
cheaper on input, which is the column most people sort by.

Now run a month of 3:1 input-heavy traffic, say 300 million input and 100 million
output:

- Model A: 300 × $0.25 + 100 × $1.25 = $75 + $125 = **$200**
- Model B: 300 × $0.50 + 100 × $0.60 = $150 + $60 = **$210**

Close, and Model A wins. Push the ratio to 20:1 summarisation — 1,000 million
input, 50 million output — and it flips hard:

- Model A: 1,000 × $0.25 + 50 × $1.25 = $250 + $62.50 = **$312.50**
- Model B: 1,000 × $0.50 + 50 × $0.60 = $500 + $30 = **$530**

Now Model A wins by a wide margin. The model that looked cheaper at the top of the
table stays cheaper here, but for a completely different reason than the one people
assume, and at the 3:1 ratio the gap is inside the noise of a rounding decision.

## What this means in practice

Sort by the column that matches your workload, not by the column that sorts
first. If you are building a summariser, input price dominates and you can ignore
output almost entirely. If you are building a chat or agent product that reasons at
length, output price is where your money goes and a "cheap" input price can be
close to irrelevant.

The comparison pages here do this arithmetic for a few standard shapes, but your
ratio is yours. The honest advice is to measure it from real traffic before you
commit, because the difference between 3:1 and 20:1 is the difference between two
opposite conclusions drawn from the same table.

## Watch the context window too

One more trap. A price is only comparable if both models accept the same input.
A model with a 128,000-token window cannot summarise a document that needs
500,000, so it is not a cheaper option for that job — it is not an option at all.
Filter by context length before you compare prices, or you will compare a model
against one that cannot do the work.
