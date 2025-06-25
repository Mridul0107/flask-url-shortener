from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from models import db, URL, ClickLog
from urllib.parse import urlparse
from datetime import datetime, timedelta
import qrcode, io, base64, re, requests
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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

def generate_qr_code(url):
    """Generate QR code for the URL"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def check_url_safety(url):
    """Check if URL is safe (basic blacklist check)"""
    dangerous_domains = ['malware.com', 'phishing.com', 'scam.com']
    domain = urlparse(url).netloc.lower()
    for bad_domain in dangerous_domains:
        if bad_domain in domain:
            return False, "Potentially dangerous domain detected"
    return True, "Safe"

def fetch_url_preview(url):
    """Fetch URL preview data (title, description, domain)"""
    try:
        response = requests.get(url, timeout=5, headers={'User-Agent': 'URL Shortener Bot'})
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title = soup.find('title')
        title = title.get_text().strip() if title else "No title available"
        
        description = soup.find('meta', attrs={'name': 'description'})
        description = description.get('content', '').strip() if description else "No description available"
        
        domain = urlparse(url).netloc
        
        return {
            'title': title,
            'description': description,
            'domain': domain
        }
    except Exception as e:
        return {
            'title': 'Unable to fetch title',
            'description': 'Unable to fetch description',
            'domain': urlparse(url).netloc if url else 'Unknown'
        }

@app.route("/", methods=["GET", "POST"])
def index():
    """Main page for URL shortening"""
    if request.method == "POST":
        original_url = request.form['url'].strip()
        custom_code = request.form.get('custom_code', '').strip()
        description = request.form.get('description', '').strip()
        expires_in = request.form.get('expires_in', '')
        click_limit = request.form.get('click_limit', '')

        # Validate and process URL
        original_url = add_protocol(original_url)
        if not is_valid_url(original_url):
            flash('Invalid URL format. Please enter a valid URL.', 'error')
            return render_template("index.html")

        # Check URL safety
        is_safe, safety_msg = check_url_safety(original_url)
        if not is_safe:
            flash(f'Unsafe URL detected: {safety_msg}', 'error')
            return render_template("index.html")

        # Handle expiration date
        expires_at = None
        if expires_in:
            try:
                days = int(expires_in)
                if days <= 0:
                    raise ValueError("Days must be positive")
                expires_at = datetime.now() + timedelta(days=days)
            except ValueError:
                flash('Invalid expiration days. Please enter a positive number.', 'error')
                return render_template("index.html")

        # Handle click limit
        click_limit_int = None
        if click_limit:
            try:
                click_limit_int = int(click_limit)
                if click_limit_int <= 0:
                    raise ValueError("Click limit must be positive")
            except ValueError:
                flash('Invalid click limit. Please enter a positive number.', 'error')
                return render_template("index.html")

        # Generate short code
        if custom_code:
            # Validate custom code
            if not re.match(r'^[a-zA-Z0-9_-]+$', custom_code):
                flash('Custom code can only contain letters, numbers, hyphens, and underscores.', 'error')
                return render_template("index.html")
            short_code = custom_code
        else:
            short_code = URL.generate_unique_short_code()

        # Create new URL entry
        new_url = URL(
            original_url=original_url,
            short_code=short_code,
            description=description or None,
            expires_at=expires_at,
            click_limit=click_limit_int,
            is_active=True
        )

        try:
            db.session.add(new_url)
            db.session.commit()
            
            short_url_full = request.host_url + short_code
            qr_code = generate_qr_code(short_url_full)
            
            return render_template("index.html", 
                                 short_url=new_url,  # Pass the URL object
                                 short_url_full=short_url_full,  # Pass the full URL string
                                 original_url=original_url,
                                 qr_code=qr_code,
                                 expires_at=expires_at,
                                 click_limit=click_limit_int,
                                 description=description)
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating short URL: {str(e)}', 'error')
            return render_template("index.html")

    return render_template("index.html")

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
        successful_urls = []

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
                
            short_code = URL.generate_unique_short_code()
            new_url = URL(
                original_url=original_url, 
                short_code=short_code,
                is_active=True
            )
            
            try:
                db.session.add(new_url)
                successful_urls.append(new_url)
                results.append({
                    'original': original_url,
                    'shortened': request.host_url + short_code,
                    'status': 'success'
                })
            except Exception as e:
                results.append({
                    'original': original_url,
                    'shortened': '',
                    'status': f'error - database error: {str(e)}'
                })

        # Commit all successful URLs at once
        try:
            db.session.commit()
            success_count = len([r for r in results if r['status'] == 'success'])
            flash(f'Successfully shortened {success_count} out of {len(urls)} URLs', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving URLs to database: {str(e)}', 'error')
            
        return render_template('bulk.html', results=results)

    return render_template('bulk.html')

@app.route("/<short_code>")
def redirect_url(short_code):
    """Redirect to original URL"""
    # Get the most recent active URL for this short code
    url = URL.get_active_url(short_code)
    
    if not url:
        return render_template("error.html", 
                             message="This link does not exist, has expired, or has reached its click limit."), 404
    
    # Log the click if ClickLog table exists
    try:
        click_log = ClickLog(
            url_id=url.id,
            ip_address=request.environ.get('HTTP_X_REAL_IP', request.remote_addr),
            user_agent=request.headers.get('User-Agent'),
            referrer=request.headers.get('Referer')
        )
        db.session.add(click_log)
    except Exception:
        pass  # ClickLog might not exist yet
    
    # Increment click count
    url.clicks += 1
    
    # Check if this click puts us at the limit
    if url.click_limit and url.clicks >= url.click_limit:
        url.is_active = False
    
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    return redirect(url.original_url)

@app.route('/preview/<short_code>')
def preview(short_code):
    """Preview URL without redirecting"""
    # Get the most recent URL for this short code
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
    # Show stats for all URLs with this short code
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
    except Exception:
        pass  # ClickLog might not exist
    
    return render_template("stats.html", 
                         urls=urls, 
                         short_code=short_code, 
                         total_clicks=total_clicks,
                         active_count=len(active_urls),
                         click_logs=click_logs[:50])  # Show last 50 clicks

@app.route('/api/shorten', methods=['POST'])
def api_shorten():
    """API endpoint for URL shortening"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'error': 'URL is required'}), 400
        
        original_url = add_protocol(data['url'].strip())
        if not is_valid_url(original_url):
            return jsonify({'error': 'Invalid URL format'}), 400
        
        is_safe, safety_msg = check_url_safety(original_url)
        if not is_safe:
            return jsonify({'error': f'Unsafe URL: {safety_msg}'}), 400
        
        short_code = URL.generate_unique_short_code()
        new_url = URL(
            original_url=original_url,
            short_code=short_code,
            is_active=True
        )
        
        db.session.add(new_url)
        db.session.commit()
        
        return jsonify({
            'short_url': request.host_url + short_code,
            'original_url': original_url,
            'short_code': short_code
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

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
    print("📋 Available endpoints:")
    print("   - /            : Main shortening interface")
    print("   - /bulk        : Bulk URL shortening")
    print("   - /preview/<code> : Preview URL without redirecting")
    print("   - /stats/<code>   : View statistics for a short URL")
    print("   - /api/shorten    : API endpoint for URL shortening")
    print("   - /health         : Health check endpoint")
    
    app.run(debug=True, host='0.0.0.0', port=5000)