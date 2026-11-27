/* DustDrift · 交互层。无依赖，渐进增强。 */
(function () {
  "use strict";

  /* 移动端导航 */
  var toggle = document.getElementById("navToggle");
  var menu = document.getElementById("navMenu");
  if (toggle && menu) {
    toggle.addEventListener("click", function () {
      var open = menu.getAttribute("data-open") === "1";
      menu.setAttribute("data-open", open ? "0" : "1");
      toggle.setAttribute("aria-expanded", String(!open));
    });
  }

  /* 复制 + Toast */
  var toast, timer;
  function showToast(msg) {
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "toast";
      toast.setAttribute("role", "status");
      toast.setAttribute("aria-live", "polite");
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.setAttribute("data-show", "1");
    clearTimeout(timer);
    timer = setTimeout(function () { toast.removeAttribute("data-show"); }, 2000);
  }

  function legacyCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:0;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
    return ok;
  }

  document.addEventListener("click", function (ev) {
    var el = ev.target.closest("[data-copy]");
    if (!el) return;
    var text = el.getAttribute("data-copy");
    var done = function () { showToast("已复制到剪贴板"); };
    var fail = function () { showToast("复制失败，请长按地址手动复制"); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () {
        legacyCopy(text) ? done() : fail();
      });
    } else {
      legacyCopy(text) ? done() : fail();
    }
  });

  /* 目录页：搜索 / 筛选 / 排序 */
  var list = document.getElementById("list");
  if (!list) return;

  var rows = Array.prototype.slice.call(list.querySelectorAll(".row"));
  var q = document.getElementById("q");
  var clearBtn = document.querySelector(".field__clear");
  var chips = document.querySelectorAll(".chips button");
  var sortSel = document.getElementById("sort");
  var empty = document.getElementById("empty");
  var emptyText = document.getElementById("emptyText");
  var clearAll = document.getElementById("clearAll");
  var current = "";
  var initialOrder = rows.slice();

  function norm(s) { return (s || "").toLowerCase().replace(/\s+/g, " ").trim(); }

  function apply() {
    var needle = norm(q && q.value);
    var shown = 0;
    rows.forEach(function (li) {
      var hay = norm(li.getAttribute("data-search"));
      var sec = li.getAttribute("data-section") || "";
      var hit = (!needle || hay.indexOf(needle) !== -1) && (!current || sec === current);
      li.hidden = !hit;
      if (hit) shown++;
    });
    if (empty) {
      var none = rows.length === 0;
      empty.hidden = shown !== 0;
      if (emptyText) emptyText.textContent = none ? "源里还没有插件" : "没有匹配的插件";
      if (clearAll) clearAll.hidden = none;
    }
    if (clearBtn) clearBtn.hidden = !(q && q.value);
    var title = document.querySelector(".pagehead__meta");
    if (title) title.textContent = shown + " / " + rows.length + " 个插件 · 数据来自 APT 索引";
  }

  function sortRows(key) {
    var copy = rows.slice().sort(function (a, b) {
      return (a.getAttribute("data-" + key) || "").localeCompare(
        b.getAttribute("data-" + key) || "", "zh-Hans-CN",
        { numeric: true, sensitivity: "base" });
    });
    copy.forEach(function (li) { list.appendChild(li); });
    rows = copy;
  }

  if (q) {
    q.addEventListener("input", apply);
    q.addEventListener("search", apply);
  }
  if (clearBtn) clearBtn.addEventListener("click", function () { q.value = ""; q.focus(); apply(); });
  if (sortSel) {
    sortSel.addEventListener("change", function () {
      if (sortSel.value === "name") {
        initialOrder.forEach(function (li) { list.appendChild(li); });
        rows = initialOrder.slice();
      } else {
        sortRows("version");
      }
      apply();
    });
  }

  Array.prototype.forEach.call(chips, function (btn, i) {
    btn.addEventListener("click", function () {
      if (btn.disabled) return;
      current = btn.getAttribute("data-section") || "";
      Array.prototype.forEach.call(chips, function (b) { b.setAttribute("aria-selected", "false"); });
      btn.setAttribute("aria-selected", "true");
      apply();
    });
    btn.addEventListener("keydown", function (ev) {
      var d = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
      if (!d) return;
      ev.preventDefault();
      var next = chips[(i + d + chips.length) % chips.length];
      if (next && !next.disabled) { next.focus(); next.click(); }
    });
  });

  if (clearAll) clearAll.addEventListener("click", function () {
    if (q) q.value = "";
    current = "";
    Array.prototype.forEach.call(chips, function (b, i) { b.setAttribute("aria-selected", i === 0 ? "true" : "false"); });
    apply();
  });

  /* 从首页分组入口带 hash 进来时，自动选中对应筛选 */
  var hash = decodeURIComponent(location.hash.replace("#", ""));
  if (hash) {
    Array.prototype.forEach.call(chips, function (b) {
      if (b.getAttribute("data-section") === hash) { current = hash; b.setAttribute("aria-selected", "true"); }
      else if (b.getAttribute("data-section") === "") { b.setAttribute("aria-selected", "false"); }
    });
  }

  apply();
})();
