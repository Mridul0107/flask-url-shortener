from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, URL, ClickLog
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse
from datetime import datetime, timedelta
import qrcode, io, base64, re, requests
from bs4 import BeautifulSoup
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///urls.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Add this after your imports and before app configuration
import os

# Force development configuration
if os.environ.get('FLASK_ENV') == 'development' or not os.environ.get('CUSTOM_DOMAIN'):
    CUSTOM_DOMAIN = 'localhost:5000'
    USE_HTTPS = False
else:
    # Configuration for custom domain (production)
    CUSTOM_DOMAIN = os.environ.get('CUSTOM_DOMAIN', 'localhost:5000')
    USE_HTTPS = os.environ.get('USE_HTTPS', 'false').lower() == 'true'

PROTOCOL = 'https' if USE_HTTPS else 'http'
# Configuration for custom domain
CUSTOM_DOMAIN = os.environ.get('CUSTOM_DOMAIN', 'localhost:5000')
USE_HTTPS = os.environ.get('USE_HTTPS', 'false').lower() == 'true'
PROTOCOL = 'https' if USE_HTTPS else 'http'

db.init_app(app)

def is_valid_url(url):
    """Check if URL is valid"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def add_protocol(url):
    """Add http:// if no protocol is specified"""
    if not url.startswith(('http://', 'https://')):
        return 'http://' + url
    return url

def get_base_url():
    """Get the base URL for the application"""
    return f"{PROTOCOL}://{CUSTOM_DOMAIN}"

def generate_qr_code(url):
    """Generate QR code for the URL"""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return None

def check_url_safety(url):
    """Check if URL is safe (basic blacklist check)"""
    dangerous_domains = ['malware.com', 'phishing.com', 'scam.com', 'spam.com']
    try:
        domain = urlparse(url).netloc.lower()
        
        for bad_domain in dangerous_domains:
            if bad_domain in domain:
                return False, "Potentially dangerous domain detected"
        
        if len(url) > 2000:
            return False, "URL is suspiciously long"
        
        return True, "Safe"
    except Exception:
        return False, "Invalid URL format"

def fetch_url_preview(url):
    """Fetch URL preview data (title, description, domain)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=5, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title = soup.find('title')
        title = title.get_text().strip() if title else "No title available"
        
        description = soup.find('meta', attrs={'name': 'description'})
        if not description:
            description = soup.find('meta', attrs={'property': 'og:description'})
        description = description.get('content', '').strip() if description else "No description available"
        
        domain = urlparse(url).netloc
        
        return {
            'title': title[:100] + ('...' if len(title) > 100 else ''),
            'description': description[:200] + ('...' if len(description) > 200 else ''),
            'domain': domain
        }
    except Exception as e:
        return {
            'title': 'Unable to fetch title',
            'description': 'Unable to fetch description',
            'domain': urlparse(url).netloc if url else 'Unknown'
        }

def log_click(url, request):
    """Log click details for analytics"""
    try:
        click_log = ClickLog(
            url_id=url.id,
            ip_address=request.environ.get('HTTP_X_REAL_IP', request.remote_addr),
            user_agent=request.headers.get('User-Agent'),
            referrer=request.headers.get('Referer')
        )
        db.session.add(click_log)
        db.session.commit()
    except Exception as e:
        print(f"Error logging click: {e}")

@app.route("/", methods=["GET", "POST"])
def index():
    """Main page for URL shortening"""
    if request.method == "POST":
        try:
            data = request.get_json() if request.is_json else request.form
            
            original_url = data.get('url', '').strip()
            custom_code = data.get('custom_code', '').strip()
            description = data.get('description', '').strip()
            expires_in = data.get('expires_in', '')
            password = data.get('password', '').strip()
            click_limit = data.get('click_limit', '')

            if not original_url:
                if request.is_json:
                    return jsonify({'error': 'Please enter a URL'}), 400
                flash('Please enter a URL', 'error')
                return render_template('index.html')

            # Validate and process URL
            original_url = add_protocol(original_url)
            if not is_valid_url(original_url):
                if request.is_json:
                    return jsonify({'error': 'Invalid URL format'}), 400
                flash('Invalid URL format. Please enter a valid URL.', 'error')
                return render_template("index.html")

            # Check URL safety
            is_safe, safety_msg = check_url_safety(original_url)
            if not is_safe:
                if request.is_json:
                    return jsonify({'error': f'Unsafe URL: {safety_msg}'}), 400
                flash(f'Unsafe URL detected: {safety_msg}', 'error')
                return render_template("index.html")

            # Handle expiration date
            expires_at = None
            if expires_in:
                try:
                    days = int(expires_in)
                    if days <= 0 or days > 365:
                        raise ValueError("Days must be between 1 and 365")
                    expires_at = datetime.now() + timedelta(days=days)
                except ValueError as e:
                    if request.is_json:
                        return jsonify({'error': 'Invalid expiration days'}), 400
                    flash('Invalid expiration days. Please enter a number between 1 and 365.', 'error')
                    return render_template("index.html")

            # Handle click limit
            click_limit_int = None
            if click_limit:
                try:
                    click_limit_int = int(click_limit)
                    if click_limit_int <= 0:
                        raise ValueError("Click limit must be positive")
                except ValueError:
                    if request.is_json:
                        return jsonify({'error': 'Invalid click limit'}), 400
                    flash('Invalid click limit. Please enter a positive number.', 'error')
                    return render_template("index.html")

            # Generate short code
            if custom_code:
                # Validate custom code
                if len(custom_code) < 3 or len(custom_code) > 20:
                    if request.is_json:
                        return jsonify({'error': 'Custom code must be 3-20 characters'}), 400
                    flash('Custom code must be 3-20 characters', 'error')
                    return render_template('index.html')
                
                if not re.match(r'^[a-zA-Z0-9_-]+$', custom_code):
                    if request.is_json:
                        return jsonify({'error': 'Custom code can only contain letters, numbers, hyphens, and underscores'}), 400
                    flash('Custom code can only contain letters, numbers, hyphens, and underscores.', 'error')
                    return render_template("index.html")
                
                if URL.query.filter_by(short_code=custom_code).first():
                    if request.is_json:
                        return jsonify({'error': 'Custom code already exists'}), 400
                    flash('Custom code already exists', 'error')
                    return render_template('index.html')
                
                short_code = custom_code
            else:
                short_code = URL.generate_unique_short_code()

            # Hash password if provided
            hashed_password = None
            if password:
                hashed_password = generate_password_hash(password)

            # Create new URL entry
            new_url = URL(
                original_url=original_url,
                short_code=short_code,
                description=description or None,
                expires_at=expires_at,
                password=hashed_password,
                click_limit=click_limit_int,
                is_active=True
            )

            db.session.add(new_url)
            db.session.commit()
            
            base_url = get_base_url()
            short_url_full = f"{base_url}/{short_code}"
            qr_code = generate_qr_code(short_url_full)
            
            # Get URL preview
            preview_data = fetch_url_preview(original_url)
            
            if request.is_json:
                return jsonify({
                    'success': True,
                    'short_url': short_url_full,
                    'short_code': short_code,
                    'original_url': original_url,
                    'qr_code': qr_code,
                    'preview': preview_data,
                    'expires_at': expires_at.isoformat() if expires_at else None,
                    'has_password': bool(password),
                    'click_limit': click_limit_int
                }), 201
            
            return render_template("index.html", 
                                 short_url=new_url,
                                 short_url_full=short_url_full,
                                 original_url=original_url,
                                 qr_code=qr_code,
                                 preview_data=preview_data,
                                 expires_at=expires_at,
                                 has_password=bool(password),
                                 click_limit=click_limit_int,
                                 description=description)
                                 
        except Exception as e:
            db.session.rollback()
            error_msg = f'Error creating short URL: {str(e)}'
            if request.is_json:
                return jsonify({'error': error_msg}), 500
            flash(error_msg, 'error')
            return render_template("index.html")

    return render_template("index.html", base_url=get_base_url())

@app.route('/bulk', methods=['GET', 'POST'])
def bulk_shorten():
    """Bulk URL shortening"""
    if request.method == 'POST':
        urls_text = request.form.get('urls', '').strip()
        if not urls_text:
            flash('Please enter URLs to shorten', 'error')
            return render_template('bulk.html')
        
        urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
        if len(urls) > 50:
            flash('Maximum 50 URLs allowed at once', 'error')
            return render_template('bulk.html')
            
        results = []
        successful_count = 0

        for original_url in urls:
            original_url = add_protocol(original_url)
            
            if not is_valid_url(original_url):
                results.append({
                    'original': original_url,
                    'shortened': '',
                    'status': 'error - invalid URL format'
                })
                continue
                
            is_safe, safety_msg = check_url_safety(original_url)
            if not is_safe:
                results.append({
                    'original': original_url,
                    'shortened': '',
                    'status': f'error - unsafe URL: {safety_msg}'
                })
                continue
                
            try:
                short_code = URL.generate_unique_short_code()
                new_url = URL(
                    original_url=original_url, 
                    short_code=short_code,
                    is_active=True
                )
                
                db.session.add(new_url)
                results.append({
                    'original': original_url,
                    'shortened': f"{get_base_url()}/{short_code}",
                    'status': 'success'
                })
                successful_count += 1
                
            except Exception as e:
                results.append({
                    'original': original_url,
                    'shortened': '',
                    'status': f'error - {str(e)}'
                })

        # Commit all successful URLs
        try:
            db.session.commit()
            flash(f'Successfully shortened {successful_count} out of {len(urls)} URLs', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving URLs: {str(e)}', 'error')
            
        return render_template('bulk.html', results=results)

    return render_template('bulk.html')

@app.route("/<short_code>")
def redirect_url(short_code):
    """Redirect to original URL"""
    url = URL.get_active_url(short_code)
    
    if not url:
        return render_template("error.html", 
                             message="This link does not exist, has expired, or has reached its click limit."), 404
    
    # Check if URL is accessible
    if not url.is_accessible():
        if url.is_expired():
            return render_template('error.html', message='This link has expired'), 410
        elif url.is_click_limit_reached():
            return render_template('error.html', message='This link has reached its click limit'), 410
        else:
            return render_template('error.html', message='This link is not accessible'), 403
    
    # Check password protection
    if url.password:
        if f'auth_{short_code}' not in session:
            return redirect(url_for('password_check', short_code=short_code))
    
    # Log the click
    log_click(url, request)
    
    # Increment click count
    url.clicks += 1
    
    # Check if this click puts us at the limit
    if url.click_limit and url.clicks >= url.click_limit:
        url.is_active = False
    
    try:
        db.session.commit()
    except Exception as e:
        print(f"Error updating click count: {e}")
        db.session.rollback()
    
    return redirect(url.original_url)

@app.route('/password/<short_code>', methods=['GET', 'POST'])
def password_check(short_code):
    """Handle password-protected URLs"""
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
def preview(short_code):
    """Preview URL without redirecting"""
    url = URL.query.filter_by(short_code=short_code).order_by(URL.created_at.desc()).first()
    
    if not url:
        return render_template("error.html", message="This link does not exist."), 404
    
    # Check if URL is accessible
    if not url.is_accessible():
        flash('Warning: This URL has expired or reached its click limit.', 'warning')
    
    preview_data = fetch_url_preview(url.original_url)
    return render_template("preview.html", url=url, preview_data=preview_data)

@app.route('/stats/<short_code>')
def stats(short_code):
    """Show statistics for a short code"""
    urls = URL.query.filter_by(short_code=short_code).order_by(URL.created_at.desc()).all()
    if not urls:
        flash("Short URL not found", "error")
        return redirect(url_for("index"))
    
    # Calculate combined stats
    total_clicks = sum(url.clicks for url in urls)
    active_urls = [url for url in urls if url.is_accessible()]
    
    # Get click logs if available
    click_logs = []
    try:
        for url in urls:
            logs = ClickLog.query.filter_by(url_id=url.id).order_by(ClickLog.clicked_at.desc()).limit(50).all()
            click_logs.extend(logs)
        click_logs.sort(key=lambda x: x.clicked_at, reverse=True)
    except Exception as e:
        print(f"Error fetching click logs: {e}")
    
    return render_template("stats.html", 
                         urls=urls, 
                         short_code=short_code, 
                         total_clicks=total_clicks,
                         active_count=len(active_urls),
                         click_logs=click_logs[:50])

@app.route('/dashboard')
def dashboard():
    """Admin dashboard"""
    try:
        recent_urls = URL.query.order_by(URL.created_at.desc()).limit(10).all()
        total_urls = URL.query.count()
        total_clicks = db.session.query(db.func.sum(URL.clicks)).scalar() or 0
        
        # Get click statistics for the last 7 days
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        daily_clicks = []
        try:
            daily_clicks = db.session.query(
                db.func.date(ClickLog.clicked_at).label('date'),
                db.func.count(ClickLog.id).label('clicks')
            ).filter(ClickLog.clicked_at >= seven_days_ago).group_by(
                db.func.date(ClickLog.clicked_at)
            ).all()
        except Exception as e:
            print(f"Error fetching daily clicks: {e}")
        
        return render_template('dashboard.html', 
                             recent_urls=recent_urls,
                             total_urls=total_urls,
                             total_clicks=total_clicks,
                             daily_clicks=daily_clicks,
                             base_url=get_base_url())
    except Exception as e:
        print(f"Error in dashboard: {e}")
        return render_template('error.html', message='Error loading dashboard'), 500

@app.route('/api/shorten', methods=['POST'])
def api_shorten():
    """API endpoint for URL shortening"""
    return index()  # Reuse the main index logic

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        return jsonify({
            'status': 'healthy', 
            'timestamp': datetime.now().isoformat(),
            'base_url': get_base_url()
        }), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/config')
def show_config():
    """Show current configuration"""
    return jsonify({
        'base_url': get_base_url(),
        'custom_domain': CUSTOM_DOMAIN,
        'protocol': PROTOCOL,
        'database_url': app.config['SQLALCHEMY_DATABASE_URI']
    })

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', message='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('error.html', message='Internal server error'), 500

if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            print("✅ Database tables created/verified successfully")
        except Exception as e:
            print(f"⚠️  Database setup warning: {e}")
    
    print("🚀 Starting Flask URL Shortener application...")
    print(f"🌐 Base URL: {get_base_url()}")
    print("📋 Available endpoints:")
    print("   - /                : Main shortening interface")
    print("   - /bulk            : Bulk URL shortening")
    print("   - /preview/<code>  : Preview URL without redirecting")
    print("   - /stats/<code>    : View statistics for a short URL")
    print("   - /password/<code> : Password protection for URLs")
    print("   - /dashboard       : Admin dashboard")
    print("   - /api/shorten     : API endpoint for URL shortening")
    print("   - /health          : Health check endpoint")
    print("   - /config          : Show current configuration")
    print("📝 Configuration:")
    print(f"   - Custom Domain: {CUSTOM_DOMAIN}")
    print(f"   - Protocol: {PROTOCOL}")
    print(f"   - Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)