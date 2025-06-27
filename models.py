from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import random
import string
import json

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

    def to_dict(self):
        """Convert category to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'emoji': self.emoji,
            'color': self.color,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'url_count': len(self.urls) if self.urls else 0
        }

    def __repr__(self):
        return f"<Category {self.emoji or ''} {self.name}>"


class URL(db.Model):
    __tablename__ = 'url'

    id = db.Column(db.Integer, primary_key=True)
    original_url = db.Column(db.Text, nullable=False)
    short_code = db.Column(db.String(20), nullable=False, unique=True, index=True)
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
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def is_click_limit_reached(self):
        """Check if the click limit has been reached"""
        if self.click_limit is None:
            return False
        return self.clicks >= self.click_limit

    def is_accessible(self):
        """Check if the URL is still accessible (not expired and within click limits)"""
        return self.is_active and not self.is_expired() and not self.is_click_limit_reached()

    def get_tags(self):
        """Get tags as a list"""
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_tags(self, tags_list):
        """Set tags from a list"""
        if isinstance(tags_list, list):
            self.tags = json.dumps(tags_list)
        else:
            self.tags = None

    def increment_clicks(self):
        """Increment click count safely"""
        self.clicks = (self.clicks or 0) + 1

    def to_dict(self):
        """Convert URL to dictionary"""
        return {
            'id': self.id,
            'original_url': self.original_url,
            'short_code': self.short_code,
            'description': self.description,
            'clicks': self.clicks,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'click_limit': self.click_limit,
            'is_active': self.is_active,
            'is_accessible': self.is_accessible(),
            'tags': self.get_tags(),
            'category_id': self.category_id,
            'category': self.category.to_dict() if self.category else None,
            'has_password': bool(self.password)
        }

    @staticmethod
    def generate_short_code(length=6):
        """Generate a random short code"""
        characters = string.ascii_letters + string.digits
        return ''.join(random.choices(characters, k=length))

    @staticmethod
    def is_short_code_available(short_code):
        """Check if a short code can be used (no active URLs are using it)"""
        try:
            existing_url = URL.query.filter_by(short_code=short_code).first()
            if not existing_url:
                return True
            
            # Check if existing URL is still active and accessible
            if not existing_url.is_active:
                return True
                
            if existing_url.is_expired() or existing_url.is_click_limit_reached():
                return True
                
            return False
        except Exception as e:
            print(f"Error checking short code availability: {e}")
            return False

    @staticmethod
    def get_active_url(short_code):
        """Get the active URL for a short code"""
        try:
            url = URL.query.filter_by(short_code=short_code, is_active=True).first()
            
            if not url:
                return None
                
            if url.is_expired() or url.is_click_limit_reached():
                return None
                
            return url
        except Exception as e:
            print(f"Error getting active URL: {e}")
            return None

    @staticmethod
    def generate_unique_short_code(length=6, max_attempts=100):
        """Generate a unique short code, trying up to max_attempts times"""
        for attempt in range(max_attempts):
            short_code = URL.generate_short_code(length)
            if URL.is_short_code_available(short_code):
                return short_code
        
        # If we can't find a unique code with current length, try with longer length
        if length < 20:  # Prevent infinite recursion
            return URL.generate_unique_short_code(length + 1, max_attempts)
        
        # Last resort: use timestamp-based code
        timestamp = str(int(datetime.utcnow().timestamp()))[-6:]
        random_suffix = ''.join(random.choices(string.ascii_letters, k=2))
        return f"{timestamp}{random_suffix}"

    def deactivate(self):
        """Deactivate this URL, making its short code available for reuse"""
        self.is_active = False

    def reactivate(self):
        """Reactivate this URL if possible"""
        if URL.is_short_code_available(self.short_code):
            self.is_active = True
            return True
        return False

    @staticmethod
    def cleanup_expired_urls():
        """Clean up expired and limit-reached URLs"""
        try:
            expired_urls = URL.query.filter(
                db.and_(
                    URL.is_active == True,
                    db.or_(
                        db.and_(URL.expires_at.isnot(None), URL.expires_at <= datetime.utcnow()),
                        db.and_(URL.click_limit.isnot(None), URL.clicks >= URL.click_limit)
                    )
                )
            ).all()
            
            count = 0
            for url in expired_urls:
                url.deactivate()
                count += 1
            
            if count > 0:
                db.session.commit()
                
            return count
        except Exception as e:
            print(f"Error during cleanup: {e}")
            db.session.rollback()
            return 0

    def __repr__(self):
        status = "Active" if self.is_accessible() else "Inactive"
        url_preview = self.original_url[:50] + "..." if len(self.original_url) > 50 else self.original_url
        return f"<URL {self.short_code} -> {url_preview} [{status}]>"


class ClickLog(db.Model):
    __tablename__ = 'click_log'

    id = db.Column(db.Integer, primary_key=True)
    url_id = db.Column(db.Integer, db.ForeignKey('url.id', ondelete='CASCADE'), nullable=False)
    clicked_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))  # IPv6 can be up to 45 chars
    user_agent = db.Column(db.Text)
    referrer = db.Column(db.Text)
    country = db.Column(db.String(2), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    browser = db.Column(db.String(50), nullable=True)
    os = db.Column(db.String(50), nullable=True)
    device_type = db.Column(db.String(20), nullable=True)  # mobile, desktop, tablet

    def to_dict(self):
        """Convert click log to dictionary"""
        return {
            'id': self.id,
            'url_id': self.url_id,
            'clicked_at': self.clicked_at.isoformat() if self.clicked_at else None,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'referrer': self.referrer,
            'country': self.country,
            'city': self.city,
            'browser': self.browser,
            'os': self.os,
            'device_type': self.device_type
        }

    @staticmethod
    def get_click_stats(url_id, days=30):
        """Get click statistics for a URL over the last N days"""
        try:
            from_date = datetime.utcnow() - timedelta(days=days)
            
            clicks = ClickLog.query.filter(
                ClickLog.url_id == url_id,
                ClickLog.clicked_at >= from_date
            ).all()
            
            stats = {
                'total_clicks': len(clicks),
                'unique_ips': len(set(click.ip_address for click in clicks if click.ip_address)),
                'countries': {},
                'browsers': {},
                'os': {},
                'device_types': {},
                'daily_clicks': {}
            }
            
            for click in clicks:
                # Count by country
                if click.country:
                    stats['countries'][click.country] = stats['countries'].get(click.country, 0) + 1
                
                # Count by browser
                if click.browser:
                    stats['browsers'][click.browser] = stats['browsers'].get(click.browser, 0) + 1
                
                # Count by OS
                if click.os:
                    stats['os'][click.os] = stats['os'].get(click.os, 0) + 1
                
                # Count by device type
                if click.device_type:
                    stats['device_types'][click.device_type] = stats['device_types'].get(click.device_type, 0) + 1
                
                # Count by day
                if click.clicked_at:
                    day_key = click.clicked_at.strftime('%Y-%m-%d')
                    stats['daily_clicks'][day_key] = stats['daily_clicks'].get(day_key, 0) + 1
            
            return stats
        except Exception as e:
            print(f"Error getting click stats: {e}")
            return None

    def __repr__(self):
        return f"<ClickLog URL_ID={self.url_id} at {self.clicked_at} from {self.ip_address}>"


# Utility functions for database operations
def init_db(app):
    """Initialize database with Flask app"""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        create_default_categories()

def create_default_categories():
    """Create default categories if they don't exist"""
    default_categories = [
        {'name': 'General', 'emoji': '🔗', 'color': '#384361'},
        {'name': 'Social Media', 'emoji': '📱', 'color': '#3b82f6'},
        {'name': 'Work', 'emoji': '💼', 'color': '#059669'},
        {'name': 'Entertainment', 'emoji': '🎬', 'color': '#dc2626'},
        {'name': 'Education', 'emoji': '📚', 'color': '#7c3aed'},
        {'name': 'Shopping', 'emoji': '🛒', 'color': '#ea580c'},
    ]
    
    for cat_data in default_categories:
        existing = Category.query.filter_by(name=cat_data['name']).first()
        if not existing:
            category = Category(**cat_data)
            db.session.add(category)
    
    try:
        db.session.commit()
    except Exception as e:
        print(f"Error creating default categories: {e}")
        db.session.rollback()