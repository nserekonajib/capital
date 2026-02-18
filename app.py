import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, flash, redirect, url_for, session
from routes.config import Config
from routes.auth import auth_bp, login_required
from flask_caching import Cache
from routes.adminauth import adminauth_bp
from routes.students_management import students_bp
from routes.courses_lectures import courses_bp
from routes.schedule_lectures import schedule_bp
import logging
from routes.library_management import library_bp, student_library_bp
from routes.dashboard import dashboard_bp
from flask_cors import CORS
from routes.admin_payments import admin_payments_bp



from routes.payments import payments_bp
# from routes.student_dashboard import student_dashboard_bp
from routes.courses import my_courses_bp
from routes.requests import requests_bp
from routes.library_management import library_bp
from routes.profile import profile_bp
from routes.admin_dashboard import admin_dashboard_bp
from routes.payments import payments_bp
from routes.reports import admin_reports_bp
import os
import time
from routes.ai import ai_bp


if hasattr(time, 'tzset'):
    os.environ['TZ'] = 'Africa/Kampala'
    time.tzset()


def format_datetime(value, format='medium'):
    """Format a datetime object to a readable string"""
    if value is None:
        return ""
    
    if isinstance(value, str):
        # Try to parse the string to datetime
        try:
            # Handle different datetime string formats
            for fmt in ['%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    value = datetime.datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue
        except:
            return value
    
    if isinstance(value, datetime.datetime):
        if format == 'full':
            format = "%B %d, %Y at %I:%M %p"
        elif format == 'medium':
            format = "%b %d, %Y %I:%M %p"
        else:
            format = "%Y-%m-%d"
        return value.strftime(format)
    
    return value

# Register the filter with Jinja2
def register_filters(app):
    app.jinja_env.filters['datetimeformat'] = format_datetime

# In your main app initialization:

load_dotenv()
app = Flask(__name__)
CORS(app)
app.config.from_object(Config)
register_filters(app)

# Register the authentication blueprint
app.register_blueprint(auth_bp)
app.register_blueprint(adminauth_bp)
app.register_blueprint(students_bp)
app.register_blueprint(courses_bp)
app.register_blueprint(schedule_bp)
app.register_blueprint(library_bp, url_prefix='/admin/library')
app.register_blueprint(student_library_bp, url_prefix='/api/library')
app.register_blueprint(profile_bp, url_prefix='/profile')
app.register_blueprint(dashboard_bp, url_prefix='/dashboards')
app.register_blueprint(admin_dashboard_bp)
app.register_blueprint(admin_payments_bp, url_prefix='/admin')




app.register_blueprint(payments_bp)

app.register_blueprint(my_courses_bp, url_prefix='/my-courses')
app.register_blueprint(requests_bp)
app.register_blueprint(admin_reports_bp, url_prefix='/admin/reports')
app.register_blueprint(ai_bp, url_prefix='/ai')


cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})

# Initialize in your app
cache.init_app(app)

@app.route('/')
def index():
    # Redirect to login if not authenticated, otherwise to dashboard
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth.login'))


@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500


if __name__ == '__main__':
    # Set up logging
    # logging.basicConfig(level=logging.INFO)
    app.run(debug=True, port=3000)





