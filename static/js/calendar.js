/* ─────────────────────────────────────────────────────────────
   ACS Booking — public calendar page
   1:1 port of the Apps Script buildCal() builder.
   All page logic lives here; calendar.html is just a shell.
   ───────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  var body   = document.body;
  var lang   = body.dataset.lang || 'ar';
  var theme  = body.dataset.theme || '';
  var ORG_AR = body.dataset.orgAr || '';
  var ORG_EN = body.dataset.orgEn || '';
  var LOGO   = body.dataset.logo  || '';

  var cY, cM, bkD = [], blkD = {}, hallsCache = [], isLoading = false;

  var MAR = ["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"];
  var MEN = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  var DAR = ["الأحد","الاثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت"];
  var DEN = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];

  function t(k) {
    var arMap = {
      orgName:ORG_AR, sub:"نظام حجز القاعات والمرافق",
      today:"اليوم", app:"معتمد", pend:"قيد المراجعة", blk:"غير متاح",
      noEv:"لا توجد حجوزات", blocked:"فترة غير متاحة:", fullDay:"يوم كامل",
      file:"مرفق", rights:"جميع الحقوق محفوظة", more:"أخرى",
      bookDay:"احجز لهذا اليوم", multiDay:"متعدد الأيام",
      pastDate:"لا يمكن الحجز بتاريخ سابق", adminBtn:"لوحة التحكم",
      allVenues:"— كل القاعات —"
    };
    var enMap = {
      orgName:ORG_EN, sub:"Venue & Facility Booking System",
      today:"Today", app:"Approved", pend:"Pending", blk:"Blocked",
      noEv:"No bookings", blocked:"Blocked:", fullDay:"Full Day",
      file:"File", rights:"All Rights Reserved", more:"more",
      bookDay:"Book this day", multiDay:"Multi-day",
      pastDate:"Cannot book past dates", adminBtn:"Admin",
      allVenues:"— All Venues —"
    };
    var map = lang === "ar" ? arMap : enMap;
    return map[k] || k;
  }

  function esc(s) {
    return s == null ? "" :
      String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  function fmtD(ds) { return ds ? String(ds) : ""; }

  function pad2(n) { return String(n).padStart(2, "0"); }

  function todayISO() {
    var n = new Date();
    return n.getFullYear() + "-" + pad2(n.getMonth() + 1) + "-" + pad2(n.getDate());
  }

  /* ── Clock ───────────────────────────────────────────────── */
  function ammanNow(){
    var p=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Amman',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'})
      .formatToParts(new Date()).reduce(function(a,x){a[x.type]=x.value;return a;},{});
    return p.year+'-'+p.month+'-'+p.day+' | '+p.hour+':'+p.minute+':'+p.second;
  }
  function updateClock() {
    var el = document.getElementById("clockEl");
    if (el) { el.dir = "ltr"; el.textContent = ammanNow(); }
  }
  setInterval(updateClock, 1000);

  /* ── Theme propagation on internal links ─────────────────── */
  function propagateTheme() {
    if (!theme) return;
    document.querySelectorAll('a[href]').forEach(function (a) {
      try {
        var u = new URL(a.href, location.href);
        if (u.origin !== location.origin) return;
        if (!u.searchParams.get('theme')) u.searchParams.set('theme', theme);
        a.href = u.pathname + '?' + u.searchParams.toString();
      } catch (e) {}
    });
  }

  /* ── Data loading ────────────────────────────────────────── */
  function loadHalls() {
    fetch('/api/halls')
      .then(function (r) { return r.json(); })
      .then(function (h) { hallsCache = h || []; updateHallFilter(); })
      .catch(function () {});
  }

  function updateHallFilter() {
    var sel = document.getElementById("hallFilter");
    if (!sel) return;
    var val = sel.value;
    sel.innerHTML = '<option value="">' + t("allVenues") + '</option>';
    for (var i = 0; i < hallsCache.length; i++) {
      var o = document.createElement("option");
      o.value = hallsCache[i].nameAr;
      o.textContent = lang === "ar"
        ? hallsCache[i].nameAr
        : (hallsCache[i].nameEn || hallsCache[i].nameAr);
      sel.appendChild(o);
    }
    sel.value = val;
  }

  function loadMonth() {
    if (isLoading) return;
    isLoading = true;
    fetch('/api/month_data?year=' + cY + '&month=' + cM)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        bkD = (d && d.bookings) || [];
        blkD = (d && d.blocked) || {};
        renderCal();
      })
      .catch(function () { renderCal(); })
      .finally(function () { isLoading = false; });
  }
  // expose for inline onchange handler
  window.loadMonth = loadMonth;

  /* ── Calendar rendering ──────────────────────────────────── */
  function getEvs(ds, hf) {
    var r = [];
    for (var i = 0; i < bkD.length; i++) {
      var bk = bkD[i];
      if (!hf || bk.hall === hf) {
        var sd = bk.date, ed = bk.endDate || sd;
        if (ds >= sd && ds <= ed) r.push(bk);
      }
    }
    return r;
  }

  function renderCal() {
    var MN = lang === "ar" ? MAR : MEN;
    var mt = document.getElementById("mTitle");
    if (mt) mt.textContent = MN[cM - 1] + " " + cY;

    var g = document.getElementById("grid");
    if (!g) return;
    while (g.children.length > 7) g.removeChild(g.lastChild);

    var fd   = new Date(cY, cM - 1, 1).getDay();
    var dim  = new Date(cY, cM, 0).getDate();
    var pDim = new Date(cY, cM - 1, 0).getDate();
    var tStr = todayISO();
    var hfEl = document.getElementById("hallFilter");
    var hf   = hfEl ? hfEl.value : "";

    for (var i = fd - 1; i >= 0; i--) g.appendChild(mkD(pDim - i, true, "", false, [], false));

    for (var d = 1; d <= dim; d++) {
      var ds = cY + "-" + pad2(cM) + "-" + pad2(d);
      g.appendChild(mkD(d, false, ds, ds === tStr, getEvs(ds, hf), ds < tStr));
    }

    var rem = 42 - g.children.length;
    for (var n = 1; n <= rem; n++) g.appendChild(mkD(n, true, "", false, [], false));
  }

  function mkD(day, other, ds, isT, evs, isPast) {
    var c = document.createElement("div");
    c.className = "cal-day";
    if (other)             c.classList.add("other");
    if (isT)               c.classList.add("today");
    if (isPast && !isT)    c.classList.add("past-day");

    var nm = document.createElement("div");
    nm.className = "dn";
    nm.textContent = day;
    c.appendChild(nm);

    var blkArr = blkD[ds] || [];
    var hfEl = document.getElementById("hallFilter");
    var hf   = hfEl ? hfEl.value : "";

    var isBlk = false, blkObj = null;
    for (var b = 0; b < blkArr.length; b++) {
      if (!hf || !blkArr[b].hall || blkArr[b].hall === hf) {
        isBlk = true; blkObj = blkArr[b]; break;
      }
    }
    if (isBlk) {
      c.classList.add("blocked-day");
      var bl = document.createElement("div");
      bl.className = "ev-bar ev-blk";
      var blkTxt = t("blk");
      if (blkObj.fromTime && blkObj.toTime) blkTxt += " " + blkObj.fromTime + "-" + blkObj.toTime;
      if (blkObj.hall) blkTxt += " (" + blkObj.hall + ")";
      bl.textContent = blkTxt;
      c.appendChild(bl);
    }

    // GAS parity: always show up to 2 event bars per day cell.
    var maxShow = 2;
    if (evs && evs.length > 0) {
      for (var i = 0; i < Math.min(evs.length, maxShow); i++) {
        var ev = evs[i];
        var bar = document.createElement("div");
        bar.className = "ev-bar s-" + ev.status;
        bar.textContent = ev.title || "";
        bar.title = ev.title || "";
        c.appendChild(bar);
      }
      if (evs.length > maxShow) {
        var m = document.createElement("div");
        m.className = "ev-more";
        m.textContent = "+" + (evs.length - maxShow) + " " + t("more");
        c.appendChild(m);
      }
    }

    if (!other && ds) c.onclick = function () { openDay(ds); };
    return c;
  }

  /* ── Nav ─────────────────────────────────────────────────── */
  function nav(d) {
    cM += d;
    if (cM > 12) { cM = 1;  cY++; }
    if (cM < 1)  { cM = 12; cY--; }
    renderCal();
    loadMonth();
  }
  function goToday() {
    var n = new Date();
    cY = n.getFullYear();
    cM = n.getMonth() + 1;
    renderCal();
    loadMonth();
  }
  window.nav     = nav;
  window.goToday = goToday;

  /* ── Day modal ───────────────────────────────────────────── */
  function openDay(ds) {
    var d  = new Date(ds + "T00:00:00");
    var DN = lang === "ar" ? DAR : DEN;
    var MN = lang === "ar" ? MAR : MEN;
    var mt = document.getElementById("modalTitle");
    if (mt) mt.textContent = DN[d.getDay()] + ", " + d.getDate() + " " + MN[d.getMonth()] + " " + d.getFullYear();

    var hfEl   = document.getElementById("hallFilter");
    var hf     = hfEl ? hfEl.value : "";
    var evs    = getEvs(ds, hf);
    var nowStr = todayISO();
    var themeQ = theme ? ('&theme=' + encodeURIComponent(theme)) : '';

    var html = "";

    if (ds >= nowStr) {
      html += '<a class="book-now-modal" href="/book?date=' + ds + '&lang=' + lang + themeQ +
              '"><i class="fas fa-calendar-plus"></i> ' + t("bookDay") + '</a>';
    } else {
      html += '<div class="past-notice"><i class="fas fa-lock"></i> ' + t("pastDate") + '</div>';
    }

    var blkArr = blkD[ds] || [];
    for (var b = 0; b < blkArr.length; b++) {
      var bo = blkArr[b];
      if (!hf || !bo.hall || bo.hall === hf) {
        var blkMsg = (lang === "ar" ? "🚫 غير متاح: " : "🚫 Blocked: ") + esc(bo.reason || "");
        if (bo.fromTime && bo.toTime) blkMsg += " (" + esc(bo.fromTime) + " – " + esc(bo.toTime) + ")";
        if (bo.hall)                  blkMsg += " - " + esc(bo.hall);
        html += '<div class="blk-info">' + blkMsg + '</div>';
      }
    }

    if (evs.length === 0) {
      html += '<div class="no-ev"><i class="fas fa-calendar-xmark"></i> ' + t("noEv") + '</div>';
    } else {
      evs.sort(function (a, b) { return (a.startTime || "").localeCompare(b.startTime || ""); });
      for (var i = 0; i < evs.length; i++) {
        var ev      = evs[i];
        var stL     = ev.status === "approved" ? t("app") : t("pend");
        var isMulti = ev.endDate && ev.endDate !== ev.date;
        var range   = fmtD(ev.date);
        if (isMulti) range = fmtD(ev.date) + " — " + fmtD(ev.endDate);

        var timeTxt = ev.fullDay
          ? t("fullDay")
          : (esc(ev.startTime) + (ev.endTime ? " - " + esc(ev.endTime) : ""));

        html += '<div class="ev-item s-' + ev.status + '">' +
                  '<div class="ev-row-top">' +
                    '<div class="ev-time"><i class="fas fa-clock"></i> ' + timeTxt + '</div>' +
                    '<span class="st-badge s-' + ev.status + '">' + stL + '</span>' +
                  '</div>';

        if (isMulti) {
          html += '<div style="margin-bottom:4px">' +
                    '<i class="fas fa-calendar-week" style="color:#1a5c64;margin:0 4px"></i>' +
                    '<span class="multiday-badge">' + t("multiDay") + '</span> ' + range +
                  '</div>';
        }

        html += '<div class="ev-title">' + esc(ev.title) + '</div>' +
                '<div class="ev-hall"><i class="fas fa-door-open"></i> ' + esc(ev.hall) +
                  (ev.behalf ? ' — ' + esc(ev.behalf) : '') +
                '</div>' +
              '</div>';
      }
    }

    document.getElementById("modalBody").innerHTML = html;
    document.getElementById("modalBg").classList.add("open");
  }
  function closeModal() {
    document.getElementById("modalBg").classList.remove("open");
  }
  window.openDay    = openDay;
  window.closeModal = closeModal;

  /* ── Language toggle (in-place, like GAS) ────────────────── */
  function toggleLang() {
    lang = lang === "ar" ? "en" : "ar";
    document.documentElement.lang = lang;
    document.documentElement.dir  = lang === "ar" ? "rtl" : "ltr";
    body.dataset.lang = lang;

    document.getElementById("btnLang").innerHTML =
      '<i class="fas fa-globe"></i> <span id="langTxt">' + (lang === "ar" ? "EN" : "عربي") + '</span>';

    document.getElementById("hdrTitle").textContent = t("orgName");
    document.getElementById("hdrSub").textContent   = t("sub");
    document.getElementById("btnToday").textContent = t("today");
    document.getElementById("tAdmin").textContent   = t("adminBtn");
    document.getElementById("lgApp").textContent    = t("app");
    document.getElementById("lgPend").textContent   = t("pend");
    document.getElementById("lgBlk").textContent    = t("blk");
    var foot = document.getElementById("footerOrg");
    if (foot) foot.textContent = lang === "ar" ? ORG_AR : ORG_EN;

    var hdrs = document.querySelectorAll(".cal-hdr");
    for (var i = 0; i < hdrs.length; i++) {
      hdrs[i].textContent = lang === "ar"
        ? hdrs[i].getAttribute("data-ar")
        : hdrs[i].getAttribute("data-en");
    }

    // Chevron icons swap
    var navBtns = document.querySelectorAll(".nav-btns .nav-btn:not(.today-btn) i");
    if (navBtns.length === 2) {
      navBtns[0].className = "fas fa-chevron-" + (lang === "ar" ? "right" : "left");
      navBtns[1].className = "fas fa-chevron-" + (lang === "ar" ? "left"  : "right");
    }

    // Update admin link's lang param too
    var adm = document.getElementById("adminLink");
    if (adm) {
      try {
        var u = new URL(adm.href, location.href);
        u.searchParams.set('lang', lang);
        adm.href = u.pathname + '?' + u.searchParams.toString();
      } catch (e) {}
    }

    // Also keep the URL's ?lang= in sync (without reload) for share links
    try {
      var url = new URL(location.href);
      url.searchParams.set('lang', lang);
      history.replaceState(null, '', url.pathname + '?' + url.searchParams.toString());
    } catch (e) {}

    updateHallFilter();
    renderCal();
    updateClock();
  }
  window.toggleLang = toggleLang;

  /* ── Init ────────────────────────────────────────────────── */
  window.addEventListener("DOMContentLoaded", function () {
    updateClock();
    var n = new Date();
    cY = n.getFullYear();
    cM = n.getMonth() + 1;

    // Footer year
    var fy = document.getElementById("footerYear");
    if (fy) fy.textContent = n.getFullYear();

    propagateTheme();
    renderCal();
    loadHalls();
    loadMonth();

    // If a pre_date was passed (deep-link), pop its modal open after data loads.
    var pd = body.dataset.preDate;
    if (pd) {
      setTimeout(function () { try { openDay(pd); } catch (e) {} }, 400);
    }
  });

  // 30-minute auto-refresh (matches GAS).
  setInterval(function () {
    var mb = document.getElementById("modalBg");
    if (!mb || !mb.classList.contains("open")) loadMonth();
  }, 1800000);

})();
