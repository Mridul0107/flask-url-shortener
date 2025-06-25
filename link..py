import csv
from io import StringIO
from flask import Response, abort
from url_shortener.models import URL, ClickLog  # adjust this import to match your structure
from url_shortener.app import app  # Adjust to match your actual app module path

@app.route('/export/<short_code>')
def export_analytics(short_code):
    url = URL.query.filter_by(short_code=short_code).first()
    if not url:
        abort(404)

    # Fetch click logs
    clicks = ClickLog.query.filter_by(url_id=url.id).order_by(ClickLog.clicked_at.desc()).all()

    # Create CSV in-memory
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Time', 'IP Address', 'User Agent', 'Referrer'])

    for click in clicks:
        writer.writerow([
            click.clicked_at.strftime('%Y-%m-%d'),
            click.clicked_at.strftime('%H:%M:%S'),
            click.ip_address or 'Unknown',
            click.user_agent or 'Unknown',
            click.referrer or 'Direct'
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={short_code}_analytics.csv'}
    )