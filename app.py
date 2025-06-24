from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from models import db, URL
import qrcode
import io
import base64
from urllib.parse import urlparse
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def is_valid_url(url):
    """Validate URL format"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def add_protocol(url):
    """Add http:// if no protocol specified"""
    if not url.startswith(('http://', 'https://')):
        return 'http://' + url
    return url

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        original_url = request.form['url'].strip()
        custom_code = request.form.get('custom_code', '').strip()
        
        if not original_url:
            flash('Please enter a URL', 'error')
            return render_template('index.html')
        
        # Add protocol if missing
        original_url = add_protocol(original_url)
        
        # Validate URL
        if not is_valid_url(original_url):
            flash('Please enter a valid URL', 'error')
            return render_template('index.html')
        
        # Handle custom code
        if custom_code:
            if len(custom_code) < 3 or len(custom_code) > 20:
                flash('Custom code must be 3-20 characters', 'error')
                return render_template('index.html')
            
            if not re.match('^[a-zA-Z0-9_-]+$', custom_code):
                flash('Custom code can only contain letters, numbers, hyphens, and underscores', 'error')
                return render_template('index.html')
            
            if URL.query.filter_by(short_code=custom_code).first():
                flash('Custom code already exists', 'error')
                return render_template('index.html')
            
            short_code = custom_code
        else:
            short_code = URL.generate_short_code()
        
        # Create new URL entry
        new_url = URL(original_url=original_url, short_code=short_code)
        db.session.add(new_url)
        db.session.commit()
        
        # Generate QR code
        qr_code = generate_qr_code(request.host_url + short_code)
        
        return render_template('index.html', 
                             short_url=request.host_url + short_code,
                             qr_code=qr_code,
                             original_url=original_url)
    
    return render_template('index.html')

@app.route('/<short_code>')
def redirect_url(short_code):
    url = URL.query.filter_by(short_code=short_code).first()
    if url:
        url.clicks += 1
        db.session.commit()
        return redirect(url.original_url)
    else:
        flash('URL not found', 'error')
        return redirect(url_for('index'))

@app.route('/stats/<short_code>')
def stats(short_code):
    url = URL.query.filter_by(short_code=short_code).first()
    if url:
        return render_template('stats.html', url=url)
    else:
        flash('URL not found', 'error')
        return redirect(url_for('index'))

def generate_qr_code(url):
    """Generate QR code for URL"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64 for embedding in HTML
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return img_str

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
from models import db, URL, ClickLog
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
import io
import base64
from urllib.parse import urlparse
import re
from datetime import datetime, timedelta
import requests
import json

# Add these new routes to your existing app.py

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        original_url = request.form['url'].strip()
        custom_code = request.form.get('custom_code', '').strip()
        description = request.form.get('description', '').strip()
        expires_in = request.form.get('expires_in', '')
        password = request.form.get('password', '').strip()
        click_limit = request.form.get('click_limit', '')
        
        if not original_url:
            flash('Please enter a URL', 'error')
            return render_template('index.html')
        
        # Add protocol if missing
        original_url = add_protocol(original_url)
        
        # Validate URL
        if not is_valid_url(original_url):
            flash('Please enter a valid URL', 'error')
            return render_template('index.html')
        
        # Handle expiration
        expires_at = None
        if expires_in:
            try:
                days = int(expires_in)
                if days > 0:
                    expires_at = datetime.utcnow() + timedelta(days=days)
            except ValueError:
                flash('Invalid expiration days', 'error')
                return render_template('index.html')
        
        # Handle click limit
        click_limit_int = None
        if click_limit:
            try:
                click_limit_int = int(click_limit)
                if click_limit_int <= 0:
                    click_limit_int = None
            except ValueError:
                flash('Invalid click limit', 'error')
                return render_template('index.html')
        
        # Handle custom code
        if custom_code:
            if len(custom_code) < 3 or len(custom_code) > 20:
                flash('Custom code must be 3-20 characters', 'error')
                return render_template('index.html')
            
            if not re.match('^[a-zA-Z0-9_-]+$', custom_code):
                flash('Custom code can only contain letters, numbers, hyphens, and underscores', 'error')
                return render_template('index.html')
            
            if URL.query.filter_by(short_code=custom_code).first():
                flash('Custom code already exists', 'error')
                return render_template('index.html')
            
            short_code = custom_code
        else:
            short_code = URL.generate_short_code()
        
        # Hash password if provided
        hashed_password = None
        if password:
            hashed_password = generate_password_hash(password)
        
        # Create new URL entry
        new_url = URL(
            original_url=original_url, 
            short_code=short_code,
            expires_at=expires_at,
            password=hashed_password,
            click_limit=click_limit_int,
            description=description
        )
        db.session.add(new_url)
        db.session.commit()
        
        # Generate QR code
        qr_code = generate_qr_code(request.host_url + short_code)
        
        return render_template('index.html', 
                             short_url=request.host_url + short_code,
                             qr_code=qr_code,
                             original_url=original_url,
                             expires_at=expires_at,
                             has_password=bool(password),
                             click_limit=click_limit_int)
    
    return render_template('index.html')

@app.route('/<short_code>')
def redirect_url(short_code):
    url = URL.query.filter_by(short_code=short_code).first()
    
    if not url:
        flash('URL not found', 'error')
        return redirect(url_for('index'))
    
    # Check if URL is accessible
    if not url.is_accessible():
        if url.is_expired():
            return render_template('error.html', message='This link has expired')
        elif url.is_click_limit_reached():
            return render_template('error.html', message='This link has reached its click limit')
        else:
            return render_template('error.html', message='This link is not accessible')
    
    # Check password protection
    if url.password:
        if f'auth_{short_code}' not in session:
            return redirect(url_for('password_check', short_code=short_code))
    
    # Log the click
    log_click(url, request)
    
    # Increment click count
    url.clicks += 1
    db.session.commit()
    
    return redirect(url.original_url)

@app.route('/password/<short_code>', methods=['GET', 'POST'])
def password_check(short_code):
    url = URL.query.filter_by(short_code=short_code).first()
    
    if not url or not url.password:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        if check_password_hash(url.password, password):
            session[f'auth_{short_code}'] = True
            return redirect(url_for('redirect_url', short_code=short_code))
        else:
            flash('Incorrect password', 'error')
    
    return render_template('password.html', short_code=short_code)

@app.route('/preview/<short_code>')
def preview_url(short_code):
    url = URL.query.filter_by(short_code=short_code).first()
    if not url:
        abort(404)
    
    # Get website preview data
    preview_data = get_url_preview(url.original_url)
    
    return render_template('preview.html', url=url, preview_data=preview_data)

@app.route('/bulk', methods=['GET', 'POST'])
def bulk_shorten():
    if request.method == 'POST':
        urls_text = request.form.get('urls', '').strip()
        if not urls_text:
            flash('Please enter URLs to shorten', 'error')
            return render_template('bulk.html')
        
        urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
        results = []
        
        for original_url in urls:
            original_url = add_protocol(original_url)
            if is_valid_url(original_url):
                short_code = URL.generate_short_code()
                new_url = URL(original_url=original_url, short_code=short_code)
                db.session.add(new_url)
                results.append({
                    'original': original_url,
                    'shortened': request.host_url + short_code,
                    'status': 'success'
                })
            else:
                results.append({
                    'original': original_url,
                    'shortened': None,
                    'status': 'error'
                })
        
        db.session.commit()
        return render_template('bulk.html', results=results)
    
    return render_template('bulk.html')

@app.route('/api/shorten', methods=['POST'])
def api_shorten():
    """API endpoint for URL shortening"""
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400
    
    original_url = data['url'].strip()
    original_url = add_protocol(original_url)
    
    if not is_valid_url(original_url):
        return jsonify({'error': 'Invalid URL'}), 400
    
    custom_code = data.get('custom_code', '').strip()
    
    if custom_code:
        if URL.query.filter_by(short_code=custom_code).first():
            return jsonify({'error': 'Custom code already exists'}), 400
        short_code = custom_code
    else:
        short_code = URL.generate_short_code()
    
    new_url = URL(original_url=original_url, short_code=short_code)
    db.session.add(new_url)
    db.session.commit()
    
    return jsonify({
        'original_url': original_url,
        'short_url': request.host_url + short_code,
        'short_code': short_code
    })

@app.route('/dashboard')
def dashboard():
    """Admin dashboard"""
    recent_urls = URL.query.order_by(URL.created_at.desc()).limit(10).all()
    total_urls = URL.query.count()
    total_clicks = db.session.query(db.func.sum(URL.clicks)).scalar() or 0
    
    # Get click statistics for the last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    daily_clicks = db.session.query(
        db.func.date(ClickLog.clicked_at).label('date'),
        db.func.count(ClickLog.id).label('clicks')
    ).filter(ClickLog.clicked_at >= seven_days_ago).group_by(
        db.func.date(ClickLog.clicked_at)
    ).all()
    
    return render_template('dashboard.html', 
                         recent_urls=recent_urls,
                         total_urls=total_urls,
                         total_clicks=total_clicks,
                         daily_clicks=daily_clicks)

def log_click(url, request):
    """Log click details for analytics"""
    click_log = ClickLog(
        url_id=url.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        referrer=request.referrer
    )
    db.session.add(click_log)
    db.session.commit()

def get_url_preview(url):
    """Get website preview data"""
    try:
        response = requests.get(url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title = soup.find('title')
        title = title.text.strip() if title else 'No title'
        
        description = soup.find('meta', attrs={'name': 'description'})
        description = description.get('content', 'No description') if description else 'No description'
        
        return {
            'title': title,
            'description': description,
            'domain': urlparse(url).netloc
        }
    except:
        return {
            'title': 'Preview not available',
            'description': 'Unable to fetch preview',
            'domain': urlparse(url).netloc
        }
@app.route('/health-check/<short_code>')
def health_check(short_code):
    url = URL.query.filter_by(short_code=short_code).first()
    if not url:
        return jsonify({'error': 'URL not found'}), 404
    
    try:
        response = requests.head(url.original_url, timeout=10, allow_redirects=True)
        status = 'healthy' if response.status_code == 200 else 'unhealthy'
        return jsonify({
            'short_code': short_code,
            'original_url': url.original_url,
            'status': status,
            'status_code': response.status_code,
            'response_time': f"{response.elapsed.total_seconds():.2f}s"
        })
    except Exception as e:
        return jsonify({
            'short_code': short_code,
            'original_url': url.original_url,
            'status': 'error',
            'error': str(e)
        })
    from urllib.parse import urlparse

def check_url_safety(url):
    """Basic URL safety check"""
    dangerous_domains = [
        'malware.com', 'phishing.com', 'spam.com'
    ]
    
    domain = urlparse(url).netloc.lower()

    for dangerous in dangerous_domains:
        if dangerous in domain:
            return False, "Potentially dangerous domain detected"
    
    if len(url) > 2000:
        return False, "URL is suspiciously long"
    
    return True, "URL appears safe"


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        original_url = request.form['url'].strip()

        # Safety check must come AFTER original_url is defined
        is_safe, safety_message = check_url_safety(original_url)
        if not is_safe:
            flash(f'Safety warning: {safety_message}', 'warning')
            return render_template('index.html')