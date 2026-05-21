/* book.js — 1:1 port of GAS buildForm() to Flask backend.
   Renders top bar, lookup/amend/cancel card, personal info, booking details,
   full-day toggle, attachments dropzone, CC emails, notes, success block,
   bilingual toggle. Calls Flask endpoints under /api/*. */

(function(){
'use strict';

var body = document.body;
var LANG = body.dataset.lang || 'ar';
var THEME = body.dataset.theme || '';
var ORG_AR = body.dataset.orgAr || '';
var ORG_EN = body.dataset.orgEn || '';
var LOGO = body.dataset.logo || '';
var PRE_DATE = body.dataset.preDate || '';
var BASE = '';

var lang = LANG;
var attachments = [];
var isAmendMode = false;
var amendReqId = '';
var hallsData = [];

var T = {
  ar:{send:"إرسال الطلب",sending:"جارٍ الإرسال...",errName:"الرجاء إدخال الاسم",errEmail:"الرجاء إدخال بريد صحيح",errTitle:"الرجاء إدخال عنوان المناسبة",errHall:"الرجاء اختيار القاعة",errDate:"الرجاء تحديد تاريخ البداية",errFrom:"الرجاء تحديد وقت البداية",errTo:"وقت النهاية يجب أن يكون بعد البداية",errEndDate:"تاريخ الانتهاء يجب أن يكون مساوياً أو بعد تاريخ البداية",uploading:"جارٍ رفع",errSize:"يتجاوز 10 ميجا",errFile:"خطأ في قراءة الملف",uploaded:"تم رفع",errUpload:"خطأ:",errLookupId:"الرجاء إدخال رقم الطلب",errLookupEmail:"الرجاء إدخال البريد الإلكتروني",lookupFail:"لم يتم العثور على الحجز",amendSuccess:"تم تعديل الحجز بنجاح!",cancelConfirm:"هل أنت متأكد من إلغاء الحجز؟",cancelSuccess:"تم إلغاء الحجز بنجاح",amendBtn:"حفظ التعديلات",cancelBtn:"إلغاء الحجز",newBooking:"حجز جديد"},
  en:{send:"Submit Request",sending:"Submitting...",errName:"Please enter your name",errEmail:"Please enter a valid email",errTitle:"Please enter event title",errHall:"Please select a venue",errDate:"Please select a start date",errFrom:"Please select start time",errTo:"End time must be after start time",errEndDate:"End date must be on or after start date",uploading:"Uploading",errSize:"exceeds 10MB",errFile:"Error reading file",uploaded:"Uploaded",errUpload:"Error:",errLookupId:"Please enter Request ID",errLookupEmail:"Please enter email",lookupFail:"Booking not found",amendSuccess:"Booking amended successfully!",cancelConfirm:"Are you sure you want to cancel this booking?",cancelSuccess:"Booking cancelled successfully",amendBtn:"Save Changes",cancelBtn:"Cancel Booking",newBooking:"New Booking"}
};

function t(k){return T[lang][k]||k;}
function esc(s){return s?String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"):"";}

function backHref(){
  var q = '/?lang='+lang;
  if (THEME) q += '&theme='+encodeURIComponent(THEME);
  return q;
}

function render(){
  var dir = lang==='ar'?'rtl':'ltr';
  document.documentElement.lang = lang;
  document.documentElement.dir = dir;

  var html = ''+
    '<div class="top-bar">'+
      '<div class="logo-area">'+
        '<img src="'+esc(LOGO)+'" alt="logo">'+
        '<div>'+
          '<h1 id="hdrTitle">'+esc(lang==='ar'?ORG_AR:ORG_EN)+'</h1>'+
          '<p id="hdrSub">'+(lang==='ar'?'نموذج طلب حجز قاعة أو مرفق':'Venue Booking Request Form')+'</p>'+
        '</div>'+
      '</div>'+
      '<div class="top-actions">'+
        '<div class="clock-display"><i class="fas fa-clock"></i> <span id="clockEl"></span></div>'+
        '<button class="btn-top" id="btnLang" type="button"><i class="fas fa-globe"></i> <span>'+(lang==='ar'?'EN':'عربي')+'</span></button>'+
      '</div>'+
    '</div>'+
    '<div class="wrap">'+
      '<a class="back-link" id="backLink" href="'+backHref()+'"><i class="fas fa-arrow-'+(lang==='ar'?'right':'left')+'"></i> <span id="tBack">'+(lang==='ar'?'العودة للروزنامة':'Back to Calendar')+'</span></a>'+
      '<div id="formWrap">'+

        '<div class="card">'+
          '<h3><i class="fas fa-search"></i> <span id="secLookup">'+(lang==='ar'?'تعديل / إلغاء حجز موجود':'Amend / Cancel Existing Booking')+'</span></h3>'+
          '<div class="row2">'+
            '<div class="fg"><label>'+(lang==='ar'?'رقم الطلب':'Request ID')+' <span class="req">*</span></label><input type="text" id="lookupId" placeholder="PUB-..." dir="ltr"></div>'+
            '<div class="fg"><label>'+(lang==='ar'?'البريد الإلكتروني':'Email')+' <span class="req">*</span></label><input type="email" id="lookupEmail" placeholder="example@email.com" dir="ltr"></div>'+
          '</div>'+
          '<button class="sub-btn secondary" id="btnLookup" type="button"><i class="fas fa-search"></i> <span id="tLookup">'+(lang==='ar'?'بحث عن حجزي':'Find My Booking')+'</span></button>'+
          '<div id="lookupResult" class="lookup-result" style="display:none"></div>'+
        '</div>'+

        '<div class="card">'+
          '<h3><i class="fas fa-user"></i> <span id="sec1">'+(lang==='ar'?'البيانات الشخصية':'Personal Information')+'</span></h3>'+
          '<div class="row2">'+
            '<div class="fg"><label><span id="lName">'+(lang==='ar'?'الاسم الكامل':'Full Name')+'</span> <span class="req">*</span></label><input type="text" id="fName" placeholder="'+(lang==='ar'?'أدخل اسمك الكامل':'Enter your full name')+'"></div>'+
            '<div class="fg"><label><span id="lEmail">'+(lang==='ar'?'البريد الإلكتروني':'Email')+'</span> <span class="req">*</span></label><input type="email" id="fEmail" placeholder="example@email.com" dir="ltr"></div>'+
          '</div>'+
          '<div class="row2">'+
            '<div class="fg"><label id="lPhone">'+(lang==='ar'?'رقم الجوال':'Phone')+'</label><input type="tel" id="fPhone" placeholder="05XXXXXXXX" dir="ltr"></div>'+
            '<div class="fg"><label id="lBehalf">'+(lang==='ar'?'الحجز نيابة عن':'On Behalf Of')+'</label><input type="text" id="fBehalf" placeholder="'+(lang==='ar'?'اسم الجهة أو الشخص (اختياري)':'Entity or person (optional)')+'"></div>'+
          '</div>'+
        '</div>'+

        '<div class="card">'+
          '<h3><i class="fas fa-calendar-check"></i> <span id="sec2">'+(lang==='ar'?'تفاصيل الحجز':'Booking Details')+'</span></h3>'+
          '<div class="fg"><label><span id="lTitle">'+(lang==='ar'?'عنوان المناسبة':'Event Title')+'</span> <span class="req">*</span></label><input type="text" id="fTitle" placeholder="'+(lang==='ar'?'مثال: ورشة عمل':'e.g. Design Workshop')+'"></div>'+
          '<div class="fg"><label><span id="lHall">'+(lang==='ar'?'اختيار القاعة':'Select Venue')+'</span> <span class="req">*</span></label><select id="fHall"><option value="">'+(lang==='ar'?'— اختر القاعة —':'— Select Venue —')+'</option></select></div>'+
          '<div class="hall-info-box" id="hallInfo"></div>'+
          '<div class="row2">'+
            '<div class="fg"><label><span id="lDate">'+(lang==='ar'?'تاريخ البداية':'Start Date')+'</span> <span class="req">*</span></label><input type="date" id="fDate" value="'+esc(PRE_DATE)+'"></div>'+
            '<div class="fg"><label><span id="lEndDate">'+(lang==='ar'?'تاريخ الانتهاء':'End Date')+'</span></label><input type="date" id="fEndDate" value="'+esc(PRE_DATE)+'"></div>'+
          '</div>'+
          '<div class="fd-wrap"><input type="checkbox" id="fFullDay"><label for="fFullDay"><i class="fas fa-sun"></i> <span id="lFull">'+(lang==='ar'?'حجز يوم كامل':'Full Day Booking')+'</span></label></div>'+
          '<div class="time-row" id="timeRow">'+
            '<div class="fg"><label><span id="lFrom">'+(lang==='ar'?'من الساعة':'From')+'</span> <span class="req">*</span></label><input type="time" id="fStart"></div>'+
            '<div class="fg"><label><span id="lTo">'+(lang==='ar'?'إلى الساعة':'To')+'</span> <span class="req">*</span></label><input type="time" id="fEnd"></div>'+
          '</div>'+
          '<div class="fg"><label id="lCC">'+(lang==='ar'?'نسخة إلى (إيميلات إضافية)':'CC (Additional Emails)')+'</label><input type="text" id="fCC" placeholder="email1@..., email2@..." dir="ltr"></div>'+
          '<div class="fg"><label id="lNotes">'+(lang==='ar'?'ملاحظات إضافية':'Additional Notes')+'</label><textarea id="fNotes" placeholder="'+(lang==='ar'?'أي تفاصيل أو متطلبات خاصة...':'Any details or special requirements...')+'"></textarea></div>'+
        '</div>'+

        '<div class="card" id="attCard">'+
          '<h3><i class="fas fa-paperclip"></i> <span id="sec3">'+(lang==='ar'?'المرفقات':'Attachments')+'</span></h3>'+
          '<label class="file-area"><i class="fas fa-cloud-upload-alt"></i><p>'+(lang==='ar'?'اضغط لرفع ملفات':'Click to upload files')+'</p><p style="font-size:11px;color:#bbb;margin-top:4px">'+(lang==='ar'?'الحد الأقصى 10 ميجا للملف':'Max 10MB per file')+'</p><input type="file" id="fileIn" multiple></label>'+
          '<div class="att-list" id="attList"></div>'+
        '</div>'+

        '<div id="actionButtons">'+
          '<button class="sub-btn" id="subBtn" type="button"><i class="fas fa-paper-plane"></i> <span id="tSub">'+(lang==='ar'?'إرسال الطلب':'Submit Request')+'</span></button>'+
        '</div>'+
        '<div id="status"></div>'+

      '</div>'+
      '<div class="success-box" id="successBox" style="display:none">'+
        '<i class="fas fa-check-circle"></i>'+
        '<h2 id="sucTitle">'+(lang==='ar'?'تم إرسال طلبك بنجاح!':'Request Submitted Successfully!')+'</h2>'+
        '<div class="req-id" id="reqIdDisp"></div>'+
        '<p id="sucMsg">'+(lang==='ar'?'سيتم مراجعة طلبك وإبلاغك بالنتيجة عبر البريد الإلكتروني':'You will be notified via email')+'</p><br>'+
        '<a class="back-link" href="'+backHref()+'" style="font-size:15px"><i class="fas fa-calendar"></i> '+(lang==='ar'?'عرض الروزنامة':'View Calendar')+'</a>'+
      '</div>'+
    '</div>';
  var app = document.getElementById('app');
  if (app) app.innerHTML = html;
  else { body.insertAdjacentHTML('afterbegin', '<div id="app">'+html+'</div>'); }
  attach();
}

function attach(){
  document.getElementById('btnLang').addEventListener('click', toggleLang);
  document.getElementById('btnLookup').addEventListener('click', lookupBooking);
  document.getElementById('subBtn').addEventListener('click', submitForm);
  document.getElementById('fHall').addEventListener('change', showHallInfo);
  document.getElementById('fFullDay').addEventListener('change', toggleFullDay);
  document.getElementById('fileIn').addEventListener('change', function(e){
    handleFiles(e.target.files);
    e.target.value = '';
  });
  document.getElementById('fDate').addEventListener('change', function(){
    var sd = document.getElementById('fDate').value;
    var ed = document.getElementById('fEndDate').value;
    if (!ed || ed < sd) document.getElementById('fEndDate').value = sd;
  });
}

function updateClock(){
  var n = new Date();
  var ds = n.toLocaleDateString(lang==='ar'?'ar-SA':'en-US',{weekday:'long',year:'numeric',month:'long',day:'numeric'});
  var ts = n.toLocaleTimeString(lang==='ar'?'ar-SA':'en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  var el = document.getElementById('clockEl');
  if (el) el.textContent = ds + ' | ' + ts;
}

function loadHalls(){
  fetch('/api/halls').then(function(r){return r.json();}).then(function(h){
    hallsData = h || [];
    var sel = document.getElementById('fHall');
    if (!sel) return;
    for (var i=0; i<hallsData.length; i++){
      var o = document.createElement('option');
      o.value = hallsData[i].nameAr;
      o.textContent = lang==='ar' ? hallsData[i].nameAr : (hallsData[i].nameEn||hallsData[i].nameAr);
      sel.appendChild(o);
    }
  }).catch(function(){});
}

function showHallInfo(){
  var v = document.getElementById('fHall').value;
  var box = document.getElementById('hallInfo');
  if (!v){ box.style.display='none'; return; }
  var hall = null;
  for (var i=0;i<hallsData.length;i++){ if (hallsData[i].nameAr===v){ hall=hallsData[i]; break; } }
  if (!hall){ box.style.display='none'; return; }
  var name = lang==='ar' ? hall.nameAr : (hall.nameEn||hall.nameAr);
  var rows = '';
  function row(icon,label,val){
    if (!val) return '';
    return '<div class="hall-info-row"><div class="hall-info-icon"><i class="fas '+icon+'"></i></div><div class="hall-info-content"><div class="hall-info-label">'+label+'</div><div class="hall-info-value">'+esc(val)+'</div></div></div>';
  }
  rows += row('fa-hashtag', lang==='ar'?'الرمز':'Code', hall.code);
  rows += row('fa-map-marker-alt', lang==='ar'?'الموقع':'Location', hall.location);
  if (hall.capacity) rows += '<div class="hall-info-row"><div class="hall-info-icon"><i class="fas fa-users"></i></div><div class="hall-info-content"><div class="hall-info-label">'+(lang==='ar'?'السعة':'Capacity')+'</div><div class="hall-info-value">'+esc(hall.capacity)+' '+(lang==='ar'?'شخص':'persons')+'</div></div></div>';
  rows += row('fa-info-circle', lang==='ar'?'الوصف':'Description', hall.description);
  rows += row('fa-tools', lang==='ar'?'المعدات والمرافق':'Equipment', hall.equipment);
  rows += row('fa-sticky-note', lang==='ar'?'ملاحظات':'Notes', hall.notes);
  box.innerHTML = '<div class="hall-info-header"><i class="fas fa-building"></i> '+esc(name)+'</div><div class="hall-info-body">'+rows+'</div>';
  box.style.display = 'block';
}

function toggleFullDay(){
  document.getElementById('timeRow').classList.toggle('hidden', document.getElementById('fFullDay').checked);
}

function handleFiles(files){
  if (!files || !files.length) return;
  for (var i=0;i<files.length;i++){
    (function(f){
      if (f.size > 10*1024*1024){ showSt(f.name+' '+t('errSize'),'err'); return; }
      showSt(t('uploading')+' '+f.name+'...','');
      var reader = new FileReader();
      reader.onload = function(ev){
        var b64 = ev.target.result.split(',')[1];
        if (!b64){ showSt(t('errFile'),'err'); return; }
        fetch('/api/upload', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({fileName:f.name, dataBase64:b64, mimeType:f.type||'application/octet-stream'})
        }).then(function(r){
          if (!r.ok) return r.json().then(function(j){ throw new Error(j.error||'upload failed'); });
          return r.json();
        }).then(function(res){
          attachments.push({name:res.name||f.name, url:res.url});
          renderAtt();
          showSt(t('uploaded')+' '+f.name,'ok');
        }).catch(function(err){
          showSt(t('errUpload')+' '+err.message,'err');
        });
      };
      reader.onerror = function(){ showSt(t('errFile'),'err'); };
      reader.readAsDataURL(f);
    })(files[i]);
  }
}

function renderAtt(){
  var c = document.getElementById('attList');
  if (!attachments.length){ c.innerHTML=''; return; }
  var h = '';
  for (var i=0;i<attachments.length;i++){
    h += '<div class="att-item"><i class="fas fa-file"></i> '+esc(attachments[i].name)+'<button class="rm" type="button" data-i="'+i+'"><i class="fas fa-times"></i></button></div>';
  }
  c.innerHTML = h;
  var btns = c.querySelectorAll('.rm');
  for (var j=0;j<btns.length;j++){
    btns[j].addEventListener('click', function(e){
      var idx = parseInt(this.getAttribute('data-i'),10);
      attachments.splice(idx,1); renderAtt();
    });
  }
}

function lookupBooking(){
  var id = document.getElementById('lookupId').value.trim();
  var em = document.getElementById('lookupEmail').value.trim();
  if (!id){ showSt(t('errLookupId'),'err'); return; }
  if (!em || em.indexOf('@')<0){ showSt(t('errLookupEmail'),'err'); return; }
  fetch('/api/lookup_booking',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reqId:id,email:em})})
    .then(function(r){ if(!r.ok) return r.json().then(function(j){throw new Error(j.error||t('lookupFail'));}); return r.json(); })
    .then(function(bk){
      isAmendMode = true;
      amendReqId = bk.reqId;
      document.getElementById('fName').value = bk.name||'';
      document.getElementById('fEmail').value = bk.email||'';
      document.getElementById('fPhone').value = bk.phone||'';
      document.getElementById('fBehalf').value = bk.behalf||'';
      document.getElementById('fTitle').value = bk.title||'';
      document.getElementById('fHall').value = bk.hall||'';
      showHallInfo();
      document.getElementById('fDate').value = bk.date||'';
      document.getElementById('fEndDate').value = bk.endDate||bk.date||'';
      document.getElementById('fStart').value = bk.startTime||'';
      document.getElementById('fEnd').value = bk.endTime||'';
      document.getElementById('fFullDay').checked = !!bk.fullDay;
      document.getElementById('fNotes').value = bk.notes||'';
      document.getElementById('fCC').value = bk.ccEmails||'';
      toggleFullDay();
      document.getElementById('fEmail').readOnly = true;
      var status = bk.status||'pending';
      var stLabel = status==='approved'?(lang==='ar'?'معتمد':'Approved'):(status==='cancelled'?(lang==='ar'?'ملغي':'Cancelled'):(lang==='ar'?'قيد المراجعة':'Pending'));
      var html = '<div style="text-align:center;margin-bottom:12px"><span class="st-badge s-'+status+'" style="font-size:13px;padding:6px 14px">'+stLabel+'</span></div>';
      html += '<div style="display:flex;gap:10px;flex-wrap:wrap"><button class="sub-btn secondary" type="button" id="btnAmendSave" style="flex:1"><i class="fas fa-save"></i> '+t('amendBtn')+'</button><button class="sub-btn danger" type="button" id="btnCancel" style="flex:1"><i class="fas fa-trash"></i> '+t('cancelBtn')+'</button></div>';
      var box = document.getElementById('lookupResult');
      box.innerHTML = html;
      box.style.display = 'block';
      document.getElementById('btnAmendSave').addEventListener('click', amendMyBooking);
      document.getElementById('btnCancel').addEventListener('click', cancelMyBooking);
      document.getElementById('subBtn').style.display = 'none';
      document.getElementById('attCard').style.display = 'none';
      showSt(lang==='ar'?'تم العثور على الحجز':'Booking found','ok');
    })
    .catch(function(e){ showSt(e.message||t('lookupFail'),'err'); });
}

function amendMyBooking(){
  var name = document.getElementById('fName').value.trim();
  var email = document.getElementById('fEmail').value.trim();
  var title = document.getElementById('fTitle').value.trim();
  var hall = document.getElementById('fHall').value;
  var date = document.getElementById('fDate').value;
  var endDate = document.getElementById('fEndDate').value || date;
  var fullDay = document.getElementById('fFullDay').checked;
  var start = document.getElementById('fStart').value;
  var end = document.getElementById('fEnd').value;
  if (!name){ showSt(t('errName'),'err'); return; }
  if (!title){ showSt(t('errTitle'),'err'); return; }
  if (!hall){ showSt(t('errHall'),'err'); return; }
  if (!date){ showSt(t('errDate'),'err'); return; }
  if (endDate < date){ showSt(t('errEndDate'),'err'); return; }
  if (!fullDay && !start){ showSt(t('errFrom'),'err'); return; }
  if (!fullDay && end && end <= start){ showSt(t('errTo'),'err'); return; }
  var btn = document.getElementById('btnAmendSave');
  if (btn){ btn.disabled=true; btn.innerHTML='<i class="fas fa-spinner fa-spin"></i> '+t('sending'); }
  fetch('/api/amend_booking_user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    reqId:amendReqId,email:email,name:name,
    phone:document.getElementById('fPhone').value.trim(),
    behalf:document.getElementById('fBehalf').value.trim(),
    title:title,hall:hall,date:date,endDate:endDate,
    startTime:start,endTime:end,fullDay:fullDay,
    notes:document.getElementById('fNotes').value.trim(),
    ccEmails:document.getElementById('fCC').value.trim()
  })})
  .then(function(r){ if(!r.ok) return r.json().then(function(j){throw new Error(j.error||'error');}); return r.json(); })
  .then(function(){
    showSt(t('amendSuccess'),'ok');
    document.getElementById('lookupResult').style.display='none';
    document.getElementById('fEmail').readOnly = false;
    isAmendMode=false; amendReqId='';
    resetForm();
  })
  .catch(function(e){ showSt(t('errUpload')+' '+e.message,'err'); })
  .then(function(){ if(btn){ btn.disabled=false; btn.innerHTML='<i class="fas fa-save"></i> '+t('amendBtn'); } });
}

function cancelMyBooking(){
  if (!confirm(t('cancelConfirm'))) return;
  var btn = document.getElementById('btnCancel');
  if (btn){ btn.disabled=true; btn.innerHTML='<i class="fas fa-spinner fa-spin"></i>'; }
  fetch('/api/cancel_booking_user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    reqId:amendReqId, email:document.getElementById('fEmail').value.trim()
  })})
  .then(function(r){ if(!r.ok) return r.json().then(function(j){throw new Error(j.error||'error');}); return r.json(); })
  .then(function(){
    showSt(t('cancelSuccess'),'ok');
    document.getElementById('lookupResult').style.display='none';
    document.getElementById('fEmail').readOnly = false;
    isAmendMode=false; amendReqId='';
    resetForm();
  })
  .catch(function(e){ showSt(e.message,'err'); if(btn){ btn.disabled=false; btn.innerHTML='<i class="fas fa-trash"></i> '+t('cancelBtn'); } });
}

function resetForm(){
  ['fName','fEmail','fPhone','fBehalf','fTitle','fHall','fDate','fEndDate','fStart','fEnd','fNotes','fCC','lookupId','lookupEmail'].forEach(function(id){
    var el = document.getElementById(id); if (el) el.value='';
  });
  document.getElementById('fFullDay').checked = false;
  document.getElementById('subBtn').style.display='flex';
  document.getElementById('attCard').style.display='block';
  document.getElementById('hallInfo').style.display='none';
  attachments = []; renderAtt();
  toggleFullDay();
}

function submitForm(){
  var name = document.getElementById('fName').value.trim();
  var email = document.getElementById('fEmail').value.trim();
  var title = document.getElementById('fTitle').value.trim();
  var hall = document.getElementById('fHall').value;
  var date = document.getElementById('fDate').value;
  var endDate = document.getElementById('fEndDate').value || date;
  var fullDay = document.getElementById('fFullDay').checked;
  var start = document.getElementById('fStart').value;
  var end = document.getElementById('fEnd').value;
  if (!name){ showSt(t('errName'),'err'); return; }
  if (!email || email.indexOf('@')<0 || email.indexOf('@')>=email.length-1){ showSt(t('errEmail'),'err'); return; }
  if (!title){ showSt(t('errTitle'),'err'); return; }
  if (!hall){ showSt(t('errHall'),'err'); return; }
  if (!date){ showSt(t('errDate'),'err'); return; }
  if (endDate < date){ showSt(t('errEndDate'),'err'); return; }
  if (!fullDay && !start){ showSt(t('errFrom'),'err'); return; }
  if (!fullDay && end && end <= start){ showSt(t('errTo'),'err'); return; }
  var btn = document.getElementById('subBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> '+t('sending');
  var urls = []; for (var i=0;i<attachments.length;i++) urls.push(attachments[i].url);
  fetch('/api/submit_booking',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    fullName:name,email:email,
    phone:document.getElementById('fPhone').value.trim(),
    onBehalf:document.getElementById('fBehalf').value.trim(),
    eventTitle:title,hall:hall,
    bookingDate:date,endDate:endDate,
    startTime:start,endTime:end,fullDay:fullDay,
    notes:document.getElementById('fNotes').value.trim(),
    ccEmails:document.getElementById('fCC').value.trim(),
    attUrls:urls
  })})
  .then(function(r){ if(!r.ok) return r.json().then(function(j){throw new Error(j.error||'error');}); return r.json(); })
  .then(function(res){
    var reqId = res.reqId || res.req_id || '';
    document.getElementById('formWrap').style.display='none';
    document.getElementById('successBox').style.display='block';
    document.getElementById('reqIdDisp').textContent = reqId;
  })
  .catch(function(e){
    showSt(t('errUpload')+' '+e.message,'err');
    btn.disabled=false; btn.innerHTML='<i class="fas fa-paper-plane"></i> '+t('send');
  });
}

function showSt(m,tp){
  var s = document.getElementById('status'); if (!s) return;
  s.textContent = m;
  s.className = tp==='ok' ? 'st-ok' : (tp==='err' ? 'st-err' : '');
  s.style.display = 'block';
  if (tp) setTimeout(function(){ s.style.display='none'; }, 5000);
}

function toggleLang(){
  lang = lang === 'ar' ? 'en' : 'ar';
  // preserve form values across re-render
  var keep = {};
  ['fName','fEmail','fPhone','fBehalf','fTitle','fHall','fDate','fEndDate','fStart','fEnd','fNotes','fCC','lookupId','lookupEmail'].forEach(function(id){
    var el = document.getElementById(id); if (el) keep[id] = el.value;
  });
  var fullDay = document.getElementById('fFullDay') && document.getElementById('fFullDay').checked;
  render();
  loadHalls();
  setTimeout(function(){
    Object.keys(keep).forEach(function(id){
      var el = document.getElementById(id); if (el) el.value = keep[id];
    });
    var fd = document.getElementById('fFullDay'); if (fd){ fd.checked = !!fullDay; toggleFullDay(); }
    showHallInfo();
    updateClock();
  }, 0);
}

// boot
render();
loadHalls();
updateClock();
setInterval(updateClock, 1000);

})();
