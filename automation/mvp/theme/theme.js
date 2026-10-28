/* ==========================================================================
   Toolsummary — theme interactions
   Vanilla, no dependencies, progressive enhancement. Every page works with
   this file absent; it only adds filtering, sorting, nav and form feedback.
   ========================================================================== */
(function () {
  "use strict";

  /* ---------------------------------------------------------- mobile nav */
  function initNav() {
    var toggle = document.querySelector(".nav__toggle");
    var nav = document.getElementById("site-nav");
    if (!toggle || !nav) return;
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? "Close" : "Menu";
    });
  }

  /* ------------------------------------------- ledger: filter, sort, page */
  // One controller owns row visibility. Filtering and paging both hide rows,
  // so they cannot be independent or they fight: the pager would reveal rows
  // the filter had hidden, and vice versa.
  function initLedger() {
    var table = document.getElementById("t");
    if (!table || !table.tHead) return;
    var body = table.tBodies[0];
    var input = document.getElementById("q");
    var count = document.querySelector(".search__count");
    var empty = document.querySelector(".empty");
    var pager = document.getElementById("pager");
    var PER = 50;
    var state = { q: "", page: 1 };

    function rows() { return Array.prototype.slice.call(body.rows); }

    function matches(r) {
      return !state.q || r.textContent.toLowerCase().indexOf(state.q) !== -1;
    }

    function render() {
      var list = rows();
      var hits = list.filter(matches);
      var pages = Math.max(1, Math.ceil(hits.length / PER));
      if (state.page > pages) state.page = pages;
      if (state.page < 1) state.page = 1;
      var start = (state.page - 1) * PER;

      list.forEach(function (r) { r.hidden = true; });
      hits.slice(start, start + PER).forEach(function (r) { r.hidden = false; });

      if (count) {
        count.textContent = state.q
          ? hits.length + " of " + list.length
          : list.length + " models";
      }
      if (empty) empty.classList.toggle("is-on", hits.length === 0);
      if (pager) {
        pager.hidden = hits.length <= PER;
        buildPager(pager, pages, state.page, hits.length, list.length,
                   start, function (p) { state.page = p; render(); });
      }
    }

    if (input) {
      input.addEventListener("input", function () {
        state.q = input.value.trim().toLowerCase();
        state.page = 1;
        render();
      });
      input.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { input.value = ""; state.q = ""; state.page = 1; render(); }
      });
    }

    var headers = Array.prototype.slice.call(table.tHead.rows[0].cells);
    headers.forEach(function (th, idx) {
      if (th.dataset.sort === "off") return;
      th.style.cursor = "pointer";
      th.setAttribute("role", "button");
      th.setAttribute("tabindex", "0");
      th.setAttribute("aria-sort", "none");

      function sort() {
        var dir = th.dataset.dir === "asc" ? "desc" : "asc";
        headers.forEach(function (h) {
          h.dataset.dir = "";
          h.removeAttribute("aria-sort");
          var mark = h.querySelector(".sort-mark");
          if (mark) mark.remove();
        });
        th.dataset.dir = dir;
        th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
        var mark = document.createElement("span");
        mark.className = "sort-mark";
        mark.textContent = dir === "asc" ? " \u2191" : " \u2193";
        mark.style.color = "var(--teal-ink)";
        th.appendChild(mark);

        var numeric = th.dataset.sort === "num";
        var list = rows();
        list.sort(function (a, b) {
          var av = a.cells[idx].dataset.value || a.cells[idx].textContent.trim();
          var bv = b.cells[idx].dataset.value || b.cells[idx].textContent.trim();
          if (numeric) {
            var an = parseFloat(av), bn = parseFloat(bv);
            if (isNaN(an)) an = Infinity;
            if (isNaN(bn)) bn = Infinity;
            return dir === "asc" ? an - bn : bn - an;
          }
          return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
        });
        list.forEach(function (r) { body.appendChild(r); });
        render();
      }

      th.addEventListener("click", sort);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); }
      });
    });

    render();
  }

  /* ----------------------------------------------------------- pager UI */
  function buildPager(nav, pages, current, shown, total, start, go) {
    function btn(label, page, opts) {
      opts = opts || {};
      var b = document.createElement("button");
      b.type = "button";
      b.className = "pager__btn" + (opts.cls ? " " + opts.cls : "");
      b.textContent = label;
      if (opts.aria) b.setAttribute("aria-label", opts.aria);
      if (opts.disabled) b.disabled = true;
      else b.addEventListener("click", function () { go(page); });
      if (opts.current) b.setAttribute("aria-current", "page");
      return b;
    }

    nav.textContent = "";
    var info = document.createElement("span");
    info.className = "pager__info";
    info.textContent = "Showing " + (start + 1) + "\u2013" +
      Math.min(start + 50, shown) + " of " + shown +
      (shown === total ? "" : " matching") + " models";
    nav.appendChild(info);

    var controls = document.createElement("span");
    controls.className = "pager__controls";
    controls.appendChild(btn("\u2190 Prev", current - 1,
      { disabled: current <= 1, aria: "Previous page" }));

    // A window of page numbers around the current page, with the ends always
    // reachable, so 15 pages do not become 15 buttons on a phone.
    var nums = [];
    for (var p = 1; p <= pages; p++) {
      if (p === 1 || p === pages || Math.abs(p - current) <= 1) nums.push(p);
      else if (nums[nums.length - 1] !== "\u2026") nums.push("\u2026");
    }
    nums.forEach(function (n) {
      if (n === "\u2026") {
        var s = document.createElement("span");
        s.className = "pager__gap";
        s.textContent = "\u2026";
        controls.appendChild(s);
      } else {
        controls.appendChild(btn(String(n), n,
          { cls: n === current ? "is-current" : "", current: n === current,
            aria: "Page " + n }));
      }
    });

    controls.appendChild(btn("Next \u2192", current + 1,
      { disabled: current >= pages, aria: "Next page" }));
    nav.appendChild(controls);
  }

  /* ---------------------------------------------------------------- modal */
  // One modal per page, reused for success and failure. Focus is moved into
  // the dialog and trapped there while it is open, then returned to whatever
  // had focus before, so a keyboard user is not dumped back at the top.
  function initModal() {
    var modal = document.getElementById("form-modal");
    if (!modal) return null;
    var box = modal.querySelector(".modal__box");
    var title = modal.querySelector(".modal__title");
    var msg = modal.querySelector(".modal__msg");
    var icon = modal.querySelector(".modal__icon");
    var okBtn = modal.querySelector("[data-modal-ok]");
    var lastFocus = null;

    function close() {
      modal.classList.remove("is-on");
      modal.hidden = true;
      document.body.style.overflow = "";
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    function open(kind, heading, text) {
      lastFocus = document.activeElement;
      modal.classList.toggle("modal--error", kind === "error");
      if (icon) icon.textContent = kind === "error" ? "!" : "\u2713";
      if (title) title.textContent = heading;
      if (msg) msg.textContent = text;
      modal.hidden = false;
      document.body.style.overflow = "hidden";
      // Next frame, so the opacity transition actually runs.
      requestAnimationFrame(function () { modal.classList.add("is-on"); });
      if (okBtn) okBtn.focus();
    }

    if (okBtn) okBtn.addEventListener("click", close);
    modal.addEventListener("click", function (e) { if (e.target === modal) close(); });
    document.addEventListener("keydown", function (e) {
      if (modal.hidden) return;
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      if (e.key !== "Tab") return;
      var f = box.querySelectorAll("button, [href], input, select, textarea");
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });

    return { open: open, close: close };
  }

  /* --------------------------------------------------------- submit form */
  function initForm() {
    var form = document.getElementById("submit-form");
    if (!form) return;
    var modal = initModal();
    var btn = form.querySelector('button[type="submit"]');
    var btnLabel = btn ? btn.textContent : "";

    function fieldOf(el) { return el.closest(".field"); }

    function validate(el) {
      var wrap = fieldOf(el);
      if (!wrap) return true;
      var ok = el.checkValidity();
      wrap.classList.toggle("is-bad", !ok);
      return ok;
    }

    form.addEventListener("input", function (e) {
      if (e.target.matches("input, select, textarea")) validate(e.target);
    });
    form.addEventListener("blur", function (e) {
      if (e.target.matches("input, select, textarea")) validate(e.target);
    }, true);

    // Post with fetch so the page can tell success from failure and respond
    // in place. A native submit would hand the user to the provider and lose
    // the distinction: a 200 and a 400 both look like "the page went away".
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var fields = Array.prototype.slice.call(
        form.querySelectorAll("input, select, textarea")
      );
      var bad = fields.filter(function (f) { return !validate(f); });
      if (bad.length) {
        var first = fieldOf(bad[0]);
        if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
        if (modal) {
          modal.open("error", "Check the highlighted fields",
            "Some required answers are missing or invalid. Nothing was sent, and "
            + "what you typed is still here.");
        }
        return;
      }

      if (btn) { btn.disabled = true; btn.textContent = "Sending\u2026"; }

      fetch(form.action, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(Object.fromEntries(new FormData(form))),
      })
        .then(function (r) {
          return r.json()
            .catch(function () { return {}; })
            .then(function (j) { return { ok: r.ok, status: r.status, body: j }; });
        })
        .then(function (res) {
          if (res.ok && res.body && res.body.success) {
            form.reset();
            fields.forEach(function (f) {
              var w = fieldOf(f);
              if (w) w.classList.remove("is-bad");
            });
            if (modal) {
              modal.open("ok", "Thank you",
                form.dataset.okMessage
                || "Your message reached us. We usually reply within one working day.");
            }
          } else {
            var why = (res.body && res.body.message) || "The form service rejected it.";
            if (modal) {
              modal.open("error", "Not sent",
                why + " Your answers are still here, so you can try again without retyping.");
            }
          }
        })
        .catch(function () {
          if (modal) {
            modal.open("error", "Not sent",
              "We could not reach the server. Check your connection and try again. "
              + "Your answers are still here.");
          }
        })
        .then(function () {
          if (btn) { btn.disabled = false; btn.textContent = btnLabel; }
        });
    });
  }

  /* ------------------------------------------------------------ footer */
  function initYear() {
    var el = document.querySelector("[data-year]");
    if (el) el.textContent = new Date().getFullYear();
  }

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    initNav();
    initLedger();
    initForm();
    initYear();
  });
})();
