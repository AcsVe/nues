"""الدخول إلى لوحة التحكم: حسابات بكلمات مرور مشفّرة، وحدّ لمحاولات الدخول الخاطئة، ورمز CSRF للطلبات المغيِّرة."""
import hmac
import secrets
import time
from functools import wraps

from flask import jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from models import AdminUser, db

MAX_FAILS = 10          # عشر محاولات خاطئة توقف الدخول من العنوان نفسه
LOCK_SECONDS = 15 * 60
_FAILED = {}            # عنوان الزائر ← (عدد المحاولات، وقت أولها)


def hash_password(pw):
    return generate_password_hash(pw)


def password_ok(user, pw):
    return bool(user and user.password_hash and check_password_hash(user.password_hash, pw or ''))


def client_ip():
    return request.headers.get('CF-Connecting-IP') or request.remote_addr or ''


def too_many(ip):
    n, first = _FAILED.get(ip, (0, 0))
    if n and time.time() - first > LOCK_SECONDS:
        _FAILED.pop(ip, None)
        return False
    return n >= MAX_FAILS


def note_failure(ip):
    n, first = _FAILED.get(ip, (0, time.time()))
    _FAILED[ip] = (n + 1, first)


def clear_failures(ip):
    _FAILED.pop(ip, None)


def current_user():
    uid = session.get('uid')
    if not uid:
        return None
    user = db.session.get(AdminUser, uid)
    if not user or not user.active:
        return None
    # تغيير كلمة المرور يُخرج الجلسات المفتوحة لهذا الحساب
    if session.get('pv') != (user.password_hash or '')[-12:]:
        return None
    return user


def sign_in(user, remember=False):
    session.clear()
    session['uid'] = user.id
    session['pv'] = (user.password_hash or '')[-12:]
    session['csrf'] = secrets.token_urlsafe(24)
    session.permanent = bool(remember)


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(24)
    return session['csrf']


def admin_required(fn):
    """مسار للإدارة فقط: دخول صالح، ورمز CSRF في كل طلب غير القراءة."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return jsonify({'error': 'Unauthorized', 'errorAr': 'انتهت الجلسة، سجّل الدخول من جديد'}), 401
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            sent = request.headers.get('X-CSRF-Token', '')
            if not sent or not hmac.compare_digest(sent, session.get('csrf', '')):
                return jsonify({'error': 'Bad token', 'errorAr': 'رمز الحماية غير صالح، حدّث الصفحة'}), 403
        return fn(*args, **kwargs)
    return wrapper


def ensure_first_admin(app):
    """أول تشغيل: إن لم يوجد أي حساب وضُبط ADMIN_PASS في .env صار حساب مدير النظام الأول."""
    if AdminUser.query.first() is not None:
        return
    user = (app.config.get('ADMIN_USER') or 'admin').strip()
    pw = app.config.get('ADMIN_PASS') or ''
    if len(pw) < 8:
        print('[auth] no administrator yet - run: python ops/reset_password.py --create', flush=True)
        return
    db.session.add(AdminUser(username=user, name=user, password_hash=hash_password(pw), role='admin', active=True))
    db.session.commit()
    print(f'[auth] first administrator "{user}" created from .env', flush=True)
