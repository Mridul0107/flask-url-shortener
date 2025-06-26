from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import random
import string

db = SQLAlchemy()

class Category(db.Model):
    __tablename__ = 'category'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    emoji = db.Column(db.String(5), nullable=True)
    color = db.Column(db.String(7), default="#384361")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # One-to-many: Category → URLs
    urls = db.relationship('URL', backref='category', lazy=True)

    def __repr__(self):
        return f"<Category {self.emoji or ''} {self.name}>"


class URL(db.Model):
    __tablename__ = 'url'

    id = db.Column(db.Integer, primary_key=True)
    original_url = db.Column(db.Text, nullable=False)
    short_code = db.Column(db.String(20), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    clicks = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Expiration and limits
    expires_at = db.Column(db.DateTime, nullable=True)
    click_limit = db.Column(db.Integer, nullable=True)
    password = db.Column(db.String(255), nullable=True)
    
    # Status and categorization
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    tags = db.Column(db.Text, nullable=True)  # JSON string of tags

    # Foreign key to Category
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)

    # Relationship to click logs
    click_logs = db.relationship('ClickLog', backref='url', lazy=True, cascade='all, delete-orphan')

    def is_expired(self):
        """Check if the URL has expired"""
        return self.expires_at and datetime.utcnow() > self.expires_at

    def is_click_limit_reached(self):
        """Check if the click limit has been reached"""
        return self.click_limit is not None and self.clicks >= self.click_limit

    def is_accessible(self):
        """Check if the URL is still accessible (not expired and within click limits)"""
        return self.is_active and not self.is_expired() and not self.is_click_limit_reached()

    @staticmethod
    def generate_short_code(length=6):
        """Generate a random short code"""
        characters = string.ascii_letters + string.digits
        return ''.join(random.choices(characters, k=length))

    @staticmethod
    def is_short_code_available(short_code):
        """Check if a short code can be used (no active URLs are using it)"""
        active_urls = URL.query.filter_by(
            short_code=short_code,
            is_active=True
        ).filter(
            db.or_(
                URL.expires_at.is_(None),
                URL.expires_at > datetime.utcnow()
            )
        ).filter(
            db.or_(
                URL.click_limit.is_(None),
                URL.clicks < URL.click_limit
            )
        ).first()
        
        return active_urls is None

    @staticmethod
    def get_active_url(short_code):
        """Get the active URL for a short code"""
        return URL.query.filter_by(
            short_code=short_code,
            is_active=True
        ).filter(
            db.or_(
                URL.expires_at.is_(None),
                URL.expires_at > datetime.utcnow()
            )
        ).filter(
            db.or_(
                URL.click_limit.is_(None),
                URL.clicks < URL.click_limit
            )
        ).first()

    @staticmethod
    def generate_unique_short_code(length=6, max_attempts=100):
        """Generate a unique short code, trying up to max_attempts times"""
        for _ in range(max_attempts):
            short_code = URL.generate_short_code(length)
            if URL.is_short_code_available(short_code):
                return short_code
        
        # If we can't find a unique code, try with longer length
        return URL.generate_unique_short_code(length + 1, max_attempts)

    def deactivate(self):
        """Deactivate this URL, making its short code available for reuse"""
        self.is_active = False
        db.session.commit()

    def __repr__(self):
        status = "Active" if self.is_accessible() else "Inactive"
        return f"<URL {self.short_code} -> {self.original_url[:50]}... [{status}]>"


class ClickLog(db.Model):
    __tablename__ = 'click_log'

    id = db.Column(db.Integer, primary_key=True)
    url_id = db.Column(db.Integer, db.ForeignKey('url.id', ondelete='CASCADE'), nullable=False)
    clicked_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(100))
    user_agent = db.Column(db.Text)
    referrer = db.Column(db.Text)
    country = db.Column(db.String(2), nullable=True)

    def __repr__(self):
        return f"<ClickLog URL_ID={self.url_id} at {self.clicked_at}>"