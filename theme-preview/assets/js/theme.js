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

  /* ------------------------------------------------------- table filter */
  function initFilter() {
    var input = document.getElementById("q");
    var table = document.getElementById("t");
    if (!input || !table) return;

    var body = table.tBodies[0];
    var rows = Array.prototype.slice.call(body.rows);
    var count = document.querySelector(".search__count");
    var empty = document.querySelector(".empty");
    var total = rows.length;

    function apply() {
      var v = input.value.trim().toLowerCase();
      var shown = 0;
      rows.forEach(function (r) {
        var hit = !v || r.textContent.toLowerCase().indexOf(v) !== -1;
        r.hidden = !hit;
        if (hit) shown++;
      });
      if (count) {
        count.textContent = v ? shown + " of " + total : total + " models";
      }
      if (empty) empty.classList.toggle("is-on", shown === 0);
    }

    input.addEventListener("input", apply);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { input.value = ""; apply(); }
    });
    apply();
  }

  /* ------------------------------------------------------- table sorting */
  function initSort() {
    var table = document.getElementById("t");
    if (!table || !table.tHead) return;
    var headers = Array.prototype.slice.call(table.tHead.rows[0].cells);
    var body = table.tBodies[0];

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
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          var av = a.cells[idx].dataset.value || a.cells[idx].textContent.trim();
          var bv = b.cells[idx].dataset.value || b.cells[idx].textContent.trim();
          if (numeric) {
            var an = parseFloat(av), bn = parseFloat(bv);
            if (isNaN(an)) an = Infinity;
            if (isNaN(bn)) bn = Infinity;
            return dir === "asc" ? an - bn : bn - an;
          }
          return dir === "asc"
            ? av.localeCompare(bv)
            : bv.localeCompare(av);
        });
        rows.forEach(function (r) { body.appendChild(r); });
      }

      th.addEventListener("click", sort);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); }
      });
    });
  }

  /* --------------------------------------------------------- submit form */
  function initForm() {
    var form = document.getElementById("submit-form");
    if (!form) return;

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

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var fields = Array.prototype.slice.call(
        form.querySelectorAll("input, select, textarea")
      );
      var bad = fields.filter(function (f) { return !validate(f); });
      if (bad.length) {
        var first = fieldOf(bad[0]);
        if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      var done = document.getElementById("submit-done");
      if (done) {
        done.hidden = false;
        done.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      form.reset();
      fields.forEach(function (f) {
        var w = fieldOf(f);
        if (w) w.classList.remove("is-bad");
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
    initFilter();
    initSort();
    initForm();
    initYear();
  });
})();
