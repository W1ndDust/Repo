/* DustDrift-Repo · 交互层。无依赖，渐进增强：禁用 JS 时列表与复制降级为原生行为。 */
(function () {
  "use strict";

  /* ── 外观切换：auto → light → dark ── */
  var root = document.documentElement;
  var order = ["auto", "light", "dark"];
  var label = { auto: "跟随系统", light: "浅色", dark: "深色" };
  var themeBtn = document.getElementById("themeBtn");
  function applyTheme(t) {
    if (t === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", t);
    root.setAttribute("data-theme-mode", t);
    if (themeBtn) themeBtn.setAttribute("aria-label", "切换外观：" + label[t]);
    try { localStorage.setItem("dd-theme", t); } catch (e) {}
  }
  var current = "auto";
  try { current = localStorage.getItem("dd-theme") || "auto"; } catch (e) {}
  applyTheme(current);
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      current = order[(order.indexOf(current) + 1) % order.length];
      applyTheme(current);
    });
  }

  /* ── 移动端导航 ── */
  var menuBtn = document.getElementById("menuBtn");
  var nav = document.getElementById("nav");
  if (menuBtn && nav) {
    menuBtn.addEventListener("click", function () {
      var open = nav.getAttribute("data-open") === "1";
      nav.setAttribute("data-open", open ? "0" : "1");
      menuBtn.setAttribute("aria-expanded", String(!open));
    });
  }

  /* ── 复制（含降级） ── */
  var toast, toastTimer;
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
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.removeAttribute("data-show"); }, 2000);
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
    var done = function () { showToast("已复制，去客户端粘贴"); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () {
        showToast(legacyCopy(text) ? "已复制，去客户端粘贴" : "复制失败，请长按地址手动复制");
      });
    } else {
      showToast(legacyCopy(text) ? "已复制，去客户端粘贴" : "复制失败，请长按地址手动复制");
    }
  });

  /* ── 列表：搜索 / 分组 / 排序 ── */
  var list = document.getElementById("list");
  if (!list) return;

  var rows = Array.prototype.slice.call(list.querySelectorAll("li"));
  var q = document.getElementById("q");
  var clearBtn = document.querySelector(".search__clear");
  var segs = document.querySelectorAll(".seg button");
  var sortSel = document.getElementById("sort");
  var empty = document.getElementById("empty");
  var countEl = document.getElementById("resultCount");
  var clearAll = document.getElementById("clearAll");
  var section = "";

  function norm(s) { return (s || "").toLowerCase(); }

  function apply() {
    var needle = norm(q && q.value.trim());
    var shown = 0;
    rows.forEach(function (li) {
      var hay = norm(li.getAttribute("data-search"));
      var sec = li.getAttribute("data-section") || "";
      var hit = (!needle || hay.indexOf(needle) !== -1) && (!section || sec === section);
      li.hidden = !hit;
      if (hit) shown++;
    });
    if (empty) empty.hidden = shown !== 0;
    if (countEl) countEl.textContent = shown + " 个";
    if (clearBtn) clearBtn.hidden = !(q && q.value);
  }

  function sortRows(key) {
    var copy = rows.slice().sort(function (a, b) {
      var va = a.getAttribute("data-" + key) || "";
      var vb = b.getAttribute("data-" + key) || "";
      return va.localeCompare(vb, "zh-Hans-CN", { numeric: true, sensitivity: "base" });
    });
    copy.forEach(function (li) { list.appendChild(li); });
    rows = copy;
  }

  if (q) {
    q.addEventListener("input", apply);
    q.addEventListener("search", apply);
  }
  if (clearBtn) clearBtn.addEventListener("click", function () { q.value = ""; q.focus(); apply(); });
  if (sortSel) sortSel.addEventListener("change", function () { sortRows(sortSel.value); apply(); });

  Array.prototype.forEach.call(segs, function (btn, i) {
    btn.addEventListener("click", function () {
      section = btn.getAttribute("data-section") || "";
      Array.prototype.forEach.call(segs, function (b) { b.setAttribute("aria-selected", "false"); });
      btn.setAttribute("aria-selected", "true");
      apply();
    });
    btn.addEventListener("keydown", function (ev) {
      var d = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
      if (!d) return;
      ev.preventDefault();
      var next = segs[(i + d + segs.length) % segs.length];
      next.focus();
      next.click();
    });
  });

  if (clearAll) clearAll.addEventListener("click", function () {
    if (q) q.value = "";
    section = "";
    Array.prototype.forEach.call(segs, function (b, i) { b.setAttribute("aria-selected", i === 0 ? "true" : "false"); });
    apply();
  });

  apply();
})();
