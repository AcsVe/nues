import base64
import io
from datetime import date, datetime, timedelta

import pytest

from conftest import login

HALL = 'القاعة الرئيسية'


def day(n):
    return (date.today() + timedelta(days=n)).isoformat()


def book(client, **kw):
    body = dict(bookingDate=day(5), hall=HALL, fullName='أحمد', email='a@example.org', eventTitle='ندوة',
                startTime='10:00', endTime='11:00')
    body.update(kw)
    return client.post('/api/submit_booking', json=body)


def post(c, _path, **body):
    return c.post(_path, json=body, headers=c.headers)


def test_pages_open(client):
    for url in ('/calendar', '/book', '/lookup', '/admin/login', '/healthz', '/api/halls', '/api/ticker',
                '/api/month_data?year=2026&month=11', '/sw.js', '/static/manifest.json'):
        assert client.get(url).status_code == 200, url
    assert client.get('/').status_code == 302
    assert client.get('/admin').status_code == 302        # بلا دخول: إلى صفحة الدخول


def test_admin_api_needs_login(client):
    assert client.get('/api/admin/bookings').status_code == 401
    assert client.post('/api/admin/halls/add', json={'nameAr': 'x'}).status_code == 401


def test_csrf_required(admin):
    assert admin.post('/api/admin/halls/add', json={'nameAr': 'قاعة'}).status_code == 403


def test_login_rate_limit_and_wrong_password(app):
    c = app.test_client()
    codes = [c.post('/admin/login', data={'username': 'admin', 'password': 'bad'}).status_code for _ in range(11)]
    assert codes[0] == 200 and codes[-1] == 200
    assert 'محاولات كثيرة' in c.post('/admin/login', data={'username': 'admin', 'password': 'bad'}).get_data(as_text=True)


def test_password_is_hashed(app):
    from models import AdminUser
    with app.app_context():
        u = AdminUser.query.filter_by(username='admin').first()
        assert u.password_hash != 'Secret-pass-1' and u.password_hash.startswith(('scrypt:', 'pbkdf2:'))
        assert u.is_sysadmin


def test_booking_and_conflict(client):
    assert book(client).status_code == 200
    assert book(client, startTime='10:30', endTime='11:30').status_code == 409
    assert book(client, startTime='11:00', endTime='12:00').status_code == 200     # متجاور لا متقاطع


def test_booking_validation(client):
    assert book(client, email='x').status_code == 400
    assert book(client, fullName='').status_code == 400
    assert book(client, hall='لا يوجد').status_code == 400
    assert book(client, bookingDate='bad').status_code == 400
    assert book(client, bookingDate=day(-1)).status_code == 400
    assert book(client, startTime='25:00').status_code == 400
    assert book(client, startTime='12:00', endTime='11:00').status_code == 400


def test_lookup_needs_matching_email(client):
    rid = book(client, bookingDate=day(8)).get_json()['reqId']
    assert client.post('/api/lookup_booking', json={'reqId': rid, 'email': 'other@example.org'}).status_code == 404
    assert client.post('/api/lookup_booking', json={'reqId': rid, 'email': 'A@example.org'}).status_code == 200


def test_amend_and_cancel_by_user(client):
    rid = book(client, bookingDate=day(40)).get_json()['reqId']
    r = client.post('/api/amend_booking_user', json={'reqId': rid, 'email': 'a@example.org', 'hall': HALL, 'date': day(41),
                                                    'startTime': '09:00', 'endTime': '10:00', 'title': 'جديد', 'name': 'أحمد'})
    assert r.status_code == 200
    assert client.post('/api/cancel_booking_user', json={'reqId': rid, 'email': 'a@example.org'}).status_code == 200
    assert client.post('/api/cancel_booking_user', json={'reqId': rid, 'email': 'a@example.org'}).status_code == 400


def test_upload_rules(client):
    ok = client.post('/api/upload', json={'fileName': 'a.pdf', 'dataBase64': base64.b64encode(b'%PDF-1').decode()})
    assert ok.status_code == 200 and ok.get_json()['url'].startswith('/uploads/')
    assert client.get(ok.get_json()['url']).status_code == 200
    for bad in ('a.html', 'a.svg', 'a.exe', 'a.php'):
        assert client.post('/api/upload', json={'fileName': bad, 'dataBase64': 'PGI+'}).status_code == 400


def test_attachment_urls_must_be_uploaded_files(client, admin):
    rid = book(client, bookingDate=day(9), attUrls=['https://evil.example/x', '/uploads/none.pdf']).get_json()['reqId']
    row = next(b for b in admin.get('/api/admin/bookings').get_json() if b['reqId'] == rid)
    assert row['attachments'] == []


def test_bulk_booking_actions_and_protected_delete(client, admin):
    rid = book(client, bookingDate=day(12)).get_json()['reqId']
    assert post(admin, '/api/admin/bookings/bulk', action='approve', reqIds=[rid]).get_json()['done'] == 1
    r = post(admin, '/api/admin/bookings/bulk', action='delete', reqIds=[rid]).get_json()
    assert r['done'] == 0 and r['skipped'] == 1           # حجز معتمد لا يُحذف قبل إلغائه
    assert post(admin, '/api/admin/bookings/bulk', action='cancel', reqIds=[rid]).get_json()['done'] == 1
    assert post(admin, '/api/admin/bookings/bulk', action='delete', reqIds=[rid]).get_json()['done'] == 1


def test_reject_needs_reason(client, admin):
    rid = book(client, bookingDate=day(13)).get_json()['reqId']
    assert post(admin, f'/api/admin/reject/{rid}').status_code == 400
    assert post(admin, f'/api/admin/reject/{rid}', reason='مشغول').status_code == 200


def test_cannot_approve_conflicting_pending(client, admin):
    d = day(14)
    a = book(client, bookingDate=d).get_json()['reqId']
    assert post(admin, f'/api/admin/approve/{a}').status_code == 200
    # حجز آخر في الوقت نفسه لا يُقبل أصلاً؛ نُنشئه بتعديل ثم نحاول اعتماده
    b = book(client, bookingDate=day(15)).get_json()['reqId']
    assert post(admin, f'/api/admin/update/{b}', date=d, endDate=d).status_code == 409


def test_hall_categories_and_delete_protection(admin, client):
    book(client, bookingDate=day(16))
    halls = admin.get('/api/admin/halls').get_json()
    assert {h['category'] for h in halls} >= {'hall', 'theater', 'field', 'gym'}
    main = next(h for h in halls if h['nameAr'] == HALL)
    assert post(admin, f"/api/admin/halls/delete/{main['id']}").status_code == 400     # له حجوزات
    assert post(admin, '/api/admin/halls/add', nameAr='ملعب جديد', nameEn='New field', category='field').status_code == 200
    new = next(h for h in admin.get('/api/admin/halls').get_json() if h['nameAr'] == 'ملعب جديد')
    assert new['category'] == 'field'
    assert post(admin, f"/api/admin/halls/delete/{new['id']}").status_code == 200
    assert {h['category'] for h in client.get('/api/halls?category=field').get_json()} == {'field'}


def test_cannot_deactivate_last_active_hall(admin):
    active = [h for h in admin.get('/api/admin/halls').get_json() if h['active']]
    for h in active[:-1]:
        assert post(admin, '/api/admin/halls/update', **dict(h, active=False)).status_code == 200
    assert post(admin, '/api/admin/halls/update', **dict(active[-1], active=False)).status_code == 400
    for h in active[:-1]:
        post(admin, '/api/admin/halls/update', **dict(h, active=True))


def test_hall_rename_follows_bookings(admin, client):
    admin_halls = admin.get('/api/admin/halls').get_json()
    g = next(h for h in admin_halls if h['category'] == 'gym')
    rid = book(client, bookingDate=day(18), hall=g['nameAr']).get_json()['reqId']
    assert post(admin, '/api/admin/halls/update', **dict(g, nameAr='صالة الألعاب')).status_code == 200
    row = next(b for b in admin.get('/api/admin/bookings').get_json() if b['reqId'] == rid)
    assert row['hall'] == 'صالة الألعاب'
    post(admin, '/api/admin/halls/update', **dict(g, nameAr=g['nameAr']))


def test_blocked_period_blocks_booking(client, admin):
    d = day(20)
    assert post(admin, '/api/admin/blocked/add', start=d, end=d, hall=HALL, fromT='', toT='', reason='صيانة').status_code == 200
    r = book(client, bookingDate=d)
    assert r.status_code == 409 and 'صيانة' in r.get_json()['error']
    assert post(admin, '/api/admin/blocked/add', start=d, end=d, hall=HALL, fromT='10:00', toT='', reason='x').status_code == 400


def test_auto_approve_respects_hall_setting(client, admin):
    assert post(admin, '/api/admin/settings', autoApproveBookings=True).status_code == 200
    try:
        r = book(client, bookingDate=day(22))
        assert r.get_json()['status'] == 'approved'
        theater = next(h for h in admin.get('/api/admin/halls').get_json() if h['category'] == 'theater')
        assert post(admin, '/api/admin/halls/update', **dict(theater, requiresApproval=True)).status_code == 200
        r = book(client, bookingDate=day(23), hall=theater['nameAr'])
        assert r.get_json()['status'] == 'pending'
    finally:
        post(admin, '/api/admin/settings', autoApproveBookings=False)


def test_users_protection_and_permissions(app, admin):
    me = next(u for u in admin.get('/api/admin/users').get_json() if u['me'])
    assert post(admin, f"/api/admin/users/delete/{me['id']}").status_code == 400
    assert post(admin, '/api/admin/users/update', **dict(me, active=False)).status_code == 400
    assert post(admin, '/api/admin/users/add', username='viewer1', password='short').status_code == 400
    assert post(admin, '/api/admin/users/add', username='viewer1', password='long-enough-1', perms=['bookings.view', 'bogus']).status_code == 200
    assert post(admin, '/api/admin/users/add', username='VIEWER1', password='long-enough-1').status_code == 400
    v = login(app, 'viewer1', 'long-enough-1')
    assert v.get('/api/admin/bookings').status_code == 200
    assert v.get('/api/admin/users').status_code == 403                       # مدير النظام فقط
    assert post(v, '/api/admin/halls/add', nameAr='x').status_code == 403
    assert post(v, '/api/admin/settings', orgAr='x').status_code == 403
    rid = book(app.test_client(), bookingDate=day(25)).get_json()['reqId']
    assert post(v, f'/api/admin/approve/{rid}').status_code == 403
    uid = next(u['id'] for u in admin.get('/api/admin/users').get_json() if u['username'] == 'viewer1')
    assert post(admin, '/api/admin/users/update', id=uid, username='viewer1', perms=['bookings.view', 'bookings.manage']).status_code == 200
    assert post(v, f'/api/admin/approve/{rid}').status_code == 200


def test_last_sysadmin_cannot_lose_role(admin):
    me = next(u for u in admin.get('/api/admin/users').get_json() if u['me'])
    assert post(admin, '/api/admin/users/update', **dict(me, sysadmin=False)).status_code == 400


def test_settings_and_logo(admin):
    assert post(admin, '/api/admin/settings', orgAr='جمعية', orgEn='Society', accent='#112233').status_code == 200
    assert post(admin, '/api/admin/settings', accent='red').status_code == 400
    s = admin.get('/api/admin/settings').get_json()
    assert s['orgAr'] == 'جمعية' and s['accent'] == '#112233'
    r = admin.post('/api/admin/logo', data={'file': (io.BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"/>'), 'logo.svg')},
                   headers=admin.headers, content_type='multipart/form-data')
    assert r.status_code == 200
    assert admin.get('/api/admin/settings').get_json()['logo'].startswith('/uploads/brand/logo.')
    bad = admin.post('/api/admin/logo', data={'file': (io.BytesIO(b'x'), 'logo.exe')}, headers=admin.headers, content_type='multipart/form-data')
    assert bad.status_code == 400
    post(admin, '/api/admin/settings', orgAr='الجمعية الثقافية العربية', orgEn='Arab Cultural Society', accent='#0A7C86')


def test_reminder_settings_validation(admin):
    assert post(admin, '/api/admin/settings', staffDailySummaryTime='07:30', staffReminderLeadMinutes='30', staffDailySummaryEnabled=True).status_code == 200
    s = admin.get('/api/admin/settings').get_json()
    assert s['staffDailySummaryTime'] == '07:30' and s['staffReminderLeadMinutes'] == '30'
    post(admin, '/api/admin/settings', staffDailySummaryTime='bad', staffReminderLeadMinutes='x')
    assert admin.get('/api/admin/settings').get_json()['staffDailySummaryTime'] == '07:30'
    post(admin, '/api/admin/settings', staffDailySummaryEnabled=False, staffReminderLeadMinutes='')


def test_contacts_flags_and_csv_is_safe(admin):
    post(admin, '/api/admin/contacts/add', email='x@example.org', name='=HYPERLINK("http://e")', notify_new=True, new_readonly=True)
    rows = admin.get('/api/admin/contacts').get_json()
    c = next(r for r in rows if r['email'] == 'x@example.org')
    assert c['new_readonly'] is True and c['notify_approved'] is True
    assert post(admin, '/api/admin/contacts/update', **dict(c, notify_comment=True, hall=HALL)).status_code == 200
    c = next(r for r in admin.get('/api/admin/contacts').get_json() if r['email'] == 'x@example.org')
    assert c['notify_comment'] and c['hall'] == HALL
    assert "'=HYPERLINK" in admin.get('/api/admin/contacts/export').get_data(as_text=True)


def test_staff_notifications_follow_contact_flags(app, client, admin, monkeypatch):
    import email_service as mail
    sent = []
    monkeypatch.setattr(mail, 'send_staff_new_booking', lambda to, d, a=None, r=None: sent.append((to, bool(a))))
    post(admin, '/api/admin/contacts/add', email='full@example.org', notify_new=True, new_readonly=False)
    post(admin, '/api/admin/contacts/add', email='ro@example.org', notify_new=True, new_readonly=True)
    book(client, bookingDate=day(27))
    got = dict(sent)
    assert got.get('full@example.org') is True and got.get('ro@example.org') is False


def test_email_action_links(app, client, admin):
    rid = book(client, bookingDate=day(30)).get_json()['reqId']
    from models import Booking
    with app.app_context():
        token = Booking.query.filter_by(req_id=rid).first().action_token
    assert client.get(f'/action/approve/{rid}?token=bad').status_code == 404
    page = client.get(f'/action/approve/{rid}?token={token}')
    assert page.status_code == 200
    with app.app_context():
        assert Booking.query.filter_by(req_id=rid).first().status == 'pending'    # GET لا يغيّر شيئاً
    assert client.post(f'/action/reject/{rid}?token={token}', data={'reason': ''}).status_code == 200
    with app.app_context():
        assert Booking.query.filter_by(req_id=rid).first().status == 'pending'    # الرفض يحتاج سبباً
    client.post(f'/action/approve/{rid}?token={token}', data={})
    with app.app_context():
        assert Booking.query.filter_by(req_id=rid).first().status == 'approved'


def test_comments(admin, client):
    rid = book(client, bookingDate=day(31)).get_json()['reqId']
    assert post(admin, f'/api/admin/comments/{rid}', body='').status_code == 400
    assert post(admin, f'/api/admin/comments/{rid}', body='يرجى تجهيز القاعة').status_code == 200
    rows = admin.get(f'/api/admin/comments/{rid}').get_json()
    assert rows[0]['body'] == 'يرجى تجهيز القاعة'
    assert next(b for b in admin.get('/api/admin/bookings').get_json() if b['reqId'] == rid)['comments'] == 1


def test_ticker_is_cleaned(admin, client):
    r = post(admin, '/api/admin/ticker', enabled=True, html='<p onclick="x()">مرحبا</p><script>alert(1)</script><a href="javascript:alert(1)">ر</a>', speedSeconds=999)
    cfg = r.get_json()
    assert '<script' not in cfg['html'] and 'onclick' not in cfg['html'] and 'javascript:' not in cfg['html']
    assert cfg['speedSeconds'] == 180
    assert client.get('/api/ticker').get_json()['enabled'] is True
    post(admin, '/api/admin/ticker', enabled=False, html='')


def test_password_reset_flow(app, admin, client, monkeypatch):
    import email_service as mail
    links = []
    monkeypatch.setattr(mail, 'send_password_reset', lambda to, name, link: links.append(link))
    post(admin, '/api/admin/users/add', username='resetme', password='old-password-1', email='r@example.org')
    c = app.test_client()
    assert c.post('/admin/forgot', data={'username': 'resetme'}).status_code == 200
    assert c.post('/admin/forgot', data={'username': 'nobody'}).status_code == 200      # الجواب واحد دائماً
    assert len(links) == 1
    token = links[0].rsplit('/', 1)[1]
    assert c.get(f'/admin/reset/{token}').status_code == 200
    assert c.post(f'/admin/reset/{token}', data={'password': 'new-password-1', 'password2': 'different'}).status_code == 200
    assert c.post(f'/admin/reset/{token}', data={'password': 'new-password-1', 'password2': 'new-password-1'}).status_code == 302
    assert 'غير صالح' in c.get(f'/admin/reset/{token}').get_data(as_text=True) or 'not valid' in c.get(f'/admin/reset/{token}').get_data(as_text=True)
    assert login(app, 'resetme', 'new-password-1')


def test_scheduled_reminders_and_daily_summary(app, client, admin, monkeypatch):
    import email_service as mail
    from models import Booking, BookingReminder, db
    import services
    from utils.reminders import check_and_send_reminders
    sent = []
    monkeypatch.setattr(mail, 'send_booker_reminder', lambda d, note='': sent.append(('booker', d['reqId'])))
    monkeypatch.setattr(mail, 'send_daily_summary', lambda to, ds, items: sent.append(('summary', to, len(items))))
    now = services.amman_now()
    rid = book(client, bookingDate=day(2), reminderAt=(now + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')).get_json()['reqId']
    with app.app_context():
        r = BookingReminder.query.filter_by(booking_id=Booking.query.filter_by(req_id=rid).first().id).first()
        assert r is not None
        r.remind_at = now - timedelta(minutes=1)
        db.session.commit()
    post(admin, '/api/admin/contacts/add', email='sum@example.org', notify_staff_reminder=True)
    post(admin, '/api/admin/settings', staffDailySummaryEnabled=True, staffDailySummaryTime='00:00')
    # حجز معتمد اليوم ليظهر في الملخص
    today_rid = book(client, bookingDate=date.today().isoformat(), startTime='23:00', endTime='23:30').get_json()
    if 'reqId' in today_rid:
        post(admin, f"/api/admin/approve/{today_rid['reqId']}")
    with app.app_context():
        from models import AppSetting
        AppSetting.set_str('last_daily_summary', '')
        res = check_and_send_reminders()
    assert res['scheduled'] == 1 and ('booker', rid) in sent
    assert any(s[0] == 'summary' and s[1] == 'sum@example.org' for s in sent)
    with app.app_context():
        assert check_and_send_reminders()['scheduled'] == 0                          # لا يُرسل مرتين
    post(admin, '/api/admin/settings', staffDailySummaryEnabled=False)


def test_email_text_is_escaped(app):
    from email_service import _row
    assert '<script>' not in _row('x', '<script>alert(1)</script>')


def test_database_migration_adds_missing_columns_with_defaults(app):
    from sqlalchemy import text
    from models import add_missing_columns, db
    with app.app_context():
        db.session.execute(text('ALTER TABLE halls RENAME TO halls_old'))
        db.session.execute(text('CREATE TABLE halls (id INTEGER PRIMARY KEY, name_ar VARCHAR(100) NOT NULL)'))
        db.session.execute(text("INSERT INTO halls (id, name_ar) VALUES (1, 'قاعة قديمة')"))
        db.session.commit()
        add_missing_columns()
        row = db.session.execute(text('SELECT category, active FROM halls WHERE id = 1')).fetchone()
        assert row[0] == 'hall' and row[1] == 1          # القيمة الافتراضية للصفوف القائمة
        db.session.execute(text('DROP TABLE halls'))
        db.session.execute(text('ALTER TABLE halls_old RENAME TO halls'))
        db.session.commit()


def test_short_links(admin, client):
    assert post(admin, '/api/admin/links/save', url='ftp://x').status_code == 400
    assert post(admin, '/api/admin/links/save', url='https://example.org/f', slug='calendar').status_code == 400      # محجوز
    assert post(admin, '/api/admin/links/save', url='https://example.org/file').status_code == 200                   # رقم تلقائي
    link = next(l for l in admin.get('/api/admin/links').get_json() if l['url'] == 'https://example.org/file')
    assert link['slug'].isdigit()
    r = client.get('/' + link['slug'])
    assert r.status_code == 302 and r.headers['Location'] == 'https://example.org/file'
    assert next(l for l in admin.get('/api/admin/links').get_json() if l['id'] == link['id'])['clicks'] == 1
    assert post(admin, '/api/admin/links/save', url='https://example.org/other', slug=link['slug']).status_code == 400
    post(admin, '/api/admin/links/bulk', action='deactivate', ids=[link['id']])
    assert client.get('/' + link['slug']).status_code == 404
    assert client.get('/no-such-link').status_code == 404
    post(admin, '/api/admin/links/bulk', action='delete', ids=[link['id']])


def test_archive_flow(admin, client):
    rid = book(client, bookingDate=day(60)).get_json()['reqId']
    post(admin, f'/api/admin/cancel/{rid}')
    before = day(400)
    pre = admin.get('/api/admin/archive-preview?before=' + before).get_json()
    assert pre['count'] >= 1
    zipped = admin.get('/api/admin/archive-export?before=' + before)
    assert zipped.status_code == 200 and zipped.data[:2] == b'PK'
    assert post(admin, '/api/admin/archive-delete', before=before).status_code == 400          # بلا تأكيد
    pending = book(client, bookingDate=day(61)).get_json()['reqId']
    done = post(admin, '/api/admin/archive-delete', before=before, confirm='DELETE').get_json()['deleted']
    assert done >= 1
    rows = {b['reqId'] for b in admin.get('/api/admin/bookings').get_json()}
    assert rid not in rows and pending in rows                                                  # قيد المراجعة لا يُؤرشف


def test_full_export_sysadmin_only(app, admin):
    z = admin.get('/api/admin/full-export')
    assert z.status_code == 200 and z.data[:2] == b'PK'
    post(admin, '/api/admin/users/add', username='arch1', password='long-enough-1', perms=['archive'])
    u = login(app, 'arch1', 'long-enough-1')
    assert u.get('/api/admin/full-export').status_code == 403
    assert u.get('/api/admin/archive-preview?before=' + day(1)).status_code == 200


def test_server_errors_have_english(client):
    j = book(client, email='x').get_json()
    assert j['error'] and j['errorEn'] == 'The email address is not valid'


def test_range_data_and_pages(client):
    book(client, bookingDate=day(3))
    r = client.get(f'/api/range_data?from={day(0)}&to={day(7)}').get_json()
    assert any(b['hall'] == HALL for b in r['bookings'])
    assert client.get(f'/api/range_data?from={day(0)}&to={day(200)}').status_code == 400
    assert client.get('/schedule').status_code == 200
    assert client.get('/schedule?lang=en&hall=x&date=2026-01-01').status_code == 200


def test_attendance_and_extras(admin, client):
    hall = next(h for h in admin.get('/api/admin/halls').get_json() if h['nameAr'] == HALL)
    post(admin, '/api/admin/halls/update', **{**hall, 'extras': 'ميكروفون\nكراسٍ إضافية\nميكروفون'})
    assert next(h for h in client.get('/api/halls').get_json() if h['nameAr'] == HALL)['extras'] == ['ميكروفون', 'كراسٍ إضافية']
    assert book(client, attendees='500').status_code == 400                          # فوق السعة (100)
    assert book(client, attendees='abc').status_code == 400
    assert book(client, extras=['شيء غير موجود']).status_code == 400
    ok = book(client, attendees='40', extras=['ميكروفون'], bookingDate=day(33))
    assert ok.status_code == 200
    row = next(b for b in admin.get('/api/admin/bookings').get_json() if b['reqId'] == ok.get_json()['reqId'])
    assert row['attendees'] == 40 and row['extras'] == ['ميكروفون']


def test_repeat_series(admin, client):
    r = book(client, bookingDate=day(10), startTime='18:00', endTime='19:00', repeat={'freq': 'weekly', 'count': 4})
    assert r.status_code == 200 and r.get_json()['count'] == 4
    rows = [b for b in admin.get('/api/admin/bookings').get_json() if b['seriesId']]
    assert len(rows) == 4 and {b['seriesCount'] for b in rows} == {4}
    assert sorted(b['date'] for b in rows) == [day(10 + 7 * i) for i in range(4)]
    # تعارض أحد التواريخ يرفض الطلب كله
    clash = book(client, bookingDate=day(3), startTime='18:30', endTime='19:30', repeat={'freq': 'weekly', 'count': 3})
    assert clash.status_code == 409 and clash.get_json()['conflicts'] == [day(10), day(17)]
    assert not [b for b in admin.get('/api/admin/bookings').get_json() if b['date'] == day(3) and b['startTime'] == '18:30']
    assert book(client, bookingDate=day(40), startTime='18:00', endTime='19:00', repeat={'freq': 'weekly'}).status_code == 400       # بلا نهاية
    assert book(client, bookingDate=day(40), startTime='18:00', endTime='19:00', repeat={'freq': 'yearly', 'count': 3}).status_code == 400
    # اعتماد السلسلة كلها بإجراء واحد
    first = next(b for b in rows if b['seriesNo'] == 1)
    d = post(admin, f"/api/admin/approve/{first['reqId']}", scope='series').get_json()
    assert d['count'] == 4
    assert {b['status'] for b in admin.get('/api/admin/bookings').get_json() if b['seriesId'] == first['seriesId']} == {'approved'}
    # الإلغاء من صاحب الحجز: السلسلة كلها
    lk = client.post('/api/lookup_booking', json={'reqId': first['reqId'], 'email': 'a@example.org'}).get_json()
    assert lk['seriesCount'] == 4
    c = client.post('/api/cancel_booking_user', json={'reqId': first['reqId'], 'email': 'a@example.org', 'series': True}).get_json()
    assert c['count'] == 4
    assert {b['status'] for b in admin.get('/api/admin/bookings').get_json() if b['seriesId'] == first['seriesId']} == {'cancelled'}


def test_repeat_monthly_clamps_day():
    from datetime import date as d
    from services import repeat_dates
    assert repeat_dates(d(2026, 1, 31), 'monthly', count=3) == [d(2026, 1, 31), d(2026, 2, 28), d(2026, 3, 31)]
    assert len(repeat_dates(d(2026, 1, 1), 'daily', count=500)) == 52


def test_ticket_and_ics(client):
    j = book(client, bookingDate=day(12)).get_json()
    url = j['ticket']
    assert url.startswith('/ticket/')
    page = client.get(url)
    assert page.status_code == 200 and j['reqId'].encode() in page.data
    assert client.get(f"/ticket/{j['reqId']}").status_code == 404                          # بلا رمز
    assert client.get(f"/ticket/{j['reqId']}?t=wrong").status_code == 404
    ics = client.get(url.replace(f"/ticket/{j['reqId']}", f"/ticket/{j['reqId']}.ics"))
    assert ics.status_code == 200 and ics.mimetype == 'text/calendar'
    body = ics.data.decode()
    assert 'BEGIN:VEVENT' in body and 'DTSTART;TZID=Asia/Amman:' in body and j['reqId'] in body
    assert client.get('/ticket/x.ics').status_code == 404


def test_public_calendar_hides_private_details(admin, client):
    j = book(client, bookingDate=day(14), startTime='13:00', endTime='14:00', eventTitle='اجتماع سري', fullName='سامي السري',
             onBehalf='جهة خاصة').get_json()
    raw = str(client.get(f'/api/range_data?from={day(13)}&to={day(15)}').get_json())
    assert 'اجتماع سري' not in raw and 'سامي السري' not in raw and 'جهة خاصة' not in raw and j['reqId'] not in raw
    assert "'13:00'" in raw                                                    # الموعد يظهر ليعرف الزائر ما هو محجوز
    month = str(client.get(f'/api/month_data?year={date.today().year}&month={(date.today() + timedelta(days=14)).month}').get_json())
    assert 'سامي السري' not in month and j['reqId'] not in month
    post(admin, '/api/admin/settings', publicShowDetails=True)
    shown = client.get(f'/api/range_data?from={day(13)}&to={day(15)}').get_json()
    flat = str(shown)
    assert any(b['title'] == 'اجتماع سري' for b in shown['bookings']) and 'سامي السري' not in flat and j['reqId'] not in flat   # العنوان فقط بقرار المدير
    post(admin, '/api/admin/settings', publicShowDetails=False)


def test_terms_shown_and_editable(admin, client):
    page = client.get('/book').data.decode()
    assert 'الشروط والأحكام' in page and 'يُستخدم المبنى أو المرفق للغرض المذكور' in page      # النص الافتراضي
    assert 'terms-list' in client.get('/book?lang=en').data.decode()
    post(admin, '/api/admin/settings', termsAr='شرط أول\nشرط ثانٍ')
    page = client.get('/book').data.decode()
    assert 'شرط أول' in page and 'شرط ثانٍ' in page and 'يُستخدم المبنى' not in page
    assert admin.get('/api/admin/settings').get_json()['termsAr'] == 'شرط أول\nشرط ثانٍ'
    post(admin, '/api/admin/settings', termsAr='')
    assert 'يُستخدم المبنى' in client.get('/book').data.decode()


def test_pulse_changes_with_bookings(admin, client):
    a = admin.get('/api/admin/pulse').get_json()
    j = book(client, bookingDate=day(45), startTime='20:00', endTime='21:00').get_json()
    b = admin.get('/api/admin/pulse').get_json()
    assert b['sig'] != a['sig'] and b['pending'] == a['pending'] + 1
    post(admin, f"/api/admin/approve/{j['reqId']}")
    c = admin.get('/api/admin/pulse').get_json()
    assert c['sig'] != b['sig'] and c['pending'] == a['pending']
    assert client.get('/api/admin/pulse').status_code in (401, 403)


def test_email_code_is_required_before_a_booking_exists(app, admin, client, monkeypatch):
    import services
    services._HITS.clear()                                                                      # حدّ الطلبات في العملية يتراكم عبر الاختبارات
    import re
    import email_service as mail
    sent = []
    monkeypatch.setattr(mail, 'graph_ready', lambda: True)
    monkeypatch.setattr(mail, 'send_email', lambda to, subj, html, bcc=None: sent.append((to, subj, html)) or True)
    before = len(admin.get('/api/admin/bookings').get_json())
    r = book(client, bookingDate=day(50), email='me@example.org', fullName='سامي').get_json()
    assert r['needsCode'] and r['token'] and r['maskedEmail'].startswith('me***@')
    assert len(admin.get('/api/admin/bookings').get_json()) == before                      # لا حجز قبل الرمز
    code = re.search(r'>(\d{6})<', sent[-1][2]).group(1)
    assert sent[-1][0] == 'me@example.org' and code in sent[-1][1]
    body = dict(bookingDate=day(50), hall=HALL, fullName='سامي', email='me@example.org', eventTitle='ندوة', startTime='10:00', endTime='11:00')
    bad = client.post('/api/submit_booking', json=dict(body, verifyToken=r['token'], code='000000' if code != '000000' else '111111'))
    assert bad.status_code == 400 and bad.get_json()['errorEn'] == 'The verification code is not correct'
    ok = client.post('/api/submit_booking', json=dict(body, verifyToken=r['token'], code=code))
    assert ok.status_code == 200 and ok.get_json()['reqId']
    assert len(admin.get('/api/admin/bookings').get_json()) == before + 1
    again = client.post('/api/submit_booking', json=dict(body, verifyToken=r['token'], code=code))
    assert again.status_code == 400                                                         # الرمز مرة واحدة
    # بعد 5 محاولات خاطئة يبطل الرمز، والأرقام لا تُخمَّن
    r2 = book(client, bookingDate=day(51), email='me2@example.org').get_json()
    for _ in range(5):
        client.post('/api/submit_booking', json=dict(body, email='me2@example.org', verifyToken=r2['token'], code='123456'))
    good = re.search(r'>(\d{6})<', sent[-1][2]).group(1)
    assert client.post('/api/submit_booking', json=dict(body, email='me2@example.org', verifyToken=r2['token'], code=good)).status_code == 400
    # إيقاف الميزة من الإعدادات
    post(admin, '/api/admin/settings', verifyBookingEmail=False)
    assert book(client, bookingDate=day(52), email='me3@example.org').get_json().get('reqId')
    post(admin, '/api/admin/settings', verifyBookingEmail=True)


def test_code_is_rate_limited_per_address(app, client, monkeypatch):
    import services
    services._HITS.clear()                                                                      # حدّ الطلبات في العملية يتراكم عبر الاختبارات
    import email_service as mail
    monkeypatch.setattr(mail, 'graph_ready', lambda: True)
    monkeypatch.setattr(mail, 'send_email', lambda *a, **k: True)
    import services
    codes = 0
    for i in range(services.VERIFY_PER_HOUR + 1):
        r = book(client, bookingDate=day(300 + i), email='spam@example.org')
        codes += 1 if r.get_json().get('needsCode') else 0
    assert codes == services.VERIFY_PER_HOUR and r.status_code == 429


def test_failed_email_send_creates_nothing(app, admin, client, monkeypatch):
    import services
    services._HITS.clear()                                                                      # حدّ الطلبات في العملية يتراكم عبر الاختبارات
    import email_service as mail
    monkeypatch.setattr(mail, 'graph_ready', lambda: True)
    monkeypatch.setattr(mail, 'send_email', lambda *a, **k: False)
    n = len(admin.get('/api/admin/bookings').get_json())
    r = book(client, bookingDate=day(70), email='bad@example.org')
    assert r.status_code == 502 and len(admin.get('/api/admin/bookings').get_json()) == n

def test_booker_emails_have_links_and_the_number_on_top(app, admin, client, monkeypatch):
    import email_service as mail
    app.config['BASE_URL'] = 'https://acs.example'
    sent = []
    monkeypatch.setattr(mail, 'send_email', lambda to, subj, html, bcc=None: sent.append((to, subj, html)))
    j = book(client, bookingDate=day(21), startTime='08:00', endTime='09:00').get_json()
    rid = j['reqId']
    post(admin, f'/api/admin/approve/{rid}')
    post(admin, f'/api/admin/cancel/{rid}')
    assert len(sent) >= 3
    for to, subj, html in sent:
        if to != 'a@example.org':
            continue
        assert f'/lookup?lang=ar&amp;id={rid}' in html or f'/lookup?lang=ar&id={rid}' in html           # الرقم قابل للنقر
        assert '/calendar?lang=ar&amp;date=' in html or '/calendar?lang=ar&date=' in html
        assert html.index(rid) < html.index('تفاصيل') if 'تفاصيل' in html else html.index(rid) < html.index('<table width="100%"')
        assert 'font-size:17px' in html                                                                  # خط أكبر
    approved = next(h for to, s, h in sent if 'موافقة' in s and to == 'a@example.org')
    assert '/ticket/' in approved                                                                        # التأكيد الرسمي في الموافقة


def test_lookup_page_prefills_from_the_email_link(client):
    assert client.get('/lookup?lang=ar&id=BK-X&email=a%40example.org').status_code == 200
    assert 'URLSearchParams' in client.get('/static/js/lookup.js').data.decode()


def test_audit_log_records_admin_actions_without_secrets(admin, client, app):
    r = book(client, bookingDate=day(150)); assert r.status_code == 200, r.get_json()
    rid = r.get_json()['reqId']
    assert post(admin, f'/api/admin/approve/{rid}').status_code == 200
    post(admin, '/api/admin/password', current='wrong', new='Another-pass-9')   # فشل: لا يُسجَّل
    rows = admin.get('/api/admin/audit').get_json()
    acts = [(r['action'], r['target'], r['detail']) for r in rows]
    assert ('login', 'admin', '') in acts
    assert ('booking_action', rid, 'approve') in acts
    assert 'change_password' not in [a for a, _, _ in acts]
    assert 'Secret-pass-1' not in str(rows) and 'Another-pass-9' not in str(rows)
    assert admin.get('/api/admin/audit').get_json()[0]['at'][:2] == '20'


def test_audit_needs_permission(app, admin):
    post(admin, '/api/admin/users/add', username='auditor1', password='Viewer-pass-1', perms=['reports'])
    c = login(app, 'auditor1', 'Viewer-pass-1')
    assert c.get('/api/admin/audit').status_code == 403
    assert c.get('/api/admin/occupancy').status_code == 200


def test_occupancy_counts_approved_hours(admin, client):
    d = day(160)
    r = book(client, bookingDate=d, startTime='09:00', endTime='11:00')
    rid = r.get_json()['reqId']
    post(admin, f'/api/admin/approve/{rid}')
    o = admin.get(f'/api/admin/occupancy?from={d}&to={d}').get_json()
    hall = [h for h in o['halls'] if h['hours'] == 2.0]
    assert hall and hall[0]['bookings'] == 1 and hall[0]['percent'] == round(100 * 2 / 12, 1)
    assert admin.get('/api/admin/occupancy?from=2026-01-10&to=2026-01-01').status_code == 400
