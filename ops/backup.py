"""نسخة احتياطية من القاعدة والمرفقات: ملف واحد مضغوط لكل نسخة، وتُحذف النسخ الأقدم من 14 يوماً.

    python ops/backup.py [مجلد النسخ]      # الافتراضي: ../backups/ACS بجانب مجلد النظام

يُشغَّل يومياً من cron (ينشئه سكربت التثبيت). رسائل الأمر بالإنجليزية لأن الطرفية لا تعرض العربية سليمة.
"""
import os
import sqlite3
import sys
import tempfile
import time
import zipfile
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'ops'))
from common import load_env  # noqa: E402

load_env()
DATA = os.environ.get('DATA_DIR') or os.path.join(BASE, 'data')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(BASE), 'backups', 'ACS')
KEEP_DAYS = int(os.environ.get('BACKUP_KEEP_DAYS') or 14)
os.makedirs(OUT, exist_ok=True)

db_path = os.path.join(DATA, 'acs_venues.db')
if not os.path.isfile(db_path):
    sys.exit('No database found at ' + db_path)
name = os.path.join(OUT, f"acs-{datetime.now():%Y%m%d-%H%M%S}.zip")
with tempfile.TemporaryDirectory() as tmp:
    copy = os.path.join(tmp, 'acs_venues.db')
    src, dst = sqlite3.connect(db_path), sqlite3.connect(copy)
    src.backup(dst)                      # نسخة متسقة حتى والنظام يعمل
    dst.close()
    src.close()
    with zipfile.ZipFile(name, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(copy, 'acs_venues.db')
        up = os.path.join(DATA, 'uploads')
        for root, _dirs, files in os.walk(up):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.join('uploads', os.path.relpath(full, up)))
os.chmod(name, 0o600)
print('Backup written:', name)
cut = time.time() - KEEP_DAYS * 86400
for f in os.listdir(OUT):
    p = os.path.join(OUT, f)
    if f.startswith('acs-') and f.endswith('.zip') and os.path.getmtime(p) < cut:
        os.remove(p)
        print('Removed old backup:', f)
