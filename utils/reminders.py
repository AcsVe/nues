"""تذكيرات البريد الدورية، تُستدعى من خيط في serve.py كل بضع دقائق:
1) التذكير المحدّد بوقت على حجز (لصاحبه أو للإدارة).
2) الملخص اليومي لحجوزات اليوم لجهات الاتصال المعنية، في الوقت المضبوط (مرة واحدة كل يوم).
3) تذكير اقتراب الحجز لجهات الاتصال المعنية قبل بدايته بعدد الدقائق المضبوط (مرة لكل حجز).
كلها تتبع مفاتيح «الإعدادات ← التذكيرات»."""
from datetime import datetime, timedelta

import email_service as mail
import services as svc
from models import AppSetting, BookingReminder, Booking, db


def _on(key, default=True):
    return AppSetting.get_bool(key, default)


def check_and_send_reminders():
    res = {'scheduled': 0, 'summary': 0, 'upcoming': 0}
    if not _on('reminders_enabled', True):
        return res
    now = svc.amman_now()

    # 1) تذكيرات محدّدة بوقت
    if _on('reminder_scheduled_enabled', True):
        due = BookingReminder.query.filter(BookingReminder.sent.is_(False), BookingReminder.remind_at <= now).all()
        for r in due:
            b = db.session.get(Booking, r.booking_id)
            r.sent = True
            if not b or b.status in ('rejected', 'cancelled') or b.start_date < now.date():
                continue          # حجز زال أو فات: يُغلق التذكير دون بريد
            p = svc.booking_payload(b)
            if r.kind == 'booker':
                svc.notify(mail.send_booker_reminder, p, r.note or '')
            else:
                svc.notify(mail.send_upcoming_reminder, r.recipient_email, p, 0)
            res['scheduled'] += 1
        db.session.commit()

    # 2) الملخص اليومي
    if AppSetting.get_bool('staff_daily_summary_enabled', False):
        at = AppSetting.get_str('staff_daily_summary_time', '07:00') or '07:00'
        today = now.strftime('%Y-%m-%d')
        if now.strftime('%H:%M') >= at and AppSetting.get_str('last_daily_summary', '') != today:
            AppSetting.set_str('last_daily_summary', today)
            rows = Booking.query.filter(Booking.status == 'approved', Booking.start_date <= now.date(),
                                        Booking.end_date >= now.date()).order_by(Booking.start_time).all()
            for c in svc._contacts_for(None, 'notify_staff_reminder'):
                items = [{'time': 'يوم كامل' if b.full_day else f'{b.start_time or ""} - {b.end_time or ""}', 'hall': b.hall_name,
                          'title': b.title, 'name': b.full_name} for b in rows if not c.hall_name or c.hall_name == b.hall_name]
                if items:
                    svc.notify(mail.send_daily_summary, c.email, today, items)
                    res['summary'] += 1

    # 3) اقتراب موعد الحجز
    lead = (AppSetting.get_str('staff_reminder_lead_minutes', '') or '').strip()
    if lead.isdigit() and int(lead) > 0:
        horizon = now + timedelta(minutes=int(lead))
        cands = Booking.query.filter(Booking.status == 'approved', Booking.staff_reminder_sent.isnot(True),
                                     Booking.start_date == now.date(), Booking.full_day.isnot(True)).all()
        for b in cands:
            try:
                start = datetime.strptime(f'{b.start_date:%Y-%m-%d} {b.start_time}', '%Y-%m-%d %H:%M')
            except (TypeError, ValueError):
                continue
            if now <= start <= horizon:
                b.staff_reminder_sent = True
                for c in svc._contacts_for(b.hall_name, 'notify_staff_reminder'):
                    svc.notify(mail.send_upcoming_reminder, c.email, svc.booking_payload(b), int(lead))
                    res['upcoming'] += 1
        db.session.commit()
    return res
