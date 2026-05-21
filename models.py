from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Hall(db.Model):
    __tablename__ = 'halls'
    id = db.Column(db.Integer, primary_key=True)
    name_ar = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100))
    location = db.Column(db.String(200))
    code = db.Column(db.String(50))
    capacity = db.Column(db.String(50))
    equipment = db.Column(db.Text)
    description = db.Column(db.Text)
    notes = db.Column(db.Text)
    requires_approval = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)

class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    req_id = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50))
    behalf = db.Column(db.String(100))
    title = db.Column(db.String(200), nullable=False)
    hall_name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    start_time = db.Column(db.String(10))
    end_time = db.Column(db.String(10))
    full_day = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    attachments = db.Column(db.Text) # سنخزن روابط المرفقات مفصولة بفاصلة
    status = db.Column(db.String(20), default='pending') # pending, approved, rejected, cancelled
    reject_reason = db.Column(db.Text)
    cc_emails = db.Column(db.Text)
    action_date = db.Column(db.DateTime)

class BlockedPeriod(db.Model):
    __tablename__ = 'blocked'
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    hall_name = db.Column(db.String(100)) # فارغ يعني كل القاعات
    start_time = db.Column(db.String(10))
    end_time = db.Column(db.String(10))
    reason = db.Column(db.String(200), default='محظور')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Contact(db.Model):
    __tablename__ = 'contacts'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    name = db.Column(db.String(100))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)