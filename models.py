from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import string
import random

db = SQLAlchemy()

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_url = db.Column(db.Text, nullable=False)
    short_code = db.Column(db.String(10), unique=True, nullable=False)
    clicks = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<URL {self.short_code}>'
    
    @staticmethod
    def generate_short_code():
        characters = string.ascii_letters + string.digits
        while True:
            code = ''.join(random.choice(characters) for _ in range(6))
            if not URL.query.filter_by(short_code=code).first():
                return code
            from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import string
import random

db = SQLAlchemy()

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_url = db.Column(db.Text, nullable=False)
    short_code = db.Column(db.String(10), unique=True, nullable=False)
    clicks = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)  # NEW
    password = db.Column(db.String(255), nullable=True)  # NEW
    is_active = db.Column(db.Boolean, default=True)  # NEW
    click_limit = db.Column(db.Integer, nullable=True)  # NEW
    description = db.Column(db.String(255), nullable=True)  # NEW
    
    def __repr__(self):
        return f'<URL {self.short_code}>'
    
    def is_expired(self):
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    def is_click_limit_reached(self):
        if self.click_limit:
            return self.clicks >= self.click_limit
        return False
    
    def is_accessible(self):
        return (self.is_active and 
                not self.is_expired() and 
                not self.is_click_limit_reached())
    
    @staticmethod
    def generate_short_code():
        characters = string.ascii_letters + string.digits
        while True:
            code = ''.join(random.choice(characters) for _ in range(6))
            if not URL.query.filter_by(short_code=code).first():
                return code

# NEW: Click tracking model
class ClickLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url_id = db.Column(db.Integer, db.ForeignKey('URL.id'), nullable=False)
    clicked_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    referrer = db.Column(db.Text)
    country = db.Column(db.String(2))
    
    class Category(db.Model):
     __tablename__ = 'category'

    category_id = db.Column(db.Integer, db.ForeignKey('category.category_id'), primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    emoji = db.Column(db.String(5), nullable=True)  # ✅ NEW: Emoji field
    color = db.Column(db.String(7), default="#384361")  # Optional: background color
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Category {self.emoji or ""} {self.name}>'


# Add to URL model:
class URL(db.Model):
    # ... existing fields ...
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    tags = db.Column(db.Text, nullable=True)  # JSON string of tags
    
    category = db.relationship('Category', backref=db.backref('urls', lazy=True))