import os
import sys
import tempfile

DATA = tempfile.mkdtemp(prefix='acs-test-')
os.environ.update(DATA_DIR=DATA, ADMIN_USER='admin', ADMIN_PASS='Secret-pass-1', SECRET_KEY='test', COOKIE_SECURE='0', PAGE_SHIELD='0')
for k in ('DATABASE_URL', 'MS_TENANT_ID', 'MS_CLIENT_ID', 'MS_CLIENT_SECRET', 'LOGO_URL'):
    os.environ.pop(k, None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from app import app as flask_app  # noqa: E402


@pytest.fixture()
def app():
    import routes
    from utils import auth
    routes._HITS.clear()
    auth._FAILED.clear()
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin(app):
    c = app.test_client()
    r = c.post('/api/admin/login', json={'username': 'admin', 'password': 'Secret-pass-1'})
    assert r.status_code == 200
    c.headers = {'X-CSRF-Token': r.get_json()['csrf']}
    return c
