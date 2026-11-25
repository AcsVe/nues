/* لوحة التحكم: تبويبات بصلاحياتها، وجداول موحّدة (بحث وتصفية لكل عمود وترتيب وتحديد متعدد وإجراءات جماعية)،
   وتقويم، وتقارير، وإعدادات، والشريط الإخباري. كل طلب كتابة يحمل رمز CSRF. */
(function () {
  'use strict';
  var AR = document.documentElement.lang !== 'en';
  var L = function (a, e) { return AR ? a : e; };
  var $ = function (id) { return document.getElementById(id); };
  var ME = window.ME || { perms: [] };
  var CATS = window.CATEGORIES || [];
  var halls = [], bookings = [], curStatus = 'all', statFilter = '';
  var can = function (p) { return ME.sysadmin || (Array.isArray(p) ? p.some(function (x) { return ME.perms.indexOf(x) >= 0; }) : ME.perms.indexOf(p) >= 0); };

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function nm(h) { return AR ? h.nameAr : (h.nameEn || h.nameAr); }
  function hallLabel(arName) { var h = halls.filter(function (x) { return x.nameAr === arName; })[0]; return h ? nm(h) : arName; }
  function catLabel(k) { var c = CATS.filter(function (x) { return x.key === k; })[0]; return c ? (AR ? c.ar : c.en) : k; }
  function ammanNow() {
    var p = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Amman', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
      .formatToParts(new Date()).reduce(function (a, x) { a[x.type] = x.value; return a; }, {});
    return p.year + '-' + p.month + '-' + p.day + ' ' + p.hour + ':' + p.minute + ':' + p.second;
  }
  function today() { return ammanNow().slice(0, 10); }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  var toastTimer;
  function toast(msg, bad) {
    var t = $('toast'); t.textContent = msg; t.style.background = bad ? '#991b1b' : ''; t.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.classList.remove('show'); }, 4200);
  }
  function api(url, opt) {
    opt = opt || {}; opt.credentials = 'same-origin'; opt.headers = Object.assign({}, opt.headers);
    if (opt.method && opt.method !== 'GET') opt.headers['X-CSRF-Token'] = window.CSRF || '';
    if (opt.body && typeof opt.body !== 'string' && !(window.FormData && opt.body instanceof FormData)) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(opt.body); }
    return fetch(url, opt).then(function (r) {
      if (r.status === 401) { location.href = '/admin/login?lang=' + (AR ? 'ar' : 'en'); throw new Error('401'); }
      return r.json().then(function (j) { if (!r.ok) { var e = new Error((AR ? (j.errorAr || j.error) : (j.errorEn || j.error)) || ('HTTP ' + r.status)); e.status = r.status; throw e; } return j; });
    });
  }
  function post(url, body) { return api(url, { method: 'POST', body: body || {} }); }
  function fail(e) { toast(e.message || L('حدث خطأ', 'An error occurred'), true); }
  function open(id) { $(id).classList.add('open'); }
  function close(el) { el.closest('.modal-overlay').classList.remove('open'); }
  document.addEventListener('click', function (e) {
    var c = e.target.closest('[data-close]'); if (c) close(c);
    if (e.target.classList && e.target.classList.contains('modal-overlay')) e.target.classList.remove('open');
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') [].forEach.call(document.querySelectorAll('.modal-overlay.open'), function (m) { m.classList.remove('open'); }); });

  // ───── الساعة والتبويبات ─────
  setInterval(function () { $('clockEl').textContent = ammanNow().replace(' ', ' | '); }, 1000); $('clockEl').textContent = ammanNow().replace(' ', ' | ');
  var TITLES = { home: L('الرئيسية', 'Home'), bookings: L('طلبات الحجز', 'Booking requests'), calview: L('التقويم', 'Calendar'), blocked: L('غير متاح', 'Unavailable'),
    reports: L('التقارير', 'Reports'), halls: L('المباني والمرافق', 'Buildings and facilities'), contacts: L('جهات الاتصال', 'Contacts'),
    ticker: L('الشريط الإخباري', 'News ticker'), links: L('الروابط المختصرة', 'Short links'), archive: L('الأرشفة', 'Archive'), settings: L('الإعدادات', 'Settings'), users: L('المستخدمون والصلاحيات', 'Users and permissions') };
  var loaded = {};
  function showTab(name, force) {
    if (!$('tab-' + name)) name = 'home';
    [].forEach.call(document.querySelectorAll('.tab-panel'), function (p) { p.classList.toggle('active', p.id === 'tab-' + name); });
    [].forEach.call(document.querySelectorAll('.nav-item[data-tab]'), function (b) { b.classList.toggle('active', b.dataset.tab === name); });
    $('pageTitle').textContent = TITLES[name] || '';
    if (window.closeSidebar) window.closeSidebar();
    try { history.replaceState(null, '', '#' + name); } catch (e) { /* لا يهم */ }
    var load = { bookings: loadBookings, calview: loadCal, blocked: loadBlocked, reports: loadReports, halls: loadHalls, contacts: loadContacts, ticker: loadTicker, links: loadLinks, archive: function () { /* يعمل بالأزرار */ }, settings: loadSettings, users: loadUsers, home: loadHome }[name];
    if (load && (force || !loaded[name] || name === 'home' || name === 'bookings')) { loaded[name] = true; load(); }
    window.scrollTo(0, 0);
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-tab],[data-go]');
    if (b && (b.classList.contains('nav-item') || b.dataset.go)) { e.preventDefault(); showTab(b.dataset.tab || b.dataset.go); }
  });
  $('refreshBtn').addEventListener('click', function () { loaded = {}; showTab((location.hash || '#home').slice(1), true); loadHallsList(); toast(L('تم التحديث', 'Refreshed')); });
  document.addEventListener('keydown', function (e) { var k = e.target.closest && e.target.closest('.kpi'); if (k && e.key === 'Enter') k.click(); });

  // ───── جداول موحّدة ─────
  function tableHtml(key, cols, rows, opts) {
    opts = opts || {};
    var th = opts.noSelect ? '' : '<th class="chk" data-nosort><input type="checkbox" class="bulk-all" aria-label="' + L('تحديد الكل', 'Select all') + '"></th>';
    cols.forEach(function (c) { th += '<th' + (c.filter ? ' data-filter="' + c.filter + '"' : '') + (c.sort ? ' data-sort="' + c.sort + '"' : '') + (c.act ? ' class="act" data-nosort' : '') + '>' + c.h + '</th>'; });
    return (opts.noSelect ? '' : '<div class="bulk-bar" id="bar-' + key + '"></div>') + '<div class="dt-wrap"><table data-table class="dt" data-key="' + key + '"><thead><tr>' + th + '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  }
  function chk(id) { return '<td class="chk"><input type="checkbox" class="bulk-item" value="' + esc(id) + '" aria-label="' + L('تحديد', 'Select') + '"></td>'; }
  function mount(box, key, actions, run) {
    if (window.dtInit) window.dtInit(box);
    var bar = box.querySelector('#bar-' + key), table = box.querySelector('table'), all = table.querySelector('.bulk-all');
    if (!bar || !all) return;
    bar.innerHTML = '<span class="bulk-count"></span>' + actions.map(function (a) { return '<button type="button" class="btn ' + (a.danger ? 'btn-red' : 'btn-outline') + ' btn-sm" data-act="' + a.id + '" disabled>' + a.label + '</button>'; }).join('');
    function items() { return [].slice.call(table.querySelectorAll('tbody .bulk-item')); }
    function sel() { return items().filter(function (i) { return i.checked && !i.closest('tr').hidden; }).map(function (i) { return i.value; }); }
    function refresh() {
      var n = sel().length;
      bar.querySelector('.bulk-count').textContent = n ? L('المحدّد: ', 'Selected: ') + n : L('لم يُحدَّد شيء', 'Nothing selected');
      [].forEach.call(bar.querySelectorAll('button'), function (b) { b.disabled = !n; });
      var vis = items().filter(function (i) { return !i.closest('tr').hidden; });
      all.checked = !!vis.length && vis.every(function (i) { return i.checked; });
    }
    all.addEventListener('change', function () { items().forEach(function (i) { if (!i.closest('tr').hidden) i.checked = all.checked; }); refresh(); });
    table.addEventListener('change', function (e) { if (e.target.classList.contains('bulk-item')) refresh(); });
    table.addEventListener('input', function () { setTimeout(refresh, 0); });
    bar.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      var ids = sel(), a = actions.filter(function (x) { return x.id === b.getAttribute('data-act'); })[0];
      if (!ids.length) return;
      if (a.danger && !confirm(a.label + ' (' + ids.length + ')؟')) return;
      run(a.id, ids);
    });
    refresh();
  }
  function bulkDone(r) {
    var m = L('تم: ', 'Done: ') + (r.done || 0);
    if (r.skipped) m += ' — ' + L('المستبعد: ', 'Skipped: ') + r.skipped;
    if (r.notes && r.notes.length) m += ' — ' + r.notes.join('; ');
    toast(m);
  }
  function empty(icon, msg) { return '<div class="card" style="text-align:center;color:var(--muted)"><i class="fas fa-' + icon + '" style="font-size:2rem;display:block;margin-bottom:8px"></i>' + msg + '</div>'; }
  var STATUS = { pending: [L('قيد المراجعة', 'Pending'), 'badge-pending'], approved: [L('معتمد', 'Approved'), 'badge-approved'], rejected: [L('مرفوض', 'Rejected'), 'badge-rejected'], cancelled: [L('ملغي', 'Cancelled'), 'badge-cancelled'] };
  function badge(s) { var x = STATUS[s] || [s, '']; return '<span class="badge ' + x[1] + '">' + esc(x[0]) + '</span>'; }
  function timeText(b) { return b.fullDay ? L('يوم كامل', 'Full day') : (b.startTime + (b.endTime ? ' - ' + b.endTime : '')); }
  function dateText(b) { return b.date + (b.endDate && b.endDate !== b.date ? ' → ' + b.endDate : ''); }
  function fillHallSelect(sel, withAll) {
    $(sel).innerHTML = (withAll ? '<option value="">' + L('كل المباني والمرافق', 'All buildings and facilities') + '</option>' : '') +
      halls.map(function (h) { return '<option value="' + esc(h.nameAr) + '">' + esc(nm(h)) + '</option>'; }).join('');
  }
  function loadHallsList() {
    if (!can(['halls', 'bookings.view', 'bookings.manage', 'blocked', 'contacts'])) return Promise.resolve();
    return api('/api/admin/halls').then(function (h) { halls = h; fillHallSelect('blkHall', true); fillHallSelect('bkHall'); fillHallSelect('ctHall', true); fillHallSelect('aHall', true); }).catch(function () { /* صلاحية */ });
  }

  // ───── الرئيسية ─────
  function loadHome() {
    if (!can(['bookings.view', 'reports', 'calendar'])) return;
    api('/api/admin/stats').then(function (s) {
      $('stTotal').textContent = s.total; $('stPending').textContent = s.pending; $('stApproved').textContent = s.approved; $('stRejected').textContent = s.rejected;
      $('stToday').textContent = s.today; $('stWeek').textContent = s.week;
      var nb = $('nbPending'); if (nb) nb.textContent = s.pending;
      $('upcoming').innerHTML = s.upcoming.length ? '<table><thead><tr><th>' + L('التاريخ', 'Date') + '</th><th>' + L('الوقت', 'Time') + '</th><th>' + L('المبنى أو المرفق', 'Building or facility') + '</th><th>' + L('المناسبة', 'Event') + '</th></tr></thead><tbody>' +
        s.upcoming.map(function (b) { return '<tr><td dir="ltr">' + esc(dateText(b)) + '</td><td dir="ltr">' + esc(timeText(b)) + '</td><td><bdi>' + esc(hallLabel(b.hall)) + '</bdi></td><td><bdi>' + esc(b.title) + '</bdi></td></tr>'; }).join('') + '</tbody></table>'
        : '<p class="muted" style="text-align:center;padding:12px">' + L('لا حجوزات قادمة خلال سبعة أيام.', 'No bookings in the next seven days.') + '</p>';
    }).catch(function () { /* صلاحية */ });
  }
  document.addEventListener('click', function (e) {
    var k = e.target.closest('.kpi[data-stat]'); if (!k) return;
    statFilter = k.dataset.stat; curStatus = (statFilter === 'today' || statFilter === 'week') ? 'approved' : statFilter;
    [].forEach.call($('statusBar').querySelectorAll('.filter-btn'), function (b) { b.classList.toggle('active', b.dataset.status === curStatus); });
    showTab('bookings', true);
  });

  // ───── الطلبات ─────
  $('statusBar').addEventListener('click', function (e) {
    var b = e.target.closest('.filter-btn'); if (!b) return;
    curStatus = b.dataset.status; statFilter = '';
    [].forEach.call(this.querySelectorAll('.filter-btn'), function (x) { x.classList.toggle('active', x === b); });
    loadBookings();
  });
  function loadBookings() {
    api('/api/admin/bookings?status=' + curStatus).then(function (d) {
      var t = today(), rows = d;
      if (statFilter === 'today') rows = d.filter(function (b) { return b.date <= t && b.endDate >= t; });
      if (statFilter === 'week') { var dt = new Date(t + 'T00:00:00'), dow = (dt.getDay() + 6) % 7, s = new Date(dt); s.setDate(dt.getDate() - dow); var en = new Date(s); en.setDate(s.getDate() + 6);
        var sd = s.getFullYear() + '-' + pad(s.getMonth() + 1) + '-' + pad(s.getDate()), ed = en.getFullYear() + '-' + pad(en.getMonth() + 1) + '-' + pad(en.getDate()); rows = d.filter(function (b) { return b.date >= sd && b.date <= ed; }); }
      bookings = d; renderBookings(rows);
      var pend = bookings.filter(function (b) { return b.status === 'pending'; }).length; if (curStatus === 'all' && $('nbPending')) $('nbPending').textContent = pend;
    }).catch(fail);
  }
  function renderBookings(d) {
    var box = $('bookingsBox');
    if (!d.length) { box.innerHTML = empty('inbox', L('لا توجد طلبات.', 'No requests.')); return; }
    var manage = can('bookings.manage');
    var cols = [{ h: L('رقم الطلب', 'ID'), filter: 'text' }, { h: L('مقدّم الطلب', 'Applicant'), filter: 'text' }, { h: L('المناسبة', 'Event'), filter: 'text' }, { h: L('المبنى أو المرفق', 'Building or facility'), filter: 'select' },
      { h: L('التاريخ', 'Date'), filter: 'text' }, { h: L('الوقت', 'Time'), filter: 'text' }, { h: L('الحضور والمستلزمات', 'Attendance and items'), filter: 'text' }, { h: L('الحالة', 'Status'), filter: 'select' }, { h: L('إجراءات', 'Actions'), act: true }];
    var rows = d.map(function (b) {
      var act = '';
      (b.attachments || []).forEach(function (a) { act += '<a class="btn btn-sm btn-blue" href="' + esc(a) + '" target="_blank" rel="noopener" aria-label="' + L('مرفق', 'Attachment') + '"><i class="fas fa-paperclip"></i></a>'; });
      act += '<button class="btn btn-sm btn-outline" data-cm="' + esc(b.reqId) + '" title="' + L('التعليقات', 'Comments') + '" aria-label="' + L('التعليقات', 'Comments') + '"><i class="fas fa-comment"></i>' + (b.comments ? ' ' + b.comments : '') + '</button>';
      if (manage) {
        act += '<button class="btn btn-sm btn-outline" data-edit="' + esc(b.reqId) + '" title="' + L('تعديل', 'Edit') + '" aria-label="' + L('تعديل', 'Edit') + '"><i class="fas fa-pen"></i></button>';
        if (b.status === 'pending') act += '<button class="btn btn-sm btn-green" data-do="approve" data-id="' + esc(b.reqId) + '" title="' + L('موافقة', 'Approve') + '" aria-label="' + L('موافقة', 'Approve') + '"><i class="fas fa-check"></i></button><button class="btn btn-sm btn-red" data-do="reject" data-id="' + esc(b.reqId) + '" title="' + L('رفض', 'Reject') + '" aria-label="' + L('رفض', 'Reject') + '"><i class="fas fa-xmark"></i></button>';
        if (b.status !== 'cancelled') act += '<button class="btn btn-sm btn-orange" data-do="cancel" data-id="' + esc(b.reqId) + '" title="' + L('إلغاء', 'Cancel') + '" aria-label="' + L('إلغاء', 'Cancel') + '"><i class="fas fa-ban"></i></button>';
        if (b.status !== 'pending' && b.status !== 'cancelled') act += '<button class="btn btn-sm btn-outline" data-do="pending" data-id="' + esc(b.reqId) + '" title="' + L('إرجاع إلى قيد المراجعة', 'Back to pending') + '" aria-label="' + L('إرجاع إلى قيد المراجعة', 'Back to pending') + '"><i class="fas fa-rotate-left"></i></button>';
      }
      return '<tr>' + chk(b.reqId) + '<td class="id-cell">' + esc(b.reqId) + '</td><td><bdi>' + esc(b.name) + '</bdi><span class="sub-line" dir="ltr">' + esc(b.email) + '</span>' + (b.behalf ? '<span class="sub-line"><bdi>' + esc(b.behalf) + '</bdi></span>' : '') + '</td>' +
        '<td><bdi>' + esc(b.title) + '</bdi>' + (b.seriesCount > 1 ? '<span class="sub-line"><i class="fas fa-repeat"></i> ' + L('سلسلة ' + b.seriesNo + ' من ' + b.seriesCount, 'Series ' + b.seriesNo + ' of ' + b.seriesCount) + '</span>' : '') + '</td><td data-value="' + esc(hallLabel(b.hall)) + '"><bdi>' + esc(hallLabel(b.hall)) + '</bdi></td>' +
        '<td data-value="' + esc(b.date) + '" style="white-space:nowrap" dir="ltr">' + esc(dateText(b)) + '</td><td data-value="' + esc(timeText(b)) + '" style="white-space:nowrap"><span dir="ltr">' + esc(timeText(b)) + '</span></td>' +
        '<td data-value="' + esc((b.attendees || '') + ' ' + (b.extras || []).join(' ')) + '">' + (b.attendees ? '<span dir="ltr">' + esc(b.attendees) + '</span> ' + L('حضور', 'attendees') : '') + (b.extras && b.extras.length ? '<span class="sub-line"><bdi>' + esc(b.extras.join('، ')) + '</bdi></span>' : '') + '</td>' +
        '<td data-value="' + esc(STATUS[b.status] ? STATUS[b.status][0] : b.status) + '">' + badge(b.status) + (b.rejectReason ? '<div class="reasons"><bdi>' + esc(b.rejectReason) + '</bdi></div>' : '') + '</td><td class="act"><div class="action-btns">' + act + '</div></td></tr>';
    }).join('');
    box.innerHTML = tableHtml('bk', cols, rows);
    mount(box, 'bk', manage ? [{ id: 'approve', label: L('موافقة', 'Approve') }, { id: 'reject', label: L('رفض', 'Reject') }, { id: 'cancel', label: L('إلغاء الحجز', 'Cancel booking'), danger: true },
      { id: 'pending', label: L('إرجاع إلى قيد المراجعة', 'Back to pending') }, { id: 'delete', label: L('حذف', 'Delete'), danger: true }] : [], function (action, ids) {
      var run = function (reason) { post('/api/admin/bookings/bulk', { action: action, reqIds: ids, reason: reason || '' }).then(function (r) { bulkDone(r); loadBookings(); loadHome(); }).catch(fail); };
      if (action === 'reject') askText(L('رفض الطلبات المحدّدة', 'Reject the selected requests'), L('سبب الرفض', 'Rejection reason'), false, run); else run();
    });
  }
  // نافذة نص واحد: سبب الرفض أو بريد إبلاغ إضافي
  var actCb = null;
  function askText(title, label, ltr, cb, okText) {
    $('actTitle').textContent = title; $('actExtraLbl').textContent = label; $('actExtra').value = ''; $('actExtra').dir = ltr ? 'ltr' : 'auto';
    $('actOk').textContent = okText || L('تأكيد', 'Confirm'); actCb = cb; open('mdAction'); setTimeout(function () { $('actExtra').focus(); }, 50);
  }
  $('actOk').addEventListener('click', function () { var v = $('actExtra').value.trim(); var cb = actCb; if (cb && cb.length && cb.needValue && !v) return; $('mdAction').classList.remove('open'); if (cb) cb(v); });
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-do]');
    if (b) {
      var id = b.dataset.id, what = b.dataset.do;
      var bk0 = bookings.filter(function (x) { return x.reqId === id; })[0], sc = '';
      if (bk0 && bk0.seriesCount > 1 && what !== 'pending' && confirm(L('هذا الحجز ضمن سلسلة من ' + bk0.seriesCount + ' حجزاً. هل تريد تطبيق الإجراء على السلسلة كلها؟ (إلغاء = هذا الحجز فقط)', 'This booking is part of a series of ' + bk0.seriesCount + '. Apply the action to the whole series? (Cancel = this booking only)'))) sc = 'series';
      if (what === 'approve') return askText(L('الموافقة على الحجز ', 'Approve booking ') + id, L('بريد إبلاغ إضافي (اختياري، افصل بفاصلة)', 'Extra BCC emails (optional, comma-separated)'), true, function (v) { post('/api/admin/approve/' + encodeURIComponent(id), { extraBcc: v, scope: sc }).then(function () { toast(L('تمت الموافقة', 'Approved')); loadBookings(); loadHome(); }).catch(fail); }, L('موافقة', 'Approve'));
      if (what === 'reject') { var rj = function (v) { if (!v) { toast(L('اكتب سبب الرفض', 'Write the rejection reason'), true); return; } post('/api/admin/reject/' + encodeURIComponent(id), { reason: v, scope: sc }).then(function () { toast(L('تم الرفض', 'Rejected')); loadBookings(); loadHome(); }).catch(fail); }; return askText(L('رفض الحجز ', 'Reject booking ') + id, L('سبب الرفض', 'Rejection reason'), false, rj, L('رفض', 'Reject')); }
      if (!confirm((what === 'cancel' ? L('إلغاء الحجز ', 'Cancel booking ') : L('إرجاع إلى قيد المراجعة: ', 'Back to pending: ')) + id + '؟')) return;
      post('/api/admin/' + what + '/' + encodeURIComponent(id), { scope: sc }).then(function () { toast(L('تم', 'Done')); loadBookings(); loadHome(); }).catch(fail);
      return;
    }
    var ed = e.target.closest('[data-edit]'); if (ed) return openEditBooking(ed.dataset.edit);
    var cm = e.target.closest('[data-cm]'); if (cm) return openComments(cm.dataset.cm);
  });
  function openEditBooking(id) {
    var b = bookings.filter(function (x) { return x.reqId === id; })[0]; if (!b) return;
    $('bkReq').textContent = id; $('bkName').value = b.name; $('bkEmail').value = b.email; $('bkPhone').value = b.phone || ''; $('bkBehalf').value = b.behalf || '';
    $('bkTitle').value = b.title; $('bkHall').value = b.hall; $('bkDate').value = b.date; $('bkEndDate').value = b.endDate; $('bkStart').value = b.startTime; $('bkEnd').value = b.endTime;
    $('bkFull').checked = !!b.fullDay; $('bkNotes').value = b.notes || ''; open('mdBooking');
  }
  $('bkSave').addEventListener('click', function () {
    post('/api/admin/update/' + encodeURIComponent($('bkReq').textContent), { name: $('bkName').value.trim(), email: $('bkEmail').value.trim(), phone: $('bkPhone').value.trim(), behalf: $('bkBehalf').value.trim(),
      title: $('bkTitle').value.trim(), hall: $('bkHall').value, date: $('bkDate').value, endDate: $('bkEndDate').value || $('bkDate').value, startTime: $('bkStart').value, endTime: $('bkEnd').value,
      fullDay: $('bkFull').checked, notes: $('bkNotes').value.trim() }).then(function () { toast(L('تم الحفظ', 'Saved')); $('mdBooking').classList.remove('open'); loadBookings(); }).catch(fail);
  });
  var cmReq = '';
  function openComments(id) {
    cmReq = id; $('cmReq').textContent = id; $('cmBody').value = ''; $('cmForm').style.display = can('bookings.manage') ? '' : 'none'; $('cmSend').style.display = can('bookings.manage') ? '' : 'none';
    api('/api/admin/comments/' + encodeURIComponent(id)).then(function (rows) {
      $('cmList').innerHTML = rows.length ? rows.map(function (c) { return '<div class="comment"><small><bdi>' + esc(c.author) + '</bdi> · <span dir="ltr">' + esc(c.at) + '</span></small><bdi>' + esc(c.body).replace(/\n/g, '<br>') + '</bdi></div>'; }).join('') : '<p class="muted">' + L('لا تعليقات بعد.', 'No comments yet.') + '</p>';
      open('mdComments');
    }).catch(fail);
  }
  $('cmSend').addEventListener('click', function () {
    var body = $('cmBody').value.trim(); if (!body) return;
    post('/api/admin/comments/' + encodeURIComponent(cmReq), { body: body }).then(function () { openComments(cmReq); loadBookings(); }).catch(fail);
  });

  // ───── التقويم ─────
  var aCur = { y: +today().slice(0, 4), m: +today().slice(5, 7) }, aData = [];
  var MONTHS = AR ? ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'] : ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  var DAYS = AR ? ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'] : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  function loadCal() { api('/api/admin/calendar?year=' + aCur.y + '&month=' + aCur.m).then(function (d) { aData = d; renderCal(); }).catch(fail); }
  function calOn(ds) { var h = $('aHall').value; return aData.filter(function (b) { return b.date <= ds && b.endDate >= ds && (!h || b.hall === h); }); }
  function renderCal() {
    $('aTitle').textContent = MONTHS[aCur.m - 1] + ' ' + aCur.y;
    var first = new Date(aCur.y, aCur.m - 1, 1).getDay(), days = new Date(aCur.y, aCur.m, 0).getDate(), t = today(), html = '';
    DAYS.forEach(function (d) { html += '<div class="cal-hdr">' + d + '</div>'; });
    for (var i = 0; i < first; i++) html += '<div class="cal-day other"></div>';
    for (var d = 1; d <= days; d++) {
      var ds = aCur.y + '-' + pad(aCur.m) + '-' + pad(d), bk = calOn(ds);
      html += '<div class="cal-day' + (ds === t ? ' today' : '') + '" role="button" tabindex="0" data-date="' + ds + '"><span class="dn">' + d + '</span>';
      bk.slice(0, 3).forEach(function (b) { html += '<span class="ev ' + (b.status === 'pending' ? 'pending' : '') + '"><span class="t">' + esc(hallLabel(b.hall)) + '</span></span>'; });
      if (bk.length > 3) html += '<span class="more">+' + (bk.length - 3) + '</span>';
      html += '</div>';
    }
    var tail = (7 - (first + days) % 7) % 7; for (var k = 0; k < tail; k++) html += '<div class="cal-day other"></div>';
    $('aGrid').innerHTML = html;
  }
  $('aGrid').addEventListener('click', function (e) {
    var c = e.target.closest('.cal-day[data-date]'); if (!c) return;
    $('dayTitle').textContent = c.dataset.date;
    $('dayList').innerHTML = calOn(c.dataset.date).map(function (b) { return '<div class="item ' + (b.status === 'pending' ? 'pending' : '') + '"><b><bdi>' + esc(b.title) + '</bdi></b> ' + badge(b.status) + '<div class="meta"><span><bdi>' + esc(hallLabel(b.hall)) + '</bdi></span><span dir="ltr">' + esc(timeText(b)) + '</span><span><bdi>' + esc(b.name) + '</bdi></span></div></div>'; }).join('') || '<p class="muted" style="text-align:center">' + L('لا حجوزات.', 'No bookings.') + '</p>';
    open('mdDay');
  });
  function aGo(dm) { aCur.m += dm; if (aCur.m < 1) { aCur.m = 12; aCur.y--; } if (aCur.m > 12) { aCur.m = 1; aCur.y++; } loadCal(); }
  $('aPrev').addEventListener('click', function () { aGo(-1); }); $('aNext').addEventListener('click', function () { aGo(1); });
  $('aToday').addEventListener('click', function () { aCur = { y: +today().slice(0, 4), m: +today().slice(5, 7) }; loadCal(); });
  $('aHall').addEventListener('change', renderCal);

  // ───── الفترات غير المتاحة ─────
  function loadBlocked() {
    api('/api/admin/blocked').then(function (d) {
      var box = $('blockedBox'); if (!d.length) { box.innerHTML = empty('check-circle', L('لا توجد فترات غير متاحة.', 'No unavailable periods.')); return; }
      var cols = [{ h: L('من', 'From'), filter: 'text' }, { h: L('إلى', 'To'), filter: 'text' }, { h: L('المبنى أو المرفق', 'Building or facility'), filter: 'select' }, { h: L('الوقت', 'Time'), filter: 'text' }, { h: L('السبب', 'Reason'), filter: 'text' }, { h: L('إجراءات', 'Actions'), act: true }];
      var rows = d.map(function (it) { var h = it.hall ? hallLabel(it.hall) : L('كل المباني والمرافق', 'All buildings and facilities');
        return '<tr>' + chk(it.id) + '<td dir="ltr" data-value="' + esc(it.start) + '">' + esc(it.start) + '</td><td dir="ltr" data-value="' + esc(it.end) + '">' + esc(it.end) + '</td><td data-value="' + esc(h) + '"><bdi>' + esc(h) + '</bdi></td>' +
          '<td>' + (it.fromT ? '<span dir="ltr">' + esc(it.fromT) + ' - ' + esc(it.toT) + '</span>' : L('يوم كامل', 'Full day')) + '</td><td><bdi>' + esc(it.reason) + '</bdi></td>' +
          '<td class="act"><button class="btn btn-sm btn-red" data-delblk="' + it.id + '" title="' + L('حذف', 'Delete') + '" aria-label="' + L('حذف', 'Delete') + '"><i class="fas fa-trash"></i></button></td></tr>'; }).join('');
      box.innerHTML = tableHtml('blk', cols, rows);
      mount(box, 'blk', [{ id: 'delete', label: L('حذف', 'Delete'), danger: true }], function (a, ids) { post('/api/admin/blocked/bulk', { ids: ids }).then(function (r) { bulkDone(r); loadBlocked(); }).catch(fail); });
    }).catch(fail);
  }
  $('blkAdd').addEventListener('click', function () {
    var s = $('blkStart').value, e = $('blkEnd').value; if (!s || !e) return toast(L('حدّد التاريخين', 'Set both dates'), true);
    post('/api/admin/blocked/add', { start: s, end: e, hall: $('blkHall').value, fromT: $('blkFromT').value, toT: $('blkToT').value, reason: $('blkReason').value.trim() })
      .then(function () { toast(L('تمت الإضافة', 'Added')); ['blkStart', 'blkEnd', 'blkFromT', 'blkToT', 'blkReason'].forEach(function (i) { $(i).value = ''; }); loadBlocked(); }).catch(fail);
  });
  document.addEventListener('click', function (e) {
    var d = e.target.closest('[data-delblk]'); if (!d || !confirm(L('حذف هذه الفترة؟', 'Delete this period?'))) return;
    post('/api/admin/blocked/delete/' + d.dataset.delblk).then(loadBlocked).catch(fail);
  });

  // ───── التقارير ─────
  function loadReports() {
    api('/api/admin/stats').then(function (s) {
      var max = Math.max.apply(null, s.byHall.map(function (x) { return x.count; }).concat([1]));
      $('chartTop').innerHTML = s.byHall.length ? s.byHall.slice(0, 10).map(function (x) { return '<div class="bar-item"><div class="bar-label"><bdi>' + esc(hallLabel(x.hall)) + '</bdi></div><div class="bar-track"><div class="bar-fill" style="width:' + Math.max(6, x.count / max * 100) + '%"><span>' + x.count + '</span></div></div></div>'; }).join('') : '<p class="muted">' + L('لا بيانات.', 'No data.') + '</p>';
      var cmax = Math.max.apply(null, s.byCategory.map(function (x) { return x.count; }).concat([1]));
      $('chartCat').innerHTML = s.byCategory.length ? s.byCategory.map(function (x) { return '<div class="bar-item"><div class="bar-label">' + esc(catLabel(x.category)) + '</div><div class="bar-track"><div class="bar-fill" style="width:' + Math.max(6, x.count / cmax * 100) + '%"><span>' + x.count + '</span></div></div></div>'; }).join('') : '<p class="muted">' + L('لا بيانات.', 'No data.') + '</p>';
      var months = Object.keys(s.byMonth).sort().reverse(), names = s.byHall.map(function (x) { return x.hall; });
      $('monthTable').innerHTML = months.length ? '<div class="table-wrap"><table><thead><tr><th>' + L('الشهر', 'Month') + '</th>' + names.map(function (n) { return '<th><bdi>' + esc(hallLabel(n)) + '</bdi></th>'; }).join('') + '<th>' + L('المجموع', 'Total') + '</th></tr></thead><tbody>' +
        months.map(function (m) { var tot = 0; return '<tr><td dir="ltr">' + m + '</td>' + names.map(function (n) { var v = s.byMonth[m][n] || 0; tot += v; return '<td>' + (v || '') + '</td>'; }).join('') + '<td><b>' + tot + '</b></td></tr>'; }).join('') + '</tbody></table></div>' : '<p class="muted">' + L('لا بيانات.', 'No data.') + '</p>';
    }).catch(fail);
  }

  // ───── المباني والمرافق ─────
  function loadHalls() {
    loadHallsList().then(function () {
      var box = $('hallsBox'); if (!halls.length) { box.innerHTML = empty('building', L('لا توجد مبانٍ أو مرافق.', 'None yet.')); return; }
      var cols = [{ h: L('الاسم', 'Name'), filter: 'text' }, { h: L('النوع', 'Type'), filter: 'select' }, { h: L('الرمز', 'Code'), filter: 'text' }, { h: L('السعة', 'Capacity'), sort: 'num' }, { h: L('الموقع', 'Location'), filter: 'text' },
        { h: L('الحالة', 'Status'), filter: 'select' }, { h: L('الحجوزات', 'Bookings'), sort: 'num' }, { h: L('إجراءات', 'Actions'), act: true }];
      var rows = halls.map(function (h) { var st = h.active ? L('فعّال', 'Active') : L('موقوف', 'Inactive');
        return '<tr>' + chk(h.id) + '<td><b><bdi>' + esc(h.nameAr) + '</bdi></b>' + (h.nameEn ? '<span class="sub-line" dir="ltr">' + esc(h.nameEn) + '</span>' : '') + (h.requiresApproval ? '<span class="badge badge-pending">' + L('يتطلب موافقة', 'Needs approval') + '</span>' : '') + '</td>' +
          '<td data-value="' + esc(catLabel(h.category)) + '">' + esc(catLabel(h.category)) + '</td><td dir="ltr">' + esc(h.code || '') + '</td><td data-value="' + esc(h.capacity || 0) + '">' + esc(h.capacity || '') + '</td><td><bdi>' + esc(h.location || '') + '</bdi></td>' +
          '<td data-value="' + esc(st) + '"><span class="badge ' + (h.active ? 'badge-approved' : 'badge-cancelled') + '">' + st + '</span></td><td data-value="' + h.bookings + '">' + h.bookings + '</td>' +
          '<td class="act"><div class="action-btns"><button class="btn btn-sm btn-outline" data-hedit="' + h.id + '" title="' + L('تعديل', 'Edit') + '" aria-label="' + L('تعديل', 'Edit') + '"><i class="fas fa-pen"></i></button><button class="btn btn-sm btn-red" data-hdel="' + h.id + '" title="' + L('حذف', 'Delete') + '" aria-label="' + L('حذف', 'Delete') + '"><i class="fas fa-trash"></i></button></div></td></tr>'; }).join('');
      box.innerHTML = tableHtml('halls', cols, rows);
      mount(box, 'halls', [{ id: 'activate', label: L('تفعيل', 'Activate') }, { id: 'deactivate', label: L('إيقاف', 'Deactivate') }, { id: 'delete', label: L('حذف', 'Delete'), danger: true }], function (a, ids) {
        post('/api/admin/halls/bulk', { action: a, ids: ids }).then(function (r) { bulkDone(r); loadHalls(); }).catch(fail); });
    });
  }
  function openHall(h) {
    h = h || {}; $('mdHallTitle').textContent = h.id ? L('تعديل مبنى أو مرفق', 'Edit a building or facility') : L('إضافة مبنى أو مرفق', 'Add a building or facility');
    $('hId').value = h.id || ''; $('hNameAr').value = h.nameAr || ''; $('hNameEn').value = h.nameEn || ''; $('hCat').value = h.category || 'hall'; $('hCode').value = h.code || ''; $('hLocation').value = h.location || '';
    $('hCapacity').value = h.capacity || ''; $('hEquip').value = h.equipment || ''; $('hExtras').value = h.extras || ''; $('hDesc').value = h.description || ''; $('hNotes').value = h.notes || ''; $('hApproval').checked = !!h.requiresApproval; $('hActive').checked = h.id ? !!h.active : true; open('mdHall');
  }
  $('hallAdd').addEventListener('click', function () { openHall(); });
  $('hSave').addEventListener('click', function () {
    var id = $('hId').value, body = { id: id ? +id : undefined, nameAr: $('hNameAr').value.trim(), nameEn: $('hNameEn').value.trim(), category: $('hCat').value, code: $('hCode').value.trim(), location: $('hLocation').value.trim(),
      capacity: $('hCapacity').value.trim(), equipment: $('hEquip').value.trim(), extras: $('hExtras').value, description: $('hDesc').value.trim(), notes: $('hNotes').value.trim(), requiresApproval: $('hApproval').checked, active: $('hActive').checked };
    if (!body.nameAr) return toast(L('الاسم بالعربية مطلوب', 'The Arabic name is required'), true);
    post(id ? '/api/admin/halls/update' : '/api/admin/halls/add', body).then(function () { toast(L('تم الحفظ', 'Saved')); $('mdHall').classList.remove('open'); loadHalls(); }).catch(fail);
  });
  document.addEventListener('click', function (e) {
    var ed = e.target.closest('[data-hedit]'); if (ed) return openHall(halls.filter(function (h) { return h.id === +ed.dataset.hedit; })[0]);
    var dl = e.target.closest('[data-hdel]'); if (dl && confirm(L('حذف هذا المبنى أو المرفق؟', 'Delete this building or facility?'))) post('/api/admin/halls/delete/' + dl.dataset.hdel).then(function () { toast(L('تم الحذف', 'Deleted')); loadHalls(); }).catch(fail);
  });

  // ───── جهات الاتصال ─────
  var contacts = [];
  function loadContacts() {
    loadHallsList().then(function () { return api('/api/admin/contacts'); }).then(function (d) {
      contacts = d; var box = $('contactsBox'); if (!d.length) { box.innerHTML = empty('address-book', L('لا جهات اتصال بعد.', 'No contacts yet.')); return; }
      var yes = function (v) { return v ? '<i class="fas fa-check" style="color:var(--ok)" aria-label="' + L('نعم', 'Yes') + '"></i>' : '<span class="muted">—</span>'; };
      var cols = [{ h: L('البريد الإلكتروني', 'Email'), filter: 'text' }, { h: L('الاسم', 'Name'), filter: 'text' }, { h: L('يخص', 'Concerns'), filter: 'select' }, { h: L('حجز جديد', 'New') }, { h: L('اطّلاع فقط', 'Read-only') },
        { h: L('اعتماد', 'Approved') }, { h: L('تعليقات', 'Comments') }, { h: L('ملخص وتذكير', 'Summary') }, { h: L('إجراءات', 'Actions'), act: true }];
      var rows = d.map(function (c) { var h = c.hall ? hallLabel(c.hall) : L('الكل', 'All');
        return '<tr>' + chk(c.id) + '<td dir="ltr">' + esc(c.email) + '</td><td><bdi>' + esc(c.name) + '</bdi></td><td data-value="' + esc(h) + '"><bdi>' + esc(h) + '</bdi></td><td>' + yes(c.notify_new) + '</td><td>' + yes(c.new_readonly) + '</td><td>' + yes(c.notify_approved) + '</td><td>' + yes(c.notify_comment) + '</td><td>' + yes(c.notify_staff_reminder) + '</td>' +
          '<td class="act"><div class="action-btns"><button class="btn btn-sm btn-outline" data-cedit="' + c.id + '" title="' + L('تعديل', 'Edit') + '" aria-label="' + L('تعديل', 'Edit') + '"><i class="fas fa-pen"></i></button><button class="btn btn-sm btn-red" data-cdel="' + c.id + '" title="' + L('حذف', 'Delete') + '" aria-label="' + L('حذف', 'Delete') + '"><i class="fas fa-trash"></i></button></div></td></tr>'; }).join('');
      box.innerHTML = tableHtml('ct', cols, rows);
      mount(box, 'ct', [{ id: 'notify_staff_reminder', label: L('تفعيل الملخص والتذكير', 'Turn on summary and reminder') }, { id: 'off_notify_staff_reminder', label: L('إيقاف الملخص والتذكير', 'Turn off summary and reminder') }, { id: 'delete', label: L('حذف', 'Delete'), danger: true }], function (a, ids) {
        post('/api/admin/contacts/bulk', { action: a, ids: ids }).then(function (r) { bulkDone(r); loadContacts(); }).catch(fail); });
    }).catch(fail);
  }
  function openContact(c) {
    c = c || { notify_new: true, notify_approved: true };
    $('ctTitle').textContent = c.id ? L('تعديل جهة اتصال', 'Edit a contact') : L('إضافة جهة اتصال', 'Add a contact');
    $('ctId').value = c.id || ''; $('ctEmail').value = c.email || ''; $('ctName').value = c.name || ''; $('ctHall').value = c.hall || '';
    $('fNew').checked = !!c.notify_new; $('fRead').checked = !!c.new_readonly; $('fApp').checked = !!c.notify_approved; $('fCom').checked = !!c.notify_comment; $('fRem').checked = !!c.notify_staff_reminder; open('mdContact');
  }
  $('ctAdd').addEventListener('click', function () { openContact(); });
  $('ctSave').addEventListener('click', function () {
    var id = $('ctId').value, body = { id: id ? +id : undefined, email: $('ctEmail').value.trim(), name: $('ctName').value.trim(), hall: $('ctHall').value,
      notify_new: $('fNew').checked, new_readonly: $('fRead').checked, notify_approved: $('fApp').checked, notify_comment: $('fCom').checked, notify_staff_reminder: $('fRem').checked };
    post(id ? '/api/admin/contacts/update' : '/api/admin/contacts/add', body).then(function (r) { toast(id ? L('تم الحفظ', 'Saved') : (r.count ? L('تمت الإضافة', 'Added') : L('البريد غير صالح أو مسجّل مسبقاً', 'The email is invalid or already listed')), !id && !r.count); $('mdContact').classList.remove('open'); loadContacts(); }).catch(fail);
  });
  document.addEventListener('click', function (e) {
    var ed = e.target.closest('[data-cedit]'); if (ed) return openContact(contacts.filter(function (c) { return c.id === +ed.dataset.cedit; })[0]);
    var dl = e.target.closest('[data-cdel]'); if (dl && confirm(L('حذف جهة الاتصال؟', 'Delete the contact?'))) post('/api/admin/contacts/delete/' + dl.dataset.cdel).then(loadContacts).catch(fail);
  });
  $('ctFile').addEventListener('change', function () {
    var f = this.files[0]; this.value = ''; if (!f) return;
    var rd = new FileReader(); rd.onload = function (ev) {
      var list = (String(ev.target.result).match(/[^\s,;"']+@[^\s,;"']+\.[^\s,;"']+/g) || []).map(function (m) { return { email: m }; });
      if (!list.length) return toast(L('لم تُوجد عناوين بريد صالحة', 'No valid emails found'), true);
      post('/api/admin/contacts/add', { list: list }).then(function (r) { toast(L('أُضيفت ', 'Added ') + r.count + L(' جهة', ' contact(s)')); loadContacts(); }).catch(fail);
    }; rd.readAsText(f);
  });

  // ───── الإعدادات ─────
  function loadSettings() {
    api('/api/admin/settings').then(function (s) {
      var set = function (id, v) { var el = $(id); if (el) el.value = v; };
      set('sOrgAr', s.orgAr); set('sOrgEn', s.orgEn); set('sAccent', s.accent); set('sSummaryTime', s.staffDailySummaryTime || '07:00'); set('sLead', s.staffReminderLeadMinutes || '');
      $('sAutoApprove').checked = !!s.autoApproveBookings; $('sPublicDetails').checked = !!s.publicShowDetails; $('sVerifyEmail').checked = s.verifyBookingEmail !== false; $('sRemindersOn').checked = !!s.remindersEnabled; $('sRemindScheduled').checked = !!s.reminderScheduledEnabled; $('sSummaryOn').checked = !!s.staffDailySummaryEnabled;
      $('sTermsAr').value = s.termsAr || ''; $('sTermsEn').value = s.termsEn || ''; $('sTermsAr').placeholder = s.termsDefaultAr; $('sTermsEn').placeholder = s.termsDefaultEn;
      var img = $('sLogoImg'); if (s.logo) { img.src = s.logo; img.style.display = ''; } else img.style.display = 'none';
      $('sMail').textContent = s.mail ? L('البريد الإلكتروني مُفعَّل (المرسل: ', 'Email is on (sender: ') + s.sender + ')' : L('البريد الإلكتروني غير مُعدّ: لا تُرسل رسائل الحجز ولا التذكيرات.', 'Email is not set up: booking messages and reminders are not sent.');
      $('sRemindNote').textContent = L('الإبلاغ بالحجز الجديد والاعتماد والتعليقات يتبع خيارات كل جهة في «جهات الاتصال».', 'New-booking, approval and comment notices follow each contact’s options in “Contacts”.');
    }).catch(fail);
    [].forEach.call(document.querySelectorAll('[data-perm]'), function (c) { c.style.display = can(c.dataset.perm) ? '' : 'none'; });
  }
  $('sTermsSave').addEventListener('click', function () { post('/api/admin/settings', { termsAr: $('sTermsAr').value, termsEn: $('sTermsEn').value }).then(function () { toast(L('تم الحفظ', 'Saved')); }).catch(fail); });
  $('sIdentitySave').addEventListener('click', function () {
    post('/api/admin/settings', { orgAr: $('sOrgAr').value, orgEn: $('sOrgEn').value, accent: $('sAccent').value }).then(function () { toast(L('تم الحفظ، حدّث الصفحة لرؤية الهوية الجديدة', 'Saved - refresh the page to see the new identity')); }).catch(fail);
  });
  $('sLogoFile').addEventListener('change', function () {
    var f = this.files[0]; this.value = ''; if (!f) return; var fd = new FormData(); fd.append('file', f);
    api('/api/admin/logo', { method: 'POST', body: fd }).then(function () { toast(L('تم رفع الشعار', 'Logo uploaded')); loadSettings(); }).catch(fail);
  });
  $('sLogoDel').addEventListener('click', function () { if (confirm(L('إزالة الشعار؟ تظهر أيقونة النظام بدلاً منه.', 'Remove the logo? The system icon is shown instead.'))) post('/api/admin/logo/delete').then(function () { toast(L('تمت الإزالة', 'Removed')); loadSettings(); }).catch(fail); });
  $('sVerifyEmail').addEventListener('change', function () { post('/api/admin/settings', { verifyBookingEmail: this.checked }).then(function () { toast(L('تم الحفظ', 'Saved')); }).catch(fail); });
  $('sPublicDetails').addEventListener('change', function () { post('/api/admin/settings', { publicShowDetails: this.checked }).then(function () { toast(L('تم الحفظ', 'Saved')); }).catch(fail); });
  $('sAutoApprove').addEventListener('change', function () { post('/api/admin/settings', { autoApproveBookings: this.checked }).then(function () { toast(L('تم الحفظ', 'Saved')); }).catch(fail); });
  $('sRemindSave').addEventListener('click', function () {
    post('/api/admin/settings', { remindersEnabled: $('sRemindersOn').checked, reminderScheduledEnabled: $('sRemindScheduled').checked, staffDailySummaryEnabled: $('sSummaryOn').checked,
      staffDailySummaryTime: $('sSummaryTime').value, staffReminderLeadMinutes: $('sLead').value }).then(function () { toast(L('تم الحفظ', 'Saved')); }).catch(fail);
  });
  $('pwSave').addEventListener('click', function () {
    if ($('pwNew').value !== $('pwRep').value) return toast(L('كلمتا المرور الجديدتان غير متطابقتين', 'The new passwords do not match'), true);
    post('/api/admin/password', { current: $('pwCur').value, new: $('pwNew').value }).then(function (r) { window.CSRF = r.csrf || window.CSRF; toast(L('تم تغيير كلمة المرور', 'Password changed')); ['pwCur', 'pwNew', 'pwRep'].forEach(function (i) { $(i).value = ''; }); }).catch(fail);
  });

  // ───── المستخدمون ─────
  var users = [];
  function loadUsers() {
    api('/api/admin/users').then(function (d) {
      users = d; var box = $('usersBox');
      var cols = [{ h: L('اسم المستخدم', 'Username'), filter: 'text' }, { h: L('الاسم', 'Name'), filter: 'text' }, { h: L('البريد', 'Email'), filter: 'text' }, { h: L('الدور', 'Role'), filter: 'select' }, { h: L('الحالة', 'Status'), filter: 'select' }, { h: L('آخر دخول', 'Last sign-in'), filter: 'text' }, { h: L('إجراءات', 'Actions'), act: true }];
      var rows = d.map(function (u) { var st = u.active ? L('فعّال', 'Active') : L('موقوف', 'Disabled'), role = u.sysadmin ? L('مدير النظام', 'System administrator') : L('مستخدم', 'User');
        return '<tr>' + chk(u.id) + '<td dir="ltr">' + esc(u.username) + (u.me ? ' <span class="badge">' + L('حسابك', 'You') + '</span>' : '') + '</td><td><bdi>' + esc(u.name) + '</bdi></td><td dir="ltr">' + esc(u.email) + '</td><td data-value="' + esc(role) + '">' + role + '</td>' +
          '<td data-value="' + esc(st) + '"><span class="badge ' + (u.active ? 'badge-approved' : 'badge-cancelled') + '">' + st + '</span></td><td dir="ltr" data-value="' + esc(u.lastLogin) + '">' + esc(u.lastLogin) + '</td>' +
          '<td class="act"><div class="action-btns"><button class="btn btn-sm btn-outline" data-uedit="' + u.id + '" title="' + L('تعديل', 'Edit') + '" aria-label="' + L('تعديل', 'Edit') + '"><i class="fas fa-pen"></i></button><button class="btn btn-sm btn-red" data-udel="' + u.id + '" title="' + L('حذف', 'Delete') + '" aria-label="' + L('حذف', 'Delete') + '"><i class="fas fa-trash"></i></button></div></td></tr>'; }).join('');
      box.innerHTML = tableHtml('users', cols, rows);
      mount(box, 'users', [{ id: 'activate', label: L('تفعيل', 'Activate') }, { id: 'deactivate', label: L('إيقاف', 'Deactivate') }, { id: 'delete', label: L('حذف', 'Delete'), danger: true }], function (a, ids) {
        post('/api/admin/users/bulk', { action: a, ids: ids }).then(function (r) { bulkDone(r); loadUsers(); }).catch(fail); });
    }).catch(fail);
  }
  function setPerms(list) { [].forEach.call(document.querySelectorAll('#mdUser .perm'), function (c) { c.checked = list.indexOf(c.value) >= 0; }); }
  function openUser(u) {
    u = u || {}; $('uTitle').textContent = u.id ? L('تعديل مستخدم', 'Edit a user') : L('إضافة مستخدم', 'Add a user');
    $('uId').value = u.id || ''; $('uName').value = u.username || ''; $('uFull').value = u.name || ''; $('uEmail').value = u.email || ''; $('uPass').value = ''; $('uActive').checked = u.id ? !!u.active : true; $('uSys').checked = !!u.sysadmin;
    setPerms(u.perms || []); $('uPermBox').style.display = $('uSys').checked ? 'none' : ''; open('mdUser');
  }
  $('userAdd').addEventListener('click', function () { openUser(); });
  $('uSys').addEventListener('change', function () { $('uPermBox').style.display = this.checked ? 'none' : ''; });
  $('uPermBox').addEventListener('click', function (e) { var p = e.target.closest('[data-preset]'); if (p) setPerms(p.dataset.preset === 'none' ? [] : (window.PRESETS[p.dataset.preset] || [])); });
  $('uSave').addEventListener('click', function () {
    var id = $('uId').value, perms = [].filter.call(document.querySelectorAll('#mdUser .perm'), function (c) { return c.checked; }).map(function (c) { return c.value; });
    var body = { id: id ? +id : undefined, username: $('uName').value.trim(), name: $('uFull').value.trim(), email: $('uEmail').value.trim(), password: $('uPass').value, active: $('uActive').checked, sysadmin: $('uSys').checked, perms: perms };
    post(id ? '/api/admin/users/update' : '/api/admin/users/add', body).then(function () { toast(L('تم الحفظ', 'Saved')); $('mdUser').classList.remove('open'); loadUsers(); }).catch(fail);
  });
  document.addEventListener('click', function (e) {
    var ed = e.target.closest('[data-uedit]'); if (ed) return openUser(users.filter(function (u) { return u.id === +ed.dataset.uedit; })[0]);
    var dl = e.target.closest('[data-udel]'); if (dl && confirm(L('حذف هذا المستخدم؟', 'Delete this user?'))) post('/api/admin/users/delete/' + dl.dataset.udel).then(function () { toast(L('تم الحذف', 'Deleted')); loadUsers(); }).catch(fail);
  });

  // ───── الشريط الإخباري (محرر Quill) ─────
  var qAr = null, qEn = null;
  function makeQuill(sel) {
    var Size = Quill.import('attributors/style/size'); Size.whitelist = ['14px', '16px', '22px', '32px']; Quill.register(Size, true);
    return new Quill(sel, { theme: 'snow', modules: { toolbar: [['bold', 'italic', 'underline'], [{ color: [] }, { background: [] }], [{ size: ['14px', '16px', '22px', '32px'] }], ['link'], ['clean']] } });
  }
  function loadTicker() {
    if (typeof Quill === 'undefined') return toast(L('تعذّر تحميل محرر النص: تحقّق من الاتصال بالإنترنت', 'The text editor could not be loaded: check the connection'), true);
    api('/api/admin/ticker').then(function (c) {
      if (!qAr) { qAr = makeQuill('#tickerQuill'); qAr.root.setAttribute('dir', 'rtl'); }
      if (!qEn) qEn = makeQuill('#tickerQuillEn');
      qAr.root.innerHTML = c.html || ''; qEn.root.innerHTML = c.htmlEn || '';
      $('tickerEnabled').checked = !!c.enabled; $('tickerSpeed').value = c.speedSeconds || 25; $('tickerRssUrl').value = c.rssUrl || ''; $('tickerRssColor').value = c.rssColor || '#ffffff';
      $('tickerRssFontSize').value = Math.max(13, c.rssFontSize || 16); $('tickerRssBold').checked = c.rssBold !== false; $('tickerLogoBetween').checked = !!c.logoBetween; $('tickerPulse').checked = !!c.pulse;
      $('tickerPulseSpeed').value = c.pulseSeconds || 1.6; $('tickerPulseRow').style.display = c.pulse ? '' : 'none'; $('tickerShadow').value = c.textShadow || 'light';
      $('tickerBgColor').value = c.bgColor || '#075E66'; $('tickerBgOpacity').value = c.bgOpacity || 0; $('tickerBgOpacityVal').textContent = (c.bgOpacity || 0) + '%'; $('tickerTextColor').value = c.textColor || '#ffffff';
    }).catch(fail);
  }
  function previewTicker() {
    var op = parseInt($('tickerBgOpacity').value, 10) || 0; $('tickerBgOpacityVal').textContent = op + '%';
    var bar = $('globalTicker'); if (!bar) return; var n = parseInt($('tickerBgColor').value.slice(1), 16);
    bar.style.background = op > 0 ? 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + op / 100 + ')' : ''; bar.style.setProperty('--ticker-text', $('tickerTextColor').value);
  }
  ['tickerBgColor', 'tickerBgOpacity', 'tickerTextColor'].forEach(function (i) { $(i).addEventListener('input', previewTicker); });
  $('tickerPulse').addEventListener('change', function () { $('tickerPulseRow').style.display = this.checked ? '' : 'none'; });
  $('tickerSave').addEventListener('click', function () {
    if (!qAr) return;
    post('/api/admin/ticker', { enabled: $('tickerEnabled').checked, html: qAr.root.innerHTML, htmlEn: qEn.root.innerHTML, speedSeconds: parseInt($('tickerSpeed').value, 10) || 25, rssUrl: $('tickerRssUrl').value.trim(),
      rssColor: $('tickerRssColor').value, rssFontSize: parseInt($('tickerRssFontSize').value, 10) || 16, rssBold: $('tickerRssBold').checked, logoBetween: $('tickerLogoBetween').checked, pulse: $('tickerPulse').checked,
      pulseSeconds: parseFloat($('tickerPulseSpeed').value) || 1.6, textShadow: $('tickerShadow').value, bgColor: $('tickerBgColor').value, bgOpacity: parseInt($('tickerBgOpacity').value, 10) || 0, textColor: $('tickerTextColor').value })
      .then(function () { toast(L('تم الحفظ', 'Saved')); if (window.reloadTicker) window.reloadTicker(); }).catch(fail);
  });

  // ───── الروابط المختصرة ─────
  var links = [];
  function loadLinks() {
    api('/api/admin/links').then(function (d) {
      links = d; var box = $('linksBox'); if (!d.length) { box.innerHTML = empty('link', L('لا روابط مختصرة بعد.', 'No short links yet.')); return; }
      var cols = [{ h: L('الرابط المختصر', 'Short link'), filter: 'text' }, { h: L('الرابط الأصلي', 'Original link'), filter: 'text' }, { h: L('ملاحظة', 'Note'), filter: 'text' }, { h: L('الحالة', 'Status'), filter: 'select' },
        { h: L('الضغطات', 'Clicks'), sort: 'num' }, { h: L('آخر ضغطة', 'Last click'), filter: 'text' }, { h: L('إجراءات', 'Actions'), act: true }];
      var rows = d.map(function (l) { var st = l.active ? L('فعّال', 'Active') : L('موقوف', 'Inactive');
        return '<tr>' + chk(l.id) + '<td dir="ltr"><a href="' + esc(l.shortUrl) + '" target="_blank" rel="noopener">' + esc(l.shortUrl) + '</a></td><td dir="ltr" style="max-width:320px;overflow-wrap:anywhere">' + esc(l.url) + '</td><td><bdi>' + esc(l.note) + '</bdi></td>' +
          '<td data-value="' + esc(st) + '"><span class="badge ' + (l.active ? 'badge-approved' : 'badge-cancelled') + '">' + st + '</span></td><td data-value="' + l.clicks + '">' + l.clicks + '</td><td dir="ltr" data-value="' + esc(l.lastClick) + '">' + esc(l.lastClick) + '</td>' +
          '<td class="act"><div class="action-btns"><button class="btn btn-sm btn-outline" data-lkedit="' + l.id + '" title="' + L('تعديل', 'Edit') + '" aria-label="' + L('تعديل', 'Edit') + '"><i class="fas fa-pen"></i></button></div></td></tr>'; }).join('');
      box.innerHTML = tableHtml('lk', cols, rows);
      mount(box, 'lk', [{ id: 'activate', label: L('تفعيل', 'Activate') }, { id: 'deactivate', label: L('إيقاف', 'Deactivate') }, { id: 'delete', label: L('حذف', 'Delete'), danger: true }], function (a, ids) {
        post('/api/admin/links/bulk', { action: a, ids: ids }).then(function (r) { bulkDone(r); loadLinks(); }).catch(fail); });
    }).catch(fail);
  }
  function openLink(l) {
    l = l || {}; $('lkTitle').textContent = l.id ? L('تعديل رابط', 'Edit a link') : L('إضافة رابط مختصر', 'Add a short link');
    $('lkId').value = l.id || ''; $('lkUrl').value = l.url || ''; $('lkSlug').value = l.slug || ''; $('lkNote').value = l.note || ''; $('lkActive').checked = l.id ? !!l.active : true; open('mdLink');
  }
  $('linkAdd').addEventListener('click', function () { openLink(); });
  $('lkSave').addEventListener('click', function () {
    post('/api/admin/links/save', { id: $('lkId').value ? +$('lkId').value : undefined, url: $('lkUrl').value.trim(), slug: $('lkSlug').value.trim(), note: $('lkNote').value.trim(), active: $('lkActive').checked })
      .then(function () { toast(L('تم الحفظ', 'Saved')); $('mdLink').classList.remove('open'); loadLinks(); }).catch(fail);
  });
  document.addEventListener('click', function (e) { var b = e.target.closest('[data-lkedit]'); if (b) openLink(links.filter(function (l) { return l.id === +b.dataset.lkedit; })[0]); });

  // ───── الأرشفة ─────
  $('arcPreview').addEventListener('click', function () {
    var d = $('arcDate').value; if (!d) return toast(L('اختر التاريخ', 'Choose the date'), true);
    api('/api/admin/archive-preview?before=' + encodeURIComponent(d)).then(function (r) {
      if (!r.count) { $('arcResult').innerHTML = '<div class="alert alert-info">' + L('لا حجوزات منتهية قبل هذا التاريخ.', 'No bookings ended before this date.') + '</div>'; return; }
      $('arcResult').innerHTML = '<div class="alert alert-warning"><b>' + r.count + '</b> ' + L('حجز منتهٍ قبل ', 'bookings ended before ') + '<span dir="ltr">' + esc(d) + '</span> (' + L('معتمد ', 'approved ') + r.byStatus.approved + ' · ' + L('مرفوض ', 'rejected ') + r.byStatus.rejected + ' · ' + L('ملغي ', 'cancelled ') + r.byStatus.cancelled + ')</div>' +
        '<div class="action-btns"><a class="btn btn-primary" href="/api/admin/archive-export?before=' + encodeURIComponent(d) + '"><i class="fas fa-download"></i> ' + L('1) حمِّل الملف', '1) Download the file') + '</a>' +
        '<input type="text" id="arcConfirm" dir="ltr" placeholder="DELETE" style="max-width:150px" aria-label="' + L('كلمة التأكيد', 'Confirmation word') + '">' +
        '<button class="btn btn-red" type="button" id="arcDelete"><i class="fas fa-trash"></i> ' + L('2) حذف من النظام', '2) Delete from the system') + '</button></div><p class="hint">' + L('اكتب DELETE (بالإنجليزية) ثم اضغط حذف.', 'Type DELETE and press delete.') + '</p>';
    }).catch(fail);
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('#arcDelete')) return;
    post('/api/admin/archive-delete', { before: $('arcDate').value, confirm: $('arcConfirm').value.trim() }).then(function (r) { toast(L('حُذف ', 'Deleted ') + r.deleted + L(' حجزاً', ' bookings')); $('arcResult').innerHTML = ''; }).catch(fail);
  });

  // ───── تحديث تلقائي: طلب جديد أو تغيير حالة يظهر دون تحديث الصفحة ─────
  var pulseSig = null, pulsePending = null;
  function userBusy() {
    var panel = document.querySelector('.tab-panel.active');
    return !!(document.querySelector('.modal-overlay.open') || (panel && (panel.querySelector('.bulk-item:checked') ||
      [].some.call(panel.querySelectorAll('.dt-filter input, .dt-filter select, input[type=search]'), function (el) { return el.value; }))));
  }
  function pulse() {
    if (document.hidden || !can(['bookings.view', 'reports', 'calendar'])) return;
    api('/api/admin/pulse').then(function (p) {
      if (pulseSig !== null && p.sig !== pulseSig) {
        if (pulsePending !== null && p.pending > pulsePending) toast(L('وصل طلب حجز جديد', 'A new booking request arrived'));
        if ($('nbPending')) $('nbPending').textContent = p.pending;
        var tab = (location.hash || '#home').slice(1), fn = { home: loadHome, bookings: loadBookings, calview: loadCal }[tab];
        if (fn && !userBusy()) fn(); else if (fn) toast(L('تغيّرت الحجوزات، اضغط زر التحديث لعرض الجديد', 'Bookings changed, press refresh to see the new data'));
      }
      pulseSig = p.sig; pulsePending = p.pending;
    }).catch(function () { /* انقطاع مؤقت */ });
  }
  setInterval(pulse, 20000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) pulse(); });
  pulse();

  // ───── تثبيت التطبيق (PWA) ─────
  var deferred = null, ib = $('installAppBtn');
  window.addEventListener('beforeinstallprompt', function (e) { deferred = e; if (ib) ib.style.display = 'flex'; });
  if (ib) ib.addEventListener('click', function (e) { e.preventDefault(); if (deferred) { deferred.prompt(); deferred.userChoice.finally(function () { deferred = null; ib.style.display = 'none'; }); } });
  if ('serviceWorker' in navigator) window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js').catch(function () { /* لا يهم */ }); });

  // ───── الإقلاع ─────
  // القائمة تُخفي ما لا صلاحية له؛ نبدأ بالتبويب في العنوان إن كان مسموحاً
  loadHallsList().then(function () {
    var hash = (location.hash || '#home').slice(1);
    var btn = document.querySelector('.nav-item[data-tab="' + hash + '"]');
    showTab(btn || hash === 'home' ? hash : 'home');
    if (can(['bookings.view'])) api('/api/admin/stats').then(function (s) { if ($('nbPending')) $('nbPending').textContent = s.pending; }).catch(function () { /* صلاحية */ });
  });
})();
