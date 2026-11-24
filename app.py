import os
from datetime import datetime

from flask import Flask, jsonify, request

from config import Config
from models import Hall, add_missing_columns, db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS']['connect_args'] = {'timeout': 30}
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 60 * 60 * 24 * 7
    db.init_app(app)

    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        from sqlalchemy import event
        with app.app_context():
            @event.listens_for(db.engine, 'connect')
            def _pragmas(conn, _rec):
                cur = conn.cursor()
                cur.execute('PRAGMA journal_mode=WAL')
                cur.execute('PRAGMA synchronous=NORMAL')
                cur.execute('PRAGMA busy_timeout=30000')
                cur.close()

    with app.app_context():
        db.create_all()
        add_missing_columns()      # ترحيل آلي: أعمدة جديدة تُضاف دون مسح بيانات
        if Hall.query.count() == 0:
            db.session.add_all([
                Hall(name_ar='القاعة الرئيسية', name_en='Main Hall', location='المبنى الرئيسي', code='H001',
                     capacity='100', equipment='جهاز عرض، سبورة ذكية', active=True, category='hall'),
                Hall(name_ar='قاعة الاجتماعات', name_en='Meeting Room', location='المبنى الرئيسي', code='H002',
                     capacity='30', equipment='شاشة، ميكروفون', active=True, category='hall'),
                Hall(name_ar='المسرح', name_en='Theater', location='المبنى الرئيسي', code='T001',
                     capacity='250', equipment='إضاءة وصوتيات', active=True, category='theater', requires_approval=True),
                Hall(name_ar='الملعب الرئيسي', name_en='Main Field', location='الساحة الخارجية', code='F001',
                     capacity='60', active=True, category='field'),
                Hall(name_ar='الصالة الرياضية', name_en='Sports Hall', location='المبنى الرياضي', code='G001',
                     capacity='80', active=True, category='gym')])
            db.session.commit()
        from utils.auth import ensure_first_admin
        ensure_first_admin(app)
        from utils.brand import ensure_brand
        ensure_brand(app)

    from blueprints.admin import admin_bp, api_bp
    from blueprints.public import public_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    from utils import app_version, favicon, page_shield
    app_version.install(app, os.path.dirname(os.path.abspath(__file__)))
    favicon.install(app)
    page_shield.install(app)

    _static_v = {}

    @app.context_processor
    def _brand_context():
        from utils.brand import get_brand

        def asset(path):
            # رقم نسخة من تاريخ الملف حتى لا يبقى المتصفح على نسخة قديمة
            if path not in _static_v:
                try:
                    _static_v[path] = int(os.path.getmtime(os.path.join(app.static_folder, path)))
                except OSError:
                    _static_v[path] = 0
            return f'/static/{path}?v={_static_v[path]}'
        return {'brand': get_brand(), 'asset': asset, 'now_year': datetime.now().year}

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        if request.path.startswith('/api/'):
            resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.errorhandler(413)
    def _too_large(_e):
        return jsonify({'error': 'الملف كبير جداً'}), 413

    return app


app = create_app()
