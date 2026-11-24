/* جدول المباني والمرافق: عرض يومي (عمود لكل مبنى) أو أسبوعي (عمود لكل يوم لمبنى واحد).
   الضغط على فراغ ينقل إلى نموذج الحجز بالتاريخ والمبنى والساعة، وعلى حجز يعرض تفاصيله. */
(function () {
  'use strict';
  var AR = document.documentElement.lang !== 'en';
  var LANG = AR ? 'ar' : 'en';
  var L = function (a, e) { return AR ? a : e; };
  var $ = function (id) { return document.getElementById(id); };
  var HOUR = 52;                       // ارتفاع الساعة بالبكسل
  var MONTHS_AR = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
  var MONTHS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var DAYS_AR = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
  var DAYS_EN = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var halls = [], data = { bookings: [], blocked: {} }, view = 'day', cat = '', hallSel = '';
  var today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Amman' }).format(new Date());
  var cur = today, lastKey = '', uid = 0;

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function toDate(ds) { var p = ds.split('-'); return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])); }
  function iso(d) { return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()); }
  function addDays(ds, n) { var d = toDate(ds); d.setUTCDate(d.getUTCDate() + n); return iso(d); }
  function mins(t) { var p = (t || '').split(':'); return p.length === 2 ? +p[0] * 60 + +p[1] : null; }
  function hm(m) { return pad(Math.floor(m / 60)) + ':' + pad(m % 60); }
  function nm(h) { return AR ? h.nameAr : (h.nameEn || h.nameAr); }
  function nameOf(arName) { var h = halls.filter(function (x) { return x.nameAr === arName; })[0]; return h ? nm(h) : arName; }
  function weekStart(ds) { var d = toDate(ds); return addDays(ds, -d.getUTCDay()); }          // الأحد أول الأسبوع
  function dayLabel(ds) { var d = toDate(ds); return (AR ? DAYS_AR : DAYS_EN)[d.getUTCDay()]; }

  function visibleHalls() { return halls.filter(function (h) { return (!cat || h.category === cat) && (!hallSel || h.nameAr === hallSel); }); }

  function fillControls() {
    var seen = {}, chips = '<button class="chip' + (cat ? '' : ' active') + '" type="button" data-cat="">' + L('الكل', 'All') + '</button>';
    halls.forEach(function (h) { if (!seen[h.category]) { seen[h.category] = 1; chips += '<button class="chip' + (cat === h.category ? ' active' : '') + '" type="button" data-cat="' + esc(h.category) + '">' + esc(AR ? h.categoryAr : h.categoryEn) + '</button>'; } });
    $('scChips').innerHTML = chips;
    var sel = $('scHall'), list = halls.filter(function (h) { return !cat || h.category === cat; });
    sel.innerHTML = '<option value="">' + (view === 'week' ? L('اختر المبنى أو المرفق', 'Choose a building or facility') : L('كل المباني والمرافق', 'All buildings and facilities')) + '</option>' +
      list.map(function (h) { return '<option value="' + esc(h.nameAr) + '">' + esc(nm(h)) + '</option>'; }).join('');
    if (!list.some(function (h) { return h.nameAr === hallSel; })) hallSel = '';
    if (view === 'week' && !hallSel && list.length) hallSel = list[0].nameAr;
    sel.value = hallSel;
  }

  function range() { return view === 'week' ? [weekStart(cur), addDays(weekStart(cur), 6)] : [cur, cur]; }

  function load() {
    var r = range(), key = r[0] + '|' + r[1];
    $('scTitle').textContent = title(r);
    fetch('/api/range_data?from=' + r[0] + '&to=' + r[1]).then(function (x) { return x.json(); }).then(function (d) { data = d; lastKey = key; render(); })
      .catch(function () { $('sched').innerHTML = '<div class="alert alert-error" style="margin:10px">' + L('تعذّر تحميل الجدول', 'The schedule could not be loaded') + '</div>'; });
  }
  function title(r) {
    var a = toDate(r[0]), b = toDate(r[1]), M = AR ? MONTHS_AR : MONTHS_EN;
    if (view === 'day') return dayLabel(r[0]) + ' ' + a.getUTCDate() + ' ' + M[a.getUTCMonth()] + ' ' + a.getUTCFullYear();
    return a.getUTCDate() + ' ' + M[a.getUTCMonth()] + ' – ' + b.getUTCDate() + ' ' + M[b.getUTCMonth()] + ' ' + b.getUTCFullYear();
  }

  // أحداث عمود (مبنى في يوم): كل حجز يقطع اليوم، والحجز متعدد الأيام يُعامل يوماً كاملاً
  function eventsFor(hallAr, ds) {
    var out = [];
    data.bookings.forEach(function (b) {
      if (b.hall !== hallAr || b.date > ds || b.endDate < ds) return;
      var multi = b.endDate !== b.date, s = mins(b.startTime), e = mins(b.endTime);
      var full = b.fullDay || multi || s === null;
      out.push({ uid: ++uid, kind: 'bk', b: b, full: full, s: full ? 0 : s, e: full ? 1440 : (e === null ? s + 60 : e) });
    });
    (data.blocked[ds] || []).forEach(function (x) {
      if (x.hall && x.hall !== hallAr) return;
      var s = mins(x.fromTime), e = mins(x.toTime), full = s === null || e === null;
      out.push({ uid: ++uid, kind: 'blk', x: x, full: full, s: full ? 0 : s, e: full ? 1440 : e });
    });
    return out;
  }
  function lanes(evs) {           // يوزّع الأحداث المتداخلة على مسارات متجاورة
    evs.sort(function (a, b) { return a.s - b.s || a.e - b.e; });
    var cols = [];
    evs.forEach(function (ev) {
      var i = 0; while (i < cols.length && cols[i] > ev.s) i++;
      cols[i] = ev.e; ev.lane = i;
    });
    evs.forEach(function (ev) {
      ev.lanes = 1;
      evs.forEach(function (o) { if (o !== ev && o.s < ev.e && ev.s < o.e) ev.lanes = Math.max(ev.lanes, o.lane + 1, ev.lane + 1); });
    });
    return evs;
  }

  function render() {
    var cols = [];       // كل عمود: {label, sub, hall, ds}
    if (view === 'day') visibleHalls().forEach(function (h) { cols.push({ label: nm(h), sub: '', hall: h.nameAr, ds: cur }); });
    else { var ws = weekStart(cur); for (var i = 0; i < 7; i++) { var d = addDays(ws, i); cols.push({ label: dayLabel(d), sub: toDate(d).getUTCDate() + '', hall: hallSel, ds: d }); } }
    var box = $('sched');
    $('scHint').textContent = view === 'week' ? L('اختر مبنى أو مرفقاً لعرض أسبوعه.', 'Choose a building or facility to see its week.') : L('اضغط فراغاً في الجدول لبدء حجز في ذلك الوقت.', 'Click an empty slot to start a booking at that time.');
    if (!cols.length || (view === 'week' && !hallSel)) { box.innerHTML = '<p class="muted" style="padding:20px;text-align:center">' + L('لا توجد مبانٍ أو مرافق لعرضها.', 'There are no buildings or facilities to show.') + '</p>'; return; }
    var all = cols.map(function (c) { return lanes(eventsFor(c.hall, c.ds)); }), lo = 7 * 60, hi = 22 * 60;
    all.forEach(function (evs) { evs.forEach(function (ev) { if (!ev.full) { lo = Math.min(lo, Math.floor(ev.s / 60) * 60); hi = Math.max(hi, Math.ceil(ev.e / 60) * 60); } }); });
    hi = Math.min(hi, 24 * 60);
    var h0 = lo / 60, h1 = hi / 60, total = (h1 - h0) * HOUR;
    var html = '<div class="sc-head"><div class="sc-axis-h"></div>';
    cols.forEach(function (c) { html += '<div class="sc-colh' + (c.ds === today ? ' today' : '') + '"><b><bdi>' + esc(c.label) + '</bdi></b>' + (c.sub ? '<span dir="ltr">' + esc(c.sub) + '</span>' : '') + '</div>'; });
    html += '</div>';
    if (all.some(function (evs) { return evs.some(function (e) { return e.full; }); })) {
      html += '<div class="sc-fullrow"><div class="sc-axis-h"><span>' + L('يوم كامل', 'All day') + '</span></div>';
      cols.forEach(function (c, ci) { html += '<div class="sc-fullcell">' + all[ci].filter(function (e) { return e.full; }).map(function (e) { return chip(e); }).join('') + '</div>'; });
      html += '</div>';
    }
    html += '<div class="sc-body"><div class="sc-axis" style="height:' + total + 'px">';
    for (var h = h0; h < h1; h++) html += '<div class="sc-hour" style="height:' + HOUR + 'px"><span dir="ltr">' + pad(h) + ':00</span></div>';
    html += '</div>';
    var nowM = (function () { var p = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Amman', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date()).split(':'); return +p[0] * 60 + +p[1]; })();
    cols.forEach(function (c, ci) {
      var past = c.ds < today;
      html += '<div class="sc-col' + (past ? ' past' : '') + '" data-ds="' + c.ds + '" data-hall="' + esc(c.hall) + '" style="height:' + total + 'px">';
      for (var h2 = h0; h2 < h1; h2++) html += '<div class="sc-line" style="height:' + HOUR + 'px"></div>';
      all[ci].filter(function (e) { return !e.full; }).forEach(function (e) {
        var top = (e.s - lo) / 60 * HOUR, hh = Math.max(22, (e.e - e.s) / 60 * HOUR - 2), w = 100 / e.lanes;
        html += '<button type="button" class="sc-ev ' + cls(e) + '" data-i="' + ci + '|' + all[ci].indexOf(e) + '" style="top:' + top + 'px;height:' + hh + 'px;inset-inline-start:' + (e.lane * w) + '%;width:calc(' + w + '% - 2px)">' + inner(e, hh) + '</button>';
      });
      if (c.ds === today && nowM >= lo && nowM <= hi) html += '<div class="sc-now" style="top:' + ((nowM - lo) / 60 * HOUR) + 'px"></div>';
      html += '</div>';
    });
    html += '</div>';
    box.innerHTML = html;
    var hd = box.querySelector('.sc-head'), fr = box.querySelector('.sc-fullrow'); if (hd && fr) fr.style.top = hd.offsetHeight + 'px';
    box.style.setProperty('--cols', cols.length);
    box._all = all; box._lo = lo; box._cols = cols;
  }
  function cls(e) { return e.kind === 'blk' ? 'blk' : (e.b.status === 'pending' ? 'pending' : ''); }
  function inner(e, h) {
    var t = e.kind === 'blk' ? e.x.reason : (e.b.title || L('محجوز', 'Booked')), tm = hm(e.s) + '–' + hm(Math.min(e.e, 1439));
    return '<b><bdi>' + esc(t) + '</bdi></b>' + (h > 40 ? '<span dir="ltr">' + tm + '</span>' : '');
  }
  function chip(e) { var all = $('sched'); return '<button type="button" class="sc-chip ' + cls(e) + '" data-full="' + e.uid + '"><bdi>' + esc(e.kind === 'blk' ? e.x.reason : (e.b.title || L('محجوز', 'Booked'))) + '</bdi></button>'; }

  function openModal(html, ttl) { $('scMTitle').textContent = ttl; $('scMBody').innerHTML = html; $('scModal').classList.add('open'); }
  function detail(e) {
    if (e.kind === 'blk') return '<div class="item blk"><b><i class="fas fa-ban"></i> ' + esc(e.x.reason) + '</b><div class="meta"><span>' + (e.x.hall ? esc(nameOf(e.x.hall)) : L('كل المباني والمرافق', 'All buildings and facilities')) + '</span>' +
      (e.x.fromTime ? '<span dir="ltr">' + esc(e.x.fromTime) + ' - ' + esc(e.x.toTime) + '</span>' : '<span>' + L('يوم كامل', 'Full day') + '</span>') + '</div></div>';
    var b = e.b;
    return '<div class="item ' + (b.status === 'pending' ? 'pending' : '') + '"><b><bdi>' + esc(b.title || L('محجوز', 'Booked')) + '</bdi></b><div class="meta"><span><i class="fas fa-building"></i> <bdi>' + esc(nameOf(b.hall)) + '</bdi></span>' +
      '<span dir="ltr"><i class="fas fa-clock"></i> ' + (b.fullDay ? esc(L('يوم كامل', 'Full day')) : esc(b.startTime + (b.endTime ? ' - ' + b.endTime : ''))) + '</span>' + 
      '<span class="badge ' + (b.status === 'pending' ? 'badge-pending' : 'badge-approved') + '">' + (b.status === 'pending' ? L('قيد المراجعة', 'Pending') : L('معتمد', 'Approved')) + '</span></div></div>';
  }

  $('sched').addEventListener('click', function (ev) {
    var box = $('sched'), b = ev.target.closest('.sc-ev');
    if (b) { var p = b.dataset.i.split('|'), e = box._all[+p[0]][+p[1]]; return openModal(detail(e), e.kind === 'blk' ? L('فترة غير متاحة', 'Unavailable') : L('تفاصيل الحجز', 'Booking details')); }
    var c = ev.target.closest('.sc-chip');
    if (c) {
      var found = null; box._all.forEach(function (evs) { evs.forEach(function (e) { if (e.full && String(e.uid) === c.dataset.full) found = found || e; }); });
      if (found) return openModal(detail(found), found.kind === 'blk' ? L('فترة غير متاحة', 'Unavailable') : L('تفاصيل الحجز', 'Booking details'));
    }
    var col = ev.target.closest('.sc-col');
    if (!col || col.classList.contains('past')) return;
    var r = col.getBoundingClientRect(), y = ev.clientY - r.top, m = box._lo + Math.floor(y / HOUR * 2) * 30;
    var hall = col.dataset.hall;
    location.href = '/book?lang=' + LANG + '&date=' + col.dataset.ds + '&start=' + hm(Math.min(m, 23 * 60)) + (hall ? '&hall=' + encodeURIComponent(hall) : '');
  });
  $('scMClose').addEventListener('click', function () { $('scModal').classList.remove('open'); });
  $('scModal').addEventListener('click', function (e) { if (e.target === this) this.classList.remove('open'); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') $('scModal').classList.remove('open'); });

  function setView(v) {
    view = v; $('scDay').classList.toggle('active', v === 'day'); $('scWeek').classList.toggle('active', v === 'week');
    fillControls(); load();
  }
  $('scDay').addEventListener('click', function () { setView('day'); });
  $('scWeek').addEventListener('click', function () { setView('week'); });
  $('scPrev').addEventListener('click', function () { cur = addDays(cur, view === 'week' ? -7 : -1); load(); });
  $('scNext').addEventListener('click', function () { cur = addDays(cur, view === 'week' ? 7 : 1); load(); });
  $('scToday').addEventListener('click', function () { cur = today; load(); });
  $('scHall').addEventListener('change', function () { hallSel = this.value; render(); });
  $('scChips').addEventListener('click', function (e) { var b = e.target.closest('.chip'); if (b) { cat = b.dataset.cat; fillControls(); render(); } });

  if (window.PRE_DATE && /^\d{4}-\d{2}-\d{2}$/.test(window.PRE_DATE)) cur = window.PRE_DATE;
  fetch('/api/halls').then(function (r) { return r.json(); }).then(function (h) {
    halls = h; if (window.PRE_HALL && h.some(function (x) { return x.nameAr === window.PRE_HALL; })) hallSel = window.PRE_HALL;
    fillControls(); load();
  });
})();
