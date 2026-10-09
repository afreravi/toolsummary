# ToolSummary

ToolSummary is a small, self-contained web app that turns long text into a short,
readable summary right in the browser. It was bootstrapped by an
[OpenHands](https://www.openhands.dev) automation on behalf of the repository owner.

## What it does

Paste any passage of text into the input box, choose how many sentences you want,
and ToolSummary scores the most representative sentences using a classic
extractive-summarization approach (word-frequency scoring with stop-word removal).
Everything runs client-side in vanilla JavaScript — no build step, no server, and no
data ever leaves the page.

## How it works

1. Open `index.html` in a browser (or serve the folder with any static server).
2. Paste text into the **Source text** box.
3. Pick a summary length and press **Summarize**.
4. Read the shortened text and the keyword chart below it.

## Layout

```
toolsummary/
├── index.html           ← landing page + the summarizer tool
├── style.css            ← light theme, purple accent (#60089c)
├── script.js            ← extractive summarizer + keyword chart
├── GUIDELINES.md        ← build rules for the daily builder automation
├── tools-queue.txt      ← queue of upcoming tool ideas
├── automation_prompt.md ← prompt used by the daily builder automation
└── README.md
```

## Automation

A daily cron automation (04:30 UTC) reads `GUIDELINES.md` and `tools-queue.txt`,
builds one new tool idea, and opens a pull request. The owner reviews and merges to
approve.

## Disclaimer

ToolSummary produces automatic, extractive summaries. Results are a best-effort aid
for reading and are not guaranteed to be accurate or complete. Always read the
original source when correctness matters.
