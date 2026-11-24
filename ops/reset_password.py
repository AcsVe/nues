"""إنشاء حساب مدير أو إعادة تعيين كلمة مرور حساب في لوحة الإدارة من الخادم نفسه.

    python ops/reset_password.py            # يعرض الحسابات ثم يسأل عن اسم المستخدم وكلمة المرور الجديدة
    python ops/reset_password.py --create   # ينشئ حساباً جديداً إن لم يوجد

رسائل هذا الأمر بالإنجليزية لأن الطرفية لا تعرض العربية سليمة.
"""
import getpass
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'ops'))
from common import load_env  # noqa: E402

load_env()
from app import app  # noqa: E402
from models import AdminUser, db  # noqa: E402
from utils.auth import hash_password  # noqa: E402

with app.app_context():
    users = AdminUser.query.order_by(AdminUser.id).all()
    print('Accounts: ' + (', '.join(f"{u.username}{'' if u.active else ' (disabled)'}" for u in users) or '(none)'))
    name = input('User name: ').strip()
    user = next((u for u in users if u.username.lower() == name.lower()), None)
    create = '--create' in sys.argv
    if not user and not create:
        sys.exit('No account with this name (use --create to add one)')
    pw = getpass.getpass('Password (at least 8 characters, hidden while typing): ')
    if len(pw) < 8 or pw != getpass.getpass('Type it again: '):
        sys.exit('Too short or not matching')
    if not user:
        user = AdminUser(username=name, name=name, role='admin', active=True, password_hash=hash_password(pw))
        db.session.add(user)
    else:
        user.password_hash = hash_password(pw)     # تغيير الهاش يُخرج الجلسات المفتوحة لهذا الحساب
        user.active = True
    db.session.commit()
    print(f'Done. Sign in as "{user.username}" with the new password.')
