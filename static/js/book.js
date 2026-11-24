/* صفحة الحجز: اختيار المبنى أو المرفق بحسب نوعه، ثم الموعد والبيانات والمرفقات، ثم الإرسال. */
(function () {
  'use strict';
  var AR = document.documentElement.lang !== 'en';
  var L = function (a, e) { return AR ? a : e; };
  var $ = function (id) { return document.getElementById(id); };
  var halls = [], cat = '', chosen = '', attachments = [];
  var ICONS = { hall: 'door-open', theater: 'masks-theater', field: 'futbol', gym: 'dumbbell', building: 'building', facility: 'warehouse' };
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function nm(h) { return AR ? h.nameAr : (h.nameEn || h.nameAr); }
  function today() { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Amman' }).format(new Date()); }

  $('fDate').min = today();
  $('fEndDate').min = today();

  function alertBox(msg, type) {
    $('formAlert').innerHTML = '<div class="alert alert-' + (type || 'error') + '" role="alert"><i class="fas fa-circle-' + (type === 'success' ? 'check' : 'exclamation') + '"></i> ' + esc(msg) + '</div>';
    $('formAlert').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function renderPicks() {
    var seen = {}, chips = '<button class="chip' + (cat ? '' : ' active') + '" type="button" data-cat="">' + L('الكل', 'All') + '</button>';
    halls.forEach(function (h) { if (!seen[h.category]) { seen[h.category] = 1; chips += '<button class="chip' + (cat === h.category ? ' active' : '') + '" type="button" data-cat="' + esc(h.category) + '">' + esc(AR ? h.categoryAr : h.categoryEn) + '</button>'; } });
    $('catChips').innerHTML = chips;
    $('hallPicks').innerHTML = halls.filter(function (h) { return !cat || h.category === cat; }).map(function (h) {
      return '<button type="button" class="hall-pick' + (chosen === h.nameAr ? ' active' : '') + '" role="radio" aria-checked="' + (chosen === h.nameAr) + '" data-hall="' + esc(h.nameAr) + '">' +
        '<span class="ic"><i class="fas fa-' + (ICONS[h.category] || 'building') + '"></i></span><span><b><bdi>' + esc(nm(h)) + '</bdi></b><small>' + esc(AR ? h.categoryAr : h.categoryEn) +
        (h.capacity ? ' · ' + L('السعة ', 'Capacity ') + esc(h.capacity) : '') + '</small></span></button>';
    }).join('') || '<p class="muted">' + L('لا توجد مبانٍ أو مرافق متاحة.', 'No buildings or facilities are available.') + '</p>';
    showInfo();
  }
  function showInfo() {
    var h = halls.filter(function (x) { return x.nameAr === chosen; })[0], box = $('hallInfo');
    if (!h) { box.classList.remove('show'); return; }
    var rows = [[L('الموقع', 'Location'), h.location], [L('الرمز', 'Code'), h.code], [L('السعة', 'Capacity'), h.capacity], [L('المعدات والمرافق', 'Equipment'), h.equipment],
      [L('الوصف', 'Description'), h.description], [L('ملاحظات', 'Notes'), h.notes]].filter(function (r) { return r[1]; });
    box.innerHTML = '<b style="color:var(--navy)"><bdi>' + esc(nm(h)) + '</bdi></b>' + (h.requiresApproval ? ' <span class="badge badge-pending">' + L('يحتاج موافقة الإدارة', 'Needs approval') + '</span>' : '') +
      rows.map(function (r) { return '<div class="row"><b>' + r[0] + '</b><span><bdi>' + esc(r[1]) + '</bdi></span></div>'; }).join('');
    box.classList.add('show');
  }

  fetch('/api/halls').then(function (r) { return r.json(); }).then(function (h) {
    halls = h;
    if (window.PRE_HALL && h.some(function (x) { return x.nameAr === window.PRE_HALL; })) chosen = window.PRE_HALL;
    renderPicks();
  });
  $('catChips').addEventListener('click', function (e) { var b = e.target.closest('.chip'); if (b) { cat = b.dataset.cat; renderPicks(); } });
  $('hallPicks').addEventListener('click', function (e) { var b = e.target.closest('.hall-pick'); if (b) { chosen = b.dataset.hall; renderPicks(); } });
  $('fFull').addEventListener('change', function () { $('timeRow').hidden = this.checked; });
  $('fDate').addEventListener('change', function () { $('fEndDate').min = this.value || today(); if ($('fEndDate').value && $('fEndDate').value < this.value) $('fEndDate').value = this.value; });

  // المرفقات: تُرفع فور اختيارها، ويُرسل مع الحجز روابطها
  function renderAtt() {
    $('attList').innerHTML = attachments.map(function (a, i) {
      return '<div class="att"><i class="fas fa-file"></i><span><bdi>' + esc(a.name) + '</bdi></span><button type="button" data-i="' + i + '" aria-label="' + L('إزالة', 'Remove') + '"><i class="fas fa-xmark"></i></button></div>';
    }).join('');
  }
  $('attList').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) { attachments.splice(+b.dataset.i, 1); renderAtt(); } });
  $('fFiles').addEventListener('change', function () {
    var files = [].slice.call(this.files); this.value = '';
    files.forEach(function (f) {
      if (f.size > 10 * 1024 * 1024) { alertBox(f.name + ': ' + L('الملف أكبر من 10 ميغابايت', 'the file is larger than 10 MB')); return; }
      var rd = new FileReader();
      rd.onload = function (ev) {
        var b64 = String(ev.target.result).split(',')[1] || '';
        fetch('/api/upload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fileName: f.name, dataBase64: b64 }) })
          .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || ''); return j; }); })
          .then(function (j) { attachments.push({ name: j.name || f.name, url: j.url }); renderAtt(); })
          .catch(function (er) { alertBox(f.name + ': ' + (er.message || L('تعذّر رفع الملف', 'The file could not be uploaded'))); });
      };
      rd.readAsDataURL(f);
    });
  });

  $('bookForm').addEventListener('submit', function (e) {
    e.preventDefault();
    $('formAlert').innerHTML = '';
    var date = $('fDate').value, end = $('fEndDate').value || date, full = $('fFull').checked, s = $('fStart').value, en = $('fEnd').value;
    var name = $('fName').value.trim(), email = $('fEmail').value.trim(), title = $('fTitle').value.trim();
    if (!chosen) return alertBox(L('اختر المبنى أو المرفق.', 'Choose a building or facility.'));
    if (!date) return alertBox(L('اختر تاريخ البداية.', 'Choose the start date.'));
    if (end < date) return alertBox(L('تاريخ الانتهاء يجب أن يكون بعد البداية.', 'The end date must be after the start date.'));
    if (!full && !s) return alertBox(L('حدّد وقت البداية.', 'Set the start time.'));
    if (!full && en && en <= s) return alertBox(L('وقت النهاية يجب أن يكون بعد وقت البداية.', 'The end time must be after the start time.'));
    if (!title) return alertBox(L('اكتب عنوان المناسبة.', 'Write the event title.'));
    if (!name) return alertBox(L('اكتب الاسم الكامل.', 'Write your full name.'));
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return alertBox(L('اكتب بريداً إلكترونياً صحيحاً.', 'Write a valid email address.'));
    if (!$('fTerms').checked) return alertBox(L('يجب الموافقة على شروط الاستخدام.', 'You must agree to the terms of use.'));
    var btn = $('subBtn'); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> ' + L('جارٍ الإرسال…', 'Submitting…');
    fetch('/api/submit_booking', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      fullName: name, email: email, phone: $('fPhone').value.trim(), onBehalf: $('fBehalf').value.trim(), eventTitle: title, hall: chosen,
      bookingDate: date, endDate: end, startTime: s, endTime: en, fullDay: full, notes: $('fNotes').value.trim(), ccEmails: $('fCC').value.trim(),
      reminderAt: $('fRemind').value, attUrls: attachments.map(function (a) { return a.url; }) }) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || ''); return j; }); })
      .then(function (j) {
        $('bookForm').hidden = true; $('done').hidden = false; $('reqId').textContent = j.reqId;
        $('doneTitle').textContent = j.status === 'approved' ? L('تمّت الموافقة على حجزك', 'Your booking is approved') : L('تم استلام طلبك بنجاح', 'Your request was received');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      })
      .catch(function (er) {
        alertBox(er.message || L('تعذّر إرسال الطلب.', 'The request could not be sent.'));
        btn.disabled = false; btn.innerHTML = '<i class="fas fa-paper-plane"></i> ' + L('إرسال الطلب', 'Submit the request');
      });
  });
})();
