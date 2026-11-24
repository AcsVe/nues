"""إعدادات النظام من متغيرات البيئة (.env). لا قيم سرية افتراضية: المفتاح السري يُولَّد ويُحفظ في مجلد البيانات."""
import os
import secrets


def _data_dir():
    base = os.path.abspath(os.path.dirname(__file__))
    d = os.environ.get('DATA_DIR', '').strip() or os.path.join(base, 'data')
    os.makedirs(d, exist_ok=True)
    return d


def _secret_key(data_dir):
    key = os.environ.get('SECRET_KEY', '').strip()
    if key:
        return key
    path = os.path.join(data_dir, '.secret_key')
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            return f.read().strip()
    key = secrets.token_urlsafe(48)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def _database_uri(data_dir):
    url = os.environ.get('DATABASE_URL', '').strip()
    if url:
        return 'postgresql://' + url[len('postgres://'):] if url.startswith('postgres://') else url
    return 'sqlite:///' + os.path.join(data_dir, 'acs_venues.db')


class Config:
    DATA_DIR = _data_dir()
    SQLALCHEMY_DATABASE_URI = _database_uri(DATA_DIR)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    SECRET_KEY = _secret_key(DATA_DIR)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('COOKIE_SECURE', '1') != '0'   # الدخول عبر https فقط (0 للتجربة المحلية)

    # البريد: Microsoft 365 (Graph)
    MS_TENANT_ID = os.environ.get('MS_TENANT_ID', '')
    MS_CLIENT_ID = os.environ.get('MS_CLIENT_ID', '')
    MS_CLIENT_SECRET = os.environ.get('MS_CLIENT_SECRET', '')
    MS_SENDER_EMAIL = os.environ.get('MS_SENDER_EMAIL', '')

    # أول مدير (يُنشأ عند أول تشغيل إن لم يوجد أي حساب)
    ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
    ADMIN_PASS = os.environ.get('ADMIN_PASS', '')

    # الهوية الافتراضية (تُغيَّر من لوحة التحكم ← الإعدادات)
    LOGO_URL = os.environ.get('LOGO_URL', 'https://i.postimg.cc/S2W2hXZ6/acs.png')
    ORG_AR = os.environ.get('ORG_AR', 'الجمعية الثقافية العربية')
    ORG_EN = os.environ.get('ORG_EN', 'Arab Cultural Society')
    BASE_URL = os.environ.get('BASE_URL', 'https://acs.edjo.win').rstrip('/')
