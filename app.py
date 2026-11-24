import os

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
                     capacity='100', equipment='جهاز عرض، سبورة ذكية', active=True),
                Hall(name_ar='قاعة الاجتماعات', name_en='Meeting Room', location='المبنى الرئيسي', code='H002',
                     capacity='30', equipment='شاشة، ميكروفون', active=True)])
            db.session.commit()
        from utils.auth import ensure_first_admin
        ensure_first_admin(app)
        from utils.brand import ensure_brand
        ensure_brand(app)

    from routes import main_bp
    app.register_blueprint(main_bp)

    from utils import app_version, favicon, page_shield
    app_version.install(app, os.path.dirname(os.path.abspath(__file__)))
    favicon.install(app)
    page_shield.install(app)

    @app.context_processor
    def _brand_context():
        from utils.brand import get_brand
        return {'brand': get_brand()}

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
