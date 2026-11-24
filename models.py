from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Hall(db.Model):
    __tablename__ = 'halls'
    id = db.Column(db.Integer, primary_key=True)
    name_ar = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100))
    location = db.Column(db.String(200))
    code = db.Column(db.String(50))
    capacity = db.Column(db.String(50))
    equipment = db.Column(db.Text)
    description = db.Column(db.Text)
    notes = db.Column(db.Text)
    requires_approval = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)


class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    req_id = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50))
    behalf = db.Column(db.String(100))
    title = db.Column(db.String(200), nullable=False)
    hall_name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    start_time = db.Column(db.String(10))
    end_time = db.Column(db.String(10))
    full_day = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    attachments = db.Column(db.Text)  # روابط المرفقات مفصولة بفاصلة
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, cancelled
    reject_reason = db.Column(db.Text)
    cc_emails = db.Column(db.Text)
    action_date = db.Column(db.DateTime)


class BlockedPeriod(db.Model):
    __tablename__ = 'blocked'
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    hall_name = db.Column(db.String(100))  # فارغ يعني كل القاعات
    start_time = db.Column(db.String(10))
    end_time = db.Column(db.String(10))
    reason = db.Column(db.String(200), default='محظور')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Contact(db.Model):
    __tablename__ = 'contacts'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    name = db.Column(db.String(100))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)


class AppSetting(db.Model):
    """إعدادات النظام (اسم المؤسسة، اللون، الشعار...) كمفتاح وقيمة نصية."""
    __tablename__ = 'app_settings'
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text)

    @staticmethod
    def get_str(key, default=''):
        row = db.session.get(AppSetting, key)
        return default if row is None or row.value is None else row.value

    @staticmethod
    def set_str(key, value):
        row = db.session.get(AppSetting, key)
        if row is None:
            db.session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
        db.session.commit()

    @staticmethod
    def get_bool(key, default=False):
        v = AppSetting.get_str(key, '')
        return default if v == '' else v == '1'

    @staticmethod
    def set_bool(key, value):
        AppSetting.set_str(key, '1' if value else '0')


class BrandAsset(db.Model):
    """نسخة الشعار المرفوع داخل القاعدة: تعيده إلى المجلد إن فُقد (تحديث أو نقل)."""
    __tablename__ = 'brand_assets'
    name = db.Column(db.String(100), primary_key=True)
    data = db.Column(db.LargeBinary, nullable=False)


class AdminUser(db.Model):
    """حساب دخول إلى لوحة التحكم. كلمة المرور مشفّرة (لا تُخزَّن ولا تُعرض)."""
    __tablename__ = 'admin_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    name = db.Column(db.String(120))
    email = db.Column(db.String(150))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='admin')
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def to_dict(self):
        return {'id': self.id, 'username': self.username, 'name': self.name or '', 'email': self.email or '',
                'active': bool(self.active),
                'lastLogin': self.last_login.strftime('%Y-%m-%d %H:%M') if self.last_login else ''}


def add_missing_columns():
    """يُضيف عند الإقلاع أي عمود عرّفه النموذج ولم يوجد بعد في القاعدة (دون مسح بيانات)."""
    from sqlalchemy import inspect, text
    with db.engine.begin() as conn:
        insp = inspect(conn)
        tables = set(insp.get_table_names())
        for tb in db.metadata.sorted_tables:
            if tb.name not in tables:
                continue
            have = {c['name'] for c in insp.get_columns(tb.name)}
            for col in tb.columns:
                if col.name in have:
                    continue
                coltype = col.type.compile(db.engine.dialect)
                conn.execute(text(f'ALTER TABLE {tb.name} ADD COLUMN {col.name} {coltype}'))
