/* ToolSummary — extractive summarizer + keyword chart. Vanilla JS, no dependencies. */
(function () {
  "use strict";

  var STOP_WORDS = new Set((
    "a an the and or but if while of to in on at by for with without from into onto over under " +
    "is are was were be been being am do does did doing have has had having i you he she it we they " +
    "me him her us them my your his its our their this that these those as not no nor so than then " +
    "too very can will just don should now about above after again against all any because before " +
    "below between both down during each few further here how more most other out same some such " +
    "there through up what when where which who whom why would could may might must shall"
  ).split(/\s+/));

  function splitSentences(text) {
    var cleaned = text.replace(/\s+/g, " ").trim();
    if (!cleaned) return [];
    var parts = cleaned.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g);
    if (!parts) return [cleaned];
    return parts
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });
  }

  function tokenize(sentence) {
    var matches = sentence.toLowerCase().match(/[a-z0-9][a-z0-9'’-]*/g);
    return matches || [];
  }

  function scoreSentences(sentences) {
    var freq = Object.create(null);
    var contentWords = 0;

    sentences.forEach(function (sentence) {
      tokenize(sentence).forEach(function (w) {
        if (STOP_WORDS.has(w) || w.length < 3) return;
        freq[w] = (freq[w] || 0) + 1;
        contentWords += 1;
      });
    });

    var maxFreq = 0;
    Object.keys(freq).forEach(function (w) {
      if (freq[w] > maxFreq) maxFreq = freq[w];
    });

    var scored = sentences.map(function (sentence, index) {
      var words = tokenize(sentence).filter(function (w) {
        return !STOP_WORDS.has(w) && w.length >= 3;
      });
      var total = 0;
      var seen = Object.create(null);
      words.forEach(function (w) {
        if (seen[w]) return; // count each distinct content word once per sentence
        seen[w] = true;
        total += (freq[w] || 0) / (maxFreq || 1);
      });
      // Normalize by sentence length (with a floor) so long sentences do not always win.
      var lengthPenalty = Math.sqrt(Math.max(words.length, 3));
      return { sentence: sentence, index: index, score: total / lengthPenalty };
    });

    return { scored: scored, freq: freq, contentWords: contentWords, maxFreq: maxFreq };
  }

  function escapeHtml(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderChart(freq, limit) {
    var chart = document.getElementById("chart");
    var entries = Object.keys(freq).map(function (w) {
      return { word: w, count: freq[w] };
    }).sort(function (a, b) {
      return b.count - a.count || a.word.localeCompare(b.word);
    }).slice(0, limit || 8);

    chart.innerHTML = "";
    if (!entries.length) {
      chart.innerHTML = '<p class="small text-muted mb-0">No keywords found in the text.</p>';
      return;
    }
    var max = entries[0].count;
    entries.forEach(function (entry) {
      var row = document.createElement("div");
      row.className = "chart-row";
      var pct = Math.max(6, Math.round((entry.count / max) * 100));
      row.innerHTML =
        '<span class="chart-label">' + escapeHtml(entry.word) + "</span>" +
        '<span class="chart-track"><span class="chart-bar" style="width:' + pct + '%"></span></span>' +
        '<span class="chart-count">' + entry.count + "</span>";
      chart.appendChild(row);
    });
  }

  function optimizeLength(varLength, sentenceCount) {
    var requested = parseInt(varLength, 10) || 3;
    if (sentenceCount <= 1) return sentenceCount;
    return Math.max(1, Math.min(requested, Math.max(1, sentenceCount - 1)));
  }

  function summarize() {
    var source = document.getElementById("source").value;
    var status = document.getElementById("status");
    var wrap = document.getElementById("result-wrap");

    if (!source || !source.trim()) {
      status.textContent = "Please paste some text to summarize.";
      wrap.classList.add("d-none");
      return;
    }

    var sentences = splitSentences(source);
    if (sentences.length < 2) {
      status.textContent = "Add at least two sentences so there is something to rank.";
      wrap.classList.add("d-none");
      return;
    }

    var analysis = scoreSentences(sentences);
    var count = optimizeLength(document.getElementById("length").value, sentences.length);
    var top = analysis.scored
      .slice()
      .sort(function (a, b) {
        return b.score - a.score || a.index - b.index;
      })
      .slice(0, count)
      .sort(function (a, b) { return a.index - b.index; });

    var summaryHtml = top.map(function (item) {
      return "<mark>" + escapeHtml(item.sentence) + "</mark>";
    }).join(" ");
    document.getElementById("summary").innerHTML = summaryHtml;

    var sourceWords = source.match(/\S+/g) || [];
    var summaryWords = top.reduce(function (n, item) {
      return n + (item.sentence.match(/\S+/g) || []).length;
    }, 0);
    var reduction = sourceWords.length
      ? Math.round((1 - summaryWords / sourceWords.length) * 100)
      : 0;

    document.getElementById("stats").textContent =
      sentences.length + " sentences in, " + count + " out · " +
      sourceWords.length + " → " + summaryWords + " words (" +
      reduction + "% shorter) · " + analysis.contentWords + " content words analysed.";

    renderChart(analysis.freq, 8);
    wrap.classList.remove("d-none");
    status.textContent = "Summary generated.";
  }

  function clearAll() {
    document.getElementById("source").value = "";
    document.getElementById("summary").innerHTML = "";
    document.getElementById("stats").textContent = "";
    document.getElementById("chart").innerHTML = "";
    document.getElementById("result-wrap").classList.add("d-none");
    document.getElementById("status").textContent = "";
    document.getElementById("source").focus();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("run").addEventListener("click", summarize);
    document.getElementById("clear").addEventListener("click", clearAll);
    document.getElementById("source").addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") summarize();
    });
  });
})();
