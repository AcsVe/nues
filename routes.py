import os
import csv
import io
import base64
import re
from flask import Blueprint, render_template, request, jsonify, session, Response
from models import db, Hall, Booking, BlockedPeriod, Contact
from config import Config
from datetime import datetime, timedelta, date as date_cls
from werkzeug.utils import secure_filename
import calendar
from email_service import (
    send_confirm_email, send_approve_email, send_reject_email,
    send_cancel_email, send_pending_email, send_update_email,
)

main_bp = Blueprint('main', __name__)

# ──────────── Helpers ────────────

def _get_contact_emails():
    """Return all contact emails (lowercased, deduped)."""
    rows = Contact.query.with_entities(Contact.email).all()
    return list({(r[0] or "").strip().lower() for r in rows if r[0]})


def _split_emails(raw):
    if not raw:
        return []
    raw = raw.replace(';', ',').replace('\n', ',')
    return [e.strip() for e in raw.split(',') if e.strip() and '@' in e.strip()]


def _build_bcc(primary_email, *sources):
    """Merge several email lists, lowercase, dedupe, drop the primary."""
    seen = set()
    out = []
    primary = (primary_email or "").strip().lower()
    for src in sources:
        if not src:
            continue
        if isinstance(src, str):
            src = _split_emails(src)
        for e in src:
            el = e.strip().lower()
            if not el or '@' not in el or el == primary or el in seen:
                continue
            seen.add(el)
            out.append(e.strip())
    return out


def _booking_payload(b):
    time_str = "يوم كامل" if b.full_day else f"{b.start_time or ''} - {b.end_time or ''}"
    date_str = b.start_date.strftime('%Y-%m-%d')
    if b.end_date and b.end_date != b.start_date:
        date_str += f" — {b.end_date.strftime('%Y-%m-%d')}"
    return {
        "reqId": b.req_id, "name": b.full_name, "email": b.email,
        "title": b.title, "hall": b.hall_name,
        "timeStr": time_str, "dateStr": date_str,
    }


def _times_overlap(s1, e1, s2, e2):
    """Compare HH:MM strings. Treat None/empty as fully open."""
    if not s1 or not e1 or not s2 or not e2:
        return True
    return s1 < e2 and s2 < e1


def _conflict_check(new_start, new_end, new_s_time, new_e_time, new_full, hall, exclude_id=None):
    """Return an existing Booking that conflicts, or None."""
    q = Booking.query.filter(
        Booking.hall_name == hall,
        Booking.start_date <= new_end,
        Booking.end_date >= new_start,
        ~Booking.status.in_(['rejected', 'cancelled']),
    )
    if exclude_id is not None:
        q = q.filter(Booking.id != exclude_id)
    for b in q.all():
        if new_full or b.full_day:
            return b
        if _times_overlap(new_s_time, new_e_time, b.start_time or '', b.end_time or ''):
            return b
    return None


def _blocked_check(new_start, new_end, new_s_time, new_e_time, new_full, hall):
    q = BlockedPeriod.query.filter(
        BlockedPeriod.start_date <= new_end,
        BlockedPeriod.end_date >= new_start,
    )
    for bp in q.all():
        if bp.hall_name and bp.hall_name != hall:
            continue
        if new_full or not (bp.start_time and bp.end_time):
            return bp
        if _times_overlap(new_s_time, new_e_time, bp.start_time, bp.end_time):
            return bp
    return None


def _upsert_contact(email, name):
    if not email or '@' not in email:
        return
    existing = Contact.query.filter_by(email=email).first()
    if existing:
        return
    try:
        db.session.add(Contact(email=email, name=name or ''))
        db.session.commit()
    except Exception:
        db.session.rollback()


# ── الصفحات الرئيسية ──
@main_bp.route('/')
def calendar_page():
    lang = request.args.get('lang', 'ar')
    theme = request.args.get('theme', '')
    pre_date = request.args.get('date', '')
    return render_template('calendar.html', lang=lang, theme=theme, pre_date=pre_date, org_ar=Config.ORG_AR, org_en=Config.ORG_EN, logo=Config.LOGO_URL)

@main_bp.route('/book')
def book_page():
    date = request.args.get('date', '')
    lang = request.args.get('lang', 'ar')
    theme = request.args.get('theme', '')
    return render_template('book.html', lang=lang, theme=theme, org_ar=Config.ORG_AR, org_en=Config.ORG_EN, logo=Config.LOGO_URL, pre_date=date)

@main_bp.route('/admin')
@main_bp.route('/admin/login')
def admin_page():
    lang = request.args.get('lang', 'ar')
    theme = request.args.get('theme', '')
    return render_template('admin.html', lang=lang, theme=theme, org_ar=Config.ORG_AR, org_en=Config.ORG_EN, logo=Config.LOGO_URL)

# ── API: جلب القاعات ──
@main_bp.route('/api/halls', methods=['GET'])
def get_halls():
    halls = Hall.query.filter_by(active=True).all()
    result = [{"nameAr": h.name_ar, "nameEn": h.name_en or h.name_ar, "location": h.location, "code": h.code, "capacity": h.capacity, "equipment": h.equipment, "description": h.description, "notes": h.notes} for h in halls]
    return jsonify(result)

# ── API: رفع الملفات (matches GAS uploadFile: JSON base64) ──
@main_bp.route('/api/upload', methods=['POST'])
def upload_file():
    # Accept either multipart (legacy) or JSON {fileName,dataBase64,mimeType}
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    if request.is_json or (request.data and not request.files):
        data = request.get_json(silent=True) or {}
        name = data.get('fileName') or data.get('name')
        b64 = data.get('dataBase64') or data.get('data') or ''
        if not name or not b64:
            return jsonify({"error": "فشل رفع الملف / Missing file payload"}), 400
        # Strip whitespace and URL-safe variants the GAS code allowed
        b64 = re.sub(r'\s+', '', str(b64))
        b64 = b64.replace('-', '+').replace('_', '/')
        # Strip optional data-URL prefix
        if ',' in b64 and b64.lstrip().startswith('data:'):
            b64 = b64.split(',', 1)[1]
        # Pad to multiple of 4 for permissive decoding
        pad = (-len(b64)) % 4
        if pad:
            b64 += '=' * pad
        try:
            payload_bytes = base64.b64decode(b64, validate=False)
        except Exception as e:
            return jsonify({"error": f"فشل رفع الملف: {e}"}), 400
        if len(payload_bytes) > Config.MAX_CONTENT_LENGTH:
            return jsonify({"error": "الملف كبير جداً / File too large"}), 413
        unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(name)}"
        full_path = os.path.join(Config.UPLOAD_FOLDER, unique_name)
        with open(full_path, 'wb') as f:
            f.write(payload_bytes)
        return jsonify({"url": f"/static/uploads/{unique_name}", "name": name, "id": unique_name})

    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"error": "No selected file"}), 400
    unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
    file.save(os.path.join(Config.UPLOAD_FOLDER, unique_name))
    return jsonify({"url": f"/static/uploads/{unique_name}", "name": file.filename, "id": unique_name})

# ── API: تسجيل حجز جديد ──
@main_bp.route('/api/submit_booking', methods=['POST'])
def submit_booking():
    data = request.json or {}
    # Required fields
    try:
        start_date_obj = datetime.strptime(data.get('bookingDate'), '%Y-%m-%d').date()
    except Exception:
        return jsonify({"error": "تاريخ غير صالح / Invalid date"}), 400
    end_date_str = data.get('endDate') or data.get('bookingDate')
    try:
        end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except Exception:
        end_date_obj = start_date_obj

    # 1. Reject past dates
    today = datetime.now().date()
    if start_date_obj < today:
        return jsonify({"error": "لا يمكن الحجز بتاريخ سابق / Cannot book a past date"}), 400
    if end_date_obj < start_date_obj:
        return jsonify({"error": "تاريخ الانتهاء يجب أن يكون بعد البداية / End date must be after start date"}), 400

    hall = data.get('hall') or ''
    full_day = bool(data.get('fullDay', False))
    s_time = (data.get('startTime') or '').strip()
    e_time = (data.get('endTime') or '').strip()

    # 2. Conflict check (mirror GAS submitBooking messages)
    conflict = _conflict_check(start_date_obj, end_date_obj, s_time, e_time, full_day, hall)
    if conflict:
        if conflict.full_day:
            msg = f"القاعة محجوزة يوم كامل في هذا التاريخ: {conflict.title}"
        elif full_day:
            msg = f"لا يمكن الحجز يوم كامل، يوجد حجز في هذا التاريخ: {conflict.title}"
        else:
            cdate = conflict.start_date.strftime('%Y-%m-%d')
            msg = f"القاعة محجوزة في هذا الوقت ({conflict.start_time or ''} - {conflict.end_time or ''}) بتاريخ {cdate}"
        return jsonify({"error": msg}), 409

    # 3. Blocked-period check (mirror GAS checkBlocked message)
    blocked = _blocked_check(start_date_obj, end_date_obj, s_time, e_time, full_day, hall)
    if blocked:
        reason = blocked.reason or 'فترة غير متاحة'
        msg = f"التاريخ غير متاح: {reason}"
        if blocked.start_time and blocked.end_time:
            msg += f" ({blocked.start_time} - {blocked.end_time})"
        return jsonify({"error": msg}), 409

    today_str = datetime.now().strftime('%y%m%d')
    count = Booking.query.count() + 1
    req_id = f"PUB-{today_str}-{str(count).zfill(4)}"
    new_booking = Booking(
        req_id=req_id, full_name=data.get('fullName'), email=data.get('email'),
        phone=data.get('phone'), behalf=data.get('onBehalf'), title=data.get('eventTitle'),
        hall_name=hall, start_date=start_date_obj, end_date=end_date_obj,
        start_time=s_time or None, end_time=e_time or None,
        full_day=full_day, notes=data.get('notes'),
        attachments=",".join(data.get('attUrls', [])), cc_emails=data.get('ccEmails', ''), status='pending'
    )
    db.session.add(new_booking)
    db.session.commit()

    # GAS sendConfirm goes only to the booker (no bcc) — match 1:1
    try:
        send_confirm_email(_booking_payload(new_booking), bcc_list=None)
    except Exception as e:
        print(f"Email Error: {e}")
    return jsonify({"success": True, "reqId": req_id})

# ── API: البحث وتعديل وإلغاء حجز المستخدم ──
@main_bp.route('/api/lookup_booking', methods=['POST'])
def lookup_booking():
    data = request.json or {}
    booking = Booking.query.filter_by(req_id=data.get('reqId'), email=data.get('email')).first()
    if not booking:
        return jsonify({"error": "لم يتم العثور على الحجز أو البريد غير مطابق"}), 404
    if booking.status == 'cancelled':
        return jsonify({"error": "هذا الحجز ملغي"}), 400
    return jsonify({
        "reqId": booking.req_id, "name": booking.full_name, "email": booking.email,
        "phone": booking.phone, "behalf": booking.behalf, "title": booking.title,
        "hall": booking.hall_name, "date": booking.start_date.strftime('%Y-%m-%d'),
        "endDate": booking.end_date.strftime('%Y-%m-%d'),
        "startTime": booking.start_time or "", "endTime": booking.end_time or "",
        "fullDay": booking.full_day, "notes": booking.notes, "status": booking.status,
        "ccEmails": booking.cc_emails or "",
    })

@main_bp.route('/api/amend_booking_user', methods=['POST'])
def amend_booking_user():
    data = request.json or {}
    booking = Booking.query.filter_by(req_id=data.get('reqId'), email=data.get('email')).first()
    if not booking:
        return jsonify({"error": "غير موجود"}), 404

    new_start = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
    new_end = datetime.strptime(data.get('endDate') or data.get('date'), '%Y-%m-%d').date()
    s_time = (data.get('startTime') or '').strip()
    e_time = (data.get('endTime') or '').strip()
    full_day = bool(data.get('fullDay', False))
    hall = data.get('hall') or booking.hall_name

    today = datetime.now().date()
    if new_start < today:
        return jsonify({"error": "لا يمكن الحجز بتاريخ سابق"}), 400

    conflict = _conflict_check(new_start, new_end, s_time, e_time, full_day, hall, exclude_id=booking.id)
    if conflict:
        return jsonify({"error": f"يتعارض مع حجز موجود ({conflict.req_id})"}), 409

    blocked = _blocked_check(new_start, new_end, s_time, e_time, full_day, hall)
    if blocked:
        return jsonify({"error": f"الموعد ضمن فترة محظورة: {blocked.reason or 'غير متاح'}"}), 409

    booking.full_name = data.get('name'); booking.phone = data.get('phone')
    booking.behalf = data.get('behalf'); booking.title = data.get('title')
    booking.hall_name = hall; booking.start_date = new_start; booking.end_date = new_end
    booking.start_time = s_time or None; booking.end_time = e_time or None
    booking.full_day = full_day; booking.notes = data.get('notes')
    if data.get('ccEmails') is not None:
        booking.cc_emails = data.get('ccEmails', '')
    if booking.status == 'approved':
        booking.status = 'pending'
    db.session.commit()

    # GAS amendBookingByUser sends sendUpdate WITHOUT bcc
    try:
        send_update_email(_booking_payload(booking), bcc_list=None)
    except Exception as e:
        print(f"Email Error: {e}")
    return jsonify({"success": True})

@main_bp.route('/api/cancel_booking_user', methods=['POST'])
def cancel_booking_user():
    data = request.json or {}
    booking = Booking.query.filter_by(req_id=data.get('reqId'), email=data.get('email')).first()
    if not booking: return jsonify({"error": "لم يتم العثور على الحجز أو البريد غير مطابق"}), 404
    if booking.status == 'cancelled':
        return jsonify({"error": "هذا الحجز ملغي بالفعل"}), 400
    booking.status = 'cancelled'; booking.action_date = datetime.utcnow(); db.session.commit()
    # GAS cancelBookingByUser sends sendCancel WITHOUT bcc
    try:
        send_cancel_email(_booking_payload(booking), bcc_list=None)
    except Exception as e: print(f"Email Error: {e}")
    return jsonify({"success": True})

# ── API: جلب بيانات الشهر للروزنامة ──
@main_bp.route('/api/month_data', methods=['GET'])
def get_month_data():
    y = request.args.get('year', datetime.now().year, type=int); m = request.args.get('month', datetime.now().month, type=int)
    _, last_day = calendar.monthrange(y, m); month_start = datetime(y, m, 1).date(); month_end = datetime(y, m, last_day).date()
    bookings = Booking.query.filter(Booking.start_date <= month_end, Booking.end_date >= month_start, ~Booking.status.in_(['rejected', 'cancelled'])).all()
    bk_list = [{
        "reqId": b.req_id, "title": b.title, "hall": b.hall_name,
        "date": b.start_date.strftime('%Y-%m-%d'), "endDate": b.end_date.strftime('%Y-%m-%d'),
        "startTime": b.start_time or "", "endTime": b.end_time or "",
        "fullDay": b.full_day, "status": b.status,
        "behalf": b.behalf or "", "name": b.full_name or "",
    } for b in bookings]
    blocked_periods = BlockedPeriod.query.filter(BlockedPeriod.start_date <= month_end, BlockedPeriod.end_date >= month_start).all()
    blk_dict = {}
    for bp in blocked_periods:
        current_date = max(bp.start_date, month_start); end_d = min(bp.end_date, month_end)
        while current_date <= end_d:
            date_str = current_date.strftime('%Y-%m-%d')
            if date_str not in blk_dict: blk_dict[date_str] = []
            blk_dict[date_str].append({"reason": bp.reason, "fromTime": bp.start_time or "", "toTime": bp.end_time or "", "hall": bp.hall_name or ""})
            current_date += timedelta(days=1)
    return jsonify({"bookings": bk_list, "blocked": blk_dict})

# ══════════════ APIs الأدمن ══════════════
@main_bp.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data.get('username') == Config.ADMIN_USER and data.get('password') == Config.ADMIN_PASS:
        session['is_admin'] = True; return jsonify({"success": True})
    return jsonify({"success": False}), 401

@main_bp.route('/api/admin/bookings', methods=['GET'])
def get_admin_bookings():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    status_filter = request.args.get('status', 'all'); query = Booking.query
    if status_filter != 'all': query = query.filter_by(status=status_filter)
    bookings = query.order_by(Booking.id.desc()).all()
    result = [{"reqId": b.req_id, "name": b.full_name, "email": b.email, "phone": b.phone, "behalf": b.behalf, "title": b.title, "hall": b.hall_name, "date": b.start_date.strftime('%Y-%m-%d'), "endDate": b.end_date.strftime('%Y-%m-%d'), "startTime": b.start_time or "", "endTime": b.end_time or "", "fullDay": b.full_day, "notes": b.notes, "status": b.status, "rejectReason": b.reject_reason or "", "ccEmails": b.cc_emails or "", "attachments": b.attachments.split(',') if b.attachments else []} for b in bookings]
    return jsonify(result)

@main_bp.route('/api/admin/approve/<req_id>', methods=['POST'])
def approve_booking(req_id):
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    extra_bcc = body.get('extraBcc', '')
    booking = Booking.query.filter_by(req_id=req_id).first()
    if not booking: return jsonify({"error": "غير موجود"}), 404
    booking.status = 'approved'; booking.action_date = datetime.utcnow(); db.session.commit()
    try:
        bcc = _build_bcc(booking.email, booking.cc_emails, extra_bcc, _get_contact_emails())
        send_approve_email(_booking_payload(booking), bcc_list=bcc)
    except Exception as e: print(f"Email Error: {e}")
    return jsonify({"success": True})

@main_bp.route('/api/admin/reject/<req_id>', methods=['POST'])
def reject_booking(req_id):
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    reason = (request.json or {}).get('reason', '')
    booking = Booking.query.filter_by(req_id=req_id).first()
    if not booking: return jsonify({"error": "غير موجود"}), 404
    booking.status = 'rejected'; booking.reject_reason = reason; booking.action_date = datetime.utcnow(); db.session.commit()
    # GAS sendReject goes only to the booker (no bcc)
    try:
        payload = _booking_payload(booking); payload['reason'] = reason
        send_reject_email(payload, bcc_list=None)
    except Exception as e: print(f"Email Error: {e}")
    return jsonify({"success": True})

@main_bp.route('/api/admin/cancel/<req_id>', methods=['POST'])
def admin_cancel_booking(req_id):
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    booking = Booking.query.filter_by(req_id=req_id).first()
    if not booking: return jsonify({"error": "غير موجود"}), 404
    if booking.status == 'cancelled':
        return jsonify({"error": "هذا الحجز ملغي بالفعل"}), 400
    booking.status = 'cancelled'; booking.action_date = datetime.utcnow(); db.session.commit()
    # GAS adminCancelBooking sends sendCancel WITHOUT bcc
    try:
        send_cancel_email(_booking_payload(booking), bcc_list=None)
    except Exception as e: print(f"Email Error: {e}")
    return jsonify({"success": True})

@main_bp.route('/api/admin/pending/<req_id>', methods=['POST'])
def admin_pending_booking(req_id):
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    booking = Booking.query.filter_by(req_id=req_id).first()
    if not booking: return jsonify({"error": "غير موجود"}), 404
    booking.status = 'pending'; booking.reject_reason = ''; booking.action_date = datetime.utcnow(); db.session.commit()
    try:
        bcc = _build_bcc(booking.email, booking.cc_emails, _get_contact_emails())
        send_pending_email(_booking_payload(booking), bcc_list=bcc)
    except Exception as e: print(f"Email Error: {e}")
    return jsonify({"success": True})

@main_bp.route('/api/admin/update/<req_id>', methods=['POST'])
def admin_update_booking(req_id):
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json or {}
    booking = Booking.query.filter_by(req_id=req_id).first()
    if not booking: return jsonify({"error": "غير موجود"}), 404

    # Accept both snake_case and GAS camelCase keys
    def _g(*keys):
        for k in keys:
            if k in data and data[k] is not None: return data[k]
        return None
    v = _g('full_name','name')
    if v is not None: booking.full_name = v
    v = _g('email')
    if v is not None: booking.email = v
    v = _g('phone')
    if v is not None: booking.phone = v
    v = _g('behalf')
    if v is not None: booking.behalf = v
    v = _g('title')
    if v is not None: booking.title = v
    v = _g('hall_name','hall')
    if v is not None: booking.hall_name = v
    v = _g('start_date','date')
    if v: booking.start_date = datetime.strptime(v, '%Y-%m-%d').date()
    v = _g('end_date','endDate')
    if v: booking.end_date = datetime.strptime(v, '%Y-%m-%d').date()
    v = _g('start_time','startTime')
    if v is not None: booking.start_time = v or None
    v = _g('end_time','endTime')
    if v is not None: booking.end_time = v or None
    v = _g('full_day','fullDay')
    if v is not None: booking.full_day = bool(v)
    v = _g('notes')
    if v is not None: booking.notes = v
    # GAS updateBooking does NOT change status; only fields above + action_date
    booking.action_date = datetime.utcnow()
    db.session.commit()
    try:
        bcc = _build_bcc(booking.email, booking.cc_emails, _get_contact_emails())
        send_update_email(_booking_payload(booking), bcc_list=bcc)
    except Exception as e: print(f"Email Error: {e}")
    return jsonify({"success": True})

@main_bp.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    today = datetime.now().date()
    week_ago = today - timedelta(days=today.weekday())
    approved = Booking.query.filter_by(status='approved').all()
    by_hall_count = {}
    by_month = {}
    for b in approved:
        by_hall_count[b.hall_name] = by_hall_count.get(b.hall_name, 0) + 1
        key = b.start_date.strftime('%Y-%m')
        if key not in by_month: by_month[key] = {}
        by_month[key][b.hall_name] = by_month[key].get(b.hall_name, 0) + 1
    by_hall_arr = sorted(
        [{"hall": k, "count": v} for k, v in by_hall_count.items()],
        key=lambda x: -x['count']
    )
    return jsonify({
        "total": Booking.query.count(),
        "pending": Booking.query.filter_by(status='pending').count(),
        "approved": Booking.query.filter_by(status='approved').count(),
        "rejected": Booking.query.filter_by(status='rejected').count(),
        "cancelled": Booking.query.filter_by(status='cancelled').count(),
        "today": Booking.query.filter(Booking.start_date == today, Booking.status == 'approved').count(),
        "week": Booking.query.filter(Booking.start_date >= week_ago, Booking.status == 'approved').count(),
        "byHall": by_hall_arr,
        "byMonth": by_month,
    })

# ── إدارة القاعات (Halls) ──
@main_bp.route('/api/admin/halls', methods=['GET'])
def get_admin_halls():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    halls = Hall.query.all()
    return jsonify([{"id": h.id, "nameAr": h.name_ar, "nameEn": h.name_en, "location": h.location, "code": h.code, "capacity": h.capacity, "equipment": h.equipment, "description": h.description, "notes": h.notes, "requiresApproval": h.requires_approval, "active": h.active} for h in halls])

@main_bp.route('/api/admin/halls/add', methods=['POST'])
def add_hall():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    hall = Hall(name_ar=data.get('nameAr'), name_en=data.get('nameEn'), location=data.get('location'), code=data.get('code'), capacity=data.get('capacity'), equipment=data.get('equipment'), description=data.get('description'), notes=data.get('notes'), requires_approval=data.get('requiresApproval', False), active=data.get('active', True))
    db.session.add(hall); db.session.commit()
    return jsonify({"success": True})

@main_bp.route('/api/admin/halls/update', methods=['POST'])
def update_hall():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json; hall = Hall.query.get(data.get('id'))
    if not hall: return jsonify({"error": "Not found"}), 404
    hall.name_ar = data.get('nameAr'); hall.name_en = data.get('nameEn'); hall.location = data.get('location'); hall.code = data.get('code'); hall.capacity = data.get('capacity'); hall.equipment = data.get('equipment'); hall.description = data.get('description'); hall.notes = data.get('notes'); hall.requires_approval = data.get('requiresApproval', False); hall.active = data.get('active', True)
    db.session.commit(); return jsonify({"success": True})

@main_bp.route('/api/admin/halls/delete/<int:id>', methods=['POST'])
def delete_hall(id):
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    hall = Hall.query.get(id)
    if not hall:
        return jsonify({"error": "Not found"}), 404
    if hall.active:
        active_count = Hall.query.filter_by(active=True).count()
        if active_count <= 1:
            return jsonify({"error": "لا يمكن حذف آخر قاعة نشطة / Cannot delete the last active hall"}), 400
    db.session.delete(hall); db.session.commit()
    return jsonify({"success": True})

# ── إدارة الفترات المحظورة (Blocked) ──
@main_bp.route('/api/admin/blocked', methods=['GET'])
def get_blocked():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    periods = BlockedPeriod.query.all()
    return jsonify([{"id": b.id, "start": b.start_date.strftime('%Y-%m-%d'), "end": b.end_date.strftime('%Y-%m-%d'), "hall": b.hall_name or "", "fromT": b.start_time or "", "toT": b.end_time or "", "reason": b.reason} for b in periods])

@main_bp.route('/api/admin/blocked/add', methods=['POST'])
def add_blocked():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    bp = BlockedPeriod(start_date=datetime.strptime(data.get('start'), '%Y-%m-%d').date(), end_date=datetime.strptime(data.get('end'), '%Y-%m-%d').date(), hall_name=data.get('hall'), start_time=data.get('fromT'), end_time=data.get('toT'), reason=data.get('reason'))
    db.session.add(bp); db.session.commit()
    return jsonify({"success": True})

@main_bp.route('/api/admin/blocked/delete/<int:id>', methods=['POST'])
def delete_blocked(id):
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    bp = BlockedPeriod.query.get(id)
    if bp: db.session.delete(bp); db.session.commit()
    return jsonify({"success": True})

# ── إدارة جهات الاتصال (Contacts) ──
@main_bp.route('/api/admin/contacts', methods=['GET'])
def get_contacts():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    rows = Contact.query.order_by(Contact.id.desc()).all()
    return jsonify([{
        "id": c.id, "email": c.email, "name": c.name or "",
        "addedAt": c.added_at.strftime('%Y-%m-%d %H:%M') if c.added_at else "",
    } for c in rows])

@main_bp.route('/api/admin/contacts/add', methods=['POST'])
def add_contact():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json or {}
    items = data.get('list')
    if not items:
        items = [{"email": data.get('email'), "name": data.get('name', '')}]
    added = 0
    for it in items:
        em = (it.get('email') or '').strip()
        if not em or '@' not in em:
            continue
        if Contact.query.filter_by(email=em).first():
            continue
        db.session.add(Contact(email=em, name=(it.get('name') or '').strip()))
        added += 1
    db.session.commit()
    return jsonify({"success": True, "count": added})

@main_bp.route('/api/admin/contacts/delete/<int:id>', methods=['POST'])
def delete_contact(id):
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    c = Contact.query.get(id)
    if c:
        db.session.delete(c); db.session.commit()
    return jsonify({"success": True})

@main_bp.route('/api/admin/contacts/export', methods=['GET'])
def export_contacts():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 401
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['email', 'name', 'added_at'])
    for c in Contact.query.order_by(Contact.id.asc()).all():
        writer.writerow([
            c.email, c.name or '',
            c.added_at.strftime('%Y-%m-%d %H:%M') if c.added_at else ''
        ])
    return Response(
        buf.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="contacts.csv"'}
    )
