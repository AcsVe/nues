"""مسارات الصفحات والواجهة البرمجية: الجزء العام (الروزنامة والحجز) والإدارة (محمية بالدخول ورمز CSRF)."""
import base64
import csv
import io
import os
import re
import secrets
import time
from datetime import date as date_cls, datetime, timedelta
from html import escape

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from email_service import (send_approve_email, send_cancel_email, send_confirm_email, send_pending_email,
                           send_reject_email, send_update_email, graph_ready)
from models import AdminUser, AppSetting, BlockedPeriod, Booking, Contact, Hall, db
from utils import auth
from utils.auth import admin_required

main_bp = Blueprint('main', __name__)

TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
ALLOWED_UPLOADS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'zip', 'jpg', 'jpeg', 'png', 'gif', 'webp'}
INLINE_TYPES = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf'}
STATUSES = ('pending', 'approved', 'rejected', 'cancelled')
_HITS = {}   # (الفئة، عنوان الزائر) ← أوقات الطلبات الأخيرة


# ───────────── أدوات مساعدة ─────────────
def rate_ok(bucket, limit, window):
    """حدّ بسيط لعدد الطلبات من العنوان نفسه في نافذة زمنية (يحمي النماذج العامة من الإغراق)."""
    key = (bucket, auth.client_ip())
    now = time.time()
    hits = [t for t in _HITS.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _HITS[key] = hits
        return False
    hits.append(now)
    _HITS[key] = hits
    return True


def err(msg_ar, msg_en, code=400):
    return jsonify({'error': f'{msg_ar} / {msg_en}'}), code


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


def contact_emails():
    return list({(r[0] or '').strip().lower() for r in Contact.query.with_entities(Contact.email).all() if r[0]})


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


def booking_payload(b):
    time_str = 'يوم كامل' if b.full_day else f"{b.start_time or ''} - {b.end_time or ''}"
    date_str = b.start_date.strftime('%Y-%m-%d')
    if b.end_date and b.end_date != b.start_date:
        date_str += f" — {b.end_date.strftime('%Y-%m-%d')}"
    return {'reqId': b.req_id, 'name': b.full_name, 'email': b.email, 'title': b.title, 'hall': b.hall_name,
            'timeStr': time_str, 'dateStr': date_str}


def notify(fn, *args, **kwargs):
    """الإرسال بالبريد لا يُفشل الطلب أبداً."""
    try:
        fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        print(f'[email] {fn.__name__} failed: {type(e).__name__}', flush=True)


def new_req_id():
    while True:
        rid = 'BK-' + secrets.token_hex(5).upper()
        if not Booking.query.filter_by(req_id=rid).first():
            return rid


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


def upsert_contact(email, name):
    if not email or not EMAIL_RE.match(email) or Contact.query.filter_by(email=email).first():
        return
    try:
        db.session.add(Contact(email=email, name=name or ''))
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


def valid_attachments(urls):
    """المرفقات المقبولة هي ملفات رُفعت إلى هذا النظام فقط."""
    out = []
    folder = current_app.config['UPLOAD_FOLDER']
    for u in (urls or [])[:10]:
        u = str(u)
        if u.startswith('/uploads/') and '/' not in u[len('/uploads/'):] and os.path.isfile(os.path.join(folder, u[len('/uploads/'):])):
            out.append(u)
    return out


# ───────────── الصفحات ─────────────
def _page(template, **extra):
    lang = 'en' if request.args.get('lang') == 'en' else 'ar'
    theme = request.args.get('theme', '') if request.args.get('theme') in ('dark', 'light') else ''
    from utils.brand import get_brand
    b = get_brand()
    return render_template(template, lang=lang, theme=theme, csrf=auth.csrf_token(),
                           org_ar=b['org_ar'], org_en=b['org_en'], logo=b['logo_src'], **extra)


@main_bp.route('/')
def calendar_page():
    return _page('calendar.html', pre_date=txt(request.args.get('date'), 10))


@main_bp.route('/book')
def book_page():
    return _page('book.html', pre_date=txt(request.args.get('date'), 10))


@main_bp.route('/admin')
@main_bp.route('/admin/login')
def admin_page():
    return _page('admin.html', logged_in=auth.current_user() is not None)


@main_bp.route('/healthz')
def healthz():
    try:
        db.session.execute(db.text('select 1'))
        return jsonify({'ok': True})
    except Exception:  # noqa: BLE001
        return jsonify({'ok': False}), 503


@main_bp.route('/uploads/brand/<name>')
def brand_file(name):
    """شعار المؤسسة المرفوع من الإعدادات (يُعرض في الصفحات والبريد)."""
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'brand')
    if not os.path.isfile(os.path.join(folder, name)):
        abort(404)
    resp = send_from_directory(folder, name, max_age=3600)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Content-Security-Policy'] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    return resp


@main_bp.route('/uploads/<path:name>')
def uploaded(name):
    folder = current_app.config['UPLOAD_FOLDER']
    if '/' in name or not os.path.isfile(os.path.join(folder, name)):
        abort(404)
    ext = name.rsplit('.', 1)[-1].lower()
    resp = send_from_directory(folder, name, as_attachment=ext not in INLINE_TYPES)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Content-Security-Policy'] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    return resp


# ───────────── الواجهة العامة ─────────────
@main_bp.route('/api/halls')
def get_halls():
    halls = Hall.query.filter_by(active=True).order_by(Hall.id).all()
    return jsonify([{'nameAr': h.name_ar, 'nameEn': h.name_en or h.name_ar, 'location': h.location, 'code': h.code,
                     'capacity': h.capacity, 'equipment': h.equipment, 'description': h.description,
                     'notes': h.notes} for h in halls])


@main_bp.route('/api/upload', methods=['POST'])
def upload_file():
    if not rate_ok('upload', 30, 3600):
        return err('طلبات رفع كثيرة، حاول لاحقاً', 'Too many uploads, try later', 429)
    data = request.get_json(silent=True) or {}
    name = secure_filename(txt(data.get('fileName') or data.get('name'), 120))
    b64 = data.get('dataBase64') or data.get('data') or ''
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if not name or not b64:
        return err('فشل رفع الملف', 'Missing file payload')
    if ext not in ALLOWED_UPLOADS:
        return err('نوع الملف غير مسموح به', 'This file type is not allowed')
    b64 = re.sub(r'\s+', '', str(b64))
    if ',' in b64 and b64.startswith('data:'):
        b64 = b64.split(',', 1)[1]
    b64 += '=' * ((-len(b64)) % 4)
    try:
        payload = base64.b64decode(b64, validate=False)
    except Exception:  # noqa: BLE001
        return err('فشل رفع الملف', 'Invalid file data')
    if len(payload) > 10 * 1024 * 1024:
        return err('الملف كبير جداً', 'File too large', 413)
    unique = f"{secrets.token_hex(8)}.{ext}"
    with open(os.path.join(current_app.config['UPLOAD_FOLDER'], unique), 'wb') as f:
        f.write(payload)
    return jsonify({'url': f'/uploads/{unique}', 'name': name, 'id': unique})


@main_bp.route('/api/submit_booking', methods=['POST'])
def submit_booking():
    if not rate_ok('submit', 20, 3600):
        return err('طلبات كثيرة، حاول لاحقاً', 'Too many requests, try later', 429)
    data = request.get_json(silent=True) or {}
    start = parse_date(data.get('bookingDate'))
    if not start:
        return err('تاريخ غير صالح', 'Invalid date')
    end = parse_date(data.get('endDate')) or start
    name, email = txt(data.get('fullName'), 100), txt(data.get('email'), 100)
    title, hall_name = txt(data.get('eventTitle'), 200), txt(data.get('hall'), 100)
    if not name or not title:
        return err('الاسم وعنوان المناسبة مطلوبان', 'Name and event title are required')
    if not EMAIL_RE.match(email):
        return err('البريد الإلكتروني غير صالح', 'Invalid email address')
    hall = Hall.query.filter_by(name_ar=hall_name, active=True).first() or Hall.query.filter_by(name_en=hall_name, active=True).first()
    if not hall:
        return err('القاعة غير صحيحة', 'Unknown venue')
    hall_name = hall.name_ar
    if start < datetime.now().date():
        return err('لا يمكن الحجز بتاريخ سابق', 'Cannot book a past date')
    if end < start:
        return err('تاريخ الانتهاء يجب أن يكون بعد البداية', 'End date must be after start date')
    if (end - start).days > 366:
        return err('مدة الحجز أطول من المسموح', 'The booking period is too long')
    full = bool(data.get('fullDay', False))
    s_time, e_time = clean_time(data.get('startTime')), clean_time(data.get('endTime'))
    if not full:
        if not s_time:
            return err('وقت البداية مطلوب', 'Start time is required')
        if e_time and e_time <= s_time:
            return err('وقت النهاية يجب أن يكون بعد البداية', 'End time must be after start time')

    conflict = conflict_check(start, end, s_time, e_time, full, hall_name)
    if conflict:
        if conflict.full_day:
            msg = 'القاعة محجوزة يوم كامل في هذا التاريخ'
        elif full:
            msg = 'لا يمكن الحجز يوم كامل، يوجد حجز في هذا التاريخ'
        else:
            msg = f"القاعة محجوزة في هذا الوقت ({conflict.start_time or ''} - {conflict.end_time or ''}) بتاريخ {conflict.start_date:%Y-%m-%d}"
        return jsonify({'error': msg}), 409
    blocked = blocked_check(start, end, s_time, e_time, full, hall_name)
    if blocked:
        msg = f"التاريخ غير متاح: {blocked.reason or 'فترة غير متاحة'}"
        if blocked.start_time and blocked.end_time:
            msg += f' ({blocked.start_time} - {blocked.end_time})'
        return jsonify({'error': msg}), 409

    booking = Booking(
        req_id=new_req_id(), full_name=name, email=email, phone=txt(data.get('phone'), 50),
        behalf=txt(data.get('onBehalf'), 100), title=title, hall_name=hall_name, start_date=start, end_date=end,
        start_time=s_time or None, end_time=e_time or None, full_day=full, notes=txt(data.get('notes'), 2000),
        attachments=','.join(valid_attachments(data.get('attUrls'))),
        cc_emails=','.join(split_emails(data.get('ccEmails'))[:10]), status='pending')
    db.session.add(booking)
    db.session.commit()
    notify(send_confirm_email, booking_payload(booking), bcc_list=build_bcc(email, contact_emails()))
    return jsonify({'success': True, 'reqId': booking.req_id})


def _own_booking(data):
    """الحجز الذي يطابق رقمه وبريده؛ محاولات التخمين محدودة بالعنوان."""
    if not rate_ok('lookup', 40, 3600):
        return None, err('محاولات كثيرة، حاول لاحقاً', 'Too many attempts, try later', 429)
    b = Booking.query.filter_by(req_id=txt(data.get('reqId'), 50)).first()
    email = txt(data.get('email'), 100).lower()
    if not b or (b.email or '').lower() != email:
        return None, (jsonify({'error': 'لم يتم العثور على الحجز أو البريد غير مطابق'}), 404)
    return b, None


@main_bp.route('/api/lookup_booking', methods=['POST'])
def lookup_booking():
    b, bad = _own_booking(request.get_json(silent=True) or {})
    if bad:
        return bad
    if b.status == 'cancelled':
        return jsonify({'error': 'هذا الحجز ملغي'}), 400
    return jsonify({
        'reqId': b.req_id, 'name': b.full_name, 'email': b.email, 'phone': b.phone, 'behalf': b.behalf, 'title': b.title,
        'hall': b.hall_name, 'date': b.start_date.strftime('%Y-%m-%d'), 'endDate': (b.end_date or b.start_date).strftime('%Y-%m-%d'),
        'startTime': b.start_time or '', 'endTime': b.end_time or '', 'fullDay': b.full_day, 'notes': b.notes,
        'status': b.status, 'ccEmails': b.cc_emails or ''})


@main_bp.route('/api/amend_booking_user', methods=['POST'])
def amend_booking_user():
    data = request.get_json(silent=True) or {}
    b, bad = _own_booking(data)
    if bad:
        return bad
    if b.status in ('cancelled', 'rejected'):
        return jsonify({'error': 'لا يمكن تعديل هذا الحجز'}), 400
    start = parse_date(data.get('date'))
    end = parse_date(data.get('endDate')) or start
    if not start or end < start:
        return jsonify({'error': 'تاريخ غير صالح'}), 400
    s_time, e_time = clean_time(data.get('startTime')), clean_time(data.get('endTime'))
    full = bool(data.get('fullDay', False))
    if not full and (not s_time or (e_time and e_time <= s_time)):
        return jsonify({'error': 'الوقت غير صالح'}), 400
    hall = Hall.query.filter_by(name_ar=txt(data.get('hall'), 100) or b.hall_name).first()
    hall_name = hall.name_ar if hall else b.hall_name
    if start < datetime.now().date():
        return jsonify({'error': 'لا يمكن الحجز بتاريخ سابق'}), 400
    conflict = conflict_check(start, end, s_time, e_time, full, hall_name, exclude_id=b.id)
    if conflict:
        return jsonify({'error': f'يتعارض مع حجز موجود ({conflict.req_id})'}), 409
    blocked = blocked_check(start, end, s_time, e_time, full, hall_name)
    if blocked:
        return jsonify({'error': f"الموعد ضمن فترة محظورة: {blocked.reason or 'غير متاح'}"}), 409
    b.full_name = txt(data.get('name'), 100) or b.full_name
    b.phone, b.behalf = txt(data.get('phone'), 50), txt(data.get('behalf'), 100)
    b.title = txt(data.get('title'), 200) or b.title
    b.hall_name, b.start_date, b.end_date = hall_name, start, end
    b.start_time, b.end_time, b.full_day = s_time or None, e_time or None, full
    b.notes = txt(data.get('notes'), 2000)
    if data.get('ccEmails') is not None:
        b.cc_emails = ','.join(split_emails(data.get('ccEmails'))[:10])
    if b.status == 'approved':
        b.status = 'pending'
    db.session.commit()
    notify(send_update_email, booking_payload(b), bcc_list=build_bcc(b.email, contact_emails()))
    return jsonify({'success': True})


@main_bp.route('/api/cancel_booking_user', methods=['POST'])
def cancel_booking_user():
    b, bad = _own_booking(request.get_json(silent=True) or {})
    if bad:
        return bad
    if b.status == 'cancelled':
        return jsonify({'error': 'هذا الحجز ملغي بالفعل'}), 400
    b.status, b.action_date = 'cancelled', datetime.utcnow()
    db.session.commit()
    notify(send_cancel_email, booking_payload(b), bcc_list=build_bcc(b.email, contact_emails()))
    return jsonify({'success': True})


@main_bp.route('/api/month_data')
def get_month_data():
    y = request.args.get('year', datetime.now().year, type=int)
    m = request.args.get('month', datetime.now().month, type=int)
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        return err('شهر غير صالح', 'Invalid month')
    import calendar
    month_start = date_cls(y, m, 1)
    month_end = date_cls(y, m, calendar.monthrange(y, m)[1])
    bookings = Booking.query.filter(Booking.start_date <= month_end, Booking.end_date >= month_start,
                                    ~Booking.status.in_(['rejected', 'cancelled'])).all()
    bk = [{'reqId': b.req_id, 'title': b.title, 'hall': b.hall_name, 'date': b.start_date.strftime('%Y-%m-%d'),
           'endDate': (b.end_date or b.start_date).strftime('%Y-%m-%d'), 'startTime': b.start_time or '',
           'endTime': b.end_time or '', 'fullDay': b.full_day, 'status': b.status, 'behalf': b.behalf or '',
           'name': b.full_name or ''} for b in bookings]
    blocked = {}
    for bp in BlockedPeriod.query.filter(BlockedPeriod.start_date <= month_end, BlockedPeriod.end_date >= month_start).all():
        cur, last = max(bp.start_date, month_start), min(bp.end_date, month_end)
        while cur <= last:
            blocked.setdefault(cur.strftime('%Y-%m-%d'), []).append(
                {'reason': bp.reason, 'fromTime': bp.start_time or '', 'toTime': bp.end_time or '', 'hall': bp.hall_name or ''})
            cur += timedelta(days=1)
    return jsonify({'bookings': bk, 'blocked': blocked})


# ───────────── الدخول والخروج ─────────────
@main_bp.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json(silent=True) or {}
    ip = auth.client_ip()
    if auth.too_many(ip):
        return jsonify({'success': False, 'error': 'محاولات كثيرة غير صحيحة، انتظر 15 دقيقة'}), 429
    ident = txt(data.get('username'), 150).lower()
    user = AdminUser.query.filter(db.func.lower(AdminUser.username) == ident).first() or \
        (AdminUser.query.filter(db.func.lower(AdminUser.email) == ident).first() if ident else None)
    if user and user.active and auth.password_ok(user, data.get('password')):
        auth.clear_failures(ip)
        user.last_login = datetime.utcnow()
        db.session.commit()
        auth.sign_in(user, bool(data.get('remember')))
        return jsonify({'success': True, 'csrf': auth.csrf_token(), 'name': user.name or user.username})
    auth.note_failure(ip)
    return jsonify({'success': False, 'error': 'اسم المستخدم أو كلمة المرور غير صحيحة'}), 401


@main_bp.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    from flask import session
    session.clear()
    return jsonify({'success': True})


@main_bp.route('/api/admin/session')
def admin_session():
    """هل الجلسة الحالية مسجّلة؟ (بلا خطأ 401 في المتصفح عند عدم الدخول)."""
    u = auth.current_user()
    return jsonify({'loggedIn': bool(u), 'csrf': auth.csrf_token() if u else ''})


@main_bp.route('/api/admin/me')
@admin_required
def admin_me():
    u = auth.current_user()
    return jsonify({'username': u.username, 'name': u.name or u.username, 'csrf': auth.csrf_token()})


# ───────────── الحجوزات ─────────────
def booking_row(b):
    return {'reqId': b.req_id, 'name': b.full_name, 'email': b.email, 'phone': b.phone, 'behalf': b.behalf,
            'title': b.title, 'hall': b.hall_name, 'date': b.start_date.strftime('%Y-%m-%d'),
            'endDate': (b.end_date or b.start_date).strftime('%Y-%m-%d'), 'startTime': b.start_time or '',
            'endTime': b.end_time or '', 'fullDay': b.full_day, 'notes': b.notes, 'status': b.status,
            'rejectReason': b.reject_reason or '', 'ccEmails': b.cc_emails or '',
            'attachments': [a for a in (b.attachments or '').split(',') if a.startswith('/uploads/')]}


@main_bp.route('/api/admin/bookings')
@admin_required
def get_admin_bookings():
    q = Booking.query
    status = request.args.get('status', 'all')
    if status in STATUSES:
        q = q.filter_by(status=status)
    return jsonify([booking_row(b) for b in q.order_by(Booking.id.desc()).all()])


def _set_status(b, status, reason=''):
    b.status, b.action_date = status, datetime.utcnow()
    b.reject_reason = reason if status == 'rejected' else ''


def _status_mail(b, status, reason='', extra_bcc=''):
    p = booking_payload(b)
    bcc = build_bcc(b.email, b.cc_emails, extra_bcc, contact_emails())
    if status == 'approved':
        notify(send_approve_email, p, bcc_list=bcc)
    elif status == 'rejected':
        p['reason'] = reason
        notify(send_reject_email, p, bcc_list=None)
    elif status == 'cancelled':
        notify(send_cancel_email, p, bcc_list=None)
    elif status == 'pending':
        notify(send_pending_email, p, bcc_list=bcc)


@main_bp.route('/api/admin/<action>/<req_id>', methods=['POST'])
@admin_required
def booking_action(action, req_id):
    status = {'approve': 'approved', 'reject': 'rejected', 'cancel': 'cancelled', 'pending': 'pending'}.get(action)
    if not status:
        abort(404)
    b = Booking.query.filter_by(req_id=req_id).first()
    if not b:
        return jsonify({'error': 'غير موجود'}), 404
    body = request.get_json(silent=True) or {}
    reason = txt(body.get('reason'), 500)
    if status == 'cancelled' and b.status == 'cancelled':
        return jsonify({'error': 'هذا الحجز ملغي بالفعل'}), 400
    _set_status(b, status, reason)
    db.session.commit()
    _status_mail(b, status, reason, body.get('extraBcc', ''))
    return jsonify({'success': True})


@main_bp.route('/api/admin/bookings/bulk', methods=['POST'])
@admin_required
def bookings_bulk():
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    ids = [txt(i, 50) for i in (body.get('reqIds') or [])][:200]
    reason = txt(body.get('reason'), 500)
    rows = Booking.query.filter(Booking.req_id.in_(ids)).all() if ids else []
    if not rows:
        return jsonify({'error': 'لم يُحدَّد أي حجز'}), 400
    done = skipped = 0
    for b in rows:
        if action == 'delete':
            if b.status in ('cancelled', 'rejected'):
                db.session.delete(b)
                done += 1
            else:
                skipped += 1      # حجز قائم لا يُحذف: يُلغى أولاً
            continue
        status = {'approve': 'approved', 'reject': 'rejected', 'cancel': 'cancelled', 'pending': 'pending'}.get(action)
        if not status:
            return jsonify({'error': 'إجراء غير معروف'}), 400
        if b.status == status:
            skipped += 1
            continue
        _set_status(b, status, reason)
        done += 1
    db.session.commit()
    if action != 'delete':
        for b in rows:
            if b.status == {'approve': 'approved', 'reject': 'rejected', 'cancel': 'cancelled', 'pending': 'pending'}[action]:
                _status_mail(b, b.status, reason)
    return jsonify({'success': True, 'done': done, 'skipped': skipped})


@main_bp.route('/api/admin/update/<req_id>', methods=['POST'])
@admin_required
def admin_update_booking(req_id):
    data = request.get_json(silent=True) or {}
    b = Booking.query.filter_by(req_id=req_id).first()
    if not b:
        return jsonify({'error': 'غير موجود'}), 404

    def pick(*keys):
        for k in keys:
            if k in data and data[k] is not None:
                return data[k]
        return None

    name, email, title = pick('full_name', 'name'), pick('email'), pick('title')
    if email is not None and not EMAIL_RE.match(txt(email, 100)):
        return jsonify({'error': 'البريد الإلكتروني غير صالح'}), 400
    start = parse_date(pick('start_date', 'date')) if pick('start_date', 'date') else b.start_date
    end = parse_date(pick('end_date', 'endDate')) if pick('end_date', 'endDate') else (b.end_date or b.start_date)
    if not start or not end or end < start:
        return jsonify({'error': 'تاريخ غير صالح'}), 400
    s_raw, e_raw = pick('start_time', 'startTime'), pick('end_time', 'endTime')
    s_time = clean_time(s_raw) if s_raw is not None else (b.start_time or '')
    e_time = clean_time(e_raw) if e_raw is not None else (b.end_time or '')
    full = bool(pick('full_day', 'fullDay')) if pick('full_day', 'fullDay') is not None else b.full_day
    hall_raw = pick('hall_name', 'hall')
    hall_name = txt(hall_raw, 100) if hall_raw else b.hall_name
    if hall_raw and not Hall.query.filter_by(name_ar=hall_name).first():
        return jsonify({'error': 'القاعة غير صحيحة'}), 400
    if b.status in ('pending', 'approved') and (start, end, s_time, e_time, full, hall_name) != \
            (b.start_date, b.end_date or b.start_date, b.start_time or '', b.end_time or '', b.full_day, b.hall_name):
        conflict = conflict_check(start, end, s_time, e_time, full, hall_name, exclude_id=b.id)
        if conflict:
            return jsonify({'error': f'يتعارض مع حجز موجود ({conflict.req_id})'}), 409
    if name is not None:
        b.full_name = txt(name, 100) or b.full_name
    if email is not None:
        b.email = txt(email, 100)
    if pick('phone') is not None:
        b.phone = txt(pick('phone'), 50)
    if pick('behalf') is not None:
        b.behalf = txt(pick('behalf'), 100)
    if title is not None:
        b.title = txt(title, 200) or b.title
    b.hall_name, b.start_date, b.end_date = hall_name, start, end
    b.start_time, b.end_time, b.full_day = s_time or None, e_time or None, full
    if pick('notes') is not None:
        b.notes = txt(pick('notes'), 2000)
    b.action_date = datetime.utcnow()
    db.session.commit()
    notify(send_update_email, booking_payload(b), bcc_list=build_bcc(b.email, b.cc_emails, contact_emails()))
    return jsonify({'success': True})


@main_bp.route('/api/admin/stats')
@admin_required
def get_admin_stats():
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    by_hall, by_month = {}, {}
    for b in Booking.query.filter_by(status='approved').all():
        by_hall[b.hall_name] = by_hall.get(b.hall_name, 0) + 1
        month = by_month.setdefault(b.start_date.strftime('%Y-%m'), {})
        month[b.hall_name] = month.get(b.hall_name, 0) + 1
    return jsonify({
        'total': Booking.query.count(),
        **{s: Booking.query.filter_by(status=s).count() for s in STATUSES},
        'today': Booking.query.filter(Booking.start_date == today, Booking.status == 'approved').count(),
        'week': Booking.query.filter(Booking.start_date >= week_start, Booking.status == 'approved').count(),
        'byHall': sorted([{'hall': k, 'count': v} for k, v in by_hall.items()], key=lambda x: -x['count']),
        'byMonth': by_month})


# ───────────── القاعات ─────────────
def hall_row(h):
    return {'id': h.id, 'nameAr': h.name_ar, 'nameEn': h.name_en, 'location': h.location, 'code': h.code,
            'capacity': h.capacity, 'equipment': h.equipment, 'description': h.description, 'notes': h.notes,
            'requiresApproval': h.requires_approval, 'active': h.active,
            'bookings': Booking.query.filter_by(hall_name=h.name_ar).count()}


def _hall_fields(h, d):
    h.name_ar, h.name_en = txt(d.get('nameAr'), 100), txt(d.get('nameEn'), 100)
    h.location, h.code, h.capacity = txt(d.get('location'), 200), txt(d.get('code'), 50), txt(d.get('capacity'), 50)
    h.equipment, h.description, h.notes = txt(d.get('equipment'), 1000), txt(d.get('description'), 2000), txt(d.get('notes'), 1000)
    h.requires_approval, h.active = bool(d.get('requiresApproval', False)), bool(d.get('active', True))


@main_bp.route('/api/admin/halls')
@admin_required
def get_admin_halls():
    return jsonify([hall_row(h) for h in Hall.query.order_by(Hall.id).all()])


@main_bp.route('/api/admin/halls/add', methods=['POST'])
@admin_required
def add_hall():
    d = request.get_json(silent=True) or {}
    if not txt(d.get('nameAr'), 100):
        return jsonify({'error': 'اسم القاعة بالعربية مطلوب'}), 400
    if Hall.query.filter_by(name_ar=txt(d.get('nameAr'), 100)).first():
        return jsonify({'error': 'يوجد قاعة بهذا الاسم'}), 400
    h = Hall()
    _hall_fields(h, d)
    db.session.add(h)
    db.session.commit()
    return jsonify({'success': True})


@main_bp.route('/api/admin/halls/update', methods=['POST'])
@admin_required
def update_hall():
    d = request.get_json(silent=True) or {}
    h = db.session.get(Hall, d.get('id'))
    if not h:
        return jsonify({'error': 'Not found'}), 404
    old = h.name_ar
    if not txt(d.get('nameAr'), 100):
        return jsonify({'error': 'اسم القاعة بالعربية مطلوب'}), 400
    if txt(d.get('nameAr'), 100) != old and Hall.query.filter_by(name_ar=txt(d.get('nameAr'), 100)).first():
        return jsonify({'error': 'يوجد قاعة بهذا الاسم'}), 400
    if not bool(d.get('active', True)) and h.active and Hall.query.filter_by(active=True).count() <= 1:
        return jsonify({'error': 'لا يمكن إيقاف آخر قاعة نشطة'}), 400
    _hall_fields(h, d)
    if h.name_ar != old:      # الحجوزات والفترات المحظورة تحمل اسم القاعة: يتبع الاسم الجديد
        Booking.query.filter_by(hall_name=old).update({'hall_name': h.name_ar})
        BlockedPeriod.query.filter_by(hall_name=old).update({'hall_name': h.name_ar})
    db.session.commit()
    return jsonify({'success': True})


def _delete_hall(h):
    """يرجع رسالة عند المنع، وإلا None."""
    if Booking.query.filter_by(hall_name=h.name_ar).first():
        return 'لهذه القاعة حجوزات؛ أوقفها بدل حذفها'
    if h.active and Hall.query.filter_by(active=True).count() <= 1:
        return 'لا يمكن حذف آخر قاعة نشطة'
    BlockedPeriod.query.filter_by(hall_name=h.name_ar).delete()
    db.session.delete(h)
    return None


@main_bp.route('/api/admin/halls/delete/<int:id>', methods=['POST'])
@admin_required
def delete_hall(id):
    h = db.session.get(Hall, id)
    if not h:
        return jsonify({'error': 'Not found'}), 404
    msg = _delete_hall(h)
    if msg:
        return jsonify({'error': msg}), 400
    db.session.commit()
    return jsonify({'success': True})


@main_bp.route('/api/admin/halls/bulk', methods=['POST'])
@admin_required
def halls_bulk():
    d = request.get_json(silent=True) or {}
    rows = Hall.query.filter(Hall.id.in_([int(i) for i in (d.get('ids') or []) if str(i).isdigit()])).all()
    action = d.get('action')
    if not rows or action not in ('activate', 'deactivate', 'delete'):
        return jsonify({'error': 'لم يُحدَّد أي عنصر'}), 400
    done, notes = 0, []
    for h in rows:
        if action == 'delete':
            msg = _delete_hall(h)
            if msg:
                notes.append(f'{h.name_ar}: {msg}')
                continue
        elif action == 'deactivate':
            if h.active and Hall.query.filter_by(active=True).count() <= 1:
                notes.append(f'{h.name_ar}: لا يمكن إيقاف آخر قاعة نشطة')
                continue
            h.active = False
            db.session.flush()
        else:
            h.active = True
        done += 1
    db.session.commit()
    return jsonify({'success': True, 'done': done, 'notes': notes})


# ───────────── الفترات المحظورة ─────────────
@main_bp.route('/api/admin/blocked')
@admin_required
def get_blocked():
    return jsonify([{'id': b.id, 'start': b.start_date.strftime('%Y-%m-%d'), 'end': b.end_date.strftime('%Y-%m-%d'),
                     'hall': b.hall_name or '', 'fromT': b.start_time or '', 'toT': b.end_time or '',
                     'reason': b.reason} for b in BlockedPeriod.query.order_by(BlockedPeriod.start_date.desc()).all()])


@main_bp.route('/api/admin/blocked/add', methods=['POST'])
@admin_required
def add_blocked():
    d = request.get_json(silent=True) or {}
    start, end = parse_date(d.get('start')), parse_date(d.get('end'))
    if not start or not end or end < start:
        return jsonify({'error': 'تاريخ غير صالح'}), 400
    f_t, t_t = clean_time(d.get('fromT')), clean_time(d.get('toT'))
    if bool(f_t) != bool(t_t) or (f_t and t_t <= f_t):
        return jsonify({'error': 'الوقت غير صالح'}), 400
    db.session.add(BlockedPeriod(start_date=start, end_date=end, hall_name=txt(d.get('hall'), 100) or None,
                                 start_time=f_t or None, end_time=t_t or None, reason=txt(d.get('reason'), 200) or 'محظور'))
    db.session.commit()
    return jsonify({'success': True})


@main_bp.route('/api/admin/blocked/delete/<int:id>', methods=['POST'])
@admin_required
def delete_blocked(id):
    bp = db.session.get(BlockedPeriod, id)
    if bp:
        db.session.delete(bp)
        db.session.commit()
    return jsonify({'success': True})


@main_bp.route('/api/admin/blocked/bulk', methods=['POST'])
@admin_required
def blocked_bulk():
    ids = [int(i) for i in (request.get_json(silent=True) or {}).get('ids', []) if str(i).isdigit()]
    n = BlockedPeriod.query.filter(BlockedPeriod.id.in_(ids)).delete(synchronize_session=False) if ids else 0
    db.session.commit()
    return jsonify({'success': True, 'done': n})


# ───────────── جهات الاتصال ─────────────
@main_bp.route('/api/admin/contacts')
@admin_required
def get_contacts():
    return jsonify([{'id': c.id, 'email': c.email, 'name': c.name or '',
                     'addedAt': c.added_at.strftime('%Y-%m-%d %H:%M') if c.added_at else ''}
                    for c in Contact.query.order_by(Contact.id.desc()).all()])


@main_bp.route('/api/admin/contacts/add', methods=['POST'])
@admin_required
def add_contact():
    d = request.get_json(silent=True) or {}
    items = d.get('list') or [{'email': d.get('email'), 'name': d.get('name', '')}]
    added = 0
    for it in items[:500]:
        em = txt(it.get('email'), 100)
        if not EMAIL_RE.match(em) or Contact.query.filter_by(email=em).first():
            continue
        db.session.add(Contact(email=em, name=txt(it.get('name'), 100)))
        added += 1
    db.session.commit()
    return jsonify({'success': True, 'count': added})


@main_bp.route('/api/admin/contacts/update', methods=['POST'])
@admin_required
def update_contact():
    d = request.get_json(silent=True) or {}
    c = db.session.get(Contact, d.get('id'))
    em = txt(d.get('email'), 100)
    if not c or not EMAIL_RE.match(em):
        return jsonify({'error': 'بيانات غير صالحة'}), 400
    other = Contact.query.filter_by(email=em).first()
    if other and other.id != c.id:
        return jsonify({'error': 'هذا البريد مسجّل مسبقاً'}), 400
    c.email, c.name = em, txt(d.get('name'), 100)
    db.session.commit()
    return jsonify({'success': True})


@main_bp.route('/api/admin/contacts/delete/<int:id>', methods=['POST'])
@admin_required
def delete_contact(id):
    c = db.session.get(Contact, id)
    if c:
        db.session.delete(c)
        db.session.commit()
    return jsonify({'success': True})


@main_bp.route('/api/admin/contacts/bulk', methods=['POST'])
@admin_required
def contacts_bulk():
    ids = [int(i) for i in (request.get_json(silent=True) or {}).get('ids', []) if str(i).isdigit()]
    n = Contact.query.filter(Contact.id.in_(ids)).delete(synchronize_session=False) if ids else 0
    db.session.commit()
    return jsonify({'success': True, 'done': n})


def _csv_cell(v):
    """يمنع تنفيذ الصيغ عند فتح الملف في Excel."""
    v = '' if v is None else str(v)
    return "'" + v if v[:1] in ('=', '+', '-', '@') else v


@main_bp.route('/api/admin/contacts/export')
@admin_required
def export_contacts():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['email', 'name', 'added_at'])
    for c in Contact.query.order_by(Contact.id.asc()).all():
        w.writerow([_csv_cell(c.email), _csv_cell(c.name), c.added_at.strftime('%Y-%m-%d %H:%M') if c.added_at else ''])
    return Response('﻿' + buf.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="contacts.csv"'})


# ───────────── المستخدمون ─────────────
@main_bp.route('/api/admin/users')
@admin_required
def get_users():
    me = auth.current_user()
    return jsonify([dict(u.to_dict(), me=(u.id == me.id)) for u in AdminUser.query.order_by(AdminUser.id).all()])


def _user_fields(d, u=None):
    username, email = txt(d.get('username'), 80), txt(d.get('email'), 150)
    if not re.fullmatch(r'[A-Za-z0-9_.@-]{3,80}', username):
        return None, 'اسم المستخدم من 3 إلى 80 حرفاً (أحرف إنجليزية وأرقام)'
    if email and not EMAIL_RE.match(email):
        return None, 'البريد الإلكتروني غير صالح'
    other = AdminUser.query.filter(db.func.lower(AdminUser.username) == username.lower()).first()
    if other and (u is None or other.id != u.id):
        return None, 'اسم المستخدم مستخدم مسبقاً'
    return {'username': username, 'email': email, 'name': txt(d.get('name'), 120) or username}, None


@main_bp.route('/api/admin/users/add', methods=['POST'])
@admin_required
def add_user():
    d = request.get_json(silent=True) or {}
    f, msg = _user_fields(d)
    pw = str(d.get('password') or '')
    if msg or len(pw) < 8:
        return jsonify({'error': msg or 'كلمة المرور 8 أحرف على الأقل'}), 400
    db.session.add(AdminUser(password_hash=auth.hash_password(pw), role='admin', active=True, **f))
    db.session.commit()
    return jsonify({'success': True})


@main_bp.route('/api/admin/users/update', methods=['POST'])
@admin_required
def update_user():
    d = request.get_json(silent=True) or {}
    u = db.session.get(AdminUser, d.get('id'))
    if not u:
        return jsonify({'error': 'Not found'}), 404
    f, msg = _user_fields(d, u)
    if msg:
        return jsonify({'error': msg}), 400
    active = bool(d.get('active', True))
    if not active and u.active and (u.id == auth.current_user().id or AdminUser.query.filter_by(active=True).count() <= 1):
        return jsonify({'error': 'لا يمكن إيقاف حسابك الحالي أو آخر مدير'}), 400
    u.username, u.email, u.name, u.active = f['username'], f['email'], f['name'], active
    pw = str(d.get('password') or '')
    if pw:
        if len(pw) < 8:
            return jsonify({'error': 'كلمة المرور 8 أحرف على الأقل'}), 400
        u.password_hash = auth.hash_password(pw)
    db.session.commit()
    return jsonify({'success': True})


def _delete_user(u):
    if u.id == auth.current_user().id:
        return 'لا يمكن حذف حسابك الحالي'
    if u.active and AdminUser.query.filter_by(active=True).count() <= 1:
        return 'لا يمكن حذف آخر مدير'
    db.session.delete(u)
    return None


@main_bp.route('/api/admin/users/delete/<int:id>', methods=['POST'])
@admin_required
def delete_user(id):
    u = db.session.get(AdminUser, id)
    if not u:
        return jsonify({'error': 'Not found'}), 404
    msg = _delete_user(u)
    if msg:
        return jsonify({'error': msg}), 400
    db.session.commit()
    return jsonify({'success': True})


@main_bp.route('/api/admin/users/bulk', methods=['POST'])
@admin_required
def users_bulk():
    d = request.get_json(silent=True) or {}
    rows = AdminUser.query.filter(AdminUser.id.in_([int(i) for i in (d.get('ids') or []) if str(i).isdigit()])).all()
    action = d.get('action')
    if not rows or action not in ('activate', 'deactivate', 'delete'):
        return jsonify({'error': 'لم يُحدَّد أي عنصر'}), 400
    me, done, notes = auth.current_user(), 0, []
    for u in rows:
        if action == 'delete':
            msg = _delete_user(u)
        elif action == 'deactivate':
            msg = None
            if u.id == me.id or (u.active and AdminUser.query.filter_by(active=True).count() <= 1):
                msg = 'لا يمكن إيقاف حسابك الحالي أو آخر مدير'
            else:
                u.active = False
                db.session.flush()
        else:
            msg, u.active = None, True
        if msg:
            notes.append(f'{u.username}: {msg}')
        else:
            done += 1
    db.session.commit()
    return jsonify({'success': True, 'done': done, 'notes': notes})


@main_bp.route('/api/admin/password', methods=['POST'])
@admin_required
def change_password():
    d = request.get_json(silent=True) or {}
    u = auth.current_user()
    new = str(d.get('new') or '')
    if not auth.password_ok(u, d.get('current')):
        return jsonify({'error': 'كلمة المرور الحالية غير صحيحة'}), 400
    if len(new) < 8:
        return jsonify({'error': 'كلمة المرور الجديدة 8 أحرف على الأقل'}), 400
    u.password_hash = auth.hash_password(new)
    db.session.commit()
    auth.sign_in(u, False)
    return jsonify({'success': True, 'csrf': auth.csrf_token()})


# ───────────── الإعدادات والهوية ─────────────
@main_bp.route('/api/admin/settings')
@admin_required
def get_settings():
    from utils.brand import get_brand
    b = get_brand()
    return jsonify({'orgAr': b['org_ar'], 'orgEn': b['org_en'], 'accent': b['accent'], 'logo': b['logo_url'] or '',
                    'mail': graph_ready(), 'sender': current_app.config.get('MS_SENDER_EMAIL', '')})


@main_bp.route('/api/admin/settings', methods=['POST'])
@admin_required
def save_settings():
    from utils.brand import set_identity
    d = request.get_json(silent=True) or {}
    accent = txt(d.get('accent'), 7)
    if accent and not re.fullmatch(r'#[0-9a-fA-F]{6}', accent):
        return jsonify({'error': 'اللون غير صالح'}), 400
    set_identity(txt(d.get('orgAr'), 300), txt(d.get('orgEn'), 300), accent or None)
    return jsonify({'success': True})


@main_bp.route('/api/admin/logo', methods=['POST'])
@admin_required
def upload_logo():
    from utils.brand import save_logo
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'لم يُحدَّد ملف'}), 400
    msg = save_logo(f)
    return (jsonify({'error': msg}), 400) if msg else jsonify({'success': True})


@main_bp.route('/api/admin/logo/delete', methods=['POST'])
@admin_required
def delete_logo():
    from utils.brand import remove_logo
    remove_logo()
    return jsonify({'success': True})
