from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from routes.utils import supabase
import logging
from routes.auth import login_required
from datetime import timedelta

# Configure logging
logger = logging.getLogger(__name__)

my_courses_bp = Blueprint('my_courses', __name__)

def extract_int(value: str) -> int:
    """Extracts the first integer found in a string like 'CPA1'."""
    if value is None:
        return None
    num = ''.join(ch for ch in str(value) if ch.isdigit())
    return int(num) if num else None

# Add this helper function
def normalize_cpa_level_to_int(cpa_level):
    """Normalize CPA level to integer for database comparison - uses extract_int"""
    return extract_int(cpa_level)


def get_user_enrolled_courses(user_id):
    """Get all courses that the user is enrolled in and active"""
    try:
        # Get enrolled courses with course details
        response = supabase.table('enrollments')\
            .select('''
                courses (*),
                active,
                enrolled_at
            ''')\
            .eq('user_id', user_id)\
            .eq('active', True)\
            .execute()
        
        if response.data:
            return response.data
        return []
    except Exception as e:
        logger.error(f"Error fetching enrolled courses: {e}")
        return []

def get_course_lectures(course_id):
    """Get all lectures for a specific course ordered by lecture_number"""
    try:
        response = supabase.table('lectures')\
            .select('*')\
            .eq('course_id', course_id)\
            .order('lecture_number')\
            .execute()
        
        if response.data:
            return response.data
        return []
    except Exception as e:
        logger.error(f"Error fetching lectures for course {course_id}: {e}")
        return []

def get_course_details(course_id):
    """Get detailed course information"""
    try:
        response = supabase.table('courses')\
            .select('*')\
            .eq('id', course_id)\
            .single()\
            .execute()
        
        return response.data if response.data else None
    except Exception as e:
        logger.error(f"Error fetching course details {course_id}: {e}")
        return None
    
def has_pending_request(user_id, course_id):
    """Check if user already has a pending request for a course"""
    try:
        response = supabase.table('requests')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('course_id', course_id)\
            .eq('status', 'pending')\
            .execute()
        
        return len(response.data) > 0 if response.data else False
    except Exception as e:
        logger.error(f"Error checking pending request: {e}")
        return False
    
def get_available_courses(user_cpa_level):
    """Get all courses available for the user's CPA level"""
    try:
        logger.info(f"=== GET AVAILABLE COURSES DEBUG START ===")
        logger.info(f"Input CPA level: '{user_cpa_level}' (type: {type(user_cpa_level)})")
        
        # Extract integer from CPA level using your helper function
        cpa_level_int = extract_int(user_cpa_level)
        
        if cpa_level_int is None:
            logger.error(f"Could not extract integer from CPA level: {user_cpa_level}")
            return []
        
        logger.info(f"Extracted CPA level (integer): {cpa_level_int}")
        
        # Get courses for user's CPA level - using INTEGER comparison
        response = supabase.table('courses')\
            .select('*')\
            .eq('cpa_level', cpa_level_int)\
            .execute()
        
        courses = response.data if response.data else []
        logger.info(f"Found {len(courses)} courses for level {cpa_level_int}")
        
        # Log the courses found
        for course in courses:
            logger.info(f"  - {course['title']} (ID: {course['id']}, CPA: {course.get('cpa_level')})")
        
        logger.info("=== GET AVAILABLE COURSES DEBUG END ===")
        return courses
        
    except Exception as e:
        logger.error(f"Error fetching available courses: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

def get_user_requests(user_id):
    """Get all course requests for the user"""
    try:
        response = supabase.table('requests')\
            .select('''
                *,
                courses (*)
            ''')\
            .eq('user_id', user_id)\
            .order('requested_at', desc=True)\
            .execute()
        
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error fetching user requests: {e}")
        return []
    
def format_cpa_for_display(cpa_level):
    """Format CPA level for display in templates"""
    cpa_int = extract_int(cpa_level)
    return f"CPA{cpa_int}" if cpa_int is not None else "Unknown"

def compare_cpa_levels(user_cpa, course_cpa):
    """Robust CPA level comparison that handles different data types"""
    try:
        # Convert both to integers for comparison
        user_int = int(extract_int(user_cpa)) if user_cpa is not None else None
        course_int = int(course_cpa) if course_cpa is not None else None
        
        logger.info(f"CPA Comparison - User: {user_int} (from {repr(user_cpa)}), Course: {course_int} (from {repr(course_cpa)})")
        
        # Handle None values
        if user_int is None or course_int is None:
            return False
            
        return user_int == course_int
        
    except (ValueError, TypeError) as e:
        logger.error(f"Error in CPA comparison: {e}")
        return False
    
def is_course_available_for_user(course_id, user_cpa_level):
    """Direct check if course should be available for user's CPA level"""
    try:
        # Get course CPA level directly
        course_response = supabase.table('courses')\
            .select('cpa_level')\
            .eq('id', course_id)\
            .single()\
            .execute()
        
        if not course_response.data:
            return False
            
        course_cpa = course_response.data.get('cpa_level')
        user_cpa_int = extract_int(user_cpa_level)
        
        # Direct integer comparison
        return user_cpa_int == course_cpa
        
    except Exception as e:
        logger.error(f"Error in direct CPA check: {e}")
        return False

@my_courses_bp.route('/my-courses')
@login_required
def my_courses():
    """Display enrolled courses and available courses for request"""
    if 'user_id' not in session:
        flash('Please log in to access your courses', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    user_cpa_level = session.get('cpa_level', 0)
    
    logger.info(f"=== MY COURSES DEBUG START ===")
    logger.info(f"User {user_id} with CPA level '{user_cpa_level}'")
    
    try:
        # Get enrolled courses
        enrolled_courses_data = get_user_enrolled_courses(user_id)
        enrolled_courses = []
        for enrollment in enrolled_courses_data:
            if enrollment.get('courses'):
                course = enrollment['courses']
                course['enrolled_at'] = enrollment['enrolled_at']
                course['active'] = enrollment['active']
                lectures = get_course_lectures(course['id'])
                course['lecture_count'] = len(lectures)
                enrolled_courses.append(course)
        
        logger.info(f"Enrolled courses found: {len(enrolled_courses)}")
        
        # Get available courses for user's CPA level
        available_courses = get_available_courses(user_cpa_level)
        logger.info(f"Available courses before filtering: {len(available_courses)}")
        
        # Get user's pending requests
        user_requests = get_user_requests(user_id)
        logger.info(f"User requests found: {len(user_requests)}")
        
        # Filter out courses that user is already enrolled in or has pending requests for
        enrolled_course_ids = [course['id'] for course in enrolled_courses]
        requested_course_ids = [req['course_id'] for req in user_requests if req['status'] == 'pending']
        
        available_courses = [course for course in available_courses 
                           if course['id'] not in enrolled_course_ids 
                           and course['id'] not in requested_course_ids]
        
        logger.info(f"Available courses after filtering: {len(available_courses)}")
        
        # Add request status to available courses for display
        for course in available_courses:
            course['can_request'] = True
        
        logger.info("=== MY COURSES DEBUG END ===")
        
        return render_template(
            'my_courses.html',
            enrolled_courses=enrolled_courses,
            available_courses=available_courses,
            user_requests=user_requests,
            user_email=session.get('user_email'),
            user_full_name=session.get('user_full_name'),
            cpa_level=format_cpa_for_display(user_cpa_level)  # Use formatted display
        )
        
    except Exception as e:
        logger.error(f"Error in my_courses route: {e}")
        flash('An error occurred while loading courses', 'danger')
        return render_template('my_courses.html', enrolled_courses=[], available_courses=[], user_requests=[])
    
    

@my_courses_bp.route('/request-course/<int:course_id>', methods=['POST'])
@login_required
def request_course(course_id):
    """Request enrollment in a course"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please log in first'}), 401
    
    user_id = session['user_id']
    
    try:
        logger.info(f"=== COURSE REQUEST DEBUG START ===")
        logger.info(f"User {user_id} requesting course {course_id}")
        
        # Check if course exists and is for user's CPA level
        course_response = supabase.table('courses')\
            .select('*')\
            .eq('id', course_id)\
            .single()\
            .execute()
        
        if not course_response.data:
            logger.error(f"Course {course_id} not found")
            return jsonify({'success': False, 'message': 'Course not found'}), 404
        
        course = course_response.data
        user_cpa_level = session.get('cpa_level', 0)
        
        logger.info(f"Session CPA level: '{user_cpa_level}' (type: {type(user_cpa_level)})")
        logger.info(f"Course details - ID: {course['id']}, Title: {course['title']}, CPA: '{course.get('cpa_level')}' (type: {type(course.get('cpa_level'))})")
        
        # Extract integers for comparison - ensure both are integers
        user_cpa_int = extract_int(user_cpa_level)
        course_cpa_int = course.get('cpa_level')
        
        # Convert both to integers for safe comparison
        try:
            user_cpa_int = int(user_cpa_int) if user_cpa_int is not None else None
            course_cpa_int = int(course_cpa_int) if course_cpa_int is not None else None
        except (ValueError, TypeError) as e:
            logger.error(f"Error converting CPA levels to int: {e}")
            return jsonify({'success': False, 'message': 'Invalid CPA level format'}), 400
        
        logger.info(f"CPA Level Check - User: {user_cpa_int} (type: {type(user_cpa_int)}), Course: {course_cpa_int} (type: {type(course_cpa_int)})")
        
        # Debug the actual comparison
        comparison_result = user_cpa_int == course_cpa_int
        logger.info(f"Comparison: {user_cpa_int} == {course_cpa_int} -> {comparison_result}")
        logger.info(f"ID check: {id(user_cpa_int)} vs {id(course_cpa_int)}")
        logger.info(f"Value check: {repr(user_cpa_int)} vs {repr(course_cpa_int)}")
        
        # Use explicit integer comparison
        if not comparison_result:
            logger.error(f"CPA level mismatch! User: {repr(user_cpa_int)}, Course: {repr(course_cpa_int)}")
            logger.error(f"Types - User: {type(user_cpa_int)}, Course: {type(course_cpa_int)}")
            
            # Additional debug: check what's actually in the database for this user's level
            available_courses = get_available_courses(user_cpa_level)
            available_ids = [c['id'] for c in available_courses]
            logger.info(f"Available courses for user CPA level: {available_ids}")
            logger.info(f"Requested course {course_id} in available list: {course_id in available_ids}")
            
            return jsonify({'success': False, 'message': 'This course is not available for your CPA level'}), 403
        
        logger.info("CPA level check passed")
        
        # Check if user is already enrolled
        enrollment_check = supabase.table('enrollments')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('course_id', course_id)\
            .eq('active', True)\
            .execute()
        
        if enrollment_check.data:
            logger.error(f"User already enrolled in course {course_id}")
            return jsonify({'success': False, 'message': 'You are already enrolled in this course'}), 400
        
        logger.info("User not already enrolled")
        
        # Check if there's already a pending request
        if has_pending_request(user_id, course_id):
            logger.error(f"User already has pending request for course {course_id}")
            return jsonify({'success': False, 'message': 'You already have a pending request for this course'}), 400
        
        logger.info("No pending requests found")
        
        # Create request
        request_data = {
            'user_id': user_id,
            'course_id': course_id,
            'status': 'pending'
        }
        
        logger.info(f"Creating request: {request_data}")
        
        response = supabase.table('requests').insert(request_data).execute()
        
        if response.data:
            logger.info(f"Request created successfully: {response.data}")
            return jsonify({
                'success': True, 
                'message': 'Course request submitted successfully! Waiting for admin approval.'
            })
        else:
            logger.error(f"Failed to create request: {response}")
            return jsonify({'success': False, 'message': 'Failed to submit request'}), 500
            
    except Exception as e:
        logger.error(f"Error in request_course: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': 'An error occurred while processing your request'}), 500
    finally:
        logger.info("=== COURSE REQUEST DEBUG END ===")


@my_courses_bp.route('/course/<int:course_id>')
@login_required
def course_detail(course_id):
    """Display detailed course view with lectures"""
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please log in to access this course', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    
    try:
        # Verify user is enrolled and active in this course
        enrollment_check = supabase.table('enrollments')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('course_id', course_id)\
            .eq('active', True)\
            .execute()
        
        if not enrollment_check.data:
            flash('You are not enrolled in this course or your enrollment is not active', 'danger')
            return redirect(url_for('my_courses.my_courses'))
        
        # Get course details
        course = get_course_details(course_id)
        if not course:
            flash('Course not found', 'danger')
            return redirect(url_for('my_courses.my_courses'))
        
        # Get course lectures
        lectures = get_course_lectures(course_id)
        
        return render_template(
            'course_detail.html',
            course=course,
            lectures=lectures,
            user_email=session.get('user_email'),
            user_full_name=session.get('user_full_name'),
            cpa_level=session.get('cpa_level', 0)
        )
        
    except Exception as e:
        logger.error(f"Error in course_detail route: {e}")
        flash('An error occurred while loading the course', 'danger')
        return redirect(url_for('my_courses.my_courses'))

@my_courses_bp.route('/lecture/<int:lecture_id>')
@login_required
def view_lecture(lecture_id):
    """Display a specific lecture"""
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please log in to view this lecture', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    
    try:
        # Get lecture details with course information
        response = supabase.table('lectures')\
            .select('*, courses(*)') \
            .eq('id', lecture_id)\
            .single()\
            .execute()
        
        if not response.data:
            flash('Lecture not found', 'danger')
            return redirect(url_for('my_courses.my_courses'))
        
        lecture = response.data
        course = lecture['courses']
        
        # Verify user is enrolled in the course
        enrollment_check = supabase.table('enrollments')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('course_id', course['id'])\
            .eq('active', True)\
            .execute()
        
        if not enrollment_check.data:
            flash('You are not enrolled in this course', 'danger')
            return redirect(url_for('my_courses.my_courses'))
        
        # Get all lectures in this course for navigation
        all_lectures = get_course_lectures(course['id'])
        
        # Find current lecture index for next/previous navigation
        current_index = next((i for i, l in enumerate(all_lectures) if l['id'] == lecture_id), -1)
        
        return render_template(
            'lecture_view.html',
            lecture=lecture,
            course=course,
            all_lectures=all_lectures,
            current_index=current_index,
            user_email=session.get('user_email'),
            user_full_name=session.get('user_full_name'),
            cpa_level=session.get('cpa_level', 0)
        )
        
    except Exception as e:
        logger.error(f"Error in view_lecture route: {e}")
        flash('An error occurred while loading the lecture', 'danger')
        return redirect(url_for('my_courses.my_courses'))

# API endpoint to get course progress (optional feature)
@my_courses_bp.route('/api/course-progress/<int:course_id>')
@login_required
def get_course_progress(course_id):
    """Get user's progress in a course"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    
    try:
        # This would require a user_progress table
        # For now, return basic enrollment info
        enrollment = supabase.table('enrollments')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('course_id', course_id)\
            .single()\
            .execute()
        
        if enrollment.data:
            return jsonify({
                'enrolled': True,
                'active': enrollment.data['active'],
                'enrolled_at': enrollment.data['enrolled_at']
            })
        else:
            return jsonify({'enrolled': False})
            
    except Exception as e:
        logger.error(f"Error getting course progress: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    
    
# Add this to your my_courses.py file

@my_courses_bp.route('/live-classes')
@login_required
def live_classes():
    """Display live classes for enrolled courses"""
    if 'user_id' not in session:
        flash('Please log in to access live classes', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    
    try:
        # Get user's enrolled courses
        enrolled_courses = get_user_enrolled_courses(user_id)
        enrolled_course_ids = [enrollment['courses']['id'] for enrollment in enrolled_courses if enrollment.get('courses')]
        
        # Get current date and time
        from datetime import datetime, date, time, timedelta
        current_datetime = datetime.now()
        current_date = current_datetime.date()
        current_time = current_datetime.time()
        
        if not enrolled_course_ids:
            flash('You are not enrolled in any courses to view live classes', 'info')
            return render_template(
                'live_classes.html', 
                today_classes=[], 
                upcoming_classes=[], 
                past_classes=[],
                current_time=current_datetime  # ADD THIS
            )
        
        # Get live classes for enrolled courses
        response = supabase.table('live_classes')\
            .select('''
                *,
                courses (
                    id,
                    title,
                    instructor,
                    cpa_level
                )
            ''')\
            .in_('course_id', enrolled_course_ids)\
            .eq('is_active', True)\
            .gte('scheduled_date', current_date)\
            .order('scheduled_date')\
            .order('scheduled_time')\
            .execute()
        
        live_classes_data = response.data if response.data else []
        
        # Categorize classes
        today_classes = []
        upcoming_classes = []
        
        for class_data in live_classes_data:
            class_date = datetime.strptime(class_data['scheduled_date'], '%Y-%m-%d').date() if isinstance(class_data['scheduled_date'], str) else class_data['scheduled_date']
            class_time = datetime.strptime(class_data['scheduled_time'], '%H:%M:%S').time() if isinstance(class_data['scheduled_time'], str) else class_data['scheduled_time']
            
            class_datetime = datetime.combine(class_date, class_time)
            
            # Check if class is today
            if class_date == current_date:
                # Check if class is ongoing (within duration) or upcoming today
                class_end_time = (datetime.combine(class_date, class_time) + timedelta(minutes=class_data['duration_minutes'])).time()
                
                if current_time <= class_end_time:
                    today_classes.append({
                        **class_data,
                        'class_datetime': class_datetime,
                        'can_join': current_time >= class_time and current_time <= class_end_time,
                        'status': 'ongoing' if current_time >= class_time else 'upcoming_today'
                    })
            elif class_date > current_date:
                upcoming_classes.append({
                    **class_data,
                    'class_datetime': class_datetime,
                    'can_join': False,
                    'status': 'upcoming'
                })
        
        return render_template(
            'live_classes.html',
            today_classes=today_classes,
            upcoming_classes=upcoming_classes,
            user_email=session.get('user_email'),
            user_full_name=session.get('user_full_name'),
            cpa_level=session.get('cpa_level', 0),
            current_time=current_datetime
        )
        
    except Exception as e:
        logger.error(f"Error in live_classes route: {e}")
        flash('An error occurred while loading live classes', 'danger')
        # ADD current_time to the error case as well
        current_datetime = datetime.now()
        return render_template(
            'live_classes.html', 
            today_classes=[], 
            upcoming_classes=[],
            current_time=current_datetime  # ADD THIS
        )

@my_courses_bp.route('/join-live-class/<int:class_id>')
@login_required
def join_live_class(class_id):
    """Join a live class - redirect to Zoom meeting"""
    if 'user_id' not in session:
        flash('Please log in to join the live class', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    
    try:
        # Get live class details
        response = supabase.table('live_classes')\
            .select('''
                *,
                courses (
                    id,
                    title
                )
            ''')\
            .eq('id', class_id)\
            .eq('is_active', True)\
            .single()\
            .execute()
        
        if not response.data:
            flash('Live class not found or inactive', 'danger')
            return redirect(url_for('my_courses.live_classes'))
        
        live_class = response.data
        
        # Verify user is enrolled in the course
        enrollment_check = supabase.table('enrollments')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('course_id', live_class['course_id'])\
            .eq('active', True)\
            .execute()
        
        if not enrollment_check.data:
            flash('You are not enrolled in this course', 'danger')
            return redirect(url_for('my_courses.live_classes'))
        
        # Check if class is currently active
        from datetime import datetime, time
        current_datetime = datetime.now()
        class_date = datetime.strptime(live_class['scheduled_date'], '%Y-%m-%d').date() if isinstance(live_class['scheduled_date'], str) else live_class['scheduled_date']
        class_time = datetime.strptime(live_class['scheduled_time'], '%H:%M:%S').time() if isinstance(live_class['scheduled_time'], str) else live_class['scheduled_time']
        
        class_datetime = datetime.combine(class_date, class_time)
        class_end_datetime = class_datetime + timedelta(minutes=live_class['duration_minutes'])
        
        if current_datetime < class_datetime:
            flash('This class has not started yet. Please wait until the scheduled time.', 'warning')
            return redirect(url_for('my_courses.live_classes'))
        
        if current_datetime > class_end_datetime:
            flash('This class has already ended.', 'warning')
            return redirect(url_for('my_courses.live_classes'))
        
        # Check if Zoom join URL is available
        if not live_class.get('zoom_join_url'):
            flash('Meeting link not available. Please contact administrator.', 'danger')
            return redirect(url_for('my_courses.live_classes'))
        
        # Redirect to Zoom meeting
        return redirect(live_class['zoom_join_url'])
        
    except Exception as e:
        logger.error(f"Error joining live class: {e}")
        flash('An error occurred while joining the live class', 'danger')
        return redirect(url_for('my_courses.live_classes'))

