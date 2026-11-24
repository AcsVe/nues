/* الاستعلام عن حجز برقمه وبريده: عرضه وتعديله وإلغاؤه. */
(function () {
  'use strict';
  var AR = document.documentElement.lang !== 'en';
  var L = function (a, e) { return AR ? a : e; };
  var $ = function (id) { return document.getElementById(id); };
  var cur = null, halls = [];
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  var ST = { pending: [L('قيد المراجعة', 'Pending'), 'badge-pending'], approved: [L('معتمد', 'Approved'), 'badge-approved'],
    rejected: [L('مرفوض', 'Rejected'), 'badge-rejected'], cancelled: [L('ملغي', 'Cancelled'), 'badge-cancelled'] };
  function say(id, msg, type) { $(id).innerHTML = msg ? '<div class="alert alert-' + (type || 'error') + '" role="alert">' + esc(msg) + '</div>' : ''; }
  function api(url, body) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error((AR ? j.error : (j.errorEn || j.error)) || ''); return j; }); });
  }
  fetch('/api/halls').then(function (r) { return r.json(); }).then(function (h) {
    halls = h; $('eHall').innerHTML = h.map(function (x) { return '<option value="' + esc(x.nameAr) + '">' + esc(AR ? x.nameAr : (x.nameEn || x.nameAr)) + '</option>'; }).join('');
  });
  function hallLabel(n) { var h = halls.filter(function (x) { return x.nameAr === n; })[0]; return h ? (AR ? h.nameAr : (h.nameEn || h.nameAr)) : n; }

  function show(b) {
    cur = b; $('editCard').hidden = true;
    var st = ST[b.status] || [b.status, ''];
    $('resTitle').textContent = b.reqId; $('resBadge').innerHTML = '<span class="badge ' + st[1] + '">' + esc(st[0]) + '</span>';
    var rows = [[L('الاسم', 'Name'), '<bdi>' + esc(b.name) + '</bdi>'], [L('المناسبة', 'Event'), '<bdi>' + esc(b.title) + '</bdi>'], [L('المبنى أو المرفق', 'Building or facility'), '<bdi>' + esc(hallLabel(b.hall)) + '</bdi>'],
      [L('التاريخ', 'Date'), '<span dir="ltr">' + esc(b.date) + (b.endDate !== b.date ? ' → ' + esc(b.endDate) : '') + '</span>'],
      [L('الوقت', 'Time'), b.fullDay ? L('يوم كامل', 'Full day') : '<span dir="ltr">' + esc(b.startTime) + (b.endTime ? ' - ' + esc(b.endTime) : '') + '</span>']];
    if (b.status === 'rejected' && b.rejectReason) rows.push([L('سبب الرفض', 'Rejection reason'), '<bdi>' + esc(b.rejectReason) + '</bdi>']);
    $('resTable').innerHTML = rows.map(function (r) { return '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td></tr>'; }).join('');
    var open = b.status === 'pending' || b.status === 'approved';
    $('resActions').innerHTML = open ? '<button class="btn btn-outline" type="button" id="doEdit"><i class="fas fa-pen"></i> ' + L('تعديل', 'Amend') + '</button><button class="btn btn-red" type="button" id="doCancel"><i class="fas fa-ban"></i> ' + L('إلغاء الحجز', 'Cancel the booking') + '</button>' : '';
    $('result').hidden = false;
  }
  $('lookForm').addEventListener('submit', function (e) {
    e.preventDefault(); say('lookAlert', ''); $('result').hidden = true; $('editCard').hidden = true;
    api('/api/lookup_booking', { reqId: $('lId').value.trim(), email: $('lEmail').value.trim() }).then(show)
      .catch(function (er) { say('lookAlert', er.message || L('تعذّر الاستعلام.', 'The lookup failed.')); });
  });
  document.addEventListener('click', function (e) {
    if (e.target.closest('#doEdit')) {
      $('eHall').value = cur.hall; $('eDate').value = cur.date; $('eEnd').value = cur.endDate; $('eFull').checked = !!cur.fullDay; $('eTimeRow').hidden = !!cur.fullDay;
      $('eFrom').value = cur.startTime; $('eTo').value = cur.endTime; $('eTitle').value = cur.title; $('eName').value = cur.name; $('ePhone').value = cur.phone || ''; $('eNotes').value = cur.notes || '';
      say('editAlert', ''); $('editCard').hidden = false; $('editCard').scrollIntoView({ behavior: 'smooth' });
    }
    if (e.target.closest('#doCancel')) {
      if (!confirm(L('هل تريد إلغاء هذا الحجز؟', 'Cancel this booking?'))) return;
      api('/api/cancel_booking_user', { reqId: cur.reqId, email: $('lEmail').value.trim() }).then(function () {
        say('lookAlert', L('تم إلغاء الحجز.', 'The booking was cancelled.'), 'success'); $('result').hidden = true; $('editCard').hidden = true;
      }).catch(function (er) { say('lookAlert', er.message); });
    }
  });
  $('eFull').addEventListener('change', function () { $('eTimeRow').hidden = this.checked; });
  $('cancelEdit').addEventListener('click', function () { $('editCard').hidden = true; });
  $('saveEdit').addEventListener('click', function () {
    api('/api/amend_booking_user', { reqId: cur.reqId, email: $('lEmail').value.trim(), hall: $('eHall').value, date: $('eDate').value, endDate: $('eEnd').value || $('eDate').value,
      fullDay: $('eFull').checked, startTime: $('eFrom').value, endTime: $('eTo').value, title: $('eTitle').value.trim(), name: $('eName').value.trim(),
      phone: $('ePhone').value.trim(), behalf: cur.behalf || '', notes: $('eNotes').value.trim() })
      .then(function () { say('editAlert', L('تم حفظ التعديلات.', 'The changes were saved.'), 'success'); return api('/api/lookup_booking', { reqId: cur.reqId, email: $('lEmail').value.trim() }); })
      .then(function (b) { show(b); $('editCard').hidden = false; })
      .catch(function (er) { say('editAlert', er.message || L('تعذّر الحفظ.', 'Saving failed.')); });
  });
})();
