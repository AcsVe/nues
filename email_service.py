import requests
from config import Config
from datetime import datetime

def _sanitize_email(e):
    if not e: return ''
    return ''.join(ch for ch in str(e) if ord(ch) > 32 and ch not in '\u200b\u200c\u200d\ufeff\xa0').strip()


def send_brevo_email(to_email, subject, html_body, bcc_list=None):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": Config.BREVO_API_KEY,
        "Content-Type": "application/json"
    }
    to_email = _sanitize_email(to_email)
    payload = {
        "sender": {"name": Config.SENDER_NAME, "email": Config.SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body
    }

    # Dedupe BCC, skip primary
    seen = {to_email.lower()}
    clean_bcc = []
    for b in (bcc_list or []):
        bc = _sanitize_email(b).lower()
        if not bc or '@' not in bc or bc in seen: continue
        seen.add(bc); clean_bcc.append(bc)

    try:
        if to_email and '@' in to_email:
            requests.post(url, json=payload, headers=headers, timeout=15)
        for bcc_email in clean_bcc:
            bcc_payload = dict(payload)
            bcc_payload["to"] = [{"email": bcc_email}]
            requests.post(url, json=bcc_payload, headers=headers, timeout=15)
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

def generate_email_template(inner_content):
    yr = datetime.now().year
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background-color:#EAEAEA;">
      <center style="width:100%;background-color:#EAEAEA;">
        <table role="presentation" width="600" border="0" cellpadding="0" cellspacing="0" style="max-width:600px;border-collapse:collapse;">
          <tr><td align="center" bgcolor="#1a5c64" style="background-color:#1a5c64;padding:25px;">
            <img src="{Config.LOGO_URL}" width="80" height="80" style="display:block;" alt="Logo">
          </td></tr>
          <tr><td align="center" bgcolor="#1a5c64" style="background-color:#1a5c64;padding:10px 25px 30px;">
            <font face="Tahoma,Arial,sans-serif" color="#EBB37B" style="font-size:22px;font-weight:bold;">{Config.ORG_AR}</font><br>
            <font face="Tahoma,Arial,sans-serif" color="#ffffff" style="font-size:12px;">نظام حجز القاعات والمرافق</font>
          </td></tr>
          <tr><td bgcolor="#ffffff" dir="rtl" style="background-color:#ffffff;padding:30px 25px;font-family:Tahoma,Arial,sans-serif;color:#333;font-size:14px;line-height:1.7;">
            {inner_content}
          </td></tr>
          <tr><td align="center" bgcolor="#1a5c64" style="background-color:#1a5c64;padding:18px 25px;">
            <font face="Tahoma,Arial,sans-serif" color="#EBB37B" style="font-size:11px;">&copy; {yr} {Config.ORG_AR} — جميع الحقوق محفوظة</font>
          </td></tr>
        </table>
      </center>
    </body>
    </html>
    """

def fmt_date(ds):
    if not ds: return ds
    p = ds.split("-")
    if len(p) == 3: return f"{p[2]}/{p[1]}/{p[0]}"
    return ds

# ── قوالب الإيميلات ──

def send_confirm_email(d, bcc_list=None):
    inner = f"""
    <div style="text-align:center;margin-bottom:20px;background:#EBB37B;color:#333;padding:8px 25px;display:inline-block;font-weight:bold;">⏳ تم استلام طلبك</div><br>
    <font face="Tahoma,Arial,sans-serif">مرحباً <strong>{d['name']}</strong>،<br>تم استلام طلب حجزك بنجاح وهو حالياً <strong style="color:#EBB37B;">قيد المراجعة</strong>.</font><br><br>
    <table width="100%" border="0" cellpadding="0" cellspacing="0" dir="rtl" style="border-collapse:collapse;">
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>رقم الطلب:</strong></font> <font style="font-weight:bold;color:#247680;">{d['reqId']}</font></td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>المناسبة:</strong></font> {d['title']}</td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>القاعة:</strong></font> {d['hall']}</td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;"><font color="#888888" style="font-size:13px;"><strong>الوقت والتاريخ:</strong></font> {d['timeStr']} | {d['dateStr']}</td></tr>
    </table><br>
    <font face="Tahoma,Arial,sans-serif" style="font-size:12px;color:#888888;">سيتم إبلاغك بنتيجة المراجعة عبر البريد الإلكتروني.</font>
    """
    send_brevo_email(d['email'], f"استلام طلب حجز — {d['reqId']} | {Config.ORG_AR}", generate_email_template(inner), bcc_list)

def send_approve_email(d, bcc_list=None):
    inner = f"""
    <div style="text-align:center;margin-bottom:20px;background:#27ae60;color:#fff;padding:8px 25px;display:inline-block;font-weight:bold;">✔️ تمت الموافقة</div><br>
    <font face="Tahoma,Arial,sans-serif">مرحباً <strong>{d['name']}</strong>،<br>يسعدنا إبلاغك بأنه <strong style="color:#27ae60;">تمت الموافقة</strong> على طلب حجزك.</font><br><br>
    <table width="100%" border="0" cellpadding="0" cellspacing="0" dir="rtl" style="border-collapse:collapse;">
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>رقم الطلب:</strong></font> <font style="font-weight:bold;color:#27ae60;">{d['reqId']}</font></td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>المناسبة:</strong></font> {d['title']}</td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>القاعة:</strong></font> {d['hall']}</td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;"><font color="#888888" style="font-size:13px;"><strong>الوقت والتاريخ:</strong></font> {d['timeStr']} | {d['dateStr']}</td></tr>
    </table>
    """
    send_brevo_email(d['email'], f"موافقة على طلب حجز — {d['reqId']} | {Config.ORG_AR}", generate_email_template(inner), bcc_list)

def send_reject_email(d, bcc_list=None):
    inner = f"""
    <div style="text-align:center;margin-bottom:20px;background:#e74c3c;color:#fff;padding:8px 25px;display:inline-block;font-weight:bold;">❌ تم الرفض</div><br>
    <font face="Tahoma,Arial,sans-serif">مرحباً <strong>{d['name']}</strong>،<br>نأسف لإبلاغك بأنه <strong style="color:#e74c3c;">تم رفض</strong> طلب حجزك.</font><br><br>
    <div style="background:#fff5f5;padding:12px 20px;border:1px solid #ffcdd2;color:#e74c3c;margin-bottom:15px;"><strong>سبب الرفض:</strong> {d['reason']}</div>
    <table width="100%" border="0" cellpadding="0" cellspacing="0" dir="rtl" style="border-collapse:collapse;">
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>رقم الطلب:</strong></font> <font style="font-weight:bold;color:#e74c3c;">{d['reqId']}</font></td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;"><font color="#888888" style="font-size:13px;"><strong>المناسبة:</strong></font> {d['title']}</td></tr>
    </table><br>
    <font face="Tahoma,Arial,sans-serif" style="font-size:12px;color:#888888;">يمكنك تقديم طلب جديد في أي وقت.</font>
    """
    send_brevo_email(d['email'], f"رفض طلب حجز — {d['reqId']} | {Config.ORG_AR}", generate_email_template(inner), bcc_list)

def send_cancel_email(d, bcc_list=None):
    inner = f"""
    <div style="text-align:center;margin-bottom:20px;background:#95a5a6;color:#fff;padding:8px 25px;display:inline-block;font-weight:bold;">🗑️ تم الإلغاء</div><br>
    <font face="Tahoma,Arial,sans-serif">مرحباً <strong>{d['name']}</strong>،<br>تم <strong style="color:#95a5a6;">إلغاء حجزك</strong>.</font><br><br>
    <table width="100%" border="0" cellpadding="0" cellspacing="0" dir="rtl" style="border-collapse:collapse;">
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>رقم الطلب:</strong></font> <font style="font-weight:bold;color:#95a5a6;">{d['reqId']}</font></td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>المناسبة:</strong></font> {d['title']}</td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;"><font color="#888888" style="font-size:13px;"><strong>القاعة:</strong></font> {d['hall']}</td></tr>
    </table>
    """
    send_brevo_email(d['email'], f"إلغاء حجز — {d['reqId']} | {Config.ORG_AR}", generate_email_template(inner), bcc_list)


def send_pending_email(d, bcc_list=None):
    inner = f"""
    <div style="text-align:center;margin-bottom:20px;background:#EBB37B;color:#333;padding:8px 25px;display:inline-block;font-weight:bold;">⏳ حالة الطلب: قيد المراجعة</div><br>
    <font face="Tahoma,Arial,sans-serif">مرحباً <strong>{d['name']}</strong>،<br>تم إعادة طلب حجزك إلى حالة <strong style="color:#EBB37B;">قيد المراجعة</strong>.</font><br><br>
    <table width="100%" border="0" cellpadding="0" cellspacing="0" dir="rtl" style="border-collapse:collapse;">
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>رقم الطلب:</strong></font> <font style="font-weight:bold;color:#247680;">{d['reqId']}</font></td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>المناسبة:</strong></font> {d['title']}</td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>القاعة:</strong></font> {d['hall']}</td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;"><font color="#888888" style="font-size:13px;"><strong>الوقت والتاريخ:</strong></font> {d['timeStr']} | {d['dateStr']}</td></tr>
    </table>
    """
    send_brevo_email(d['email'], f"تحديث حالة الحجز — {d['reqId']} | {Config.ORG_AR}", generate_email_template(inner), bcc_list)


def send_update_email(d, bcc_list=None):
    inner = f"""
    <div style="text-align:center;margin-bottom:20px;background:#247680;color:#fff;padding:8px 25px;display:inline-block;font-weight:bold;">✏️ تم تحديث الحجز</div><br>
    <font face="Tahoma,Arial,sans-serif">مرحباً <strong>{d['name']}</strong>،<br>تم <strong style="color:#247680;">تعديل بيانات حجزك</strong>. تفاصيل الحجز المحدثة:</font><br><br>
    <table width="100%" border="0" cellpadding="0" cellspacing="0" dir="rtl" style="border-collapse:collapse;">
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>رقم الطلب:</strong></font> <font style="font-weight:bold;color:#247680;">{d['reqId']}</font></td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>المناسبة:</strong></font> {d['title']}</td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;border-bottom:1px solid #e0e0e0;"><font color="#888888" style="font-size:13px;"><strong>القاعة:</strong></font> {d['hall']}</td></tr>
      <tr><td style="background:#f0f7f7;padding:10px 20px;"><font color="#888888" style="font-size:13px;"><strong>الوقت والتاريخ:</strong></font> {d['timeStr']} | {d['dateStr']}</td></tr>
    </table>
    """
    send_brevo_email(d['email'], f"تحديث الحجز — {d['reqId']} | {Config.ORG_AR}", generate_email_template(inner), bcc_list)