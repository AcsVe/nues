from flask import Flask
from config import Config
from models import db
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # تهيئة قاعدة البيانات
    db.init_app(app)

    # التأكد من وجود مجلد الرفع
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    with app.app_context():
        # إنشاء الجداول إذا لم تكن موجودة
        db.create_all()
        
        # إضافة بيانات افتراضية للقاعات إذا كانت فارغة
        from models import Hall
        if Hall.query.count() == 0:
            hall1 = Hall(name_ar='القاعة الرئيسية', name_en='Main Hall', location='المبنى الرئيسي', code='H001', capacity='100', equipment='جهاز عرض، سبورة ذكية', active=True)
            hall2 = Hall(name_ar='قاعة الاجتماعات', name_en='Meeting Room', location='المبنى الرئيسي', code='H002', capacity='30', equipment='شاشة، ميكروفون', active=True)
            db.session.add_all([hall1, hall2])
            db.session.commit()

    # تسجيل مسارات الـ API والصفحات (سننشئها في الخطوة القادمة)
    from routes import main_bp
    app.register_blueprint(main_bp)

    return app


# WSGI entry point used by gunicorn (`gunicorn app:app`)
app = create_app()

if __name__ == '__main__':
    # تشغيل الخادم على البورت 5000 مع تفعيل وضع التصحيح
    app.run(host='0.0.0.0', port=5000, debug=True)