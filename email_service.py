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
<font face="Tahoma,Arial,sans-serif" color="#ffffff" style="font-size:16px;">{escape(b['sys_ar'])}</font></td></tr>
<tr><td bgcolor="#ffffff" dir="rtl" style="background-color:#ffffff;padding:30px 25px;font-family:Tahoma,Arial,sans-serif;color:#222;font-size:17px;line-height:1.8;">{inner}</td></tr>
<tr><td align="center" bgcolor="{dark}" style="background-color:{dark};padding:18px 25px;">
<font face="Tahoma,Arial,sans-serif" color="#EBB37B" style="font-size:14px;">&copy; {yr} {escape(b['org_ar'])} — جميع الحقوق محفوظة</font></td></tr>
</table></center></body></html>"""


def _row(label, value, last=False, color=None):
    border = '' if last else 'border-bottom:1px solid #e0e0e0;'
    val = f'<font style="font-weight:bold;color:{color};">{escape(str(value))}</font>' if color else escape(str(value))
    return (f'<tr><td style="background:#f0f7f7;padding:12px 20px;font-size:17px;{border}"><font color="#555555" style="font-size:15px;">'
            f'<strong>{label}:</strong></font> {val}</td></tr>')


def _table(rows):
    return ('<table width="100%" border="0" cellpadding="0" cellspacing="0" dir="rtl" '
            f'style="border-collapse:collapse;">{"".join(rows)}</table>')


def _badge(text, bg, fg='#fff'):
    return (f'<div style="text-align:center;margin-bottom:16px;background:{bg};color:{fg};padding:10px 28px;font-size:19px;'
            f'display:inline-block;font-weight:bold;">{text}</div><br>')


def _top(d, color='#0A7C86', ticket=False):
    """أهم ما في رسالة صاحب الحجز، في أعلاها: رقم الحجز كبيراً وقابلاً للنقر (يفتح الاستعلام برقمه)، وأزرار الاستعلام والروزنامة والتأكيد الرسمي."""
    rid = escape(d['reqId'])
    num = (f'<a href="{escape(d["lookupUrl"])}" style="color:{color};text-decoration:underline;">{rid}</a>' if d.get('lookupUrl') else rid)
    out = ('<div style="text-align:center;margin:4px 0 14px;padding:14px;background:#f5fafa;border:2px dashed #b9d6d8;">'
           '<div style="font-size:15px;color:#555;">رقم الحجز' + (' (اضغط عليه للاستعلام عن الحجز)' if d.get('lookupUrl') else '') + '</div>'
           f'<div dir="ltr" style="font-size:30px;font-weight:bold;letter-spacing:1px;color:{color};">{num}</div></div>')
    btns = ''
    if d.get('lookupUrl'):
        btns += _button(d['lookupUrl'], 'الاستعلام عن الحجز أو تعديله', color)
    if ticket and d.get('ticketUrl'):
        btns += _button(d['ticketUrl'], 'التأكيد الرسمي (طباعة / PDF)', '#1e8449')
    if d.get('calendarUrl'):
        btns += _button(d['calendarUrl'], 'الروزنامة', '#5d6d7e')
    return out + (f'<div style="text-align:center;margin:0 0 18px;">{btns}</div>' if btns else '')


def _extra_rows(d):
    """سطور اختيارية: عدد الحضور والمستلزمات وسلسلة التكرار."""
    out = []
    if d.get('attendees'):
        out.append(('عدد الحضور', d['attendees']))
    if d.get('extras'):
        out.append(('المستلزمات', d['extras']))
    if (d.get('seriesCount') or 0) > 1:
        out.append(('حجز متكرر', f"سلسلة من {d['seriesCount']} حجزاً"))
    return out


def _rows_with_last(pairs, color=None):
    """سطور جدول من أزواج (عنوان، قيمة): الأول بلون مميز والأخير بلا حد."""
    return [_row(k, v, last=(i == len(pairs) - 1), color=color if i == 0 else None) for i, (k, v) in enumerate(pairs)]


def _full_rows(d, color):
    pairs = [('رقم الطلب', d['reqId']), ('المناسبة', d['title']), ('القاعة', d['hall']),
             ('الوقت والتاريخ', f"{d['timeStr']} | {d['dateStr']}")] + _extra_rows(d)
    return _rows_with_last(pairs, color)


def _send(d, subject_prefix, inner, bcc_list):
    from utils.brand import get_brand
    send_email(d['email'], f"{subject_prefix} — {d['reqId']} | {get_brand()['org_ar']}", _template(inner), bcc_list)


def send_confirm_email(d, bcc_list=None):
    inner = (_badge('⏳ تم استلام طلبك', '#EBB37B', '#333') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>تم استلام طلب حجزك بنجاح وهو حالياً <strong>قيد المراجعة</strong>. سيصلك بريد بنتيجة المراجعة.<br><br>"
             + _top(d, '#247680') + _table(_full_rows(d, '#247680')))
    _send(d, 'استلام طلب حجز', inner, bcc_list)


def send_approve_email(d, bcc_list=None):
    inner = (_badge('✔️ تمت الموافقة', '#1e8449') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>يسعدنا إبلاغك بأنه <strong>تمت الموافقة</strong> على طلب حجزك.<br><br>"
             + _top(d, '#1e8449', ticket=True) + _table(_full_rows(d, '#1e8449')))
    _send(d, 'موافقة على طلب حجز', inner, bcc_list)


def send_reject_email(d, bcc_list=None):
    inner = (_badge('❌ تم الرفض', '#c0392b') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>نأسف لإبلاغك بأنه <strong>تم رفض</strong> طلب حجزك.<br><br>"
             f'<div style="background:#fff5f5;padding:12px 20px;border:1px solid #ffcdd2;color:#a93226;margin-bottom:15px;">'
             f"<strong>سبب الرفض:</strong> {escape(d.get('reason') or '')}</div>"
             + _top(d, '#c0392b') + _table([_row('رقم الطلب', d['reqId'], color='#c0392b'), _row('المناسبة', d['title'], last=True)])
             + (('<div style="text-align:center;margin:18px 0 4px;">' + _button(d['bookUrl'], 'تقديم طلب جديد', '#0A7C86') + '</div>') if d.get('bookUrl') else
                '<br>يمكنك تقديم طلب جديد في أي وقت.'))
    _send(d, 'رفض طلب حجز', inner, bcc_list)


def send_cancel_email(d, bcc_list=None):
    inner = (_badge('🗑️ تم الإلغاء', '#5d6d7e') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>تم <strong>إلغاء حجزك</strong>.<br><br>"
             + _top(d, '#5d6d7e') + _table([_row('رقم الطلب', d['reqId'], color='#5d6d7e'), _row('المناسبة', d['title']),
                       _row('القاعة', d['hall'], last=True)]))
    _send(d, 'إلغاء حجز', inner, bcc_list)


def send_pending_email(d, bcc_list=None):
    inner = (_badge('⏳ حالة الطلب: قيد المراجعة', '#EBB37B', '#333') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>أُعيد طلب حجزك إلى حالة <strong>قيد المراجعة</strong>.<br><br>"
             + _top(d, '#247680') + _table(_full_rows(d, '#247680')))
    _send(d, 'تحديث حالة الحجز', inner, bcc_list)


def send_update_email(d, bcc_list=None):
    inner = (_badge('✏️ تم تحديث الحجز', '#247680') +
             f"مرحباً <strong>{escape(d['name'])}</strong>،<br>تم <strong>تعديل بيانات حجزك</strong>. تفاصيل الحجز المحدّثة:<br><br>"
             + _top(d, '#247680') + _table(_full_rows(d, '#247680')))
    _send(d, 'تحديث الحجز', inner, bcc_list)


# ───────────── رسائل الإدارة والتذكيرات ─────────────
_EMAIL_RE = __import__('re').compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def EMAIL_OK(e):
    return bool(e and _EMAIL_RE.match(str(e).strip()))


def _button(url, label, bg):
    return (f'<a href="{escape(url)}" style="display:inline-block;background:{bg};color:#ffffff;padding:14px 30px;font-size:18px;'
            f'border-radius:8px;text-decoration:none;font-weight:bold;margin:5px 6px;">{label}</a>')


def _org():
    from utils.brand import get_brand
    return get_brand()['org_ar']


def send_staff_new_booking(to, d, approve_url=None, reject_url=None):
    """إشعار الإدارة بحجز جديد، ومعه رابطا الموافقة والرفض لمن يملكهما."""
    pairs = [('رقم الطلب', d['reqId']), ('مقدّم الطلب', d['name']), ('البريد الإلكتروني', d['email']),
             ('الهاتف', d.get('phone') or '-'), ('المناسبة', d['title']), ('المبنى أو المرفق', d['hall']),
             ('الوقت والتاريخ', f"{d['timeStr']} | {d['dateStr']}")] + _extra_rows(d)
    if d.get('notes'):
        pairs.append(('ملاحظات', d['notes']))
    rows = _rows_with_last(pairs, '#0A7C86')
    buttons = ''
    if approve_url and reject_url:
        buttons = ('<div style="text-align:center;margin:22px 0 6px;">' + _button(approve_url, 'موافقة', '#1e8449')
                   + _button(reject_url, 'رفض', '#c0392b') + '</div>')
    summary = (f'<div style="margin:6px 0 14px;padding:14px;background:#f5fafa;border:2px dashed #b9d6d8;text-align:center;">'
               f'<div dir="ltr" style="font-size:26px;font-weight:bold;color:#0A7C86;">{escape(d["reqId"])}</div>'
               f'<div style="font-size:19px;font-weight:bold;margin-top:4px;">{escape(d["title"])}</div>'
               f'<div style="font-size:17px;">{escape(d["hall"])} — {escape(d["timeStr"])} | {escape(d["dateStr"])}</div></div>')
    inner = (_badge('🔔 حجز جديد بانتظار المراجعة', '#EBB37B', '#333') + '<br>' + summary + buttons
             + '<br><br>تفاصيل الطلب:<br><br>' + _table(rows))
    send_email(to, f"حجز جديد — {d['reqId']} | {_org()}", _template(inner))


def send_comment_email(to, d, author, comment):
    inner = (_badge('💬 تعليق جديد على حجز', '#0A7C86') + _table([_row('رقم الطلب', d['reqId']), _row('المناسبة', d['title'], last=True)])
             + f'<div style="margin-top:14px;padding:12px 16px;background:#f0f7f7;border-radius:8px;"><strong>{escape(author or "")}:</strong><br>{escape(comment).replace(chr(10), "<br>")}</div>')
    send_email(to, f"تعليق على الحجز {d['reqId']} | {_org()}", _template(inner))


def send_daily_summary(to, date_str, items):
    rows = ''.join(
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #e0e0e0;">{escape(i["time"])}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #e0e0e0;">{escape(i["hall"])}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #e0e0e0;">{escape(i["title"])}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #e0e0e0;">{escape(i["name"])}</td></tr>' for i in items)
    inner = (_badge(f'📅 حجوزات اليوم {date_str}', '#0A7C86') + f'عدد الحجوزات المعتمدة اليوم: <strong>{len(items)}</strong><br><br>'
             '<table width="100%" dir="rtl" style="border-collapse:collapse;"><tr style="background:#e8f4f5;">'
             '<th style="padding:8px 12px;text-align:right;">الوقت</th><th style="padding:8px 12px;text-align:right;">المبنى أو المرفق</th>'
             '<th style="padding:8px 12px;text-align:right;">المناسبة</th><th style="padding:8px 12px;text-align:right;">مقدّم الطلب</th></tr>'
             + rows + '</table>')
    send_email(to, f'ملخص حجوزات اليوم {date_str} | {_org()}', _template(inner))


def send_upcoming_reminder(to, d, lead_minutes):
    inner = (_badge('⏰ حجز يقترب موعده', '#EBB37B', '#333') + f'يبدأ الحجز التالي خلال نحو <strong>{int(lead_minutes)}</strong> دقيقة:<br><br>'
             + _table(_full_rows(d, '#0A7C86')))
    send_email(to, f"تذكير بحجز — {d['reqId']} | {_org()}", _template(inner))


def send_booker_reminder(d, note=''):
    inner = (_badge('⏰ تذكير بحجزك', '#EBB37B', '#333') + f"مرحباً <strong>{escape(d['name'])}</strong>،<br>هذا تذكير بحجزك:<br><br>"
             + _top(d, '#0A7C86') + _table(_full_rows(d, '#0A7C86'))
             + (f'<br><div style="padding:10px 14px;background:#f0f7f7;border-radius:8px;">{escape(note)}</div>' if note else ''))
    send_email(d['email'], f"تذكير بحجزك — {d['reqId']} | {_org()}", _template(inner))


def send_verification_code(to, name, code, minutes=15):
    """رمز تأكيد البريد قبل إنشاء الحجز: الرمز كبيراً في أول الرسالة."""
    inner = (_badge('🔐 رمز تأكيد الحجز', '#0A7C86')
             + f'<div style="text-align:center;margin:6px 0 14px;padding:16px;background:#f5fafa;border:2px dashed #b9d6d8;">'
               f'<div style="font-size:15px;color:#555;">انسخ هذا الرمز والصقه في صفحة الحجز</div>'
               f'<div dir="ltr" style="font-size:42px;font-weight:bold;letter-spacing:8px;color:#0A7C86;">{escape(str(code))}</div></div>'
             + f'مرحباً <strong>{escape(name or "")}</strong>،<br>وصلنا طلب حجز بهذا البريد. الرمز صالح <strong>{int(minutes)} دقيقة</strong> ويُستعمل مرة واحدة.<br>'
             '<font style="font-size:15px;color:#666666;">إن لم تطلب حجزاً فتجاهل هذه الرسالة، ولن يُنشأ أي حجز.</font>')
    return send_email(to, f'رمز تأكيد الحجز {code} | {_org()}', _template(inner))


def send_password_reset(to, name, link):
    inner = (_badge('🔑 إعادة تعيين كلمة المرور', '#0A7C86') + f'مرحباً <strong>{escape(name or "")}</strong>،<br>'
             'وصلنا طلب لإعادة تعيين كلمة مرور حسابك. الرابط صالح ساعة واحدة ويُستعمل مرة واحدة:<br>'
             f'<div style="text-align:center;margin:18px 0;">{_button(link, "تعيين كلمة مرور جديدة", "#0A7C86")}</div>'
             '<font style="font-size:13px;color:#666666;">إن لم تطلب ذلك فتجاهل هذه الرسالة.</font>')
    send_email(to, f'إعادة تعيين كلمة المرور | {_org()}', _template(inner))
