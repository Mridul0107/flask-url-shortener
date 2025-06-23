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



