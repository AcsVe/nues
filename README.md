# nues — حجز القاعات للجمعية الثقافية العربية (ACS)

نظام حجز قاعات ومرافق ثنائي اللغة (عربي/إنجليزي): روزنامة عامة، ونموذج حجز، ولوحة تحكم.
**العنوان:** https://acs.edjo.win

- الدليل الكامل: [`SYSTEM_GUIDE_AR.md`](SYSTEM_GUIDE_AR.md)
- التثبيت والتشغيل على الخادم: [`SERVER_AR.md`](SERVER_AR.md)
- قواعد العمل على المستودع: [`CLAUDE.md`](CLAUDE.md)

## تجربة محلية
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # واضبط ADMIN_PASS لإنشاء أول مدير
COOKIE_SECURE=0 python serve.py # http://localhost:8110
```
(`COOKIE_SECURE=0` للتجربة المحلية فقط؛ على الخادم الدخول عبر https.)

## الاختبار
```bash
pip install pytest playwright && python -m playwright install chromium
python -m pytest -q tests
python tests/ui_audit.py        # يجب أن ينتهي بـ 0 ملاحظات
```
