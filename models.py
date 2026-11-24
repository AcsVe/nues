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
    # نوع المبنى أو المرفق: hall قاعة، theater مسرح، field ملعب، gym صالة رياضية، building مبنى، facility مرفق
    category = db.Column(db.String(20), default='hall')
    sort_order = db.Column(db.Integer, default=0)


CATEGORIES = ('hall', 'theater', 'field', 'gym', 'building', 'facility')
CATEGORY_NAMES = {
    'hall': ('قاعة', 'Hall'), 'theater': ('مسرح', 'Theater'), 'field': ('ملعب', 'Sports field'),
    'gym': ('صالة رياضية', 'Sports hall'), 'building': ('مبنى', 'Building'), 'facility': ('مرفق', 'Facility'),
}


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
    cancel_reason = db.Column(db.Text)
    cc_emails = db.Column(db.Text)
    action_date = db.Column(db.DateTime)
    approved_by = db.Column(db.String(200))
    action_token = db.Column(db.String(64))   # يؤمّن روابط الموافقة والرفض في بريد الإدارة
    staff_reminder_sent = db.Column(db.Boolean, default=False)


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
    hall_name = db.Column(db.String(100))              # فارغ = كل المباني والمرافق
    notify_new = db.Column(db.Boolean, default=True)        # إشعار الحجز الجديد مع رابطَي الموافقة والرفض
    new_readonly = db.Column(db.Boolean, default=False)     # الإشعار للاطّلاع فقط (بلا رابطَي الموافقة والرفض)
    notify_approved = db.Column(db.Boolean, default=True)   # إشعار بعد اعتماد حجز
    notify_comment = db.Column(db.Boolean, default=False)   # إشعار عند إضافة تعليق
    notify_staff_reminder = db.Column(db.Boolean, default=False)   # الملخص اليومي وتذكير اقتراب الحجز


class BookingReminder(db.Model):
    """تذكير بريدي في وقت محدد: لصاحب الحجز (kind=booker) أو للإدارة (kind=admin)."""
    __tablename__ = 'booking_reminders'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    kind = db.Column(db.String(10), nullable=False, default='booker')
    remind_at = db.Column(db.DateTime, nullable=False)       # بتوقيت عمّان
    recipient_email = db.Column(db.String(200), nullable=False)
    note = db.Column(db.Text)
    sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BookingComment(db.Model):
    __tablename__ = 'booking_comments'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    author_name = db.Column(db.String(200))
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PasswordReset(db.Model):
    """رمز إعادة تعيين كلمة المرور: يُحفظ مشفّراً، صالح ساعة ولمرة واحدة."""
    __tablename__ = 'password_resets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('admin_users.id'), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)


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
    is_sysadmin = db.Column(db.Boolean, default=False)   # مدير النظام: كل الصلاحيات وإدارة المستخدمين
    perms = db.Column(db.Text)                           # صلاحيات المستخدم العادي مفصولة بفاصلة
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def perm_list(self):
        return [p for p in (self.perms or '').split(',') if p]

    def to_dict(self):
        return {'id': self.id, 'username': self.username, 'name': self.name or '', 'email': self.email or '',
                'active': bool(self.active), 'sysadmin': bool(self.is_sysadmin), 'perms': self.perm_list(),
                'lastLogin': self.last_login.strftime('%Y-%m-%d %H:%M') if self.last_login else ''}


def get_setting(key, default=None):
    v = AppSetting.get_str(key, '')
    return v if v != '' else default


def set_setting(key, value):
    AppSetting.set_str(key, value)


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
                # الصفوف القائمة تأخذ القيمة الافتراضية للعمود الجديد (وإلا بقيت فارغة)
                dflt = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                if dflt is not None:
                    conn.execute(text(f'UPDATE {tb.name} SET {col.name} = :v WHERE {col.name} IS NULL'),
                                 {'v': int(dflt) if isinstance(dflt, bool) else dflt})
