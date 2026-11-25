/* الروزنامة العامة: شهر بحجوزاته والفترات غير المتاحة، وتصفية بالنوع والمبنى، ونافذة لتفاصيل اليوم. */
(function () {
  'use strict';
  var AR = document.documentElement.lang !== 'en';
  var LANG = AR ? 'ar' : 'en';
  var L = function (a, e) { return AR ? a : e; };
  var MONTHS_AR = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
  var MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  var DAYS_AR = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
  var DAYS_EN = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var grid = document.getElementById('calGrid');
  var halls = [], data = { bookings: [], blocked: {} }, cat = '', hallSel = '';
  var today = ammanToday();
  var cur = { y: +today.slice(0, 4), m: +today.slice(5, 7) };

  function ammanToday() {
    var p = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Amman', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
    return p;
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function iso(y, m, d) { return y + '-' + pad(m) + '-' + pad(d); }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function hallName(h) { return AR ? h.nameAr : (h.nameEn || h.nameAr); }
  function nameOf(arName) { var h = halls.filter(function (x) { return x.nameAr === arName; })[0]; return h ? hallName(h) : arName; }

  function loadHalls() {
    return fetch('/api/halls').then(function (r) { return r.json(); }).then(function (h) {
      halls = h;
      var seen = {}, chips = '<button class="chip active" type="button" data-cat="">' + L('الكل', 'All') + '</button>';
      h.forEach(function (x) { if (!seen[x.category]) { seen[x.category] = 1; chips += '<button class="chip" type="button" data-cat="' + esc(x.category) + '">' + esc(AR ? x.categoryAr : x.categoryEn) + '</button>'; } });
      document.getElementById('catChips').innerHTML = chips;
      fillHallSelect();
    });
  }
  function fillHallSelect() {
    var sel = document.getElementById('hallFilter');
    sel.innerHTML = '<option value="">' + L('كل المباني والمرافق', 'All buildings and facilities') + '</option>' +
      halls.filter(function (h) { return !cat || h.category === cat; }).map(function (h) { return '<option value="' + esc(h.nameAr) + '">' + esc(hallName(h)) + '</option>'; }).join('');
    sel.value = hallSel;
    if (sel.value !== hallSel) { hallSel = ''; sel.value = ''; }
  }
  function visible(b) {
    if (hallSel && b.hall !== hallSel) return false;
    return !cat || b.category === cat;
  }
  function load() {
    fetch('/api/month_data?year=' + cur.y + '&month=' + cur.m).then(function (r) { return r.json(); }).then(function (d) { data = d; render(); })
      .catch(function () { grid.innerHTML = '<div class="alert alert-error" style="grid-column:1/-1;margin:10px">' + L('تعذّر تحميل الروزنامة', 'The calendar could not be loaded') + '</div>'; });
  }
  function bookingsOn(ds) {
    return data.bookings.filter(function (b) { return visible(b) && b.date <= ds && b.endDate >= ds; });
  }
  function blockedOn(ds) {
    return (data.blocked[ds] || []).filter(function (x) { return !hallSel || !x.hall || x.hall === hallSel; });
  }
  function timeText(b) { return b.fullDay ? L('يوم كامل', 'Full day') : (b.startTime + (b.endTime ? ' - ' + b.endTime : '')); }

  function countText(n) {
    if (!AR) return n + (n === 1 ? ' booking' : ' bookings');
    return n === 1 ? 'حجز واحد' : n === 2 ? 'حجزان' : n <= 10 ? n + ' حجوزات' : n + ' حجزاً';
  }
  function render() {
    document.getElementById('calTitle').textContent = (AR ? MONTHS_AR : MONTHS_EN)[cur.m - 1] + ' ' + cur.y;
    var first = new Date(cur.y, cur.m - 1, 1).getDay(), days = new Date(cur.y, cur.m, 0).getDate();
    var prevDays = new Date(cur.y, cur.m - 1, 0).getDate(), html = '';
    (AR ? DAYS_AR : DAYS_EN).forEach(function (d) { html += '<div class="cal-hdr">' + d + '</div>'; });
    for (var i = 0; i < first; i++) html += '<div class="cal-day other"><span class="dn">' + (prevDays - first + 1 + i) + '</span></div>';
    for (var d = 1; d <= days; d++) {
      var ds = iso(cur.y, cur.m, d), bk = bookingsOn(ds), bl = blockedOn(ds);
      var cls = 'cal-day' + (bk.length || bl.length ? ' has' : '') + (ds === today ? ' today' : '') + (ds < today ? ' past' : '') + (bl.length ? ' blocked' : '');
      html += '<div class="' + cls + '" role="button" tabindex="0" data-date="' + ds + '"><span class="dn">' + d + '</span>';
      var n = bk.length + bl.length, dots = '';
      bl.slice(0, 4).forEach(function () { dots += '<i class="dot blk"></i>'; });
      bk.slice(0, 4 - Math.min(bl.length, 4)).forEach(function (b) { dots += '<i class="dot' + (b.status === 'pending' ? ' pending' : '') + '"></i>'; });
      if (n) html += '<span class="dots">' + dots + '</span><span class="cnt">' + countText(n) + '</span>';
      html += '</div>';
    }
    var tail = (7 - (first + days) % 7) % 7;
    for (var k = 1; k <= tail; k++) html += '<div class="cal-day other"><span class="dn">' + k + '</span></div>';
    grid.innerHTML = html;
  }

  function openDay(ds) {
    var bk = bookingsOn(ds), bl = blockedOn(ds), h = '';
    document.getElementById('dayTitle').textContent = ds;
    bl.forEach(function (x) {
      h += '<div class="item blk"><b><i class="fas fa-ban"></i> ' + esc(x.reason) + '</b><div class="meta"><span>' + (x.hall ? esc(nameOf(x.hall)) : L('كل المباني والمرافق', 'All buildings and facilities')) + '</span>' +
        (x.fromTime ? '<span dir="ltr">' + esc(x.fromTime) + ' - ' + esc(x.toTime) + '</span>' : '<span>' + L('يوم كامل', 'Full day') + '</span>') + '</div></div>';
    });
    bk.forEach(function (b) {
      h += '<div class="item ' + (b.status === 'pending' ? 'pending' : '') + '"><b><bdi>' + esc(b.title || L('محجوز', 'Booked')) + '</bdi></b><div class="meta"><span><i class="fas fa-building"></i> <bdi>' + esc(nameOf(b.hall)) + '</bdi></span>' +
        '<span dir="ltr"><i class="fas fa-clock"></i> ' + esc(timeText(b)) + '</span>' +
        '<span class="badge ' + (b.status === 'pending' ? 'badge-pending' : 'badge-approved') + '">' + (b.status === 'pending' ? L('قيد المراجعة', 'Pending') : L('معتمد', 'Approved')) + '</span></div></div>';
    });
    if (!h) h = '<p class="muted" style="text-align:center;padding:18px">' + L('لا توجد حجوزات في هذا اليوم.', 'No bookings on this day.') + '</p>';
    document.getElementById('dayList').innerHTML = h;
    var link = document.getElementById('dayBook');
    link.style.display = ds < today ? 'none' : '';
    if (ds < today) document.getElementById('dayList').insertAdjacentHTML('afterbegin', '<div class="alert alert-info" style="margin-bottom:10px"><i class="fas fa-circle-info"></i> ' + L('هذا اليوم مضى فلا يمكن الحجز فيه. اختر اليوم أو يوماً قادماً.', 'This day has passed, so it cannot be booked. Choose today or a later day.') + '</div>');
    link.href = '/book?lang=' + LANG + '&date=' + ds + (hallSel ? '&hall=' + encodeURIComponent(hallSel) : '');
    document.getElementById('dayModal').classList.add('open');
  }

  grid.addEventListener('click', function (e) { var c = e.target.closest('.cal-day[data-date]'); if (c) openDay(c.dataset.date); });
  grid.addEventListener('keydown', function (e) { if (e.key === 'Enter') { var c = e.target.closest('.cal-day[data-date]'); if (c) openDay(c.dataset.date); } });
  document.getElementById('dayClose').addEventListener('click', function () { document.getElementById('dayModal').classList.remove('open'); });
  document.getElementById('dayModal').addEventListener('click', function (e) { if (e.target === this) this.classList.remove('open'); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') document.getElementById('dayModal').classList.remove('open'); });
  function go(dm) { cur.m += dm; if (cur.m < 1) { cur.m = 12; cur.y--; } if (cur.m > 12) { cur.m = 1; cur.y++; } load(); }
  document.getElementById('prevBtn').addEventListener('click', function () { go(-1); });
  document.getElementById('nextBtn').addEventListener('click', function () { go(1); });
  document.getElementById('todayBtn').addEventListener('click', function () { cur = { y: +today.slice(0, 4), m: +today.slice(5, 7) }; load(); });
  document.getElementById('hallFilter').addEventListener('change', function () { hallSel = this.value; render(); });
  document.getElementById('catChips').addEventListener('click', function (e) {
    var b = e.target.closest('.chip'); if (!b) return;
    cat = b.dataset.cat; [].forEach.call(this.querySelectorAll('.chip'), function (x) { x.classList.toggle('active', x === b); });
    fillHallSelect(); render();
  });

  if (window.PRE_DATE && /^\d{4}-\d{2}-\d{2}$/.test(window.PRE_DATE)) { cur = { y: +window.PRE_DATE.slice(0, 4), m: +window.PRE_DATE.slice(5, 7) }; }
  loadHalls().then(load, load);
  // تحديث تلقائي: حجز جديد يظهر دون تحديث الصفحة
  function refreshSoon() { if (!document.hidden && !document.getElementById('dayModal').classList.contains('open')) load(); }
  setInterval(refreshSoon, 30000);
  document.addEventListener('visibilitychange', refreshSoon);
})();
