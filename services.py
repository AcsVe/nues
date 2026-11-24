"""منطق الحجز المشترك بين الصفحات العامة والإدارة: التحقق، والتعارض، والإبلاغ بالبريد، وتغيير الحالة."""
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from html import escape

from flask import current_app

import email_service as mail
from models import AppSetting, BlockedPeriod, Booking, Contact, Hall, db
from utils import auth

TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
STATUSES = ('pending', 'approved', 'rejected', 'cancelled')
_HITS = {}   # (الفئة، عنوان الزائر) ← أوقات الطلبات الأخيرة


def amman_now():
    """الوقت الحالي بتوقيت عمّان (naive)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('Asia/Amman')).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        return datetime.utcnow() + timedelta(hours=3)


def rate_ok(bucket, limit, window):
    """حدّ لعدد الطلبات من العنوان نفسه في نافذة زمنية (يحمي النماذج العامة من الإغراق)."""
    key = (bucket, auth.client_ip())
    now = time.time()
    hits = [t for t in _HITS.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _HITS[key] = hits
        return False
    hits.append(now)
    _HITS[key] = hits
    return True


def err_json(msg_ar, code=400):
    from flask import jsonify
    return jsonify({'error': msg_ar}), code


def txt(value, limit):
    return str(value or '').strip()[:limit]


def parse_date(value):
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def clean_time(value):
    v = str(value or '').strip()
    return v if TIME_RE.match(v) else ''


def split_emails(raw):
    if not raw:
        return []
    raw = str(raw).replace(';', ',').replace('\n', ',')
    return [e.strip() for e in raw.split(',') if EMAIL_RE.match(e.strip())]


def build_bcc(primary, *sources):
    seen, out = set(), []
    primary = (primary or '').strip().lower()
    for src in sources:
        if not src:
            continue
        if isinstance(src, str):
            src = split_emails(src)
        for e in src:
            el = e.strip().lower()
            if not el or '@' not in el or el == primary or el in seen:
                continue
            seen.add(el)
            out.append(e.strip())
    return out


def new_req_id():
    while True:
        rid = 'BK-' + secrets.token_hex(5).upper()
        if not Booking.query.filter_by(req_id=rid).first():
            return rid


def booking_payload(b):
    time_str = 'يوم كامل' if b.full_day else f"{b.start_time or ''} - {b.end_time or ''}"
    date_str = b.start_date.strftime('%Y-%m-%d')
    if b.end_date and b.end_date != b.start_date:
        date_str += f" — {b.end_date.strftime('%Y-%m-%d')}"
    return {'reqId': b.req_id, 'name': b.full_name, 'email': b.email, 'phone': b.phone or '', 'title': b.title,
            'hall': b.hall_name, 'timeStr': time_str, 'dateStr': date_str, 'notes': b.notes or '',
            'startTime': b.start_time or '', 'endTime': b.end_time or ''}


def notify(fn, *args, **kwargs):
    """الإرسال بالبريد لا يُفشل الطلب أبداً."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        print(f'[email] {getattr(fn, "__name__", "send")} failed: {type(e).__name__}', flush=True)
        return None


# ───────────── التعارض والفترات المحجوبة ─────────────
def times_overlap(s1, e1, s2, e2):
    """مقارنة HH:MM؛ الوقت الفارغ يعني فترة مفتوحة فيُعدّ متقاطعاً."""
    if not s1 or not e1 or not s2 or not e2:
        return True
    return s1 < e2 and s2 < e1


def conflict_check(new_start, new_end, s_time, e_time, full, hall, exclude_id=None):
    q = Booking.query.filter(Booking.hall_name == hall, Booking.start_date <= new_end,
                             Booking.end_date >= new_start, ~Booking.status.in_(['rejected', 'cancelled']))
    if exclude_id is not None:
        q = q.filter(Booking.id != exclude_id)
    for b in q.all():
        if full or b.full_day or times_overlap(s_time, e_time, b.start_time or '', b.end_time or ''):
            return b
    return None


def blocked_check(new_start, new_end, s_time, e_time, full, hall):
    q = BlockedPeriod.query.filter(BlockedPeriod.start_date <= new_end, BlockedPeriod.end_date >= new_start)
    for bp in q.all():
        if bp.hall_name and bp.hall_name != hall:
            continue
        if full or not (bp.start_time and bp.end_time) or times_overlap(s_time, e_time, bp.start_time, bp.end_time):
            return bp
    return None


def valid_attachments(urls):
    """المرفقات المقبولة هي ملفات رُفعت إلى هذا النظام فقط."""
    out = []
    folder = current_app.config['UPLOAD_FOLDER']
    for u in (urls or [])[:10]:
        u = str(u)
        name = u[len('/uploads/'):]
        if u.startswith('/uploads/') and '/' not in name and os.path.isfile(os.path.join(folder, name)):
            out.append(u)
    return out


def upsert_contact(email, name):
    if not email or not EMAIL_RE.match(email) or Contact.query.filter_by(email=email).first():
        return
    try:
        db.session.add(Contact(email=email, name=name or ''))
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


# ───────────── الإعدادات ─────────────
def setting_bool(key, default):
    return AppSetting.get_bool(key, default)


def auto_approve_on():
    return setting_bool('auto_approve_bookings', False)


# ───────────── جهات الاتصال والإبلاغ ─────────────
def _contacts_for(hall_name, flag):
    """جهات الاتصال المعنية بإشعار ما: التي رُفع علمها، وتخص هذه القاعة أو كل القاعات."""
    out = []
    for c in Contact.query.all():
        on = getattr(c, flag)
        if on is None:
            on = flag in ('notify_new', 'notify_approved')
        if on and mail.EMAIL_OK(c.email) and (hall_name is None or not c.hall_name or c.hall_name == hall_name):
            out.append(c)
    return out


def contact_emails(hall_name, flag):
    return [c.email for c in _contacts_for(hall_name, flag)]


def action_links(b):
    base = (current_app.config.get('BASE_URL') or '').rstrip('/')
    if not (base and b.action_token):
        return None, None
    return (f'{base}/action/approve/{b.req_id}?token={b.action_token}',
            f'{base}/action/reject/{b.req_id}?token={b.action_token}')


def notify_staff_new(b):
    """إشعار الحجز الجديد: لمن يملك الرابطين (الموافقة والرفض)، ولمن للاطّلاع فقط."""
    p = booking_payload(b)
    approve, reject = action_links(b)
    for c in _contacts_for(b.hall_name, 'notify_new'):
        readonly = bool(c.new_readonly)
        notify(mail.send_staff_new_booking, c.email, p, None if readonly else approve, None if readonly else reject)


def apply_status(b, status, reason='', by='', extra_bcc=''):
    """يغيّر حالة الحجز ويبلّغ المعنيين. لا يتحقق من الصلاحية: يستدعيه من تحقق منها."""
    b.status, b.action_date = status, datetime.utcnow()
    b.reject_reason = reason if status == 'rejected' else ''
    if status == 'approved':
        b.approved_by = by or b.approved_by
    if status == 'cancelled' and reason:
        b.cancel_reason = reason
    db.session.commit()
    send_status_mail(b, status, reason, extra_bcc)


def send_status_mail(b, status, reason='', extra_bcc=''):
    p = booking_payload(b)
    if status == 'approved':
        bcc = build_bcc(b.email, b.cc_emails, extra_bcc, contact_emails(b.hall_name, 'notify_approved'))
        notify(mail.send_approve_email, p, bcc_list=bcc)
    elif status == 'rejected':
        p['reason'] = reason
        notify(mail.send_reject_email, p, bcc_list=build_bcc(b.email, b.cc_emails))
    elif status == 'cancelled':
        notify(mail.send_cancel_email, p, bcc_list=build_bcc(b.email, b.cc_emails))
    elif status == 'pending':
        notify(mail.send_pending_email, p, bcc_list=build_bcc(b.email, b.cc_emails, contact_emails(b.hall_name, 'notify_new')))
