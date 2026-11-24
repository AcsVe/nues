"""رسائل البريد: الإرسال عبر Microsoft 365 (Graph) بقيم MS_* في ملف .env، وكل نص يدخله المستخدم يُهرَّب قبل وضعه في الرسالة.

إن لم تُضبط القيم لا يتوقف النظام: يُسجَّل في السجل أن البريد لم يُرسل فقط.
"""
import time
from datetime import datetime
from html import escape

import requests
from flask import current_app

_token = {'value': None, 'expires': 0}


def _clean(e):
    if not e:
        return ''
    return ''.join(ch for ch in str(e) if ord(ch) > 32 and ch not in '​‌‍﻿\xa0').strip()


def _access_token():
    c = current_app.config
    if not (c.get('MS_TENANT_ID') and c.get('MS_CLIENT_ID') and c.get('MS_CLIENT_SECRET')):
        return None
    now = time.time()
    if _token['value'] and now < _token['expires'] - 60:
        return _token['value']
    try:
        r = requests.post(
            f"https://login.microsoftonline.com/{c['MS_TENANT_ID']}/oauth2/v2.0/token",
            data={'client_id': c['MS_CLIENT_ID'], 'client_secret': c['MS_CLIENT_SECRET'],
                  'scope': 'https://graph.microsoft.com/.default', 'grant_type': 'client_credentials'},
            timeout=15)
        if r.status_code != 200:
            print(f'[email] token request failed: HTTP {r.status_code}', flush=True)
            return None
        data = r.json()
        _token['value'] = data.get('access_token')
        _token['expires'] = now + int(data.get('expires_in', 3600))
        return _token['value']
    except Exception as e:  # noqa: BLE001
        print(f'[email] token request error: {type(e).__name__}', flush=True)
        return None


def send_email(to_email, subject, html_body, bcc_list=None):
    """يرسل رسالة واحدة؛ يرجع True عند النجاح. لا يطبع قيم الأسرار."""
    to_email = _clean(to_email)
    if not to_email or '@' not in to_email:
        return False
    sender = current_app.config.get('MS_SENDER_EMAIL', '')
    token = _access_token()
    if not (sender and token):
        print('[email] Microsoft 365 is not configured - the message was not sent', flush=True)
        return False
    seen = {to_email.lower()}
    bcc = []
    for b in bcc_list or []:
        b = _clean(b)
        if b and '@' in b and b.lower() not in seen:
            seen.add(b.lower())
            bcc.append({'emailAddress': {'address': b}})
    message = {'subject': subject, 'body': {'contentType': 'HTML', 'content': html_body},
               'toRecipients': [{'emailAddress': {'address': to_email}}]}
    if bcc:
        message['bccRecipients'] = bcc[:50]
    try:
        r = requests.post(f'https://graph.microsoft.com/v1.0/users/{sender}/sendMail',
                          headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                          json={'message': message, 'saveToSentItems': True}, timeout=15)
        if r.status_code not in (200, 201, 202):
            print(f'[email] sendMail failed: HTTP {r.status_code}', flush=True)
            return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f'[email] sendMail error: {type(e).__name__}', flush=True)
        return False


def graph_ready():
    c = current_app.config
    return bool(c.get('MS_TENANT_ID') and c.get('MS_CLIENT_ID') and c.get('MS_CLIENT_SECRET') and c.get('MS_SENDER_EMAIL'))


def fmt_date(ds):
    if not ds:
        return ds
    p = ds.split('-')
    return f'{p[2]}/{p[1]}/{p[0]}' if len(p) == 3 else ds


def _template(inner):
    from utils.brand import email_logo_url, get_brand
    b = get_brand()
    logo = email_logo_url()
    dark = b['accent_dark']
    yr = datetime.now().year
    logo_html = (f'<img src="{escape(logo)}" width="80" height="80" style="display:block;" alt="">' if logo else '')
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background-color:#EAEAEA;"><center style="width:100%;background-color:#EAEAEA;">
<table role="presentation" width="600" border="0" cellpadding="0" cellspacing="0" style="max-width:600px;border-collapse:collapse;">
<tr><td align="center" bgcolor="{dark}" style="background-color:{dark};padding:25px;">{logo_html}</td></tr>
<tr><td align="center" bgcolor="{dark}" style="background-color:{dark};padding:10px 25px 30px;">
<font face="Tahoma,Arial,sans-serif" color="#EBB37B" style="font-size:22px;font-weight:bold;">{escape(b['org_ar'])}</font><br>
<font face="Tahoma,Arial,sans-serif" color="#ffffff" style="font-size:13px;">{escape(b['sys_ar'])}</font></td></tr>
<tr><td bgcolor="#ffffff" dir="rtl" style="background-color:#ffffff;padding:30px 25px;font-family:Tahoma,Arial,sans-serif;color:#333;font-size:14px;line-height:1.7;">{inner}</td></tr>
<tr><td align="center" bgcolor="{dark}" style="background-color:{dark};padding:18px 25px;">
<font face="Tahoma,Arial,sans-serif" color="#EBB37B" style="font-size:13px;">&copy; {yr} {escape(b['org_ar'])} — جميع الحقوق محفوظة</font></td></tr>
</table></center></body></html>"""


def _row(label, value, last=False, color=None):
    border = '' if last else 'border-bottom:1px solid #e0e0e0;'
    val = f'<font style="font-weight:bold;color:{color};">{escape(str(value))}</font>' if color else escape(str(value))
    return (f'<tr><td style="background:#f0f7f7;padding:10px 20px;{border}"><font color="#666666" style="font-size:13px;">'
            f'<strong>{label}:</strong></font> {val}</td></tr>')


def _table(rows):
    return ('<table width="100%" border="0" cellpadding="0" cellspacing="0" dir="rtl" '
            f'style="border-collapse:collapse;">{"".join(rows)}</table>')


def _badge(text, bg, fg='#fff'):
    return (f'<div style="text-align:center;margin-bottom:20px;background:{bg};color:{fg};padding:8px 25px;'
            f'display:inline-block;font-weight:bold;">{text}</div><br>')


def _full_rows(d, color):
    return [_row('رقم الطلب', d['reqId'], color=color), _row('المناسبة', d['title']), _row('القاعة', d['hall']),
            _row('الوقت والتاريخ', f"{d['timeStr']} | {d['dateStr']}", last=True)]


def _send(d, subject_prefix, inner, bcc_list):
    from utils.brand import get_brand
    send_email(d['email'], f"{subject_prefix} — {d['reqId']} | {get_brand()['org_ar']}", _template(inner), bcc_list)


def send_confirm_email(d, bcc_list=None):
    inner = (_badge('⏳ تم استلام طلبك', '#EBB37B', '#333') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>تم استلام طلب حجزك بنجاح وهو حالياً <strong>قيد المراجعة</strong>.<br><br>"
             + _table(_full_rows(d, '#247680')) +
             '<br><font style="font-size:13px;color:#666666;">سيتم إبلاغك بنتيجة المراجعة عبر البريد الإلكتروني.</font>')
    _send(d, 'استلام طلب حجز', inner, bcc_list)


def send_approve_email(d, bcc_list=None):
    inner = (_badge('✔️ تمت الموافقة', '#1e8449') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>يسعدنا إبلاغك بأنه <strong>تمت الموافقة</strong> على طلب حجزك.<br><br>"
             + _table(_full_rows(d, '#1e8449')))
    _send(d, 'موافقة على طلب حجز', inner, bcc_list)


def send_reject_email(d, bcc_list=None):
    inner = (_badge('❌ تم الرفض', '#c0392b') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>نأسف لإبلاغك بأنه <strong>تم رفض</strong> طلب حجزك.<br><br>"
             f'<div style="background:#fff5f5;padding:12px 20px;border:1px solid #ffcdd2;color:#a93226;margin-bottom:15px;">'
             f"<strong>سبب الرفض:</strong> {escape(d.get('reason') or '')}</div>"
             + _table([_row('رقم الطلب', d['reqId'], color='#c0392b'), _row('المناسبة', d['title'], last=True)]) +
             '<br><font style="font-size:13px;color:#666666;">يمكنك تقديم طلب جديد في أي وقت.</font>')
    _send(d, 'رفض طلب حجز', inner, bcc_list)


def send_cancel_email(d, bcc_list=None):
    inner = (_badge('🗑️ تم الإلغاء', '#5d6d7e') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>تم <strong>إلغاء حجزك</strong>.<br><br>"
             + _table([_row('رقم الطلب', d['reqId'], color='#5d6d7e'), _row('المناسبة', d['title']),
                       _row('القاعة', d['hall'], last=True)]))
    _send(d, 'إلغاء حجز', inner, bcc_list)


def send_pending_email(d, bcc_list=None):
    inner = (_badge('⏳ حالة الطلب: قيد المراجعة', '#EBB37B', '#333') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>أُعيد طلب حجزك إلى حالة <strong>قيد المراجعة</strong>.<br><br>"
             + _table(_full_rows(d, '#247680')))
    _send(d, 'تحديث حالة الحجز', inner, bcc_list)


def send_update_email(d, bcc_list=None):
    inner = (_badge('✏️ تم تحديث الحجز', '#247680') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>تم <strong>تعديل بيانات حجزك</strong>. تفاصيل الحجز المحدّثة:<br><br>"
             + _table(_full_rows(d, '#247680')))
    _send(d, 'تحديث الحجز', inner, bcc_list)
