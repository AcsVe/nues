"""الصفحات العامة (الروزنامة والحجز والاستعلام) وواجهتها البرمجية، وروابط الموافقة والرفض من البريد."""
import base64
import calendar as _cal
import hmac
import os
import re
import secrets
from datetime import date as date_cls, datetime, timedelta

from flask import (Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request, send_from_directory,
                   url_for)
from werkzeug.utils import secure_filename

import email_service as mail
import services as svc
from models import (AppSetting, BlockedPeriod, Booking, BookingReminder, CATEGORY_NAMES, Hall, db)
from services import err_json
from utils import auth

public_bp = Blueprint('public', __name__)

ALLOWED_UPLOADS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'zip', 'jpg', 'jpeg', 'png', 'gif', 'webp'}
INLINE_TYPES = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf'}
SANDBOX = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"


def _lang():
    return 'en' if request.args.get('lang') == 'en' else 'ar'


def _page(template, **extra):
    return render_template(template, lang=_lang(), csrf=auth.csrf_token(), **extra)


@public_bp.route('/')
def index():
    return redirect(url_for('public.calendar', lang=_lang()))


@public_bp.route('/calendar')
def calendar():
    return _page('calendar.html', pre_date=svc.txt(request.args.get('date'), 10))


@public_bp.route('/book')
def book():
    return _page('book.html', pre_date=svc.txt(request.args.get('date'), 10), pre_hall=svc.txt(request.args.get('hall'), 100),
                 pre_start=svc.clean_time(request.args.get('start')),
                 terms=[x.strip() for x in svc.terms_text(_lang()).splitlines() if x.strip()])


@public_bp.route('/lookup')
def lookup():
    return _page('lookup.html')


@public_bp.route('/healthz')
def healthz():
    try:
        db.session.execute(db.text('select 1'))
        return jsonify({'ok': True})
    except Exception:  # noqa: BLE001
        return jsonify({'ok': False}), 503


@public_bp.route('/sw.js')
def service_worker():
    """يُقدَّم من الجذر ليشمل نطاقه كل الصفحات (ولا يُخزَّن مؤقتاً أبداً)."""
    resp = send_from_directory(current_app.static_folder, 'sw.js', mimetype='application/javascript')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


@public_bp.route('/uploads/brand/<name>')
def brand_file(name):
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'brand')
    if not os.path.isfile(os.path.join(folder, name)):
        abort(404)
    resp = send_from_directory(folder, name, max_age=3600)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Content-Security-Policy'] = SANDBOX
    return resp


@public_bp.route('/uploads/<path:name>')
def uploaded(name):
    folder = current_app.config['UPLOAD_FOLDER']
    if '/' in name or not os.path.isfile(os.path.join(folder, name)):
        abort(404)
    ext = name.rsplit('.', 1)[-1].lower()
    resp = send_from_directory(folder, name, as_attachment=ext not in INLINE_TYPES)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Content-Security-Policy'] = SANDBOX
    return resp


# ───────────── الواجهة العامة ─────────────
def hall_json(h):
    ar, en = CATEGORY_NAMES.get(h.category or 'hall', CATEGORY_NAMES['hall'])
    return {'nameAr': h.name_ar, 'nameEn': h.name_en or h.name_ar, 'location': h.location, 'code': h.code,
            'capacity': h.capacity, 'equipment': h.equipment, 'description': h.description, 'notes': h.notes,
            'category': h.category or 'hall', 'categoryAr': ar, 'categoryEn': en,
            'requiresApproval': bool(h.requires_approval), 'extras': svc.hall_extras(h), 'capacityNum': svc.capacity_of(h)}


@public_bp.route('/api/halls')
def get_halls():
    q = Hall.query.filter_by(active=True)
    cat = request.args.get('category')
    if cat:
        q = q.filter_by(category=cat)
    return jsonify([hall_json(h) for h in q.order_by(Hall.sort_order, Hall.id).all()])


@public_bp.route('/api/ticker')
def api_ticker():
    from utils.ticker_utils import build_ticker_payload
    return jsonify(build_ticker_payload())


@public_bp.route('/api/upload', methods=['POST'])
def upload_file():
    if not svc.rate_ok('upload', 30, 3600):
        return err_json('طلبات رفع كثيرة، حاول لاحقاً', 429)
    data = request.get_json(silent=True) or {}
    name = secure_filename(svc.txt(data.get('fileName') or data.get('name'), 120))
    b64 = data.get('dataBase64') or data.get('data') or ''
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if not name or not b64:
        return err_json('فشل رفع الملف')
    if ext not in ALLOWED_UPLOADS:
        return err_json('نوع الملف غير مسموح به')
    b64 = re.sub(r'\s+', '', str(b64))
    if ',' in b64 and b64.startswith('data:'):
        b64 = b64.split(',', 1)[1]
    b64 += '=' * ((-len(b64)) % 4)
    try:
        payload = base64.b64decode(b64, validate=False)
    except Exception:  # noqa: BLE001
        return err_json('فشل رفع الملف')
    if len(payload) > 10 * 1024 * 1024:
        return err_json('الملف كبير جداً', 413)
    unique = f'{secrets.token_hex(8)}.{ext}'
    with open(os.path.join(current_app.config['UPLOAD_FOLDER'], unique), 'wb') as f:
        f.write(payload)
    return jsonify({'url': f'/uploads/{unique}', 'name': name, 'id': unique})


def _booking_fields(data, existing=None):
    """يقرأ حقول الحجز من الطلب ويتحقق منها؛ يرجع (الحقول، رسالة الخطأ)."""
    start = svc.parse_date(data.get('bookingDate') or data.get('date'))
    if not start:
        return None, 'تاريخ غير صالح'
    end = svc.parse_date(data.get('endDate')) or start
    if end < start:
        return None, 'تاريخ الانتهاء يجب أن يكون بعد البداية'
    if (end - start).days > 366:
        return None, 'مدة الحجز أطول من المسموح'
    hall_name = svc.txt(data.get('hall'), 100) or (existing.hall_name if existing else '')
    hall = Hall.query.filter_by(name_ar=hall_name, active=True).first() or Hall.query.filter_by(name_en=hall_name, active=True).first()
    if not hall:
        return None, 'المبنى أو المرفق غير صحيح'
    full = bool(data.get('fullDay', False))
    s_time, e_time = svc.clean_time(data.get('startTime')), svc.clean_time(data.get('endTime'))
    if not full:
        if not s_time:
            return None, 'وقت البداية مطلوب'
        if e_time and e_time <= s_time:
            return None, 'وقت النهاية يجب أن يكون بعد البداية'
    if start < datetime.now().date() and not (existing and existing.start_date == start):
        return None, 'لا يمكن الحجز بتاريخ سابق'
    return {'start': start, 'end': end, 'hall': hall, 'full': full, 's': s_time, 'e': e_time}, None


def _attendance_fields(data, hall):
    """عدد الحضور والمستلزمات المطلوبة: الحضور ضمن سعة القاعة، والمستلزمات من قائمتها."""
    raw = str(data.get('attendees') or '').strip()
    n = None
    if raw:
        if not raw.isdigit() or not (0 < int(raw) <= 100000):
            return None, 'عدد الحضور غير صالح'
        n = int(raw)
        cap = svc.capacity_of(hall)
        if cap and n > cap:
            return None, f'عدد الحضور ({n}) أكبر من سعة المكان ({cap})'
    allowed = svc.hall_extras(hall)
    asked = [str(x).strip() for x in (data.get('extras') or []) if str(x).strip()]
    if any(x not in allowed for x in asked):
        return None, 'مستلزم غير متاح لهذا المكان'
    return {'attendees': n, 'extras': '\n'.join(dict.fromkeys(asked))}, None


def _repeat_starts(data, f):
    """تواريخ بدايات الحجز: تاريخ واحد، أو سلسلة بتكرار يومي أو أسبوعي أو شهري حتى تاريخ أو عدد."""
    rep = data.get('repeat') or {}
    freq = rep.get('freq') if isinstance(rep, dict) else 'none'
    if freq in (None, '', 'none'):
        return [f['start']], None
    if freq not in svc.REPEATS:
        return None, 'نوع التكرار غير صالح'
    until = svc.parse_date(rep.get('until'))
    count = rep.get('count')
    count = int(count) if str(count or '').isdigit() else None
    if not until and not count:
        return None, 'حدّد تاريخ انتهاء التكرار أو عدده'
    if until and until < f['start']:
        return None, 'تاريخ انتهاء التكرار يجب أن يكون بعد البداية'
    starts = svc.repeat_dates(f['start'], freq, until, count)
    if len(starts) < 2:
        return None, 'التكرار لا يعطي أكثر من حجز واحد؛ وسّع التاريخ أو العدد'
    return starts, None


def _slot_error(f, exclude_id=None):
    """رسالة تعارض أو حجب للموعد، أو None. يرجع (الرسالة، رمز الحالة)."""
    hn = f['hall'].name_ar
    c = svc.conflict_check(f['start'], f['end'], f['s'], f['e'], f['full'], hn, exclude_id)
    if c:
        if c.full_day:
            return 'محجوز يوم كامل في هذا التاريخ', 409
        if f['full']:
            return 'لا يمكن حجز يوم كامل، يوجد حجز في هذا التاريخ', 409
        return f"محجوز في هذا الوقت ({c.start_time or ''} - {c.end_time or ''}) بتاريخ {c.start_date:%Y-%m-%d}", 409
    b = svc.blocked_check(f['start'], f['end'], f['s'], f['e'], f['full'], hn)
    if b:
        msg = f"التاريخ غير متاح: {b.reason or 'فترة غير متاحة'}"
        if b.start_time and b.end_time:
            msg += f' ({b.start_time} - {b.end_time})'
        return msg, 409
    return None, 0


@public_bp.route('/api/submit_booking', methods=['POST'])
def submit_booking():
    if not svc.rate_ok('submit', 20, 3600):
        return err_json('طلبات كثيرة، حاول لاحقاً', 429)
    data = request.get_json(silent=True) or {}
    name, email = svc.txt(data.get('fullName'), 100), svc.txt(data.get('email'), 100)
    title = svc.txt(data.get('eventTitle'), 200)
    if not name or not title:
        return err_json('الاسم وعنوان المناسبة مطلوبان')
    if not svc.EMAIL_RE.match(email):
        return err_json('البريد الإلكتروني غير صالح')
    f, msg = _booking_fields(data)
    if msg:
        return err_json(msg)
    extra, msg = _attendance_fields(data, f['hall'])
    if msg:
        return err_json(msg)
    starts, msg = _repeat_starts(data, f)
    if msg:
        return err_json(msg)
    span = (f['end'] - f['start']).days
    bad = []
    for d0 in starts:
        g = dict(f, start=d0, end=d0 + timedelta(days=span))
        m, code = _slot_error(g)
        if m:
            bad.append((d0, m, code))
    if bad:
        if len(starts) == 1:
            return err_json(bad[0][1], bad[0][2])
        days = '، '.join(d.strftime('%Y-%m-%d') for d, _, _ in bad[:6])
        resp = jsonify({'error': f'تتعارض مواعيد في {len(bad)} من {len(starts)} تاريخاً ({days}). غيّر الموعد أو التكرار.',
                        'errorEn': f'{len(bad)} of {len(starts)} dates clash ({", ".join(d.strftime("%Y-%m-%d") for d, _, _ in bad[:6])}). Change the time or the repeat.',
                        'conflicts': [d.strftime('%Y-%m-%d') for d, _, _ in bad]})
        resp.status_code = 409
        return resp

    series = 'SR-' + secrets.token_hex(4).upper() if len(starts) > 1 else None
    rows = []
    for i, d0 in enumerate(starts):
        rows.append(Booking(
            req_id=svc.new_req_id(), action_token=secrets.token_urlsafe(32), full_name=name, email=email,
            phone=svc.txt(data.get('phone'), 50), behalf=svc.txt(data.get('onBehalf'), 100), title=title,
            hall_name=f['hall'].name_ar, start_date=d0, end_date=d0 + timedelta(days=span), start_time=f['s'] or None,
            end_time=f['e'] or None, full_day=f['full'], notes=svc.txt(data.get('notes'), 2000),
            attachments=','.join(svc.valid_attachments(data.get('attUrls'))),
            cc_emails=','.join(svc.split_emails(data.get('ccEmails'))[:10]), status='pending',
            attendees=extra['attendees'], extras=extra['extras'], series_id=series, series_no=i + 1 if series else None))
        db.session.add(rows[-1])
        db.session.flush()          # يضمن تفرّد رقم الطلب قبل توليد الرقم التالي
    booking = rows[0]
    # تذكير اختياري لصاحب الحجز بوقت يحدده (بتوقيت عمّان)
    ra = svc.txt(data.get('reminderAt'), 16)
    if ra:
        try:
            when = datetime.strptime(ra, '%Y-%m-%dT%H:%M')
            if when > svc.amman_now() and when.date() <= f['start']:
                db.session.add(BookingReminder(booking_id=booking.id, kind='booker', remind_at=when, recipient_email=email))
        except ValueError:
            pass
    db.session.commit()

    p = svc.booking_payload(booking)
    if svc.auto_approve_on() and not f['hall'].requires_approval:
        for extra_row in rows[1:]:                     # بريد واحد للسلسلة كلها: عن أول حجز
            extra_row.status, extra_row.action_date, extra_row.approved_by = 'approved', datetime.utcnow(), 'اعتماد تلقائي'
        svc.apply_status(booking, 'approved', by='اعتماد تلقائي')
    else:
        svc.notify(mail.send_confirm_email, p, bcc_list=None)
        svc.notify_staff_new(booking)
    return jsonify({'success': True, 'reqId': booking.req_id, 'status': booking.status, 'count': len(rows),
                    'ticket': f'/ticket/{booking.req_id}?t={booking.action_token}'})


def _own_booking(data):
    """الحجز الذي يطابق رقمه وبريده؛ محاولات التخمين محدودة بالعنوان."""
    if not svc.rate_ok('lookup', 40, 3600):
        return None, err_json('محاولات كثيرة، حاول لاحقاً', 429)
    b = Booking.query.filter_by(req_id=svc.txt(data.get('reqId'), 50)).first()
    email = svc.txt(data.get('email'), 100).lower()
    if not b or (b.email or '').lower() != email:
        return None, err_json('لم يتم العثور على الحجز أو البريد غير مطابق', 404)
    return b, None


@public_bp.route('/api/lookup_booking', methods=['POST'])
def lookup_booking():
    b, bad = _own_booking(request.get_json(silent=True) or {})
    if bad:
        return bad
    return jsonify({
        'reqId': b.req_id, 'name': b.full_name, 'email': b.email, 'phone': b.phone, 'behalf': b.behalf, 'title': b.title,
        'hall': b.hall_name, 'date': b.start_date.strftime('%Y-%m-%d'), 'endDate': (b.end_date or b.start_date).strftime('%Y-%m-%d'),
        'startTime': b.start_time or '', 'endTime': b.end_time or '', 'fullDay': b.full_day, 'notes': b.notes,
        'status': b.status, 'ccEmails': b.cc_emails or '', 'rejectReason': b.reject_reason or '',
        'attendees': b.attendees or '', 'extras': [x for x in (b.extras or '').splitlines() if x],
        'seriesCount': svc.series_count(b), 'ticket': f'/ticket/{b.req_id}?t={b.action_token}' if b.action_token else ''})


@public_bp.route('/api/amend_booking_user', methods=['POST'])
def amend_booking_user():
    data = request.get_json(silent=True) or {}
    b, bad = _own_booking(data)
    if bad:
        return bad
    if b.status in ('cancelled', 'rejected'):
        return err_json('لا يمكن تعديل هذا الحجز')
    data = dict(data, bookingDate=data.get('date'), hall=data.get('hall') or b.hall_name)
    f, msg = _booking_fields(data, existing=b)
    if msg:
        return err_json(msg)
    msg, code = _slot_error(f, exclude_id=b.id)
    if msg:
        return err_json(msg, code)
    b.full_name = svc.txt(data.get('name'), 100) or b.full_name
    b.phone, b.behalf = svc.txt(data.get('phone'), 50), svc.txt(data.get('behalf'), 100)
    b.title = svc.txt(data.get('title'), 200) or b.title
    b.hall_name, b.start_date, b.end_date = f['hall'].name_ar, f['start'], f['end']
    b.start_time, b.end_time, b.full_day = f['s'] or None, f['e'] or None, f['full']
    b.notes = svc.txt(data.get('notes'), 2000)
    if data.get('ccEmails') is not None:
        b.cc_emails = ','.join(svc.split_emails(data.get('ccEmails'))[:10])
    if b.status == 'approved':
        b.status = 'pending'
        b.action_token = b.action_token or secrets.token_urlsafe(32)
    db.session.commit()
    svc.notify(mail.send_update_email, svc.booking_payload(b), bcc_list=svc.build_bcc(b.email, svc.contact_emails(b.hall_name, 'notify_new')))
    return jsonify({'success': True, 'status': b.status})


@public_bp.route('/api/cancel_booking_user', methods=['POST'])
def cancel_booking_user():
    b, bad = _own_booking(request.get_json(silent=True) or {})
    if bad:
        return bad
    if b.status == 'cancelled':
        return err_json('هذا الحجز ملغي بالفعل')
    count = 1
    if (request.get_json(silent=True) or {}).get('series') and b.series_id:
        # إلغاء كل الحجوزات القادمة في السلسلة (غير الملغاة) مع بريد واحد
        rest = Booking.query.filter(Booking.series_id == b.series_id, Booking.id != b.id, Booking.status != 'cancelled',
                                    Booking.status != 'rejected', Booking.start_date >= date_cls.today()).all()
        for o in rest:
            o.status, o.action_date, o.cancel_reason = 'cancelled', datetime.utcnow(), 'ألغاه صاحب الحجز (السلسلة)'
        count += len(rest)
    svc.apply_status(b, 'cancelled', reason='ألغاه صاحب الحجز')
    return jsonify({'success': True, 'count': count})


def _range_payload(month_start, month_end):
    """حجوزات النطاق (غير المرفوضة وغير الملغاة) والفترات غير المتاحة، لروزنامة الشهر وجدول القاعة."""
    bookings = Booking.query.filter(Booking.start_date <= month_end, Booking.end_date >= month_start,
                                    ~Booking.status.in_(['rejected', 'cancelled'])).all()
    cats = {h.name_ar: h.category or 'hall' for h in Hall.query.all()}
    # سرّية الحجوزات: الروزنامة العامة لا تعرض رقم الحجز ولا اسم صاحبه ولا من حجز نيابة عنه،
    # ولا عنوان المناسبة ما لم يفعّل المدير «إظهار عناوين الحجوزات للعموم».
    show_title = AppSetting.get_bool('public_show_details', False)
    bk = [{'title': b.title if show_title else '', 'hall': b.hall_name, 'category': cats.get(b.hall_name, 'hall'),
           'date': b.start_date.strftime('%Y-%m-%d'), 'endDate': (b.end_date or b.start_date).strftime('%Y-%m-%d'),
           'startTime': b.start_time or '', 'endTime': b.end_time or '', 'fullDay': b.full_day, 'status': b.status}
          for b in bookings]
    blocked = {}
    for bp in BlockedPeriod.query.filter(BlockedPeriod.start_date <= month_end, BlockedPeriod.end_date >= month_start).all():
        cur, last = max(bp.start_date, month_start), min(bp.end_date, month_end)
        while cur <= last:
            blocked.setdefault(cur.strftime('%Y-%m-%d'), []).append(
                {'reason': bp.reason, 'fromTime': bp.start_time or '', 'toTime': bp.end_time or '', 'hall': bp.hall_name or ''})
            cur += timedelta(days=1)
    return {'bookings': bk, 'blocked': blocked}


@public_bp.route('/api/month_data')
def get_month_data():
    y = request.args.get('year', datetime.now().year, type=int)
    m = request.args.get('month', datetime.now().month, type=int)
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        return err_json('شهر غير صالح')
    return jsonify(_range_payload(date_cls(y, m, 1), date_cls(y, m, _cal.monthrange(y, m)[1])))


@public_bp.route('/api/range_data')
def get_range_data():
    a, b = svc.parse_date(request.args.get('from')), svc.parse_date(request.args.get('to'))
    if not a or not b or b < a or (b - a).days > 62:
        return err_json('تاريخ غير صالح')
    return jsonify(_range_payload(a, b))


# ───────────── التأكيد الرسمي (للطباعة أو الحفظ PDF) وملف التقويم ─────────────
def _ticket_booking(req_id):
    b = Booking.query.filter_by(req_id=svc.txt(req_id, 50)).first()
    token = request.args.get('t', '')
    if not b or not b.action_token or not hmac.compare_digest(token, b.action_token):
        abort(404)
    return b


@public_bp.route('/ticket/<req_id>')
def ticket(req_id):
    b = _ticket_booking(req_id)
    hall = Hall.query.filter_by(name_ar=b.hall_name).first()
    return render_template('ticket.html', lang=_lang(), b=b, hall=hall, series=svc.series_count(b),
                           url=f'/ticket/{b.req_id}?t={b.action_token}')


def _ics_escape(s):
    return str(s or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\r', '').replace('\n', '\\n')


@public_bp.route('/ticket/<req_id>.ics')
def ticket_ics(req_id):
    b = _ticket_booking(req_id)
    end = b.end_date or b.start_date
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ACS//Hall Booking//AR', 'CALSCALE:GREGORIAN', 'BEGIN:VEVENT',
             f'UID:{b.req_id}@acs', f'DTSTAMP:{datetime.utcnow():%Y%m%dT%H%M%SZ}']
    if b.full_day or not b.start_time:
        lines += [f'DTSTART;VALUE=DATE:{b.start_date:%Y%m%d}', f'DTEND;VALUE=DATE:{end + timedelta(days=1):%Y%m%d}']
    else:
        st, en = b.start_time.replace(':', ''), (b.end_time or b.start_time).replace(':', '')
        lines += [f'DTSTART;TZID=Asia/Amman:{b.start_date:%Y%m%d}T{st}00', f'DTEND;TZID=Asia/Amman:{end:%Y%m%d}T{en}00']
    lines += [f'SUMMARY:{_ics_escape(b.title)}', f'LOCATION:{_ics_escape(b.hall_name)}',
              f'DESCRIPTION:{_ics_escape("رقم الحجز " + b.req_id)}',
              'STATUS:' + ('CONFIRMED' if b.status == 'approved' else 'TENTATIVE'), 'END:VEVENT', 'END:VCALENDAR']
    return Response('\r\n'.join(lines) + '\r\n', mimetype='text/calendar',
                    headers={'Content-Disposition': f'attachment; filename="{b.req_id}.ics"'})


@public_bp.route('/schedule')
def schedule():
    return _page('schedule.html', pre_date=svc.txt(request.args.get('date'), 10), pre_hall=svc.txt(request.args.get('hall'), 100))


# ───────────── الموافقة والرفض من البريد ─────────────
def _action_booking(req_id):
    b = Booking.query.filter_by(req_id=svc.txt(req_id, 50)).first()
    token = request.values.get('token', '')
    if not b or not b.action_token or not hmac.compare_digest(token, b.action_token):
        abort(404)
    return b


@public_bp.route('/action/<kind>/<req_id>', methods=['GET', 'POST'])
def email_action(kind, req_id):
    """رابط من بريد الإدارة: يعرض صفحة تأكيد (لا يغيّر شيئاً بطلب GET حتى لا تنفّذه برامج فحص البريد)."""
    if kind not in ('approve', 'reject'):
        abort(404)
    b = _action_booking(req_id)
    lang = _lang()
    if request.method == 'POST':
        if not svc.rate_ok('action', 30, 3600):
            abort(429)
        if b.status != 'pending':
            return render_template('action.html', lang=lang, b=b, kind=kind, done='already')
        if kind == 'approve':
            svc.apply_status(b, 'approved', by='من رابط البريد')
        else:
            reason = svc.txt(request.form.get('reason'), 500)
            if not reason:
                return render_template('action.html', lang=lang, b=b, kind=kind, need_reason=True)
            svc.apply_status(b, 'rejected', reason=reason, by='من رابط البريد')
        return render_template('action.html', lang=lang, b=b, kind=kind, done='ok')
    return render_template('action.html', lang=lang, b=b, kind=kind, done='already' if b.status != 'pending' else None)


# ───────────── الروابط المختصرة: /<الاسم> يحوّل إلى الرابط الأصلي ─────────────
@public_bp.route('/<slug>')
def short_link(slug):
    from models import ShortLink
    link = ShortLink.query.filter(db.func.lower(ShortLink.slug) == slug.lower()).first()
    if not link or not link.active or not re.match(r'^https?://', link.url or ''):
        abort(404)
    link.clicks = (link.clicks or 0) + 1
    link.last_click = datetime.utcnow()
    db.session.commit()
    return redirect(link.url, code=302)
