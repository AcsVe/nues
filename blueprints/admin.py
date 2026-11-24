"""لوحة التحكم: صفحات الدخول والوحة، وواجهتها البرمجية المحمية بالصلاحيات ورمز CSRF."""
import csv
import hashlib
import io
import re
import secrets
from datetime import datetime, timedelta

from flask import (Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request, session,
                   url_for)

import email_service as mail
import services as svc
from models import (AdminUser, AppSetting, BlockedPeriod, Booking, BookingComment, BookingReminder, CATEGORIES,
                    CATEGORY_NAMES, Contact, Hall, PasswordReset, db)
from services import err_json, parse_date, txt
from utils import auth
from utils.auth import admin_required
from utils.perms import CATALOGUE, PRESETS, can, clean

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
api_bp = Blueprint('admin_api', __name__, url_prefix='/api/admin')


def _lang():
    return 'en' if (request.args.get('lang') or request.form.get('lang')) == 'en' else 'ar'


def _safe_next(url):
    return url if url and url.startswith('/') and not url.startswith('//') else ''


def me_json(u):
    perms = (list(CATALOGUE) + ['users']) if u.is_sysadmin else u.perm_list()
    return {'id': u.id, 'username': u.username, 'name': u.name or u.username, 'sysadmin': bool(u.is_sysadmin), 'perms': perms}


# ───────────── الصفحات ─────────────
@admin_bp.route('', strict_slashes=False)
def dashboard():
    u = auth.current_user()
    if not u:
        return redirect(url_for('admin.login', lang=_lang(), next='/admin'))
    return render_template('admin/dashboard.html', lang=_lang(), me=me_json(u), csrf=auth.csrf_token(),
                           categories=[{'key': k, 'ar': CATEGORY_NAMES[k][0], 'en': CATEGORY_NAMES[k][1]} for k in CATEGORIES],
                           catalogue=[{'key': k, 'ar': v[0], 'en': v[1], 'group': v[2]} for k, v in CATALOGUE.items()],
                           presets=PRESETS)


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    lang, error = _lang(), None
    if auth.current_user() and request.method == 'GET':
        return redirect(_safe_next(request.args.get('next')) or url_for('admin.dashboard', lang=lang))
    if request.method == 'POST':
        ip = auth.client_ip()
        if auth.too_many(ip):
            error = 'محاولات كثيرة غير صحيحة — انتظر 15 دقيقة ثم أعد المحاولة' if lang == 'ar' else 'Too many failed attempts - wait 15 minutes and try again'
        else:
            ident = txt(request.form.get('username'), 150).lower()
            user = AdminUser.query.filter(db.func.lower(AdminUser.username) == ident).first() or \
                (AdminUser.query.filter(db.func.lower(AdminUser.email) == ident).first() if ident else None)
            if user and user.active and auth.password_ok(user, request.form.get('password')):
                auth.clear_failures(ip)
                user.last_login = datetime.utcnow()
                db.session.commit()
                auth.sign_in(user, request.form.get('remember') == '1')
                return redirect(_safe_next(request.form.get('next')) or url_for('admin.dashboard', lang=lang))
            auth.note_failure(ip)
            error = 'اسم المستخدم أو كلمة المرور غير صحيحة' if lang == 'ar' else 'Incorrect username or password'
    return render_template('admin/login.html', lang=lang, mode='login', error=error, next=_safe_next(request.values.get('next')),
                           username=txt(request.form.get('username'), 150), info=request.args.get('info', ''))


@admin_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('admin.login', lang=_lang()))


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


@admin_bp.route('/forgot', methods=['GET', 'POST'])
def forgot_password():
    lang, sent = _lang(), False
    if request.method == 'POST':
        sent = True       # الجواب واحد دائماً: لا يُكشف أي حساب موجود
        if svc.rate_ok('forgot', 5, 3600):
            ident = txt(request.form.get('username'), 150).lower()
            user = AdminUser.query.filter(db.func.lower(AdminUser.username) == ident).first() or \
                AdminUser.query.filter(db.func.lower(AdminUser.email) == ident).first()
            if user and user.active and mail.EMAIL_OK(user.email):
                token = secrets.token_urlsafe(32)
                db.session.add(PasswordReset(user_id=user.id, token_hash=_token_hash(token),
                                             expires_at=datetime.utcnow() + timedelta(hours=1)))
                db.session.commit()
                base = (current_app.config.get('BASE_URL') or request.host_url).rstrip('/')
                svc.notify(mail.send_password_reset, user.email, user.name, f'{base}/admin/reset/{token}')
    return render_template('admin/login.html', lang=lang, mode='forgot', sent=sent, error=None, next='', username='', info='')


@admin_bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    lang = _lang()
    row = PasswordReset.query.filter_by(token_hash=_token_hash(token), used=False).first()
    if not row or row.expires_at < datetime.utcnow():
        return render_template('admin/login.html', lang=lang, mode='invalid', error=None, next='', username='', info='')
    error = None
    if request.method == 'POST':
        pw, pw2 = request.form.get('password') or '', request.form.get('password2') or ''
        if len(pw) < 8:
            error = 'كلمة المرور 8 أحرف على الأقل' if lang == 'ar' else 'The password needs at least 8 characters'
        elif pw != pw2:
            error = 'كلمتا المرور غير متطابقتين' if lang == 'ar' else 'The passwords do not match'
        else:
            user = db.session.get(AdminUser, row.user_id)
            user.password_hash = auth.hash_password(pw)
            row.used = True
            db.session.commit()
            return redirect(url_for('admin.login', lang=lang, info='reset'))
    return render_template('admin/login.html', lang=lang, mode='reset', error=error, next='', username='', info='')


# ───────────── الجلسة ─────────────
@api_bp.route('/session')
def admin_session():
    u = auth.current_user()
    return jsonify({'loggedIn': bool(u), 'csrf': auth.csrf_token() if u else ''})


@api_bp.route('/me')
@admin_required
def admin_me():
    return jsonify(dict(me_json(auth.current_user()), csrf=auth.csrf_token()))


# ───────────── الحجوزات ─────────────
def booking_row(b):
    return {'reqId': b.req_id, 'name': b.full_name, 'email': b.email, 'phone': b.phone, 'behalf': b.behalf,
            'title': b.title, 'hall': b.hall_name, 'date': b.start_date.strftime('%Y-%m-%d'),
            'endDate': (b.end_date or b.start_date).strftime('%Y-%m-%d'), 'startTime': b.start_time or '',
            'endTime': b.end_time or '', 'fullDay': b.full_day, 'notes': b.notes, 'status': b.status,
            'rejectReason': b.reject_reason or '', 'cancelReason': b.cancel_reason or '', 'ccEmails': b.cc_emails or '',
            'approvedBy': b.approved_by or '', 'created': b.created_at.strftime('%Y-%m-%d') if b.created_at else '',
            'comments': BookingComment.query.filter_by(booking_id=b.id).count(),
            'attendees': b.attendees or '', 'extras': [x for x in (b.extras or '').splitlines() if x],
            'seriesId': b.series_id or '', 'seriesNo': b.series_no or 0, 'seriesCount': svc.series_count(b),
            'attachments': [a for a in (b.attachments or '').split(',') if a.startswith('/uploads/')]}


@api_bp.route('/bookings')
@admin_required('bookings.view')
def get_bookings():
    q = Booking.query
    status = request.args.get('status', 'all')
    if status in svc.STATUSES:
        q = q.filter_by(status=status)
    return jsonify([booking_row(b) for b in q.order_by(Booking.id.desc()).all()])


@api_bp.route('/calendar')
@admin_required(('calendar', 'bookings.view'))
def admin_calendar():
    import calendar as _cal
    y = request.args.get('year', datetime.now().year, type=int)
    m = request.args.get('month', datetime.now().month, type=int)
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        return err_json('شهر غير صالح')
    from datetime import date as d
    first, last = d(y, m, 1), d(y, m, _cal.monthrange(y, m)[1])
    rows = Booking.query.filter(Booking.start_date <= last, Booking.end_date >= first,
                                ~Booking.status.in_(['rejected', 'cancelled'])).all()
    return jsonify([booking_row(b) for b in rows])


@api_bp.route('/<action>/<req_id>', methods=['POST'])
@admin_required('bookings.manage')
def booking_action(action, req_id):
    status = {'approve': 'approved', 'reject': 'rejected', 'cancel': 'cancelled', 'pending': 'pending'}.get(action)
    if not status:
        abort(404)
    b = Booking.query.filter_by(req_id=req_id).first()
    if not b:
        return err_json('غير موجود', 404)
    body = request.get_json(silent=True) or {}
    reason = txt(body.get('reason'), 500)
    if status == 'rejected' and not reason:
        return err_json('سبب الرفض مطلوب')
    if status == 'cancelled' and b.status == 'cancelled':
        return err_json('هذا الحجز ملغي بالفعل')
    if status == 'approved':
        # لا يُعتمد حجز يتعارض مع حجز معتمد آخر (قد يكون قُدّم في الموعد نفسه)
        other = Booking.query.filter(Booking.hall_name == b.hall_name, Booking.id != b.id, Booking.status == 'approved',
                                     Booking.start_date <= (b.end_date or b.start_date), Booking.end_date >= b.start_date).all()
        for o in other:
            if b.full_day or o.full_day or svc.times_overlap(b.start_time or '', b.end_time or '', o.start_time or '', o.end_time or ''):
                return err_json(f'يتعارض مع حجز معتمد ({o.req_id})', 409)
    by = auth.current_user().name or auth.current_user().username
    if body.get('scope') == 'series' and b.series_id:
        n, skipped = svc.apply_series(b, status, reason, by=by, extra_bcc=body.get('extraBcc', ''))
        return jsonify({'success': True, 'count': n, 'skipped': skipped})
    svc.apply_status(b, status, reason, by=by, extra_bcc=body.get('extraBcc', ''))
    return jsonify({'success': True})


@api_bp.route('/bookings/bulk', methods=['POST'])
@admin_required('bookings.manage')
def bookings_bulk():
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    ids = [txt(i, 50) for i in (body.get('reqIds') or [])][:200]
    reason = txt(body.get('reason'), 500)
    rows = Booking.query.filter(Booking.req_id.in_(ids)).all() if ids else []
    if not rows:
        return err_json('لم يُحدَّد أي حجز')
    if action == 'reject' and not reason:
        return err_json('سبب الرفض مطلوب')
    smap = {'approve': 'approved', 'reject': 'rejected', 'cancel': 'cancelled', 'pending': 'pending'}
    if action != 'delete' and action not in smap:
        return err_json('إجراء غير معروف')
    done = skipped = 0
    by = auth.current_user().name or auth.current_user().username
    for b in rows:
        if action == 'delete':
            if b.status in ('cancelled', 'rejected'):
                BookingReminder.query.filter_by(booking_id=b.id).delete()
                BookingComment.query.filter_by(booking_id=b.id).delete()
                db.session.delete(b)
                done += 1
            else:
                skipped += 1      # حجز قائم لا يُحذف: يُلغى أولاً
            continue
        if b.status == smap[action]:
            skipped += 1
            continue
        svc.apply_status(b, smap[action], reason, by=by)
        done += 1
    db.session.commit()
    return jsonify({'success': True, 'done': done, 'skipped': skipped})


@api_bp.route('/update/<req_id>', methods=['POST'])
@admin_required('bookings.manage')
def admin_update_booking(req_id):
    data = request.get_json(silent=True) or {}
    b = Booking.query.filter_by(req_id=req_id).first()
    if not b:
        return err_json('غير موجود', 404)
    email = txt(data.get('email', b.email), 100)
    if not svc.EMAIL_RE.match(email):
        return err_json('البريد الإلكتروني غير صالح')
    start = parse_date(data.get('date')) if data.get('date') else b.start_date
    end = parse_date(data.get('endDate')) if data.get('endDate') else (b.end_date or b.start_date)
    if not start or not end or end < start:
        return err_json('تاريخ غير صالح')
    full = bool(data['fullDay']) if 'fullDay' in data else bool(b.full_day)
    s_time = svc.clean_time(data['startTime']) if 'startTime' in data else (b.start_time or '')
    e_time = svc.clean_time(data['endTime']) if 'endTime' in data else (b.end_time or '')
    if not full and (not s_time or (e_time and e_time <= s_time)):
        return err_json('الوقت غير صالح')
    hall_name = txt(data.get('hall'), 100) or b.hall_name
    if not Hall.query.filter_by(name_ar=hall_name).first():
        return err_json('المبنى أو المرفق غير صحيح')
    if b.status in ('pending', 'approved'):
        c = svc.conflict_check(start, end, s_time, e_time, full, hall_name, exclude_id=b.id)
        if c:
            return err_json(f'يتعارض مع حجز موجود ({c.req_id})', 409)
    b.full_name = txt(data.get('name'), 100) or b.full_name
    b.email = email
    b.phone, b.behalf = txt(data.get('phone', b.phone), 50), txt(data.get('behalf', b.behalf), 100)
    b.title = txt(data.get('title'), 200) or b.title
    b.hall_name, b.start_date, b.end_date = hall_name, start, end
    b.start_time, b.end_time, b.full_day = s_time or None, e_time or None, full
    b.notes = txt(data.get('notes', b.notes), 2000)
    b.action_date = datetime.utcnow()
    db.session.commit()
    svc.notify(mail.send_update_email, svc.booking_payload(b),
               bcc_list=svc.build_bcc(b.email, b.cc_emails, svc.contact_emails(hall_name, 'notify_approved')))
    return jsonify({'success': True})


@api_bp.route('/comments/<req_id>')
@admin_required('bookings.view')
def get_comments(req_id):
    b = Booking.query.filter_by(req_id=req_id).first()
    if not b:
        return err_json('غير موجود', 404)
    rows = BookingComment.query.filter_by(booking_id=b.id).order_by(BookingComment.id).all()
    return jsonify([{'author': c.author_name or '', 'body': c.body, 'at': c.created_at.strftime('%Y-%m-%d %H:%M')} for c in rows])


@api_bp.route('/comments/<req_id>', methods=['POST'])
@admin_required('bookings.manage')
def add_comment(req_id):
    b = Booking.query.filter_by(req_id=req_id).first()
    body = txt((request.get_json(silent=True) or {}).get('body'), 2000)
    if not b or not body:
        return err_json('تعليق فارغ')
    u = auth.current_user()
    db.session.add(BookingComment(booking_id=b.id, author_name=u.name or u.username, body=body))
    db.session.commit()
    for c in svc._contacts_for(b.hall_name, 'notify_comment'):
        svc.notify(mail.send_comment_email, c.email, svc.booking_payload(b), u.name or u.username, body)
    return jsonify({'success': True})


@api_bp.route('/stats')
@admin_required(('bookings.view', 'reports', 'calendar'))
def get_stats():
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    cats = {h.name_ar: h.category or 'hall' for h in Hall.query.all()}
    by_hall, by_month, by_cat = {}, {}, {}
    for b in Booking.query.filter_by(status='approved').all():
        by_hall[b.hall_name] = by_hall.get(b.hall_name, 0) + 1
        month = by_month.setdefault(b.start_date.strftime('%Y-%m'), {})
        month[b.hall_name] = month.get(b.hall_name, 0) + 1
        c = cats.get(b.hall_name, 'hall')
        by_cat[c] = by_cat.get(c, 0) + 1
    upcoming = Booking.query.filter(Booking.status == 'approved', Booking.end_date >= today,
                                    Booking.start_date <= today + timedelta(days=7)).order_by(Booking.start_date, Booking.start_time).limit(12).all()
    return jsonify({
        'total': Booking.query.count(), **{s: Booking.query.filter_by(status=s).count() for s in svc.STATUSES},
        'today': Booking.query.filter(Booking.start_date <= today, Booking.end_date >= today, Booking.status == 'approved').count(),
        'week': Booking.query.filter(Booking.start_date >= week_start, Booking.start_date < week_start + timedelta(days=7), Booking.status == 'approved').count(),
        'byHall': sorted([{'hall': k, 'count': v} for k, v in by_hall.items()], key=lambda x: -x['count']),
        'byCategory': [{'category': k, 'count': v} for k, v in by_cat.items()], 'byMonth': by_month,
        'upcoming': [booking_row(b) for b in upcoming]})


# ───────────── المباني والمرافق ─────────────
def hall_row(h):
    ar, en = CATEGORY_NAMES.get(h.category or 'hall', CATEGORY_NAMES['hall'])
    return {'id': h.id, 'nameAr': h.name_ar, 'nameEn': h.name_en, 'location': h.location, 'code': h.code,
            'capacity': h.capacity, 'equipment': h.equipment, 'description': h.description, 'notes': h.notes,
            'requiresApproval': h.requires_approval, 'active': h.active, 'category': h.category or 'hall', 'extras': h.extras or '',
            'categoryAr': ar, 'categoryEn': en, 'bookings': Booking.query.filter_by(hall_name=h.name_ar).count()}


def _hall_fields(h, d):
    h.name_ar, h.name_en = txt(d.get('nameAr'), 100), txt(d.get('nameEn'), 100)
    h.location, h.code, h.capacity = txt(d.get('location'), 200), txt(d.get('code'), 50), txt(d.get('capacity'), 50)
    h.equipment, h.description, h.notes = txt(d.get('equipment'), 1000), txt(d.get('description'), 2000), txt(d.get('notes'), 1000)
    h.extras = '\n'.join(dict.fromkeys(x.strip()[:80] for x in str(d.get('extras') or '').splitlines() if x.strip()))[:2000]
    h.requires_approval, h.active = bool(d.get('requiresApproval', False)), bool(d.get('active', True))
    cat = txt(d.get('category'), 20)
    h.category = cat if cat in CATEGORIES else 'hall'


@api_bp.route('/halls')
@admin_required(('halls', 'bookings.view', 'bookings.manage', 'blocked', 'contacts'))
def get_halls():
    return jsonify([hall_row(h) for h in Hall.query.order_by(Hall.sort_order, Hall.id).all()])


@api_bp.route('/halls/add', methods=['POST'])
@admin_required('halls')
def add_hall():
    d = request.get_json(silent=True) or {}
    if not txt(d.get('nameAr'), 100):
        return err_json('الاسم بالعربية مطلوب')
    if Hall.query.filter_by(name_ar=txt(d.get('nameAr'), 100)).first():
        return err_json('يوجد مبنى أو مرفق بهذا الاسم')
    h = Hall()
    _hall_fields(h, d)
    db.session.add(h)
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/halls/update', methods=['POST'])
@admin_required('halls')
def update_hall():
    d = request.get_json(silent=True) or {}
    h = db.session.get(Hall, d.get('id'))
    if not h:
        return err_json('غير موجود', 404)
    old, name = h.name_ar, txt(d.get('nameAr'), 100)
    if not name:
        return err_json('الاسم بالعربية مطلوب')
    if name != old and Hall.query.filter_by(name_ar=name).first():
        return err_json('يوجد مبنى أو مرفق بهذا الاسم')
    if not bool(d.get('active', True)) and h.active and Hall.query.filter_by(active=True).count() <= 1:
        return err_json('لا يمكن إيقاف آخر مبنى أو مرفق فعّال')
    _hall_fields(h, d)
    if h.name_ar != old:          # الحجوزات والفترات وجهات الاتصال تحمل الاسم: يتبع الاسم الجديد
        Booking.query.filter_by(hall_name=old).update({'hall_name': h.name_ar})
        BlockedPeriod.query.filter_by(hall_name=old).update({'hall_name': h.name_ar})
        Contact.query.filter_by(hall_name=old).update({'hall_name': h.name_ar})
    db.session.commit()
    return jsonify({'success': True})


def _delete_hall(h):
    if Booking.query.filter_by(hall_name=h.name_ar).first():
        return 'له حجوزات؛ أوقفه بدل حذفه'
    if h.active and Hall.query.filter_by(active=True).count() <= 1:
        return 'لا يمكن حذف آخر مبنى أو مرفق فعّال'
    BlockedPeriod.query.filter_by(hall_name=h.name_ar).delete()
    Contact.query.filter_by(hall_name=h.name_ar).update({'hall_name': None})
    db.session.delete(h)
    return None


@api_bp.route('/halls/delete/<int:id>', methods=['POST'])
@admin_required('halls')
def delete_hall(id):
    h = db.session.get(Hall, id)
    if not h:
        return err_json('غير موجود', 404)
    msg = _delete_hall(h)
    if msg:
        return err_json(msg)
    db.session.commit()
    return jsonify({'success': True})


def _ids(body):
    return [int(i) for i in (body.get('ids') or []) if str(i).isdigit()]


@api_bp.route('/halls/bulk', methods=['POST'])
@admin_required('halls')
def halls_bulk():
    d = request.get_json(silent=True) or {}
    rows = Hall.query.filter(Hall.id.in_(_ids(d))).all()
    action = d.get('action')
    if not rows or action not in ('activate', 'deactivate', 'delete'):
        return err_json('لم يُحدَّد أي عنصر')
    done, notes = 0, []
    for h in rows:
        if action == 'delete':
            msg = _delete_hall(h)
            if msg:
                notes.append(f'{h.name_ar}: {msg}')
                continue
        elif action == 'deactivate':
            if h.active and Hall.query.filter_by(active=True).count() <= 1:
                notes.append(f'{h.name_ar}: لا يمكن إيقاف آخر مبنى أو مرفق فعّال')
                continue
            h.active = False
            db.session.flush()
        else:
            h.active = True
        done += 1
    db.session.commit()
    return jsonify({'success': True, 'done': done, 'notes': notes})


# ───────────── الفترات غير المتاحة ─────────────
@api_bp.route('/blocked')
@admin_required('blocked')
def get_blocked():
    return jsonify([{'id': b.id, 'start': b.start_date.strftime('%Y-%m-%d'), 'end': b.end_date.strftime('%Y-%m-%d'),
                     'hall': b.hall_name or '', 'fromT': b.start_time or '', 'toT': b.end_time or '', 'reason': b.reason}
                    for b in BlockedPeriod.query.order_by(BlockedPeriod.start_date.desc()).all()])


@api_bp.route('/blocked/add', methods=['POST'])
@admin_required('blocked')
def add_blocked():
    d = request.get_json(silent=True) or {}
    start, end = parse_date(d.get('start')), parse_date(d.get('end'))
    if not start or not end or end < start:
        return err_json('تاريخ غير صالح')
    f_t, t_t = svc.clean_time(d.get('fromT')), svc.clean_time(d.get('toT'))
    if bool(f_t) != bool(t_t) or (f_t and t_t <= f_t):
        return err_json('الوقت غير صالح')
    db.session.add(BlockedPeriod(start_date=start, end_date=end, hall_name=txt(d.get('hall'), 100) or None,
                                 start_time=f_t or None, end_time=t_t or None, reason=txt(d.get('reason'), 200) or 'محظور'))
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/blocked/delete/<int:id>', methods=['POST'])
@admin_required('blocked')
def delete_blocked(id):
    bp = db.session.get(BlockedPeriod, id)
    if bp:
        db.session.delete(bp)
        db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/blocked/bulk', methods=['POST'])
@admin_required('blocked')
def blocked_bulk():
    ids = _ids(request.get_json(silent=True) or {})
    n = BlockedPeriod.query.filter(BlockedPeriod.id.in_(ids)).delete(synchronize_session=False) if ids else 0
    db.session.commit()
    return jsonify({'success': True, 'done': n})


# ───────────── جهات الاتصال ─────────────
FLAGS = ('notify_new', 'new_readonly', 'notify_approved', 'notify_comment', 'notify_staff_reminder')


def contact_row(c):
    row = {'id': c.id, 'email': c.email, 'name': c.name or '', 'hall': c.hall_name or '',
           'addedAt': c.added_at.strftime('%Y-%m-%d %H:%M') if c.added_at else ''}
    for f in FLAGS:
        v = getattr(c, f)
        row[f] = (f in ('notify_new', 'notify_approved')) if v is None else bool(v)
    return row


def _apply_flags(c, d):
    for f in FLAGS:
        if f in d:
            setattr(c, f, bool(d[f]))
    hall = txt(d.get('hall'), 100)
    if 'hall' in d:
        c.hall_name = hall if hall and Hall.query.filter_by(name_ar=hall).first() else None


@api_bp.route('/contacts')
@admin_required('contacts')
def get_contacts():
    return jsonify([contact_row(c) for c in Contact.query.order_by(Contact.id.desc()).all()])


@api_bp.route('/contacts/add', methods=['POST'])
@admin_required('contacts')
def add_contact():
    d = request.get_json(silent=True) or {}
    items = d.get('list') or [dict(d)]
    added = 0
    for it in items[:500]:
        em = txt(it.get('email'), 100)
        if not svc.EMAIL_RE.match(em) or Contact.query.filter_by(email=em).first():
            continue
        c = Contact(email=em, name=txt(it.get('name'), 100), notify_new=True, new_readonly=False, notify_approved=True,
                    notify_comment=False, notify_staff_reminder=False)
        _apply_flags(c, dict(d, hall=it.get('hall', d.get('hall'))) if not d.get('list') else it)
        db.session.add(c)
        added += 1
    db.session.commit()
    return jsonify({'success': True, 'count': added})


@api_bp.route('/contacts/update', methods=['POST'])
@admin_required('contacts')
def update_contact():
    d = request.get_json(silent=True) or {}
    c = db.session.get(Contact, d.get('id'))
    em = txt(d.get('email'), 100)
    if not c or not svc.EMAIL_RE.match(em):
        return err_json('بيانات غير صالحة')
    other = Contact.query.filter_by(email=em).first()
    if other and other.id != c.id:
        return err_json('هذا البريد مسجّل مسبقاً')
    c.email, c.name = em, txt(d.get('name'), 100)
    _apply_flags(c, d)
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/contacts/delete/<int:id>', methods=['POST'])
@admin_required('contacts')
def delete_contact(id):
    c = db.session.get(Contact, id)
    if c:
        db.session.delete(c)
        db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/contacts/bulk', methods=['POST'])
@admin_required('contacts')
def contacts_bulk():
    d = request.get_json(silent=True) or {}
    ids, action = _ids(d), d.get('action', 'delete')
    rows = Contact.query.filter(Contact.id.in_(ids)).all() if ids else []
    if action == 'delete':
        for c in rows:
            db.session.delete(c)
    elif action in FLAGS or action in tuple('off_' + f for f in FLAGS):
        flag = action.replace('off_', '')
        for c in rows:
            setattr(c, flag, not action.startswith('off_'))
    else:
        return err_json('إجراء غير معروف')
    db.session.commit()
    return jsonify({'success': True, 'done': len(rows)})


def _csv_cell(v):
    """يمنع تنفيذ الصيغ عند فتح الملف في Excel."""
    v = '' if v is None else str(v)
    return "'" + v if v[:1] in ('=', '+', '-', '@') else v


@api_bp.route('/contacts/export')
@admin_required('contacts')
def export_contacts():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['email', 'name', 'hall', 'added_at'])
    for c in Contact.query.order_by(Contact.id.asc()).all():
        w.writerow([_csv_cell(c.email), _csv_cell(c.name), _csv_cell(c.hall_name), c.added_at.strftime('%Y-%m-%d %H:%M') if c.added_at else ''])
    return Response('﻿' + buf.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="contacts.csv"'})


# ───────────── المستخدمون والصلاحيات (مدير النظام فقط) ─────────────
@api_bp.route('/users')
@admin_required(sysadmin=True)
def get_users():
    me = auth.current_user()
    return jsonify([dict(u.to_dict(), me=(u.id == me.id)) for u in AdminUser.query.order_by(AdminUser.id).all()])


def _user_fields(d, u=None):
    username, email = txt(d.get('username'), 80), txt(d.get('email'), 150)
    if not re.fullmatch(r'[A-Za-z0-9_.@-]{3,80}', username):
        return None, 'اسم المستخدم من 3 إلى 80 حرفاً (أحرف إنجليزية وأرقام)'
    if email and not svc.EMAIL_RE.match(email):
        return None, 'البريد الإلكتروني غير صالح'
    other = AdminUser.query.filter(db.func.lower(AdminUser.username) == username.lower()).first()
    if other and (u is None or other.id != u.id):
        return None, 'اسم المستخدم مستخدم مسبقاً'
    return {'username': username, 'email': email, 'name': txt(d.get('name'), 120) or username,
            'perms': ','.join(clean(d.get('perms') or []))}, None


@api_bp.route('/users/add', methods=['POST'])
@admin_required(sysadmin=True)
def add_user():
    d = request.get_json(silent=True) or {}
    f, msg = _user_fields(d)
    pw = str(d.get('password') or '')
    if msg or len(pw) < 8:
        return err_json(msg or 'كلمة المرور 8 أحرف على الأقل')
    db.session.add(AdminUser(password_hash=auth.hash_password(pw), role='user', active=True, is_sysadmin=bool(d.get('sysadmin')), **f))
    db.session.commit()
    return jsonify({'success': True})


def _sysadmins_left(excluding):
    return AdminUser.query.filter(AdminUser.is_sysadmin.is_(True), AdminUser.active.is_(True), AdminUser.id != excluding.id).count()


@api_bp.route('/users/update', methods=['POST'])
@admin_required(sysadmin=True)
def update_user():
    d = request.get_json(silent=True) or {}
    u = db.session.get(AdminUser, d.get('id'))
    if not u:
        return err_json('غير موجود', 404)
    f, msg = _user_fields(d, u)
    if msg:
        return err_json(msg)
    active, sysadmin = bool(d.get('active', True)), bool(d.get('sysadmin', u.is_sysadmin))
    if u.is_sysadmin and (not active or not sysadmin) and _sysadmins_left(u) < 1:
        return err_json('لا يمكن إيقاف آخر مدير للنظام أو سحب صلاحيته')
    if not active and u.id == auth.current_user().id:
        return err_json('لا يمكن إيقاف حسابك الحالي')
    u.username, u.email, u.name, u.perms = f['username'], f['email'], f['name'], f['perms']
    u.active, u.is_sysadmin = active, sysadmin
    pw = str(d.get('password') or '')
    if pw:
        if len(pw) < 8:
            return err_json('كلمة المرور 8 أحرف على الأقل')
        u.password_hash = auth.hash_password(pw)
    db.session.commit()
    return jsonify({'success': True})


def _delete_user(u):
    if u.id == auth.current_user().id:
        return 'لا يمكن حذف حسابك الحالي'
    if u.is_sysadmin and _sysadmins_left(u) < 1:
        return 'لا يمكن حذف آخر مدير للنظام'
    PasswordReset.query.filter_by(user_id=u.id).delete()
    db.session.delete(u)
    return None


@api_bp.route('/users/delete/<int:id>', methods=['POST'])
@admin_required(sysadmin=True)
def delete_user(id):
    u = db.session.get(AdminUser, id)
    if not u:
        return err_json('غير موجود', 404)
    msg = _delete_user(u)
    if msg:
        return err_json(msg)
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/users/bulk', methods=['POST'])
@admin_required(sysadmin=True)
def users_bulk():
    d = request.get_json(silent=True) or {}
    rows = AdminUser.query.filter(AdminUser.id.in_(_ids(d))).all()
    action = d.get('action')
    if not rows or action not in ('activate', 'deactivate', 'delete'):
        return err_json('لم يُحدَّد أي عنصر')
    me, done, notes = auth.current_user(), 0, []
    for u in rows:
        msg = None
        if action == 'delete':
            msg = _delete_user(u)
        elif action == 'deactivate':
            if u.id == me.id or (u.is_sysadmin and _sysadmins_left(u) < 1):
                msg = 'لا يمكن إيقاف حسابك الحالي أو آخر مدير للنظام'
            else:
                u.active = False
                db.session.flush()
        else:
            u.active = True
        if msg:
            notes.append(f'{u.username}: {msg}')
        else:
            done += 1
    db.session.commit()
    return jsonify({'success': True, 'done': done, 'notes': notes})


@api_bp.route('/password', methods=['POST'])
@admin_required
def change_password():
    d = request.get_json(silent=True) or {}
    u, new = auth.current_user(), str(d.get('new') or '')
    if not auth.password_ok(u, d.get('current')):
        return err_json('كلمة المرور الحالية غير صحيحة')
    if len(new) < 8:
        return err_json('كلمة المرور الجديدة 8 أحرف على الأقل')
    u.password_hash = auth.hash_password(new)
    db.session.commit()
    auth.sign_in(u, False)
    return jsonify({'success': True, 'csrf': auth.csrf_token()})


# ───────────── الإعدادات ─────────────
BOOL_SETTINGS = {   # المفتاح في الواجهة ← (المفتاح المخزَّن، الافتراضي، الصلاحية)
    'autoApproveBookings': ('auto_approve_bookings', False, 'settings.approval'),
    'publicShowDetails': ('public_show_details', False, 'settings.approval'),
    'remindersEnabled': ('reminders_enabled', True, 'settings.reminders'),
    'reminderScheduledEnabled': ('reminder_scheduled_enabled', True, 'settings.reminders'),
    'staffDailySummaryEnabled': ('staff_daily_summary_enabled', False, 'settings.reminders'),
}


@api_bp.route('/settings')
@admin_required(('settings.identity', 'settings.approval', 'settings.reminders'))
def get_settings():
    from utils.brand import get_brand
    b = get_brand()
    out = {'orgAr': b['org_ar'], 'orgEn': b['org_en'], 'accent': b['accent'], 'logo': b['logo_url'] or '',
           'mail': mail.graph_ready(), 'sender': current_app.config.get('MS_SENDER_EMAIL', ''),
           'staffDailySummaryTime': AppSetting.get_str('staff_daily_summary_time', '07:00'),
           'staffReminderLeadMinutes': AppSetting.get_str('staff_reminder_lead_minutes', ''),
           'remindersAvailable': bool(current_app.config.get('REMINDERS_SCHEDULER', True))}
    for k, (key, default, _perm) in BOOL_SETTINGS.items():
        out[k] = AppSetting.get_bool(key, default)
    return jsonify(out)


@api_bp.route('/settings', methods=['POST'])
@admin_required
def save_settings():
    from utils.brand import set_identity
    d = request.get_json(silent=True) or {}
    u = auth.current_user()
    identity = any(k in d for k in ('orgAr', 'orgEn', 'accent'))
    if identity and not can(u, 'settings.identity'):
        return err_json('لا تملك صلاحية تعديل الهوية', 403)
    for k, (key, _default, perm) in BOOL_SETTINGS.items():
        if k in d and not can(u, perm):
            return err_json('لا تملك صلاحية لهذا الإعداد', 403)
    if any(k in d for k in ('staffDailySummaryTime', 'staffReminderLeadMinutes')) and not can(u, 'settings.reminders'):
        return err_json('لا تملك صلاحية لهذا الإعداد', 403)
    if identity:
        accent = txt(d.get('accent'), 7)
        if accent and not re.fullmatch(r'#[0-9a-fA-F]{6}', accent):
            return err_json('اللون غير صالح')
        set_identity(txt(d.get('orgAr'), 300), txt(d.get('orgEn'), 300), accent or None)
    for k, (key, _default, _perm) in BOOL_SETTINGS.items():
        if k in d:
            AppSetting.set_bool(key, bool(d[k]))
    if 'staffDailySummaryTime' in d:
        val = txt(d['staffDailySummaryTime'], 5)
        if svc.TIME_RE.match(val):
            AppSetting.set_str('staff_daily_summary_time', val)
    if 'staffReminderLeadMinutes' in d:
        val = txt(d['staffReminderLeadMinutes'], 4)
        if val == '' or val.isdigit():
            AppSetting.set_str('staff_reminder_lead_minutes', val)
    return jsonify({'success': True})


@api_bp.route('/logo', methods=['POST'])
@admin_required('settings.identity')
def upload_logo():
    from utils.brand import save_logo
    f = request.files.get('file')
    if not f or not f.filename:
        return err_json('لم يُحدَّد ملف')
    msg = save_logo(f)
    return err_json(msg) if msg else jsonify({'success': True})


@api_bp.route('/logo/delete', methods=['POST'])
@admin_required('settings.identity')
def delete_logo():
    from utils.brand import remove_logo
    remove_logo()
    return jsonify({'success': True})


# ───────────── الشريط الإخباري ─────────────
@api_bp.route('/ticker')
@admin_required('ticker')
def get_ticker():
    from utils.ticker_utils import get_ticker_config
    return jsonify(get_ticker_config())


@api_bp.route('/ticker', methods=['POST'])
@admin_required('ticker')
def set_ticker():
    from utils.ticker_utils import set_ticker_config
    data = request.get_json(silent=True) or {}
    cfg = {}
    for k in ('enabled', 'pulse', 'rssBold', 'logoBetween'):
        if k in data:
            cfg[k] = bool(data[k])
    for k in ('html', 'htmlEn'):
        if k in data:
            cfg[k] = data[k] or ''
    for k, lo, hi, cast in (('speedSeconds', 5, 180, int), ('pulseSeconds', 0.3, 10, float), ('rssFontSize', 10, 40, int), ('bgOpacity', 0, 100, int)):
        if k in data:
            try:
                cfg[k] = max(lo, min(hi, cast(data[k])))
            except (TypeError, ValueError):
                pass
    if data.get('textShadow') in ('none', 'light', 'strong'):
        cfg['textShadow'] = data['textShadow']
    for k in ('rssColor', 'bgColor', 'textColor'):
        if k in data and re.fullmatch(r'#[0-9a-fA-F]{6}', str(data[k] or '')):
            cfg[k] = data[k]
    if 'rssUrl' in data:
        url = mail._clean(data['rssUrl'] or '')
        cfg['rssUrl'] = url if re.match(r'^https?://', url) else ''
    return jsonify(set_ticker_config(cfg))


# ───────────── الروابط المختصرة ─────────────
RESERVED_SLUGS = {'calendar', 'book', 'lookup', 'admin', 'api', 'static', 'uploads', 'action', 'ticket', 'schedule', 'healthz', 'sw.js', 'robots.txt', 'favicon.ico'}


def _base_url():
    return (current_app.config.get('BASE_URL') or request.host_url).rstrip('/')


@api_bp.route('/links')
@admin_required('links')
def get_links():
    from models import ShortLink
    return jsonify([l.to_dict(_base_url()) for l in ShortLink.query.order_by(ShortLink.id).all()])


@api_bp.route('/links/save', methods=['POST'])
@admin_required('links')
def save_link():
    from models import ShortLink
    d = request.get_json(silent=True) or {}
    url = txt(d.get('url'), 2000)
    if not re.match(r'^https?://', url):
        return err_json('الرابط يجب أن يبدأ بـ http أو https')
    link = db.session.get(ShortLink, int(d['id'])) if str(d.get('id') or '').isdigit() else None
    slug = txt(d.get('slug'), 60)
    if not slug:       # رقم تلقائي تالٍ
        nums = [int(r[0]) for r in db.session.query(ShortLink.slug).all() if r[0].isdigit()]
        slug = str(max(nums + [0]) + 1)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', slug) or slug.lower() in RESERVED_SLUGS:
        return err_json('الاسم المختصر غير صالح أو محجوز')
    clash = ShortLink.query.filter(db.func.lower(ShortLink.slug) == slug.lower()).first()
    if clash and (link is None or clash.id != link.id):
        return err_json('هذا الاسم المختصر مستخدم')
    if link is None:
        link = ShortLink(clicks=0)
        db.session.add(link)
    link.slug, link.url, link.note, link.active = slug, url, txt(d.get('note'), 300), bool(d.get('active', True))
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/links/bulk', methods=['POST'])
@admin_required('links')
def links_bulk():
    from models import ShortLink
    d = request.get_json(silent=True) or {}
    rows = ShortLink.query.filter(ShortLink.id.in_(_ids(d))).all()
    action = d.get('action')
    if not rows or action not in ('activate', 'deactivate', 'delete'):
        return err_json('لم يُحدَّد أي عنصر')
    for l in rows:
        if action == 'delete':
            db.session.delete(l)
        else:
            l.active = action == 'activate'
    db.session.commit()
    return jsonify({'success': True, 'done': len(rows)})


# ───────────── الأرشفة والنسخة الكاملة ─────────────
def _old_bookings(before):
    """الحجوزات المنتهية قبل التاريخ والتي ليست قيد المراجعة (لا يُؤرشف ما ينتظر قراراً)."""
    return Booking.query.filter(Booking.end_date < before, Booking.status != 'pending').order_by(Booking.start_date).all()


@api_bp.route('/archive-preview')
@admin_required('archive')
def archive_preview():
    before = parse_date(request.args.get('before'))
    if not before:
        return err_json('اكتب التاريخ')
    rows = _old_bookings(before)
    return jsonify({'count': len(rows), 'oldest': rows[0].start_date.strftime('%Y-%m-%d') if rows else '',
                    'byStatus': {s: sum(1 for r in rows if r.status == s) for s in ('approved', 'rejected', 'cancelled')}})


@api_bp.route('/archive-export')
@admin_required('archive')
def archive_export():
    import zipfile
    before = parse_date(request.args.get('before'))
    if not before:
        return err_json('اكتب التاريخ')
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['req_id', 'status', 'name', 'email', 'phone', 'title', 'hall', 'start_date', 'end_date', 'start_time', 'end_time', 'full_day', 'notes', 'comments'])
    for b in _old_bookings(before):
        cm = ' | '.join(c.body for c in BookingComment.query.filter_by(booking_id=b.id).order_by(BookingComment.id).all())
        w.writerow([_csv_cell(x) for x in (b.req_id, b.status, b.full_name, b.email, b.phone, b.title, b.hall_name, b.start_date, b.end_date,
                                          b.start_time, b.end_time, 'yes' if b.full_day else 'no', b.notes, cm)])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('bookings.csv', '﻿' + out.getvalue())
    return Response(buf.getvalue(), mimetype='application/zip', headers={'Content-Disposition': f'attachment; filename="archive_before_{before}.zip"'})


@api_bp.route('/archive-delete', methods=['POST'])
@admin_required('archive')
def archive_delete():
    d = request.get_json(silent=True) or {}
    before = parse_date(d.get('before'))
    if not before:
        return err_json('اكتب التاريخ')
    if d.get('confirm') != 'DELETE':
        return err_json('اكتب كلمة التأكيد')
    rows = _old_bookings(before)
    for b in rows:
        BookingReminder.query.filter_by(booking_id=b.id).delete()
        BookingComment.query.filter_by(booking_id=b.id).delete()
        db.session.delete(b)
    db.session.commit()
    return jsonify({'success': True, 'deleted': len(rows)})


@api_bp.route('/full-export')
@admin_required(sysadmin=True)
def full_export():
    """نسخة كاملة: القاعدة (نسخة متسقة) والمرفقات، في ملف واحد."""
    import os
    import sqlite3
    import tempfile
    import zipfile
    uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    if not uri.startswith('sqlite:///'):
        return err_json('النسخة الكاملة متاحة لقاعدة SQLite فقط')
    src_path = uri[len('sqlite:///'):]
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, 'acs_venues.db')
        a, b = sqlite3.connect(src_path), sqlite3.connect(copy)
        a.backup(b)
        b.close()
        a.close()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(copy, 'acs_venues.db')
            up = current_app.config['UPLOAD_FOLDER']
            for root, _d, files in os.walk(up):
                for f in files:
                    full = os.path.join(root, f)
                    z.write(full, os.path.join('uploads', os.path.relpath(full, up)))
    return Response(buf.getvalue(), mimetype='application/zip',
                    headers={'Content-Disposition': f'attachment; filename="acs-backup-{datetime.now():%Y%m%d-%H%M}.zip"'})
