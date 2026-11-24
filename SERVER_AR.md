# تشغيل نظام الجمعية (ACS) على الخادم

> الأوامر بأحرف إنجليزية وسطر واحد لكل أمر، لتُنسخ وتُلصق في الطرفية.

| البند | القيمة |
|---|---|
| العنوان | `https://acs.edjo.win` |
| المجلد | `/opt/ras/ACS` |
| الخدمة | `acs-ras` |
| المنفذ | `8110` (محلي فقط، ويصل إليه نفق Cloudflare) |
| الإعدادات | `/opt/ras/ACS/.env` |
| البيانات | `/opt/ras/ACS/data` (القاعدة `acs_venues.db` والمرفقات `uploads`) |
| النسخ الاحتياطي | `/opt/ras/backups/ACS` (يومياً 03:15، وتُحفظ 14 يوماً) |

## 1) التثبيت (مرة واحدة)
```bash
curl -fsSL https://raw.githubusercontent.com/AcsVe/nues/main/deploy/install_server.sh | bash
```
ثم أنشئ المدير (كلمة المرور تُكتب **مخفية**):
```bash
cd /opt/ras/ACS && IAJ_LANG=en .venv/bin/python ops/reset_password.py --create
```
ثم أضف العنوان إلى نفق Cloudflare (من لوحة Cloudflare، لا من الخادم):
1. Zero Trust ← Networks ← Tunnels ← النفق `edjo-server` ← Public Hostname ← Add.
2. Subdomain: `acs`، Domain: `edjo.win`، Service: `HTTP` والعنوان `localhost:8110`.
3. احفظ، ثم افتح https://acs.edjo.win

## 2) التحديث (بعد دمج تعديل)
```bash
cd /opt/ras/ACS && git pull --ff-only origin main && sudo systemctl restart acs-ras && sleep 3 && systemctl is-active acs-ras && git log --oneline -1 | cut -c1-7 && curl -s -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8110/healthz
```
المتوقع: `active` ثم رقم النسخة ثم `health=200`. بعدها افتح الصفحة بـ `Ctrl + Shift + R`.

## 3) الفحص السريع
```bash
systemctl is-active acs-ras
```
```bash
sudo journalctl -u acs-ras -n 40 --no-pager
```
```bash
tail -n 40 /opt/ras/ACS/logs/server.log
```

## 4) نسيان كلمة المرور / إضافة مدير
```bash
cd /opt/ras/ACS && IAJ_LANG=en .venv/bin/python ops/reset_password.py
```
يعرض الحسابات ثم يسأل عن اسم المستخدم وكلمة المرور الجديدة (مخفية). `--create` لإنشاء حساب جديد.

## 5) البريد (Microsoft 365)
ضع القيم نفسها المستعملة في بقية الأنظمة في `/opt/ras/ACS/.env`: `MS_TENANT_ID` و`MS_CLIENT_ID` و`MS_CLIENT_SECRET` و`MS_SENDER_EMAIL`، ثم:
```bash
sudo systemctl restart acs-ras
```
تظهر حالة البريد في «لوحة التحكم ← الإعدادات».

## 5-أ) التذكيرات الآلية
تعمل من داخل الخدمة نفسها كل 5 دقائق. لإيقافها: ضع `DISABLE_REMINDERS=1` في `/opt/ras/ACS/.env` ثم أعد تشغيل الخدمة. ولتغيير الفترة: `REMINDER_EVERY=600` (بالثواني).

## 6) النسخ الاحتياطي والاسترجاع
نسخة يدوية الآن:
```bash
cd /opt/ras/ACS && .venv/bin/python ops/backup.py
```
الاسترجاع (استبدل اسم الملف بنسخة من القائمة):
```bash
ls -1 /opt/ras/backups/ACS
```
```bash
cd /opt/ras/ACS && sudo systemctl stop acs-ras && unzip -o /opt/ras/backups/ACS/acs-XXXX.zip -d data && sudo systemctl start acs-ras
```

## 7) إيقاف / تشغيل / إعادة تشغيل
```bash
sudo systemctl restart acs-ras
```
```bash
sudo systemctl stop acs-ras
```
```bash
sudo systemctl start acs-ras
```
