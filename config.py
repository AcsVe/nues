import os

# المسار الأساسي للمشروع
basedir = os.path.abspath(os.path.dirname(__file__))


def _database_uri():
    url = os.environ.get('DATABASE_URL', '').strip()
    if url:
        # Render exposes Postgres as postgres://, SQLAlchemy needs postgresql://
        if url.startswith('postgres://'):
            url = 'postgresql://' + url[len('postgres://'):]
        return url
    # Local fallback
    return 'sqlite:///' + os.path.join(basedir, 'booking.db')


class Config:
    # قاعدة البيانات
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # مجلد رفع الملفات
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 ميجا كحد أقصى

    # المفتاح السري للجلسات (تسجيل دخول الأدمن)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'acs-super-secret-key-2024')

    # إعدادات البريد (Brevo)
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
    SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'acsvenues@gmail.com')
    SENDER_NAME = os.environ.get('SENDER_NAME', 'ACS Booking')

    # بيانات الأدمن
    ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
    ADMIN_PASS = os.environ.get('ADMIN_PASSWORD', 'acs2024')

    # إعدادات المؤسسة
    LOGO_URL = os.environ.get('LOGO_URL', 'https://i.postimg.cc/S2W2hXZ6/acs.png')
    ORG_AR = os.environ.get('ORG_AR', 'الجمعية الثقافية العربية')
    ORG_EN = os.environ.get('ORG_EN', 'Arab Cultural Society')
    ACCENT_COLOR = os.environ.get('ACCENT_COLOR', '#EBB37B')
