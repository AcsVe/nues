"""خادم تجريبي لفحص المظهر: قاعدة SQLite مؤقتة ببيانات عربية أو إنجليزية، ثم تشغيل التطبيق على منفذ محلي.

python tests/audit_server.py <مجلد البيانات> <ar|en> <المنفذ>
لا يقرأ قاعدة الجمعية ولا إعداداتها؛ كل البيانات هنا مصطنعة للفحص فقط.
"""
import os
import shutil
import sys
from datetime import date, timedelta

DATA, LANG, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(DATA)
os.environ.update(DATA_DIR=DATA, ADMIN_USER='admin', ADMIN_PASS='audit-pass-123', SECRET_KEY='audit', COOKIE_SECURE='0')
for k in ('DATABASE_URL', 'MS_TENANT_ID', 'MS_CLIENT_ID', 'MS_CLIENT_SECRET', 'LOGO_URL', 'FAVICON_FILE'):
    os.environ.pop(k, None)
os.environ['LOGO_URL'] = ''
if LANG == 'en':
    os.environ.update(ORG_AR='Arab Cultural Society', ORG_EN='Arab Cultural Society')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
app = create_app()
AR = LANG == 'ar'
T = (lambda a, e: a) if AR else (lambda a, e: e)

with app.app_context():
    from models import AdminUser, BlockedPeriod, Booking, Contact, Hall, db
    from utils.auth import hash_password
    Hall.query.delete()
    halls = [
        Hall(name_ar=T('القاعة الرئيسية', 'Main Hall'), name_en='Main Hall', location=T('المبنى الرئيسي', 'Main building'),
             code='H001', capacity='120', equipment=T('جهاز عرض، سبورة ذكية', 'Projector, smart board'), active=True),
        Hall(name_ar=T('قاعة الاجتماعات', 'Meeting Room'), name_en='Meeting Room', location=T('الطابق الثاني', 'Second floor'),
             code='H002', capacity='30', equipment=T('شاشة، ميكروفون', 'Screen, microphone'), requires_approval=True, active=True),
        Hall(name_ar=T('المسرح', 'Theater'), name_en='Theater', code='H003', capacity='300', active=True, category='theater'),
        Hall(name_ar=T('الملعب الرئيسي', 'Main Field'), name_en='Main Field', code='F001', capacity='60', active=True, category='field'),
        Hall(name_ar=T('الصالة الرياضية', 'Sports Hall'), name_en='Sports Hall', code='G001', capacity='80', active=False, category='gym')]
    db.session.add_all(halls)
    db.session.flush()
    names = [T('سامي خالد', 'Sami Khaled'), T('ليلى أحمد', 'Laila Ahmad'), T('منى سالم', 'Mona Salem')]
    statuses = ['pending', 'approved', 'rejected', 'cancelled', 'approved', 'pending']
    for i, s in enumerate(statuses):
        d = date.today() + timedelta(days=i + 1)
        db.session.add(Booking(
            req_id=f'BK-AUD{i:03d}', full_name=names[i % 3], email=f't{i % 3}@example.org', phone='0790000000',
            title=T('ندوة ثقافية', 'Cultural seminar'), hall_name=halls[i % 2].name_ar, start_date=d,
            end_date=d + timedelta(days=2 if i == 4 else 0), start_time='10:00', end_time='12:00', full_day=(i == 5),
            notes=T('يرجى تجهيز القاعة', 'Please prepare the hall'), status=s,
            reject_reason=T('القاعة محجوزة', 'The hall is taken') if s == 'rejected' else None))
    db.session.add(BlockedPeriod(start_date=date.today() + timedelta(days=9), end_date=date.today() + timedelta(days=10),
                                 hall_name=halls[0].name_ar, reason=T('صيانة القاعة', 'Hall maintenance')))
    db.session.add(Contact(email='head@example.org', name=T('رئيس الجمعية', 'Society president'), notify_new=True, notify_approved=True,
                           notify_staff_reminder=True, hall_name=halls[0].name_ar))
    from utils.ticker_utils import set_ticker_config
    set_ticker_config({'enabled': True, 'html': '<p>تعلن الجمعية عن مواعيد الفعاليات القادمة</p>',
                       'htmlEn': '<p>The society announces the coming events</p>', 'speedSeconds': 25})
    db.session.add(AdminUser(username='editor', name=T('محرر', 'Editor'), email='editor@example.org',
                             password_hash=hash_password('editor-pass-123'), role='user', active=True, perms='bookings.view,bookings.manage,calendar,reports'))
    db.session.commit()

from werkzeug.serving import make_server  # noqa: E402
make_server('127.0.0.1', PORT, app, threaded=True).serve_forever()
