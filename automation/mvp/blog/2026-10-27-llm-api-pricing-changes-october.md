---
title: What the October price moves actually were
date: 2026-10-27
author: maya
tag: Price report
read: 7 min read
excerpt: A month of the ledger, sorted into the moves that mean something and the ones that are artefacts of a near-zero baseline.
---

Every day this site records what each tracked model costs per million input and
output tokens. That log is now long enough to read a month clearly, so this is the
first of a recurring price report. The dataset currently holds 704 published
models across 112 providers, drawn from 3,576 rows before cleaning.

The headline is real: output tokens got cheaper in several places. But the loudest
numbers in the raw log are not price changes at all, and it is worth separating
those out before anyone budgets against them.

## The moves worth knowing

DeepSeek's Flash line led the month. Output prices on several variants fell
sharply — the largest real reduction was on the order of 80%, taking output from
around $1.32 to $0.24 per million tokens. Input fell on the same line by a similar
proportion.

Qwen 3.8 27B cut input from $0.425 to $0.040, a genuine reduction of roughly 90%
against a baseline that was already a real, chargeable amount. GLM 5.2 moved input
from $0.62 down to $0.034. These are the changes a buyer should act on.

There were rises too, and they were not all noise. DeepSeek's Pro line moved output
up in one step from $0.75 to $8.00, which is a real increase against a real
baseline. If you were on that model, your bill changed by an order of magnitude and
you would want to know why.

## The numbers we do not rank

The raw log contains moves like input going from $0.0001 to $0.034 — a rise of
more than 33,000%. That is arithmetic, not information. A near-zero baseline makes
any change look infinite, and a percentage against a price nobody can actually be
charged is meaningless.

This is why the trending page only ranks a move as a percentage when the starting
price is at least $0.001 per million tokens. Below that threshold the ratio is
dominated by rounding in the source data, and publishing it would discredit every
honest number next to it. The move is still recorded in the log; it is just not
presented as a headline.

There is a second class of noise worth naming: flip-flops. Some models appear to
swing up and then back down within days, by thousands of percent, in both
directions. That is almost always an upstream feed changing its mind rather than a
provider changing its price twice in a week. We record what the source says, but we
do not treat a round trip as two market events.

## How to read a price change

Three questions turn a number into a decision:

1. Was the starting price real? If it was fractions of a cent, the percentage
   tells you nothing.
2. Which token type moved? An output cut on an output-heavy workload is worth far
   more than the same percentage on input.
3. Did it stay moved? A price that reverts within a week is a data event, not a
   market one.

The ledger keeps enough history to answer the third question, which is why we keep
a daily record rather than a single current snapshot.

## What we are watching

The compression in output pricing is the trend to follow. If output tokens keep
falling, the cost advantage of short-answer models narrows and the calculus shifts
toward whichever model reasons best rather than whichever one is cheapest per
token. That is a better world to be budgeting in, but only if you are reading the
output column rather than the input one.

Next month's report will cover November against this baseline. The raw data is
published at `/api/prices.json` if you want to run your own analysis before then.
