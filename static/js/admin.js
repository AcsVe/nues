/* ACS Admin — ported 1:1 from GAS adminScript(L,base,dir).
 * Replaces google.script.run calls with Flask fetch endpoints.
 */
(function(){
  var lang = window.LANG_INIT || "ar";
  var dir  = lang === "ar" ? "rtl" : "ltr";
  var ORG_AR = window.ORG_AR || "";
  var ORG_EN = window.ORG_EN || "";
  var LOGO_URL = window.LOGO_URL || "";
  var allData = [], hallsCache = [], isLoggedIn = false;

  // ───── helpers ─────
  function esc(t){return t?String(t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"):"";}
  function fmtD(ds){return ds?String(ds):"";}
  function showSt(m,tp){var s=document.getElementById("status");if(!s)return;s.textContent=m;s.className=tp==="ok"?"st-ok":"st-err";s.style.display="block";if(tp)setTimeout(function(){s.style.display="none"},4000);}
  function stLbl(s){return lang==="ar"?({pending:"قيد المراجعة",approved:"معتمد",rejected:"مرفوض",cancelled:"ملغي"})[s]:({pending:"Pending",approved:"Approved",rejected:"Rejected",cancelled:"Cancelled"})[s];}

  // fetch wrappers
  function api(path,opt){
    opt = opt || {};
    opt.credentials = "same-origin";
    if(opt.method && opt.method!=="GET"){opt.headers=Object.assign({"X-CSRF-Token":window.CSRF||""},opt.headers||{});}
    if(opt.body && typeof opt.body!=="string" && !(window.FormData && opt.body instanceof FormData)){
      opt.headers = Object.assign({"Content-Type":"application/json"},opt.headers||{});
      opt.body = JSON.stringify(opt.body);
    }
    return fetch(path,opt).then(function(r){
      return r.json().then(function(j){
        if(!r.ok){var msg=(j&&j.error)?j.error:("HTTP "+r.status);var e=new Error(msg);e.payload=j;throw e;}
        return j;
      });
    });
  }


  function T(ar,en){return lang==="ar"?ar:en;}
  function isoVal(d){return ' data-value="'+esc(d)+'"';}

  // ───── جداول موحّدة: رأس ثابت، بحث، تصفية لكل عمود، ترتيب، تحديد متعدد وإجراءات جماعية ─────
  function tableHtml(key,cols,rows){
    var th='<th class="chk" data-nosort><input type="checkbox" class="bulk-all" aria-label="'+T("تحديد الكل","Select all")+'"></th>';
    cols.forEach(function(c){
      th+='<th'+(c.filter?' data-filter="'+c.filter+'"':'')+(c.sort?' data-sort="'+c.sort+'"':'')+(c.act?' class="act" data-nosort':'')+'>'+c.h+'</th>';
    });
    return '<div class="bulk-bar" id="bar-'+key+'"></div><div class="dt-wrap"><table data-table data-key="'+key+'"><thead><tr>'+th+'</tr></thead><tbody>'+rows+'</tbody></table></div>';
  }
  function chkCell(id){return '<td class="chk"><input type="checkbox" class="bulk-item" value="'+esc(id)+'" aria-label="'+T("تحديد","Select")+'"></td>';}
  function mountTable(box,key,actions,run){
    if(window.dtInit)window.dtInit(box);
    var bar=box.querySelector("#bar-"+key),table=box.querySelector("table"),all=table.querySelector(".bulk-all");
    bar.innerHTML='<span class="bulk-count"></span>'+actions.map(function(a){
      return '<button type="button" class="hbtn '+(a.danger?"danger":"sec")+' sm" data-act="'+a.id+'" disabled>'+a.label+'</button>';}).join("");
    function items(){return [].slice.call(table.querySelectorAll("tbody .bulk-item"));}
    function sel(){return items().filter(function(i){return i.checked&&!i.closest("tr").hidden;}).map(function(i){return i.value;});}
    function refresh(){
      var n=sel().length;
      bar.querySelector(".bulk-count").textContent=n?T("المحدد: ","Selected: ")+n:T("لم يُحدَّد شيء","Nothing selected");
      [].forEach.call(bar.querySelectorAll("button"),function(b){b.disabled=!n;});
      var vis=items().filter(function(i){return !i.closest("tr").hidden;});
      all.checked=!!vis.length&&vis.every(function(i){return i.checked;});
    }
    all.addEventListener("change",function(){items().forEach(function(i){if(!i.closest("tr").hidden)i.checked=all.checked;});refresh();});
    table.addEventListener("change",function(e){if(e.target.classList.contains("bulk-item"))refresh();});
    table.addEventListener("input",function(){setTimeout(refresh,0);});
    bar.addEventListener("click",function(e){
      var b=e.target.closest("button");if(!b)return;
      var ids=sel(),a=actions.filter(function(x){return x.id===b.getAttribute("data-act");})[0];
      if(!ids.length)return;
      if(a.danger&&!confirm(a.label+" ("+ids.length+")?"))return;
      run(a.id,ids);
    });
    refresh();
  }
  function bulkDone(r){
    var m=T("تم: ","Done: ")+(r.done||0);
    if(r.skipped)m+=" — "+T("المستبعد: ","Skipped: ")+r.skipped;
    if(r.notes&&r.notes.length)m+=" — "+r.notes.join("; ");
    showSt(m,"ok");
  }
  function nodata(icon,txt){return '<div class="nodata"><i class="fas fa-'+icon+'"></i>'+txt+'</div>';}

  // ───── clock ─────
  function ammanNow(){
    var p=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Amman',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'})
      .formatToParts(new Date()).reduce(function(a,x){a[x.type]=x.value;return a;},{});
    return p.year+'-'+p.month+'-'+p.day+' | '+p.hour+':'+p.minute+':'+p.second;
  }
  function updateClock(){var el=document.getElementById("clockEl");if(el){el.dir="ltr";el.textContent=ammanNow();}}
  setInterval(updateClock,1000);

  // ───── DOM ready ─────
  window.addEventListener("DOMContentLoaded",function(){
    updateClock();
    var lu=document.getElementById("loginUser"),lp=document.getElementById("loginPass");
    if(lu)lu.addEventListener("keydown",function(e){if(e.key==="Enter"){e.preventDefault();lp.focus();}});
    // Try to load — if 401, prompt login.
    bootstrap();
    var cf=document.getElementById("ctFile");
    if(cf)cf.addEventListener("change",onContactFile);
  });

  function bootstrap(){
    api("/api/admin/session").then(function(ss){
      if(!ss.loggedIn)return null;
      window.CSRF=ss.csrf||window.CSRF;
      return api("/api/admin/bookings?status=all");
    }).then(function(d){
      if(!d)return;
      isLoggedIn=true;
      document.getElementById("loginOverlay").style.display="none";
      allData=d;renderTable(d);updateStats(d);
      loadHallsAdmin();loadBlk();loadContacts();loadStats();loadBlkHalls();loadUsers();loadSettings();
    }).catch(function(){
      // not logged in — leave overlay visible
    });
  }

  // ───── login/logout ─────
  window.doLogin=function(){
    var u=document.getElementById("loginUser").value.trim();
    var p=document.getElementById("loginPass").value;
    var er=document.getElementById("loginErr");
    if(!u||!p){er.textContent=lang==="ar"?"الرجاء إدخال اسم المستخدم وكلمة المرور":"Please enter username and password";er.style.display="block";return;}
    api("/api/admin/login",{method:"POST",body:{username:u,password:p}}).then(function(res){
      if(res&&res.success){window.CSRF=res.csrf||"";isLoggedIn=true;document.getElementById("loginOverlay").style.display="none";bootstrap();}
      else{er.textContent=lang==="ar"?"اسم المستخدم أو كلمة المرور غير صحيحة":"Invalid username or password";er.style.display="block";document.getElementById("loginPass").value="";}
    }).catch(function(){er.textContent=lang==="ar"?"اسم المستخدم أو كلمة المرور غير صحيحة":"Invalid username or password";er.style.display="block";});
  };
  window.doLogout=function(){api("/api/admin/logout",{method:"POST"}).then(function(){window.top.location.href="/?lang="+lang;}).catch(function(){window.top.location.href="/?lang="+lang;});};

  // ───── halls (for blocked-period select + edit-booking select) ─────
  function loadBlkHalls(){
    api("/api/halls").then(function(h){
      hallsCache=h;
      var sel=document.getElementById("blkHall");
      sel.innerHTML='<option value="">'+(lang==="ar"?"— كل القاعات —":"— All Venues —")+"</option>";
      for(var i=0;i<h.length;i++){
        var o=document.createElement("option");o.value=h[i].nameAr;o.textContent=lang==="ar"?h[i].nameAr:(h[i].nameEn||h[i].nameAr);sel.appendChild(o);
      }
    });
  }

  // ───── stat filters ─────
  window.filterByStat=function(type){
    switchTab("bookings",document.querySelector(".tab"));
    if(type==="today"||type==="week"){
      var btns=document.querySelectorAll(".fbtn");
      for(var i=0;i<btns.length;i++){btns[i].classList.remove("active");if(btns[i].id==="fAppr")btns[i].classList.add("active");}
      loadDataInternal("approved",type);
    }else{
      loadData(type);
    }
  };

  window.switchTab=function(id,btn){
    var tabs=document.querySelectorAll(".tab"),contents=document.querySelectorAll(".tab-content");
    for(var i=0;i<tabs.length;i++){tabs[i].classList.remove("active");contents[i].classList.remove("active");}
    btn.classList.add("active");
    document.getElementById("tc-"+id).classList.add("active");
    if(id==="reports")loadStats();
  };

  // ───── bookings table ─────
  window.loadData=function(f,btn){
    var btns=document.querySelectorAll(".fbtn");
    for(var i=0;i<btns.length;i++)btns[i].classList.remove("active");
    if(btn)btn.classList.add("active");
    loadDataInternal(f||"all",null);
  };

  function loadDataInternal(filter,subFilter){
    api("/api/admin/bookings?status="+encodeURIComponent(filter)).then(function(d){
      allData=d;
      var rendered=d;
      if(subFilter==="today"){
        var t=new Date();var ds=t.toISOString().slice(0,10);
        rendered=d.filter(function(r){return r.date===ds;});
      }else if(subFilter==="week"){
        var t=new Date();var dow=t.getDay();var s=new Date(t);s.setDate(t.getDate()-dow);
        var e=new Date(s);e.setDate(s.getDate()+6);
        var sd=s.toISOString().slice(0,10),ed=e.toISOString().slice(0,10);
        rendered=d.filter(function(r){return r.date>=sd&&r.date<=ed;});
      }
      renderTable(rendered);updateStats(d);
    }).catch(function(e){showSt("Error: "+e.message,"err");});
  }

  function updateStats(d){
    var p=0,a=0,r=0;
    for(var i=0;i<d.length;i++){if(d[i].status==="pending")p++;else if(d[i].status==="approved")a++;else r++;}
    setT("sAll",d.length);setT("sPend",p);setT("sApp",a);setT("sRej",r);
  }
  function setT(id,v){var el=document.getElementById(id);if(el)el.textContent=v;}

  function renderTable(d){
    var c=document.getElementById("reqTable");
    if(!d.length){c.innerHTML=nodata("inbox",T("لا توجد طلبات","No requests"));return;}
    var cols=[{h:T("رقم الطلب","ID"),filter:"text"},{h:T("الاسم","Name"),filter:"text"},{h:T("المناسبة","Event"),filter:"text"},
      {h:T("القاعة","Venue"),filter:"select"},{h:T("التاريخ","Date"),filter:"text"},{h:T("الوقت","Time"),filter:"text"},
      {h:T("الحالة","Status"),filter:"select"},{h:T("إجراءات","Actions"),act:true}];
    var rows="";
    for(var i=0;i<d.length;i++){
      var r=d[i],isMulti=r.endDate&&r.endDate!==r.date;
      var dateDisp='<span dir="ltr">'+fmtD(r.date)+'</span>';
      if(isMulti)dateDisp+='<br><span class="sub-line">→ <span dir="ltr">'+fmtD(r.endDate)+'</span></span>';
      var timeTxt=r.fullDay?T("يوم كامل","Full Day"):('<span dir="ltr">'+esc(r.startTime)+(r.endTime?" - "+esc(r.endTime):"")+'</span>');
      rows+='<tr>'+chkCell(r.reqId)
        +'<td class="id-cell">'+esc(r.reqId)+'</td>'
        +'<td><bdi>'+esc(r.name)+'</bdi>'+(r.behalf?'<br><span class="sub-line"><bdi>'+esc(r.behalf)+'</bdi></span>':'')+'</td>'
        +'<td><bdi>'+esc(r.title)+'</bdi>'+(isMulti?'<br><span class="multiday-tag"><i class="fas fa-calendar-week"></i> '+T("متعدد الأيام","Multi-day")+'</span>':'')+'</td>'
        +'<td data-value="'+esc(r.hall)+'"><bdi>'+esc(r.hall)+'</bdi></td>'
        +'<td'+isoVal(r.date)+' style="white-space:nowrap">'+dateDisp+'</td>'
        +'<td style="white-space:nowrap">'+timeTxt+'</td>'
        +'<td data-value="'+esc(stLbl(r.status))+'"><span class="st-tag '+r.status+'">'+stLbl(r.status)+'</span>';
      if(r.status==="rejected"&&r.rejectReason)rows+='<div class="rj-reason"><bdi>'+esc(r.rejectReason)+'</bdi></div>';
      rows+='</td><td class="act"><div class="tbl-actions">';
      var att=r.attachments||[];
      for(var j=0;j<att.length;j++)rows+='<a href="'+esc(att[j])+'" target="_blank" rel="noopener" class="att-link" aria-label="'+T("مرفق","Attachment")+'"><i class="fas fa-paperclip"></i></a>';
      rows+='<button class="tbl-btn edit-bk" title="'+T("تعديل","Edit")+'" aria-label="'+T("تعديل","Edit")+'" onclick="openEditBk(\''+esc(r.reqId)+'\')"><i class="fas fa-pen"></i></button>';
      if(r.status==="pending"){
        rows+='<button class="tbl-btn approve" title="'+T("موافقة","Approve")+'" aria-label="'+T("موافقة","Approve")+'" onclick="showBccInput(\''+esc(r.reqId)+'\')"><i class="fas fa-check"></i></button>';
        rows+='<button class="tbl-btn reject" title="'+T("رفض","Reject")+'" aria-label="'+T("رفض","Reject")+'" onclick="showRjInput(\''+esc(r.reqId)+'\')"><i class="fas fa-times"></i></button>';
      }
      if(r.status!=="cancelled")rows+='<button class="tbl-btn cancel-btn" title="'+T("إلغاء","Cancel")+'" aria-label="'+T("إلغاء","Cancel")+'" onclick="doCancel(\''+esc(r.reqId)+'\')"><i class="fas fa-ban"></i></button>';
      if(r.status!=="pending"&&r.status!=="cancelled")rows+='<button class="tbl-btn pend-btn" title="'+T("إرجاع إلى قيد المراجعة","Back to pending")+'" aria-label="'+T("إرجاع إلى قيد المراجعة","Back to pending")+'" onclick="doPending(\''+esc(r.reqId)+'\')"><i class="fas fa-undo"></i></button>';
      rows+='</div>';
      if(r.status==="pending"){
        rows+='<div class="bcc-info" style="display:none" id="bcc-info-'+esc(r.reqId)+'"><i class="fas fa-info-circle"></i> '+T("يُرسل إبلاغ تلقائي لجهات الاتصال المسجلة","Auto-sent to registered contacts")+'</div>';
        rows+='<div class="bcc-input" id="ci-'+esc(r.reqId)+'"><input type="text" id="cc-'+esc(r.reqId)+'" placeholder="'+T("بريد إبلاغ إضافي (افصل بفاصلة)","Additional BCC emails (comma-separated)")+'" dir="ltr"><button aria-label="'+T("موافقة","Approve")+'" onclick="doApprove(\''+esc(r.reqId)+'\')"><i class="fas fa-check"></i></button></div>';
        rows+='<div class="rj-input" id="ri-'+esc(r.reqId)+'"><input type="text" id="rr-'+esc(r.reqId)+'" placeholder="'+T("سبب الرفض","Rejection reason")+'"><button aria-label="'+T("رفض","Reject")+'" onclick="doReject(\''+esc(r.reqId)+'\')"><i class="fas fa-times"></i></button></div>';
      }
      rows+='</td></tr>';
    }
    c.innerHTML=tableHtml("bk",cols,rows);
    mountTable(c,"bk",[
      {id:"approve",label:T("موافقة","Approve")},{id:"reject",label:T("رفض","Reject")},
      {id:"cancel",label:T("إلغاء الحجز","Cancel booking"),danger:true},{id:"pending",label:T("إرجاع إلى قيد المراجعة","Back to pending")},
      {id:"delete",label:T("حذف","Delete"),danger:true}],function(action,ids){
        var body={action:action,reqIds:ids};
        if(action==="reject"){var rs=prompt(T("سبب الرفض:","Rejection reason:"));if(!rs)return;body.reason=rs;}
        api("/api/admin/bookings/bulk",{method:"POST",body:body}).then(function(r){bulkDone(r);loadData("all");})
          .catch(function(e){showSt(e.message,"err");});
      });
  }

  // row actions
  window.showBccInput=function(id){
    var ci=document.getElementById("ci-"+id),bi=document.getElementById("bcc-info-"+id),ri=document.getElementById("ri-"+id);
    ri.classList.remove("show");bi.style.display=ci.classList.contains("show")?"none":"block";ci.classList.toggle("show");
  };
  window.doApprove=function(id){
    var extra=(document.getElementById("cc-"+id).value||"").trim();
    document.getElementById("ci-"+id).classList.remove("show");
    document.getElementById("bcc-info-"+id).style.display="none";
    if(!confirm((lang==="ar"?"موافقة على ":"Approve ")+id+"?"))return;
    api("/api/admin/approve/"+encodeURIComponent(id),{method:"POST",body:{extraBcc:extra}})
      .then(function(){showSt(lang==="ar"?"تمت الموافقة":"Approved","ok");loadData("all");})
      .catch(function(e){showSt("Error: "+e.message,"err");});
  };
  window.showRjInput=function(id){
    var ri=document.getElementById("ri-"+id);
    document.getElementById("ci-"+id).classList.remove("show");
    document.getElementById("bcc-info-"+id).style.display="none";
    ri.classList.toggle("show");
  };
  window.doReject=function(id){
    var reason=(document.getElementById("rr-"+id).value||"").trim();
    if(!reason){showSt(lang==="ar"?"الرجاء إدخال سبب الرفض":"Please enter reason","err");return;}
    api("/api/admin/reject/"+encodeURIComponent(id),{method:"POST",body:{reason:reason}})
      .then(function(){showSt(lang==="ar"?"تم الرفض":"Rejected","ok");loadData("all");})
      .catch(function(e){showSt("Error: "+e.message,"err");});
  };
  window.doCancel=function(id){
    if(!confirm((lang==="ar"?"إلغاء الحجز ":"Cancel booking ")+id+"?"))return;
    api("/api/admin/cancel/"+encodeURIComponent(id),{method:"POST"})
      .then(function(){showSt(lang==="ar"?"تم الإلغاء":"Cancelled","ok");loadData("all");})
      .catch(function(e){showSt("Error: "+e.message,"err");});
  };
  window.doPending=function(id){
    if(!confirm((lang==="ar"?"إرجاع إلى قيد المراجعة: ":"Revert to pending: ")+id+"?"))return;
    api("/api/admin/pending/"+encodeURIComponent(id),{method:"POST"})
      .then(function(){showSt(lang==="ar"?"تم الإرجاع":"Reverted","ok");loadData("all");})
      .catch(function(e){showSt("Error: "+e.message,"err");});
  };

  // ───── edit booking overlay ─────
  window.openEditBk=function(reqId){
    var rec=null;
    for(var i=0;i<allData.length;i++)if(allData[i].reqId===reqId){rec=allData[i];break;}
    if(!rec)return;
    document.getElementById("bkReqId").value=rec.reqId;
    document.getElementById("bkName").value=rec.name||"";
    document.getElementById("bkEmail").value=rec.email||"";
    document.getElementById("bkPhone").value=rec.phone||"";
    document.getElementById("bkBehalf").value=rec.behalf||"";
    document.getElementById("bkTitle").value=rec.title||"";
    document.getElementById("bkDate").value=rec.date||"";
    document.getElementById("bkEndDate").value=rec.endDate||rec.date||"";
    document.getElementById("bkStart").value=rec.startTime||"";
    document.getElementById("bkEnd").value=rec.endTime||"";
    document.getElementById("bkFullDay").checked=!!rec.fullDay;
    document.getElementById("bkNotes").value=rec.notes||"";
    var sel=document.getElementById("bkHall");sel.innerHTML="";
    for(var i=0;i<hallsCache.length;i++){
      var o=document.createElement("option");o.value=hallsCache[i].nameAr;o.textContent=lang==="ar"?hallsCache[i].nameAr:(hallsCache[i].nameEn||hallsCache[i].nameAr);
      if(hallsCache[i].nameAr===rec.hall)o.selected=true;sel.appendChild(o);
    }
    document.getElementById("editBkOverlay").classList.add("open");
  };
  window.closeEditBk=function(){document.getElementById("editBkOverlay").classList.remove("open");};
  window.saveEditBk=function(){
    var reqId=document.getElementById("bkReqId").value;
    var name=document.getElementById("bkName").value.trim();
    var email=document.getElementById("bkEmail").value.trim();
    var title=document.getElementById("bkTitle").value.trim();
    var hall=document.getElementById("bkHall").value;
    var date=document.getElementById("bkDate").value;
    var endDate=document.getElementById("bkEndDate").value||date;
    if(!name||!email||!title||!hall||!date){showSt(lang==="ar"?"يرجى تعبئة الحقول الإلزامية":"Please fill required fields","err");return;}
    if(!confirm(lang==="ar"?"حفظ التعديلات وإرسال إشعار؟":"Save changes and send notification?"))return;
    api("/api/admin/update/"+encodeURIComponent(reqId),{method:"POST",body:{
      name:name,email:email,phone:document.getElementById("bkPhone").value.trim(),
      behalf:document.getElementById("bkBehalf").value.trim(),title:title,hall:hall,
      date:date,endDate:endDate,startTime:document.getElementById("bkStart").value,
      endTime:document.getElementById("bkEnd").value,fullDay:document.getElementById("bkFullDay").checked,
      notes:document.getElementById("bkNotes").value.trim()
    }}).then(function(){showSt(lang==="ar"?"تم الحفظ":"Saved","ok");closeEditBk();loadData("all");})
      .catch(function(e){showSt("Error: "+e.message,"err");});
  };

  // ───── halls admin ─────
  function loadHallsAdmin(){
    api("/api/admin/halls").then(function(d){
      var c=document.getElementById("hallsList");
      if(!d.length){c.innerHTML=nodata("door-open",T("لا توجد قاعات","No venues"));return;}
      var cols=[{h:T("الاسم","Name"),filter:"text"},{h:T("الرمز","Code"),filter:"text"},{h:T("السعة","Capacity"),sort:"num"},
        {h:T("الموقع","Location"),filter:"text"},{h:T("الحالة","Status"),filter:"select"},{h:T("الحجوزات","Bookings"),sort:"num"},
        {h:T("إجراءات","Actions"),act:true}];
      var rows="";
      d.forEach(function(it){
        var st=it.active?T("فعالة","Active"):T("موقوفة","Inactive");
        rows+='<tr>'+chkCell(it.id)
          +'<td><strong><bdi>'+esc(it.nameAr)+'</bdi></strong>'+(it.nameEn?'<br><span class="sub-line" dir="ltr">'+esc(it.nameEn)+'</span>':'')
          +(it.requiresApproval?'<br><span class="multiday-tag">'+T("تتطلب موافقة","Needs approval")+'</span>':'')+'</td>'
          +'<td dir="ltr">'+esc(it.code||"")+'</td><td data-value="'+esc(it.capacity||0)+'">'+esc(it.capacity||"")+'</td>'
          +'<td><bdi>'+esc(it.location||"")+'</bdi></td>'
          +'<td data-value="'+esc(st)+'"><span class="st-tag '+(it.active?"approved":"cancelled")+'">'+st+'</span></td>'
          +'<td data-value="'+it.bookings+'">'+it.bookings+'</td>'
          +'<td class="act"><div class="tbl-actions"><button class="tbl-btn edit-bk" title="'+T("تعديل","Edit")+'" aria-label="'+T("تعديل","Edit")+'" onclick="openEdit('+it.id+')"><i class="fas fa-edit"></i></button>'
          +'<button class="tbl-btn cancel-btn" title="'+T("حذف","Delete")+'" aria-label="'+T("حذف","Delete")+'" onclick="delHall('+it.id+')"><i class="fas fa-trash"></i></button></div></td></tr>';
      });
      c.innerHTML=tableHtml("halls",cols,rows);
      mountTable(c,"halls",[{id:"activate",label:T("تفعيل","Activate")},{id:"deactivate",label:T("إيقاف","Deactivate")},
        {id:"delete",label:T("حذف","Delete"),danger:true}],function(action,ids){
          api("/api/admin/halls/bulk",{method:"POST",body:{action:action,ids:ids}}).then(function(r){bulkDone(r);loadHallsAdmin();loadBlkHalls();})
            .catch(function(e){showSt(e.message,"err");});
        });
    });
  }
  window.addNewHall=function(){
    var nAr=document.getElementById("hNameAr").value.trim();
    if(!nAr){showSt(lang==="ar"?"الرجاء إدخال الاسم":"Please enter name","err");return;}
    api("/api/admin/halls/add",{method:"POST",body:{
      nameAr:nAr,nameEn:document.getElementById("hNameEn").value.trim(),
      location:document.getElementById("hLocation").value.trim(),
      code:document.getElementById("hCode").value.trim(),
      capacity:document.getElementById("hCapacity").value.trim(),
      equipment:document.getElementById("hEquipment").value.trim(),
      description:document.getElementById("hDesc").value.trim(),
      notes:document.getElementById("hNotes").value.trim(),
      requiresApproval:document.getElementById("hApproval").checked,
      active:document.getElementById("hActive").checked
    }}).then(function(){showSt(lang==="ar"?"تمت الإضافة":"Added","ok");loadHallsAdmin();resetHallForm();loadBlkHalls();})
      .catch(function(e){showSt("Error: "+e.message,"err");});
  };
  window.resetHallForm=function(){
    ["hNameAr","hNameEn","hLocation","hCode","hCapacity","hEquipment","hDesc","hNotes"].forEach(function(id){document.getElementById(id).value="";});
    document.getElementById("hApproval").checked=false;document.getElementById("hActive").checked=true;
  };
  window.openEdit=function(id){
    api("/api/admin/halls").then(function(d){
      for(var i=0;i<d.length;i++){
        if(d[i].id===id){
          var it=d[i];
          document.getElementById("editRow").value=id;
          document.getElementById("eNameAr").value=it.nameAr||"";
          document.getElementById("eNameEn").value=it.nameEn||"";
          document.getElementById("eLocation").value=it.location||"";
          document.getElementById("eCode").value=it.code||"";
          document.getElementById("eCapacity").value=it.capacity||"";
          document.getElementById("eEquipment").value=it.equipment||"";
          document.getElementById("eDesc").value=it.description||"";
          document.getElementById("eNotes").value=it.notes||"";
          document.getElementById("eApproval").checked=!!it.requiresApproval;
          document.getElementById("eActive").checked=!!it.active;
          document.getElementById("editOverlay").classList.add("open");
          break;
        }
      }
    });
  };
  window.closeEdit=function(){document.getElementById("editOverlay").classList.remove("open");};
  window.saveEdit=function(){
    var data={
      id:parseInt(document.getElementById("editRow").value),
      nameAr:document.getElementById("eNameAr").value.trim(),
      nameEn:document.getElementById("eNameEn").value.trim(),
      location:document.getElementById("eLocation").value.trim(),
      code:document.getElementById("eCode").value.trim(),
      capacity:document.getElementById("eCapacity").value.trim(),
      equipment:document.getElementById("eEquipment").value.trim(),
      description:document.getElementById("eDesc").value.trim(),
      notes:document.getElementById("eNotes").value.trim(),
      requiresApproval:document.getElementById("eApproval").checked,
      active:document.getElementById("eActive").checked
    };
    if(!data.nameAr){showSt(lang==="ar"?"الرجاء إدخال الاسم":"Please enter name","err");return;}
    api("/api/admin/halls/update",{method:"POST",body:data}).then(function(){
      showSt(lang==="ar"?"تم التعديل":"Updated","ok");closeEdit();loadHallsAdmin();loadBlkHalls();
    }).catch(function(e){showSt("Error: "+e.message,"err");});
  };
  window.delHall=function(id){
    if(!confirm(lang==="ar"?"حذف هذه القاعة؟":"Delete this venue?"))return;
    api("/api/admin/halls/delete/"+id,{method:"POST"}).then(function(){loadHallsAdmin();loadBlkHalls();})
      .catch(function(e){showSt("Error: "+e.message,"err");});
  };

  // ───── blocked periods ─────
  function loadBlk(){
    api("/api/admin/blocked").then(function(d){
      var c=document.getElementById("blkList");
      if(!d.length){c.innerHTML=nodata("check-circle",T("لا توجد فترات غير متاحة","No unavailable periods"));return;}
      var cols=[{h:T("من","From"),filter:"text"},{h:T("إلى","To"),filter:"text"},{h:T("القاعة","Venue"),filter:"select"},
        {h:T("الوقت","Time"),filter:"text"},{h:T("السبب","Reason"),filter:"text"},{h:T("إجراءات","Actions"),act:true}];
      var rows="";
      d.forEach(function(it){
        var hall=it.hall||T("كل القاعات","All venues");
        rows+='<tr>'+chkCell(it.id)+'<td'+isoVal(it.start)+' dir="ltr">'+fmtD(it.start)+'</td><td'+isoVal(it.end)+' dir="ltr">'+fmtD(it.end)+'</td>'
          +'<td data-value="'+esc(hall)+'"><bdi>'+esc(hall)+'</bdi></td>'
          +'<td>'+(it.fromT&&it.toT?'<span dir="ltr">'+esc(it.fromT)+' – '+esc(it.toT)+'</span>':T("يوم كامل","Full day"))+'</td>'
          +'<td><bdi>'+esc(it.reason)+'</bdi></td>'
          +'<td class="act"><div class="tbl-actions"><button class="tbl-btn cancel-btn" title="'+T("حذف","Delete")+'" aria-label="'+T("حذف","Delete")+'" onclick="delBlk('+it.id+')"><i class="fas fa-trash"></i></button></div></td></tr>';
      });
      c.innerHTML=tableHtml("blk",cols,rows);
      mountTable(c,"blk",[{id:"delete",label:T("حذف","Delete"),danger:true}],function(action,ids){
        api("/api/admin/blocked/bulk",{method:"POST",body:{ids:ids}}).then(function(r){bulkDone(r);loadBlk();})
          .catch(function(e){showSt(e.message,"err");});
      });
    });
  }
  window.addBlk=function(){
    var s=document.getElementById("blkStart").value,e=document.getElementById("blkEnd").value,
        hall=document.getElementById("blkHall").value,fromT=document.getElementById("blkFromT").value,
        toT=document.getElementById("blkToT").value,r=document.getElementById("blkReason").value.trim();
    if(!s||!e){showSt(lang==="ar"?"الرجاء تحديد التواريخ":"Please select dates","err");return;}
    if(!r){showSt(lang==="ar"?"الرجاء إدخال السبب":"Please enter reason","err");return;}
    if((fromT&&!toT)||(toT&&!fromT)){showSt(lang==="ar"?"الرجاء تحديد وقت البداية والنهاية معاً":"Please specify both start and end times","err");return;}
    api("/api/admin/blocked/add",{method:"POST",body:{start:s,end:e,hall:hall,fromT:fromT,toT:toT,reason:r}})
      .then(function(){
        showSt(lang==="ar"?"تمت الإضافة":"Added","ok");loadBlk();
        ["blkStart","blkEnd","blkFromT","blkToT","blkReason"].forEach(function(id){document.getElementById(id).value="";});
        document.getElementById("blkHall").value="";
      }).catch(function(e){showSt("Error: "+e.message,"err");});
  };
  window.delBlk=function(id){
    if(!confirm(lang==="ar"?"حذف؟":"Delete?"))return;
    api("/api/admin/blocked/delete/"+id,{method:"POST"}).then(function(){loadBlk();})
      .catch(function(e){showSt("Error: "+e.message,"err");});
  };

  // ───── contacts ─────
  function loadContacts(){
    api("/api/admin/contacts").then(function(d){
      var c=document.getElementById("contactsList");
      if(!d.length){c.innerHTML=nodata("address-book",T("لا توجد جهات اتصال بعد","No contacts yet"));return;}
      var cols=[{h:T("البريد الإلكتروني","Email"),filter:"text"},{h:T("الاسم","Name"),filter:"text"},{h:T("تاريخ الإضافة","Added"),filter:"text"},{h:T("إجراءات","Actions"),act:true}];
      var rows="";
      d.forEach(function(it){
        rows+='<tr>'+chkCell(it.id)+'<td dir="ltr">'+esc(it.email)+'</td><td><bdi>'+esc(it.name)+'</bdi></td><td dir="ltr" data-value="'+esc(it.addedAt)+'">'+esc(it.addedAt)+'</td>'
          +'<td class="act"><div class="tbl-actions"><button class="tbl-btn edit-bk" title="'+T("تعديل","Edit")+'" aria-label="'+T("تعديل","Edit")+'" onclick="editContact('+it.id+',\''+esc(it.email).replace(/'/g,"")+'\',\''+esc(it.name).replace(/'/g,"")+'\')"><i class="fas fa-edit"></i></button>'
          +'<button class="tbl-btn cancel-btn" title="'+T("حذف","Delete")+'" aria-label="'+T("حذف","Delete")+'" onclick="delContact('+it.id+')"><i class="fas fa-trash"></i></button></div></td></tr>';
      });
      c.innerHTML=tableHtml("ct",cols,rows);
      mountTable(c,"ct",[{id:"delete",label:T("حذف","Delete"),danger:true}],function(action,ids){
        api("/api/admin/contacts/bulk",{method:"POST",body:{ids:ids}}).then(function(r){bulkDone(r);loadContacts();})
          .catch(function(e){showSt(e.message,"err");});
      });
    });
  }
  window.editContact=function(id,email,name){
    var e=prompt(T("البريد الإلكتروني:","Email:"),email);if(e===null)return;
    var n=prompt(T("الاسم:","Name:"),name);if(n===null)return;
    api("/api/admin/contacts/update",{method:"POST",body:{id:id,email:e.trim(),name:n.trim()}}).then(function(){showSt(T("تم الحفظ","Saved"),"ok");loadContacts();})
      .catch(function(er){showSt(er.message,"err");});
  };
  window.addSingleContact=function(){
    var em=document.getElementById("ctEmail").value.trim();
    var nm=document.getElementById("ctName").value.trim();
    if(!em||em.indexOf("@")<0||em.indexOf("@")>=em.length-1){showSt(lang==="ar"?"الرجاء إدخال بريد إلكتروني صحيح":"Please enter valid email","err");return;}
    api("/api/admin/contacts/add",{method:"POST",body:{list:[{email:em,name:nm}]}})
      .then(function(r){
        showSt((lang==="ar"?"تمت إضافة ":"Added ")+(r.count||1)+(lang==="ar"?" جهة اتصال":" contact(s)"),"ok");
        document.getElementById("ctEmail").value="";document.getElementById("ctName").value="";loadContacts();
      }).catch(function(e){showSt("Error: "+e.message,"err");});
  };
  window.delContact=function(id){
    if(!confirm(lang==="ar"?"حذف؟":"Delete?"))return;
    api("/api/admin/contacts/delete/"+id,{method:"POST"}).then(function(){loadContacts();});
  };
  function onContactFile(e){
    var file=e.target.files[0];if(!file)return;
    var reader=new FileReader();
    reader.onload=function(ev){
      var text=ev.target.result;
      var lines=text.split(/[\r\n]+/).filter(function(l){return l.trim();});
      var list=[];
      for(var i=0;i<lines.length;i++){
        var parts=lines[i].split(",");var email=parts[0].trim();
        if(email&&email.indexOf("@")>=0&&email.indexOf("@")<email.length-1)list.push({email:email,name:(parts[1]||"").trim()});
      }
      if(!list.length){showSt(lang==="ar"?"لم يتم العثور على عناوين بريد صالحة":"No valid emails found","err");return;}
      api("/api/admin/contacts/add",{method:"POST",body:{list:list}})
        .then(function(r){showSt((lang==="ar"?"تمت إضافة ":"Added ")+(r.count||0)+(lang==="ar"?" جهة اتصال":" contact(s)"),"ok");loadContacts();})
        .catch(function(err){showSt("Error: "+err.message,"err");});
    };
    reader.readAsText(file);e.target.value="";
  }

  // ───── reports / stats ─────
  function loadStats(){
    api("/api/admin/stats").then(function(s){
      setT("sToday",s.today);setT("sWeek",s.week);
      renderTopChart(s.byHall);renderPeriodStats(s);renderDetailTable(s.byMonth);
    }).catch(function(){});
  }
  function renderTopChart(data){
    var c=document.getElementById("chartTop");
    if(!data||!data.length){c.innerHTML='<div class="nodata" style="padding:10px;font-size:13px">'+(lang==="ar"?"لا توجد بيانات":"No data")+'</div>';return;}
    var mx=data[0].count;var h="";
    for(var i=0;i<Math.min(data.length,8);i++){
      var pct=mx>0?Math.round(data[i].count/mx*100):0;
      h+='<div class="bar-item"><div class="bar-label">'+esc(data[i].hall)+'</div><div class="bar-track"><div class="bar-fill" style="width:'+pct+'%"><span>'+data[i].count+'</span></div></div></div>';
    }
    c.innerHTML=h;
  }
  function renderPeriodStats(s){
    var c=document.getElementById("periodStats");
    var h='<table class="period-table"><thead><tr><th>'+(lang==="ar"?"الفترة":"Period")+'</th><th>'+(lang==="ar"?"المعتمدة":"Approved")+'</th><th>'+(lang==="ar"?"الكل":"Total")+'</th></tr></thead><tbody>'
      +'<tr><td>'+(lang==="ar"?"اليوم":"Today")+'</td><td style="font-weight:700;color:#1e8449">'+s.today+'</td><td>'+s.total+'</td></tr>'
      +'<tr><td>'+(lang==="ar"?"هذا الأسبوع":"This Week")+'</td><td style="font-weight:700;color:#1e8449">'+s.week+'</td><td>'+s.total+'</td></tr>'
      +'<tr><td>'+(lang==="ar"?"المعلّقة":"Pending")+'</td><td style="font-weight:700;color:#EBB37B">'+s.pending+'</td><td>'+s.total+'</td></tr>'
      +'</tbody></table>';
    c.innerHTML=h;
  }
  function renderDetailTable(byMonth){
    var c=document.getElementById("detailTable");
    if(!byMonth||Object.keys(byMonth).length===0){c.innerHTML='<div class="nodata" style="padding:15px">'+(lang==="ar"?"لا توجد بيانات":"No data")+'</div>';return;}
    var months=Object.keys(byMonth).sort().reverse();
    var hallSet={};
    for(var m=0;m<months.length;m++){var halls=Object.keys(byMonth[months[m]]);for(var hh=0;hh<halls.length;hh++)hallSet[halls[hh]]=true;}
    var hallNames=Object.keys(hallSet);
    var h='<table><thead><tr><th>'+(lang==="ar"?"الشهر":"Month")+'</th>';
    for(var i=0;i<hallNames.length;i++)h+='<th>'+esc(hallNames[i])+'</th>';
    h+='<th>'+(lang==="ar"?"المجموع":"Total")+'</th></tr></thead><tbody>';
    for(var m=0;m<months.length;m++){
      h+='<tr><td style="font-weight:700">'+esc(months[m])+'</td>';
      var rowTotal=0;
      for(var i=0;i<hallNames.length;i++){var v=byMonth[months[m]][hallNames[i]]||0;rowTotal+=v;h+='<td style="text-align:center;font-weight:600">'+v+'</td>';}
      h+='<td style="text-align:center;font-weight:800;color:#247680">'+rowTotal+'</td></tr>';
    }
    h+='</tbody></table>';c.innerHTML=h;
  }

  // ───── Data Explorer ─────
  window.runExplorer=function(){
    var dim=document.getElementById("anaDim").value;
    var st=document.getElementById("anaStatus").value;
    var fromD=document.getElementById("anaFrom").value;
    var toD=document.getElementById("anaTo").value;
    var data=allData.filter(function(r){
      if(st!=="all"&&r.status!==st)return false;
      if(fromD&&r.date<fromD)return false;
      if(toD&&r.date>toD)return false;
      return true;
    });
    var groups={};
    for(var i=0;i<data.length;i++){
      var key="";
      if(dim==="hall")key=data[i].hall||"غير محدد";
      else if(dim==="person")key=data[i].name||"غير محدد";
      else if(dim==="month")key=(data[i].date||"").substring(0,7);
      else if(dim==="dow"){var dt=new Date(data[i].date+"T00:00:00");var days=lang==="ar"?["الأحد","الاثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت"]:["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];key=days[dt.getDay()];}
      if(!key||key==="TaNaN")continue;
      if(!groups[key])groups[key]={count:0,approved:0,pending:0,hours:0};
      groups[key].count++;
      if(data[i].status==="approved")groups[key].approved++;
      if(data[i].status==="pending")groups[key].pending++;
      if(data[i].fullDay){groups[key].hours+=8;}
      else{var s=data[i].startTime||"09:00",e=data[i].endTime||"17:00";groups[key].hours+=calcH(s,e);}
    }
    var arr=[];for(var k in groups)arr.push({key:k,data:groups[k]});
    if(dim==="month")arr.sort(function(a,b){return a.key>b.key?1:-1;});
    else arr.sort(function(a,b){return b.data.count-a.data.count;});
    var c=document.getElementById("anaChart");
    if(!arr.length){c.innerHTML='<div class="nodata">'+(lang==="ar"?"لا توجد بيانات للتحليل":"No data to analyze")+'</div>';document.getElementById("anaTable").innerHTML="";return;}
    var mx=arr[0].data.count;var h="";
    for(var i=0;i<Math.min(arr.length,12);i++){
      var pct=mx>0?Math.round(arr[i].data.count/mx*100):0;
      h+='<div class="bar-item"><div class="bar-label" title="'+esc(arr[i].key)+'">'+esc(arr[i].key)+'</div><div class="bar-track"><div class="bar-fill" style="width:'+pct+'%"><span>'+arr[i].data.count+'</span></div></div></div>';
    }
    c.innerHTML=h;
    var th='<table class="period-table"><thead><tr><th>'+(lang==="ar"?"العنصر":"Item")+'</th><th>'+(lang==="ar"?"عدد الحجوزات":"Bookings")+'</th><th>'+(lang==="ar"?"معتمدة":"Approved")+'</th><th>'+(lang==="ar"?"قيد المراجعة":"Pending")+'</th><th>'+(lang==="ar"?"الساعات (تقريباً)":"Est. Hours")+'</th></tr></thead><tbody>';
    for(var i=0;i<arr.length;i++){
      th+='<tr><td style="font-weight:700">'+esc(arr[i].key)+'</td><td>'+arr[i].data.count+'</td><td style="color:#1e8449">'+arr[i].data.approved+'</td><td style="color:#EBB37B">'+arr[i].data.pending+'</td><td>'+arr[i].data.hours.toFixed(1)+'</td></tr>';
    }
    th+='</tbody></table>';document.getElementById("anaTable").innerHTML=th;
  };
  function calcH(s,e){if(!s||!e)return 0;var sp=s.split(":"),ep=e.split(":");if(sp.length<2||ep.length<2)return 0;var m1=parseInt(sp[0])*60+parseInt(sp[1]),m2=parseInt(ep[0])*60+parseInt(ep[1]);return Math.max(0,(m2-m1)/60);}

  // ───── PDF export ─────
  window.exportPDF=function(){
    var rc=document.getElementById("tc-reports").innerHTML;
    var orgName=lang==="ar"?ORG_AR:ORG_EN;
    var w=window.open("","_blank");
    var dt=ammanNow().slice(0,10);
    w.document.write("<html dir='"+dir+"' lang='"+lang+"'><head><title>"+(lang==="ar"?"تقرير الحجوزات":"Booking Report")+"</title><link href='https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap' rel='stylesheet'><style>body{font-family:Tajawal,sans-serif;padding:40px;max-width:800px;margin:0 auto;background:#fff;color:#333} .report-header{text-align:center;margin-bottom:40px;padding-bottom:25px;border-bottom:4px solid #EBB37B} .report-header img{height:90px;margin-bottom:20px} .report-header h1{color:#1a5c64;font-size:32px;margin:0;font-weight:800} .report-header h1 span{color:#EBB37B} .report-header p{color:#555;font-size:16px;margin:10px 0 0} table{width:100%;border-collapse:collapse;margin-top:20px} th,td{border:1px solid #ddd;padding:12px;text-align:"+(dir==="rtl"?"right":"left")+";font-size:13px} th{background:#1a5c64;color:#fff;font-weight:700} tr:nth-child(even){background:#f8f9fa} .bar-chart{display:flex;flex-direction:column;gap:8px} .bar-item{display:flex;align-items:center;margin-bottom:10px} .bar-label{font-size:13px;font-weight:600;color:#1a5c64;min-width:140px} .bar-track{flex:1;height:28px;background:#e8eaed;border-radius:8px;overflow:hidden} .bar-fill{height:100%;background:linear-gradient(90deg,#1a5c64,#247680);border-radius:8px;display:flex;align-items:center;justify-content:flex-end;padding:0 10px} .bar-fill span{color:#fff;font-size:13px;font-weight:700} .report-card{margin-bottom:30px;page-break-inside:avoid;background:#fff;border:1px solid #e8eaed;border-radius:12px;padding:25px;box-shadow:0 2px 8px rgba(0,0,0,.05)} h4{color:#1a5c64;margin-bottom:15px;font-size:18px;border-bottom:2px solid #EBB37B;padding-bottom:10px;font-weight:800;display:flex;align-items:center;gap:8px} .period-table th,.period-table td{border:1px solid #ddd;padding:10px;font-size:13px} .period-table th{background:#e8f4f5;color:#1a5c64} .report-grid{display:grid;grid-template-columns:1fr 1fr;gap:25px;margin-bottom:30px} .nodata{text-align:center;padding:20px;color:#aaa;font-size:14px} @media print{body{padding:20px} .report-card{box-shadow:none;border:1px solid #ddd}} button{display:none}</style></head><body><div class='report-header'><img src='"+LOGO_URL+"' alt='Logo'><h1>"+orgName+" <span>| "+(lang==="ar"?"تقرير الحجوزات":"Booking Report")+"</span></h1><p>"+dt+"</p></div>"+rc+"</body></html>");
    w.document.close();w.focus();setTimeout(function(){w.print();},600);
  };

  // ───── language toggle (in-place, no reload) ─────
  window.toggleLang=function(){
    lang=lang==="ar"?"en":"ar";
    dir=lang==="ar"?"rtl":"ltr";
    document.documentElement.lang=lang;document.documentElement.dir=dir;
    setH("btnLang",'<i class="fas fa-globe"></i> <span>'+(lang==="ar"?"EN":"عربي")+'</span>');
    setT("hdrTitle",lang==="ar"?ORG_AR:ORG_EN);
    setT("hdrSub",lang==="ar"?"لوحة التحكم — نظام الحجز":"Admin Panel — Booking System");
    setT("tCal",lang==="ar"?"الروزنامة":"Calendar");
    setT("tNew",lang==="ar"?"حجز جديد":"New Booking");
    setT("tLogout",lang==="ar"?"خروج":"Logout");
    setHref("linkCal","/?lang="+lang);
    setHref("linkBook","/book?lang="+lang);
    setT("slAll",lang==="ar"?"الكل":"Total");setT("slPend",lang==="ar"?"قيد المراجعة":"Pending");
    setT("slApp",lang==="ar"?"معتمد":"Approved");setT("slRej",lang==="ar"?"مرفوض":"Rejected");
    setT("slToday",lang==="ar"?"اليوم":"Today");setT("slWeek",lang==="ar"?"هذا الأسبوع":"This Week");
    setT("ttBook",lang==="ar"?"طلبات الحجز":"Bookings");setT("ttHalls",lang==="ar"?"القاعات":"Venues");
    setT("ttBlocked",lang==="ar"?"غير متاح":"Unavailable");setT("ttContacts",lang==="ar"?"جهات الإتصال":"Contacts");
    setT("ttReports",lang==="ar"?"التقارير":"Reports");
    setT("fAll",lang==="ar"?"الكل":"All");setT("fPend",lang==="ar"?"قيد المراجعة":"Pending");
    setT("fAppr",lang==="ar"?"معتمد":"Approved");setT("fRej",lang==="ar"?"مرفوض":"Rejected");
    setT("fCancel",lang==="ar"?"ملغي":"Cancelled");
    setT("addHallTitle",lang==="ar"?"إضافة قاعة جديدة":"Add New Venue");
    setT("lblNameAr",lang==="ar"?"الاسم (عربي)  *":"Name (Arabic)  *");
    setT("lblNameEn",lang==="ar"?"الاسم (إنجليزي)":"Name (English)");
    setT("lblLocation",lang==="ar"?"الموقع":"Location");setT("lblCode",lang==="ar"?"الرمز":"Code");
    setT("lblCapacity",lang==="ar"?"السعة":"Capacity");
    setT("lblEquipment",lang==="ar"?"المعدات والمرافق":"Equipment & Facilities");
    setT("lblDesc",lang==="ar"?"الوصف":"Description");setT("lblNotes",lang==="ar"?"ملاحظات":"Notes");
    setT("lblApproval",lang==="ar"?"تتطلب موافقة مسبقة":"Requires Prior Approval");
    setT("lblActive",lang==="ar"?"قاعة فعالة":"Active Venue");
    setH("btnAddHall",'<i class="fas fa-plus"></i> '+(lang==="ar"?"إضافة":"Add"));
    setH("btnResetHall",'<i class="fas fa-times"></i> '+(lang==="ar"?"إلغاء":"Cancel"));
    setT("blkTitle",lang==="ar"?"الفترات غير المتاحة":"Unavailable Periods");
    setH("btnAddBlk",'<i class="fas fa-plus"></i> '+(lang==="ar"?"إضافة":"Add"));
    setT("secAddContact",lang==="ar"?"إضافة جهة اتصال فردية":"Add Individual Contact");
    setT("secUploadContact",lang==="ar"?"رفع قائمة جهات اتصال":"Upload Contacts List");
    setT("lblCtName",lang==="ar"?"الاسم (اختياري)":"Name (optional)");
    setH("lblCtEmail",(lang==="ar"?"البريد الإلكتروني  ":"Email  ")+'<span class="req">*</span>');
    setT("ctAreaTxt",lang==="ar"?"اضغط لاختيار ملف CSV أو TXT":"Click to select CSV or TXT file");
    setT("btnPdfTxt",lang==="ar"?"طباعة / تصدير PDF":"Print / Export PDF");
    setT("rptTop",lang==="ar"?"أكثر القاعات حجزاً":"Most Booked Venues");
    setT("rptPeriod",lang==="ar"?"حجوزات حسب الفترة":"Bookings by Period");
    setT("rptDetail",lang==="ar"?"تفصيل الحجوزات لكل قاعة حسب الشهر":"Detailed Bookings per Venue by Month");
    setT("rptExplorer",lang==="ar"?"مستكشف البيانات والمقارنات":"Data Explorer & Comparisons");
    setT("lblAnaDim",lang==="ar"?"تجميع البيانات ومقارنة حسب":"Group & Compare By");
    var anaDim=document.getElementById("anaDim");
    if(anaDim){
      anaDim.options[0].text=lang==="ar"?"القاعات (قاعة مقابل قاعة)":"Venues (Hall vs Hall)";
      anaDim.options[1].text=lang==="ar"?"الأشخاص (نشاط الحاجزين)":"People (Booker Activity)";
      anaDim.options[2].text=lang==="ar"?"الأشهر (فترة مقابل فترة)":"Months (Period vs Period)";
      anaDim.options[3].text=lang==="ar"?"أيام الأسبوع (أوقات الذروة)":"Days of Week (Peak Times)";
    }
    setT("lblAnaStatus",lang==="ar"?"حالة الحجوزات":"Booking Status");
    var anaSt=document.getElementById("anaStatus");
    if(anaSt){
      anaSt.options[0].text=lang==="ar"?"الكل":"All";
      anaSt.options[1].text=lang==="ar"?"المعتمدة فقط":"Approved Only";
      anaSt.options[2].text=lang==="ar"?"قيد المراجعة فقط":"Pending Only";
    }
    setT("lblAnaFrom",lang==="ar"?"من تاريخ":"Date From");setT("lblAnaTo",lang==="ar"?"إلى تاريخ":"Date To");
    setH("btnAnaRun",'<i class="fas fa-chart-bar"></i> '+(lang==="ar"?"تحليل البيانات ومقارنة":"Analyze & Compare"));
    setT("rptAnaTitle",lang==="ar"?"نتائج التحليل والمقارنة":"Analysis & Comparison Results");
    loadData("all");loadHallsAdmin();loadBlk();loadContacts();loadStats();loadBlkHalls();updateClock();
  };
  function setH(id,h){var el=document.getElementById(id);if(el)el.innerHTML=h;}
  function setHref(id,href){var el=document.getElementById(id);if(el)el.setAttribute("href",href);}

  // ───── المستخدمون ─────
  function loadUsers(){
    api("/api/admin/users").then(function(d){
      var c=document.getElementById("usersList");if(!c)return;
      var cols=[{h:T("اسم المستخدم","Username"),filter:"text"},{h:T("الاسم","Name"),filter:"text"},{h:T("البريد","Email"),filter:"text"},
        {h:T("الحالة","Status"),filter:"select"},{h:T("آخر دخول","Last sign-in"),filter:"text"},{h:T("إجراءات","Actions"),act:true}];
      var rows="";
      d.forEach(function(u){
        var st=u.active?T("فعال","Active"):T("موقوف","Disabled");
        rows+='<tr>'+chkCell(u.id)+'<td dir="ltr">'+esc(u.username)+(u.me?' <span class="multiday-tag">'+T("حسابك","You")+'</span>':'')+'</td>'
          +'<td><bdi>'+esc(u.name)+'</bdi></td><td dir="ltr">'+esc(u.email)+'</td>'
          +'<td data-value="'+esc(st)+'"><span class="st-tag '+(u.active?"approved":"cancelled")+'">'+st+'</span></td>'
          +'<td dir="ltr" data-value="'+esc(u.lastLogin)+'">'+esc(u.lastLogin)+'</td>'
          +'<td class="act"><div class="tbl-actions"><button class="tbl-btn edit-bk" title="'+T("تعديل","Edit")+'" aria-label="'+T("تعديل","Edit")+'" onclick=\'openUser('+JSON.stringify(u).replace(/'/g,"&#39;")+')\'><i class="fas fa-edit"></i></button>'
          +'<button class="tbl-btn cancel-btn" title="'+T("حذف","Delete")+'" aria-label="'+T("حذف","Delete")+'" onclick="delUser('+u.id+')"><i class="fas fa-trash"></i></button></div></td></tr>';
      });
      c.innerHTML=tableHtml("users",cols,rows);
      mountTable(c,"users",[{id:"activate",label:T("تفعيل","Activate")},{id:"deactivate",label:T("إيقاف","Deactivate")},
        {id:"delete",label:T("حذف","Delete"),danger:true}],function(action,ids){
          api("/api/admin/users/bulk",{method:"POST",body:{action:action,ids:ids}}).then(function(r){bulkDone(r);loadUsers();})
            .catch(function(e){showSt(e.message,"err");});
        });
    }).catch(function(){});
  }
  window.openUser=function(u){
    u=u||{};
    document.getElementById("uId").value=u.id||"";
    document.getElementById("uName").value=u.username||"";
    document.getElementById("uFull").value=u.name||"";
    document.getElementById("uEmail").value=u.email||"";
    document.getElementById("uPass").value="";
    document.getElementById("uActive").checked=u.id?!!u.active:true;
    document.getElementById("uTitle").textContent=u.id?T("تعديل مستخدم","Edit user"):T("إضافة مستخدم","Add user");
    document.getElementById("editUserOverlay").classList.add("open");
  };
  window.closeUser=function(){document.getElementById("editUserOverlay").classList.remove("open");};
  window.saveUser=function(){
    var id=document.getElementById("uId").value;
    var body={username:document.getElementById("uName").value.trim(),name:document.getElementById("uFull").value.trim(),
      email:document.getElementById("uEmail").value.trim(),password:document.getElementById("uPass").value,
      active:document.getElementById("uActive").checked};
    if(id)body.id=parseInt(id,10);
    api(id?"/api/admin/users/update":"/api/admin/users/add",{method:"POST",body:body}).then(function(){
      showSt(T("تم الحفظ","Saved"),"ok");closeUser();loadUsers();
    }).catch(function(e){showSt(e.message,"err");});
  };
  window.delUser=function(id){
    if(!confirm(T("حذف هذا المستخدم؟","Delete this user?")))return;
    api("/api/admin/users/delete/"+id,{method:"POST"}).then(function(){loadUsers();}).catch(function(e){showSt(e.message,"err");});
  };

  // ───── الإعدادات والهوية ─────
  function loadSettings(){
    api("/api/admin/settings").then(function(s){
      var set=function(id,v){var el=document.getElementById(id);if(el)el.value=v;};
      set("sOrgAr",s.orgAr);set("sOrgEn",s.orgEn);set("sAccent",s.accent);
      var img=document.getElementById("sLogoImg");if(img&&s.logo){img.src=s.logo;img.style.display="";}else if(img){img.style.display="none";}
      var m=document.getElementById("sMail");
      if(m)m.textContent=s.mail?T("البريد الإلكتروني مُفعَّل (المرسل: ","Email is on (sender: ")+s.sender+")":T("البريد الإلكتروني غير مُعدّ: لا تُرسل رسائل الحجز.","Email is not set up: booking messages are not sent.");
    }).catch(function(){});
  }
  window.saveSettings=function(){
    api("/api/admin/settings",{method:"POST",body:{orgAr:document.getElementById("sOrgAr").value,orgEn:document.getElementById("sOrgEn").value,
      accent:document.getElementById("sAccent").value}}).then(function(){showSt(T("تم الحفظ، حدّث الصفحة لرؤية الهوية الجديدة","Saved - refresh the page to see the new identity"),"ok");})
      .catch(function(e){showSt(e.message,"err");});
  };
  window.uploadLogo=function(inp){
    if(!inp.files||!inp.files[0])return;
    var fd=new FormData();fd.append("file",inp.files[0]);
    api("/api/admin/logo",{method:"POST",body:fd}).then(function(){showSt(T("تم رفع الشعار","Logo uploaded"),"ok");loadSettings();})
      .catch(function(e){showSt(e.message,"err");});
    inp.value="";
  };
  window.removeLogo=function(){
    if(!confirm(T("إزالة الشعار؟ تظهر أيقونة النظام بدلاً منه.","Remove the logo? The system icon is shown instead.")))return;
    api("/api/admin/logo/delete",{method:"POST"}).then(function(){showSt(T("تمت الإزالة","Removed"),"ok");loadSettings();});
  };
  window.changePassword=function(){
    var cur=document.getElementById("pwCur").value,nw=document.getElementById("pwNew").value,rp=document.getElementById("pwRep").value;
    if(nw!==rp){showSt(T("كلمتا المرور الجديدتان غير متطابقتين","The new passwords do not match"),"err");return;}
    api("/api/admin/password",{method:"POST",body:{current:cur,new:nw}}).then(function(r){
      window.CSRF=r.csrf||window.CSRF;showSt(T("تم تغيير كلمة المرور","Password changed"),"ok");
      ["pwCur","pwNew","pwRep"].forEach(function(id){document.getElementById(id).value="";});
    }).catch(function(e){showSt(e.message,"err");});
  };

})();
