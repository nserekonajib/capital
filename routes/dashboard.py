from flask import Blueprint, render_template, session, redirect, url_for, flash
from routes.utils import supabase
import logging
from routes.auth import login_required
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboards', __name__)
def get_user_stats(user_id):
    """Get comprehensive user statistics for dashboard"""
    try:
        stats = {
            'total_courses': 0,
            'total_lectures': 0,
            'completed_lectures': 0,
            'pending_requests': 0,
            'upcoming_live_classes': 0,
            'library_resources': 0
        }
        
        # Get enrolled courses with course IDs
        enrolled_response = supabase.table('enrollments')\
            .select('course_id, courses(id, title)')\
            .eq('user_id', user_id)\
            .eq('active', True)\
            .execute()
        
        stats['total_courses'] = len(enrolled_response.data) if enrolled_response.data else 0
        
        # Get pending requests count
        requests_response = supabase.table('requests')\
            .select('id')\
            .eq('user_id', user_id)\
            .eq('status', 'pending')\
            .execute()
        
        stats['pending_requests'] = len(requests_response.data) if requests_response.data else 0
        
        # Get total lectures across enrolled courses
        if enrolled_response.data:
            enrolled_course_ids = []
            for enrollment in enrolled_response.data:
                # Extract course_id from enrollment
                course_id = enrollment.get('course_id')
                if course_id:
                    enrolled_course_ids.append(course_id)
            
            logger.info(f"Found enrolled course IDs: {enrolled_course_ids}")
            
            if enrolled_course_ids:
                # Get lectures count for these courses
                lectures_response = supabase.table('lectures')\
                    .select('id, course_id')\
                    .in_('course_id', enrolled_course_ids)\
                    .execute()
                
                stats['total_lectures'] = len(lectures_response.data) if lectures_response.data else 0
                logger.info(f"Found {stats['total_lectures']} lectures for courses {enrolled_course_ids}")
        
        # Get upcoming live classes (next 7 days)
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        
        live_classes_response = supabase.table('live_classes')\
            .select('id')\
            .gte('scheduled_date', today.isoformat())\
            .lte('scheduled_date', next_week.isoformat())\
            .eq('is_active', True)\
            .execute()
        
        stats['upcoming_live_classes'] = len(live_classes_response.data) if live_classes_response.data else 0
        
        # Get library resources count
        if enrolled_response.data:
            # Count actual library resources for enrolled courses
            library_response = supabase.table('library_resources')\
                .select('id')\
                .in_('course_id', enrolled_course_ids)\
                .eq('is_active', True)\
                .execute()
            
            stats['library_resources'] = len(library_response.data) if library_response.data else 0
        
        logger.info(f"Final stats: {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}

def get_recent_activity(user_id):
    """Get recent user activity"""
    try:
        activities = []
        
        # Get recent enrollments
        enrollments_response = supabase.table('enrollments')\
            .select('enrolled_at, courses(title)')\
            .eq('user_id', user_id)\
            .eq('active', True)\
            .order('enrolled_at', desc=True)\
            .limit(5)\
            .execute()
        
        if enrollments_response.data:
            for enrollment in enrollments_response.data:
                course_title = "Unknown Course"
                if enrollment.get('courses'):
                    if isinstance(enrollment['courses'], dict):
                        course_title = enrollment['courses'].get('title', 'Unknown Course')
                
                activities.append({
                    'type': 'enrollment',
                    'title': f'Enrolled in {course_title}',
                    'timestamp': enrollment['enrolled_at'],
                    'icon': 'book',
                    'color': 'success'
                })
        
        # Get recent requests
        requests_response = supabase.table('requests')\
            .select('requested_at, courses(title), status')\
            .eq('user_id', user_id)\
            .order('requested_at', desc=True)\
            .limit(5)\
            .execute()
        
        if requests_response.data:
            for request in requests_response.data:
                course_title = "Unknown Course"
                if request.get('courses'):
                    if isinstance(request['courses'], dict):
                        course_title = request['courses'].get('title', 'Unknown Course')
                
                status_color = 'warning' if request['status'] == 'pending' else 'success' if request['status'] == 'approved' else 'danger'
                
                activities.append({
                    'type': 'request',
                    'title': f'Requested {course_title} - {request["status"].title()}',
                    'timestamp': request['requested_at'],
                    'icon': 'send',
                    'color': status_color
                })
        
        # Sort all activities by timestamp and get top 10
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        return activities[:10]
        
    except Exception as e:
        logger.error(f"Error getting recent activity: {e}")
        return []

def get_upcoming_live_classes(user_id):
    """Get upcoming live classes for enrolled courses"""
    try:
        # Get user's enrolled course IDs
        enrolled_response = supabase.table('enrollments')\
            .select('course_id')\
            .eq('user_id', user_id)\
            .eq('active', True)\
            .execute()
        
        if not enrolled_response.data:
            return []
        
        enrolled_course_ids = []
        for enrollment in enrolled_response.data:
            course_id = enrollment.get('course_id')
            if course_id:
                enrolled_course_ids.append(course_id)
        
        if not enrolled_course_ids:
            return []
        
        # Get upcoming live classes
        today = datetime.now().date()
        
        live_classes_response = supabase.table('live_classes')\
            .select('''
                *,
                courses (
                    title,
                    instructor
                )
            ''')\
            .in_('course_id', enrolled_course_ids)\
            .gte('scheduled_date', today.isoformat())\
            .eq('is_active', True)\
            .order('scheduled_date')\
            .order('scheduled_time')\
            .limit(5)\
            .execute()
        
        upcoming_classes = []
        if live_classes_response.data:
            for class_data in live_classes_response.data:
                course_data = class_data.get('courses', {})
                if isinstance(course_data, dict):
                    course_title = course_data.get('title', 'Unknown Course')
                    instructor = course_data.get('instructor', 'Unknown Instructor')
                else:
                    course_title = 'Unknown Course'
                    instructor = 'Unknown Instructor'
                
                # Parse datetime
                class_date = class_data['scheduled_date']
                class_time = class_data['scheduled_time']
                
                # Create datetime object for display
                if isinstance(class_date, str):
                    class_date = datetime.strptime(class_date, '%Y-%m-%d').date()
                if isinstance(class_time, str):
                    class_time = datetime.strptime(class_time, '%H:%M:%S').time()
                
                class_datetime = datetime.combine(class_date, class_time)
                
                upcoming_classes.append({
                    'id': class_data['id'],
                    'title': class_data.get('title', 'Live Class'),
                    'course_title': course_title,
                    'instructor': instructor,
                    'datetime': class_datetime,
                    'duration': class_data.get('duration_minutes', 60),
                    'zoom_join_url': class_data.get('zoom_join_url')
                })
        
        return upcoming_classes
        
    except Exception as e:
        logger.error(f"Error getting upcoming live classes: {e}")
        return []

@dashboard_bp.route('/dashboards')
@login_required
def dashboards():
    """Main dashboard page"""
    if 'user_id' not in session:
        flash('Please log in to access the dashboard', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    user_email = session.get('user_email')
    user_full_name = session.get('user_full_name')
    cpa_level = session.get('cpa_level', 0)
    
    try:
        # Get user statistics
        user_stats = get_user_stats(user_id)
        
        # Get recent activity
        recent_activity = get_recent_activity(user_id)
        
        # Get upcoming live classes
        upcoming_classes = get_upcoming_live_classes(user_id)
        
        # Format CPA level for display
        def format_cpa(level):
            if isinstance(level, int):
                return f"CPA{level}"
            elif isinstance(level, str) and level.isdigit():
                return f"CPA{level}"
            else:
                return str(level)
        
        return render_template(
            'dashboards.html',
            user_stats=user_stats,
            recent_activity=recent_activity,
            upcoming_classes=upcoming_classes,
            user_email=user_email,
            user_full_name=user_full_name,
            cpa_level=format_cpa(cpa_level),
            current_time=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Error in dashboard route: {e}")
        flash('An error occurred while loading the dashboard', 'danger')
        return render_template(
            'dashboards.html',
            user_stats={},
            recent_activity=[],
            upcoming_classes=[],
            user_email=user_email,
            user_full_name=user_full_name,
            cpa_level=cpa_level,
            current_time=datetime.now()
        )

