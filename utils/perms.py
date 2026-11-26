"""صلاحيات لوحة التحكم: مدير النظام يملك كل شيء، وللمستخدم العادي صلاحيات يختارها المدير."""

# المفتاح ← (العربية، الإنجليزية، المجموعة)
CATALOGUE = {
    'bookings.view': ('عرض طلبات الحجز', 'View booking requests', 'daily'),
    'bookings.manage': ('إدارة الطلبات (موافقة ورفض وإلغاء وتعديل وحذف وتعليقات)', 'Manage requests (approve, reject, cancel, edit, delete, comments)', 'daily'),
    'calendar': ('التقويم', 'Calendar', 'daily'),
    'blocked': ('الفترات غير المتاحة', 'Unavailable periods', 'daily'),
    'reports': ('التقارير', 'Reports', 'lists'),
    'audit': ('سجل التدقيق', 'Audit log', 'lists'),
    'halls': ('المباني والمرافق', 'Buildings and facilities', 'admin'),
    'contacts': ('جهات الاتصال', 'Contacts', 'admin'),
    'ticker': ('الشريط الإخباري', 'News ticker', 'admin'),
    'links': ('الروابط المختصرة', 'Short links', 'admin'),
    'archive': ('الأرشفة والنسخة الكاملة', 'Archive and full backup', 'admin'),
    'settings.identity': ('الإعدادات: الهوية والشعار', 'Settings: identity and logo', 'settings'),
    'settings.approval': ('الإعدادات: الاعتماد التلقائي', 'Settings: automatic approval', 'settings'),
    'settings.reminders': ('الإعدادات: التذكيرات', 'Settings: reminders', 'settings'),
}

PRESETS = {
    'supervisor': ['bookings.view', 'bookings.manage', 'calendar', 'blocked', 'reports'],
    'viewer': ['bookings.view', 'calendar', 'reports'],
}


def can(user, perm):
    """perm: مفتاح، أو مجموعة مفاتيح (يكفي واحد منها)."""
    if user is None:
        return False
    if user.is_sysadmin:
        return True
    have = set(user.perm_list())
    if isinstance(perm, (tuple, list, set)):
        return any(p in have for p in perm)
    return perm in have


def clean(perms):
    """يُبقي المفاتيح المعروفة فقط."""
    return [p for p in perms if p in CATALOGUE]
