from flask import Blueprint, render_template, session, jsonify
from routes.admin_utils import get_admin_client
from routes.adminauth import admin_login_required
import logging
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)

admin_dashboard_bp = Blueprint('admin_dashboard', __name__)

def get_admin_stats():
    """Get comprehensive admin dashboard statistics"""
    try:
        client = get_admin_client()
        stats = {
            'total_students': 0,
            'total_courses': 0,
            'total_requests': 0,
            'pending_requests': 0,
            'total_live_classes': 0,
            'active_live_classes': 0,
            'total_resources': 0,
            'recent_activity': []
        }
        
        # Get total students
        students_res = client.from_("students").select("id", count="exact").execute()
        stats['total_students'] = students_res.count if hasattr(students_res, 'count') else len(students_res.data or [])
        
        # Get total courses
        courses_res = client.from_("courses").select("id", count="exact").execute()
        stats['total_courses'] = courses_res.count if hasattr(courses_res, 'count') else len(courses_res.data or [])
        
        # Get requests statistics
        requests_res = client.from_("requests").select("id, status").execute()
        if requests_res.data:
            stats['total_requests'] = len(requests_res.data)
            stats['pending_requests'] = len([r for r in requests_res.data if r.get('status') == 'pending'])
        
        # Get live classes statistics
        live_classes_res = client.from_("live_classes").select("id, is_active").execute()
        if live_classes_res.data:
            stats['total_live_classes'] = len(live_classes_res.data)
            stats['active_live_classes'] = len([lc for lc in live_classes_res.data if lc.get('is_active')])
        
        # Get library resources count
        resources_res = client.from_("library_resources").select("id", count="exact").execute()
        stats['total_resources'] = resources_res.count if hasattr(resources_res, 'count') else len(resources_res.data or [])
        
        # Get recent activity (last 10 activities)
        recent_requests = client.from_("requests")\
            .select("*, students(full_name), courses(title)")\
            .order('requested_at', desc=True)\
            .limit(5)\
            .execute()
        
        recent_enrollments = client.from_("enrollments")\
            .select("*, students(full_name), courses(title)")\
            .order('enrolled_at', desc=True)\
            .limit(5)\
            .execute()
        
        # Format recent activity
        activities = []
        
        if recent_requests.data:
            for req in recent_requests.data:
                student_name = req.get('students', {}).get('full_name', 'Unknown Student')
                course_title = req.get('courses', {}).get('title', 'Unknown Course')
                activities.append({
                    'type': 'request',
                    'title': f'New course request from {student_name}',
                    'description': f'Requested: {course_title}',
                    'timestamp': req.get('requested_at'),
                    'status': req.get('status', 'pending'),
                    'icon': 'send',
                    'color': 'warning' if req.get('status') == 'pending' else 'success' if req.get('status') == 'approved' else 'danger'
                })
        
        if recent_enrollments.data:
            for enroll in recent_enrollments.data:
                student_name = enroll.get('students', {}).get('full_name', 'Unknown Student')
                course_title = enroll.get('courses', {}).get('title', 'Unknown Course')
                activities.append({
                    'type': 'enrollment',
                    'title': f'New enrollment: {student_name}',
                    'description': f'Enrolled in: {course_title}',
                    'timestamp': enroll.get('enrolled_at'),
                    'status': 'enrolled',
                    'icon': 'person-plus',
                    'color': 'success'
                })
        
        # Sort by timestamp and get top 10
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        stats['recent_activity'] = activities[:10]
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        return {}

def get_upcoming_live_classes():
    """Get upcoming live classes for admin dashboard"""
    try:
        client = get_admin_client()
        today = datetime.now().date()
        
        live_classes_res = client.from_("live_classes")\
            .select("*, courses(title, instructor)")\
            .gte('scheduled_date', today.isoformat())\
            .eq('is_active', True)\
            .order('scheduled_date')\
            .order('scheduled_time')\
            .limit(5)\
            .execute()
        
        upcoming_classes = []
        if live_classes_res.data:
            for class_data in live_classes_res.data:
                course_data = class_data.get('courses', {})
                class_date = class_data['scheduled_date']
                class_time = class_data['scheduled_time']
                
                # Create datetime object
                if isinstance(class_date, str):
                    class_date = datetime.strptime(class_date, '%Y-%m-%d').date()
                if isinstance(class_time, str):
                    class_time = datetime.strptime(class_time, '%H:%M:%S').time()
                
                class_datetime = datetime.combine(class_date, class_time)
                
                upcoming_classes.append({
                    'id': class_data['id'],
                    'title': class_data.get('class_title', 'Live Class'),
                    'course_title': course_data.get('title', 'Unknown Course'),
                    'instructor': course_data.get('instructor', 'Unknown Instructor'),
                    'datetime': class_datetime,
                    'zoom_join_url': class_data.get('zoom_join_url'),
                     'zoom_start_url': class_data.get('zoom_join_url'),
                    'duration': class_data.get('duration_minutes', 60)
                })
        
        return upcoming_classes
        
    except Exception as e:
        logger.error(f"Error getting upcoming live classes: {e}")
        return []

def get_system_health():
    """Get system health metrics"""
    try:
        client = get_admin_client()
        health = {
            'database': 'healthy',
            'storage': 'healthy',
            'api': 'healthy',
            'last_checked': datetime.now().isoformat()
        }
        
        # Test database connection
        test_res = client.from_("students").select("id").limit(1).execute()
        if not test_res.data:
            health['database'] = 'degraded'
        
        return health
        
    except Exception as e:
        logger.error(f"Error checking system health: {e}")
        return {
            'database': 'unhealthy',
            'storage': 'unknown',
            'api': 'unknown',
            'last_checked': datetime.now().isoformat()
        }

@admin_dashboard_bp.route('/admin/dashboard')
@admin_login_required
def dashboard():
    """Admin dashboard main page"""
    try:
        admin_stats = get_admin_stats()
        upcoming_classes = get_upcoming_live_classes()
        system_health = get_system_health()
        
        return render_template(
            'admin/dashboard.html',
            admin_stats=admin_stats,
            upcoming_classes=upcoming_classes,
            system_health=system_health,
            admin_role=session.get('admin_role'),
            admin_email=session.get('admin_email'),
            current_time=datetime.now(),
            timedelta=timedelta  # Add this line
        )
        
    except Exception as e:
        logger.error(f"Error in admin dashboard route: {e}")
        return render_template(
            'admin/dashboard.html',
            admin_stats={},
            upcoming_classes=[],
            system_health={},
            admin_role=session.get('admin_role'),
            admin_email=session.get('admin_email'),
            current_time=datetime.now(),
            timedelta=timedelta  # Add this line
        )

@admin_dashboard_bp.route('/admin/api/stats')
@admin_login_required
def api_stats():
    """API endpoint for dashboard stats"""
    try:
        stats = get_admin_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error in API stats: {e}")
        return jsonify({"error": str(e)}), 500

# Add this to your main app initialization
def init_admin_dashboard_routes(app):
    """Initialize admin dashboard routes with the Flask app"""
    app.register_blueprint(admin_dashboard_bp)