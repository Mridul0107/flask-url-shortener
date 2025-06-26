import csv
from io import StringIO
from flask import Flask, Response, abort, request, jsonify
from url_shortener.models import URL, ClickLog  # adjust this import to match your structure
from url_shortener.app import app  # Adjust to match your actual app module path

@app.route('/export/<short_code>')
def export_analytics(short_code):
    url = URL.query.filter_by(short_code=short_code).first()
    if not url:
        abort(404)
    
    # Get all click logs for this URL
    clicks = ClickLog.query.filter_by(url_id=url.id).all()
    
    # Create CSV data
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Timestamp', 'IP Address', 'User Agent', 'Referrer'])
    
    # Write click data
    for click in clicks:
        writer.writerow([
            click.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            click.ip_address,
            click.user_agent,
            click.referrer or 'Direct'
        ])
    
    # Create response
    csv_data = output.getvalue()
    output.close()
    
    response = Response(
        csv_data,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=analytics_{short_code}.csv'
        }
    )
    
    return response

# Alternative JSON export endpoint
@app.route('/export/<short_code>/json')
def export_analytics_json(short_code):
    url = URL.query.filter_by(short_code=short_code).first()
    if not url:
        abort(404)
    
    clicks = ClickLog.query.filter_by(url_id=url.id).all()
    
    analytics_data = {
        'short_code': short_code,
        'original_url': url.original_url,
        'total_clicks': len(clicks),
        'clicks': [
            {
                'timestamp': click.timestamp.isoformat(),
                'ip_address': click.ip_address,
                'user_agent': click.user_agent,
                'referrer': click.referrer
            }
            for click in clicks
        ]
    }
    
    return jsonify(analytics_data)

if __name__ == '__main__':
    app.run(debug=True)
