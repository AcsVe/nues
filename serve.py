"""تشغيل نظام حجز القاعات بخادم Waitress (يعمل على لينكس وويندوز).

    python serve.py

• المنفذ في PORT (الافتراضي 8110)، والعنوان العام عبر Cloudflare: https://acs.edjo.win
• البيانات: مجلد data (القاعدة acs_venues.db والمرفقات uploads) — DATA_DIR في .env لتغييره
• السجل: logs/server.log
"""
import logging
import logging.handlers
import os
import sys
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'ops'))
from common import load_env  # noqa: E402

load_env()
os.makedirs(os.path.join(BASE, 'logs'), exist_ok=True)
handler = logging.handlers.RotatingFileHandler(os.path.join(BASE, 'logs', 'server.log'),
                                               maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])
log = logging.getLogger('acs-venues')


def reminders_loop(app):
    """خيط خلفي: التذكيرات المحدّدة بوقت، والملخص اليومي، وتذكير اقتراب الحجز (utils/reminders.py)."""
    every = max(60, int(os.environ.get('REMINDER_EVERY', '300') or 300))
    time.sleep(45)
    while True:
        try:
            from utils.reminders import check_and_send_reminders
            with app.app_context():
                res = check_and_send_reminders()
            if any(res.values()):
                log.info('Reminders: %s', res)
        except Exception:
            log.exception('Reminder check failed')
        time.sleep(every)


def main():
    from app import app
    from waitress import serve
    port = int(os.environ.get('PORT') or 8110)
    log.info('ACS venues running on http://localhost:%s', port)
    if os.environ.get('DISABLE_REMINDERS') != '1':
        threading.Thread(target=reminders_loop, args=(app,), daemon=True).start()
    serve(app, host=os.environ.get('HOST', '127.0.0.1'), port=port, threads=int(os.environ.get('THREADS') or 8),
          trusted_proxy='127.0.0.1', trusted_proxy_count=1,
          trusted_proxy_headers={'x-forwarded-proto', 'x-forwarded-host', 'x-forwarded-for'},
          clear_untrusted_proxy_headers=True, channel_timeout=300, ident='ACS-VENUES')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        log.exception('Server failed to start')
        raise
