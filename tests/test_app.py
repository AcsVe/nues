import base64
from datetime import date, timedelta

import pytest

HALL = 'القاعة الرئيسية'


def day(n):
    return (date.today() + timedelta(days=n)).isoformat()


def book(client, **kw):
    body = dict(bookingDate=day(5), hall=HALL, fullName='أحمد', email='a@example.org', eventTitle='ندوة',
                startTime='10:00', endTime='11:00')
    body.update(kw)
    return client.post('/api/submit_booking', json=body)


def post(c, url, **body):
    return c.post(url, json=body, headers=c.headers)


def test_pages_open(client):
    for url in ('/', '/book', '/admin', '/healthz', '/api/halls', '/api/month_data?year=2026&month=11'):
        assert client.get(url).status_code == 200


def test_admin_api_needs_login(client):
    assert client.get('/api/admin/bookings').status_code == 401
    assert client.post('/api/admin/halls/add', json={'nameAr': 'x'}).status_code == 401


def test_csrf_required(admin):
    r = admin.post('/api/admin/halls/add', json={'nameAr': 'قاعة'})   # بلا رمز الحماية
    assert r.status_code == 403


def test_login_rate_limit_and_wrong_password(app):
    c = app.test_client()
    codes = [c.post('/api/admin/login', json={'username': 'admin', 'password': 'bad'}).status_code for _ in range(11)]
    assert codes[0] == 401 and codes[-1] == 429


def test_password_is_hashed(app):
    from models import AdminUser
    with app.app_context():
        u = AdminUser.query.filter_by(username='admin').first()
        assert u.password_hash != 'Secret-pass-1' and u.password_hash.startswith(('scrypt:', 'pbkdf2:'))


def test_booking_and_conflict(client):
    assert book(client).status_code == 200
    r = book(client, startTime='10:30', endTime='11:30')
    assert r.status_code == 409
    assert book(client, startTime='11:00', endTime='12:00').status_code == 200   # متجاور لا متقاطع


def test_booking_validation(client):
    assert book(client, email='x').status_code == 400
    assert book(client, fullName='').status_code == 400
    assert book(client, hall='لا توجد').status_code == 400
    assert book(client, bookingDate='bad').status_code == 400
    assert book(client, bookingDate=day(-1)).status_code == 400
    assert book(client, startTime='25:00').status_code == 400
    assert book(client, startTime='12:00', endTime='11:00').status_code == 400


def test_lookup_needs_matching_email(client):
    rid = book(client, bookingDate=day(8)).get_json()['reqId']
    assert client.post('/api/lookup_booking', json={'reqId': rid, 'email': 'other@example.org'}).status_code == 404
    assert client.post('/api/lookup_booking', json={'reqId': rid, 'email': 'A@example.org'}).status_code == 200


def test_upload_rules(client):
    ok = client.post('/api/upload', json={'fileName': 'a.pdf', 'dataBase64': base64.b64encode(b'%PDF-1').decode()})
    assert ok.status_code == 200 and ok.get_json()['url'].startswith('/uploads/')
    assert client.get(ok.get_json()['url']).status_code == 200
    for bad in ('a.html', 'a.svg', 'a.exe', 'a.php'):
        assert client.post('/api/upload', json={'fileName': bad, 'dataBase64': 'PGI+'}).status_code == 400


def test_attachment_urls_must_be_uploaded_files(client, admin):
    r = book(client, bookingDate=day(9), attUrls=['https://evil.example/x', '/uploads/none.pdf'])
    rid = r.get_json()['reqId']
    row = next(b for b in admin.get('/api/admin/bookings').get_json() if b['reqId'] == rid)
    assert row['attachments'] == []


def test_bulk_booking_actions_and_protected_delete(client, admin):
    rid = book(client, bookingDate=day(12)).get_json()['reqId']
    assert post(admin, '/api/admin/bookings/bulk', action='approve', reqIds=[rid]).get_json()['done'] == 1
    r = post(admin, '/api/admin/bookings/bulk', action='delete', reqIds=[rid]).get_json()
    assert r['done'] == 0 and r['skipped'] == 1          # حجز معتمد لا يُحذف قبل إلغائه
    assert post(admin, '/api/admin/bookings/bulk', action='cancel', reqIds=[rid]).get_json()['done'] == 1
    assert post(admin, '/api/admin/bookings/bulk', action='delete', reqIds=[rid]).get_json()['done'] == 1


def test_hall_delete_protection(admin, client):
    book(client, bookingDate=day(15))
    halls = admin.get('/api/admin/halls').get_json()
    main = next(h for h in halls if h['nameAr'] == HALL)
    assert post(admin, f"/api/admin/halls/delete/{main['id']}").status_code == 400     # لها حجوزات
    assert post(admin, '/api/admin/halls/add', nameAr='قاعة جديدة', nameEn='New').status_code == 200
    new = next(h for h in admin.get('/api/admin/halls').get_json() if h['nameAr'] == 'قاعة جديدة')
    assert post(admin, f"/api/admin/halls/delete/{new['id']}").status_code == 200


def test_cannot_deactivate_last_active_hall(admin):
    halls = admin.get('/api/admin/halls').get_json()
    active = [h for h in halls if h['active']]
    for h in active[:-1]:
        body = dict(h, active=False)
        assert post(admin, '/api/admin/halls/update', **body).status_code == 200
    last = active[-1]
    assert post(admin, '/api/admin/halls/update', **dict(last, active=False)).status_code == 400
    for h in active[:-1]:
        post(admin, '/api/admin/halls/update', **dict(h, active=True))


def test_blocked_period_blocks_booking(client, admin):
    d = day(20)
    assert post(admin, '/api/admin/blocked/add', start=d, end=d, hall=HALL, fromT='', toT='', reason='صيانة').status_code == 200
    r = book(client, bookingDate=d)
    assert r.status_code == 409 and 'صيانة' in r.get_json()['error']
    assert post(admin, '/api/admin/blocked/add', start=d, end=d, hall=HALL, fromT='10:00', toT='', reason='x').status_code == 400


def test_users_protection(admin):
    users = admin.get('/api/admin/users').get_json()
    me = next(u for u in users if u['me'])
    assert post(admin, f"/api/admin/users/delete/{me['id']}").status_code == 400
    assert post(admin, '/api/admin/users/update', **dict(me, active=False)).status_code == 400
    assert post(admin, '/api/admin/users/add', username='second', password='short').status_code == 400
    assert post(admin, '/api/admin/users/add', username='second', password='long-enough-1').status_code == 200
    assert post(admin, '/api/admin/users/add', username='SECOND', password='long-enough-1').status_code == 400


def test_settings_and_logo(admin):
    assert post(admin, '/api/admin/settings', orgAr='جمعية', orgEn='Society', accent='#112233').status_code == 200
    assert post(admin, '/api/admin/settings', accent='red').status_code == 400
    s = admin.get('/api/admin/settings').get_json()
    assert s['orgAr'] == 'جمعية' and s['accent'] == '#112233'
    r = admin.post('/api/admin/logo', data={'file': (__import__('io').BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"/>'), 'logo.svg')},
                   headers=admin.headers, content_type='multipart/form-data')
    assert r.status_code == 200
    assert admin.get('/api/admin/settings').get_json()['logo'].startswith('/uploads/brand/logo.')
    bad = admin.post('/api/admin/logo', data={'file': (__import__('io').BytesIO(b'x'), 'logo.exe')},
                     headers=admin.headers, content_type='multipart/form-data')
    assert bad.status_code == 400
    post(admin, '/api/admin/settings', orgAr='الجمعية الثقافية العربية', orgEn='Arab Cultural Society', accent='#247680')


def test_contacts_csv_is_safe(admin):
    post(admin, '/api/admin/contacts/add', list=[{'email': 'x@example.org', 'name': '=HYPERLINK("http://e")'}])
    csv_text = admin.get('/api/admin/contacts/export').get_data(as_text=True)
    assert "'=HYPERLINK" in csv_text


def test_email_text_is_escaped(app):
    from email_service import _row
    assert '<script>' not in _row('x', '<script>alert(1)</script>')


def test_database_migration_adds_missing_columns(app):
    from sqlalchemy import text
    from models import add_missing_columns, db
    with app.app_context():
        db.session.execute(text('ALTER TABLE contacts RENAME TO contacts_old'))
        db.session.execute(text('CREATE TABLE contacts (id INTEGER PRIMARY KEY, email VARCHAR(100) NOT NULL)'))
        db.session.commit()
        add_missing_columns()
        cols = [r[1] for r in db.session.execute(text('PRAGMA table_info(contacts)')).fetchall()]
        assert 'name' in cols and 'added_at' in cols
        db.session.execute(text('DROP TABLE contacts'))
        db.session.execute(text('ALTER TABLE contacts_old RENAME TO contacts'))
        db.session.commit()
