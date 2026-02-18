from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from functools import wraps
from routes.admin_utils import get_admin_client
from routes.admin_config import AdminConfig
import requests
from datetime import datetime, timedelta
import json
from routes.adminauth import admin_login_required
from routes.zoom_utils import get_zoom_access_token, create_zoom_meeting
from routes.email_manager import send_class_invite_html
from routes.config import Config

schedule_bp = Blueprint('schedule', __name__)
sender_email = Config.sender_email
sender_password = Config.sender_password
def update_elapsed_classes_status():
    
    """Update live class status - only deactivate when class duration is completely finished"""
    try:
        client = get_admin_client()
        
        # Get all active live classes
        res = client.from_("live_classes")\
            .select("*")\
            .eq("is_active", True)\
            .execute()
        
        if not res.data:
            return
        
        current_time = datetime.now()
        updated_count = 0
        
        for class_data in res.data:
            # Parse scheduled date and time
            scheduled_date = class_data['scheduled_date']
            scheduled_time = class_data['scheduled_time']
            duration_minutes = class_data.get('duration_minutes', 60)
            
            # Create datetime objects
            if isinstance(scheduled_date, str):
                scheduled_date = datetime.strptime(scheduled_date, '%Y-%m-%d').date()
            if isinstance(scheduled_time, str):
                scheduled_time = datetime.strptime(scheduled_time, '%H:%M:%S').time()
            
            # Combine date and time to create class start datetime
            class_start_datetime = datetime.combine(scheduled_date, scheduled_time)
            
            # Calculate class end datetime by adding duration
            class_end_datetime = class_start_datetime + timedelta(minutes=duration_minutes)
            
            # Only deactivate if current time is AFTER the class end time
            if current_time > class_end_datetime:
                # Update class to inactive
                update_res = client.from_("live_classes")\
                    .update({
                        "is_active": False,
                        "updated_at": current_time.isoformat()
                    })\
                    .eq("id", class_data['id'])\
                    .execute()
                
                if update_res.data:
                    updated_count += 1
                    print(f"Auto-deactivated class: {class_data['class_title']} (ID: {class_data['id']})")
        
        if updated_count > 0:
            print(f"Auto-deactivated {updated_count} completed live classes")
            
    except Exception as e:
        print(f"Error updating elapsed classes status: {e}")

# -------------------- Routes --------------------
@schedule_bp.route('/admin/live-classes')
@admin_login_required
def live_classes():
    """Display all live classes with automatic status updates"""
    try:
      
        client = get_admin_client()
        
        # Update status of elapsed classes first
        update_elapsed_classes_status()
        
        # Get live classes with course information
        res = client.from_("live_classes")\
            .select("*, courses!inner(title)")\
            .order("scheduled_date", desc=True)\
            .order("scheduled_time", desc=True)\
            .execute()
        
        # Format the data properly
        live_classes = []
        if res.data:
            for class_data in res.data:
                formatted_class = class_data.copy()
                formatted_class['course_title'] = class_data.get('courses', {}).get('title', 'N/A')
                
                # Calculate class end time for display
                scheduled_date = class_data['scheduled_date']
                scheduled_time = class_data['scheduled_time']
                duration_minutes = class_data.get('duration_minutes', 60)
                
                if isinstance(scheduled_date, str):
                    scheduled_date = datetime.strptime(scheduled_date, '%Y-%m-%d').date()
                if isinstance(scheduled_time, str):
                    scheduled_time = datetime.strptime(scheduled_time, '%H:%M:%S').time()
                
                class_start_datetime = datetime.combine(scheduled_date, scheduled_time)
                class_end_datetime = class_start_datetime + timedelta(minutes=duration_minutes)
                formatted_class['end_datetime'] = class_end_datetime
                
                live_classes.append(formatted_class)
        
        return render_template('admin/courses/live_classes.html', live_classes=live_classes)
    
    except Exception as e:
        print(f"Error fetching live classes: {e}")
        flash('Error loading live classes', 'danger')
        return render_template('admin/courses/live_classes.html', live_classes=[])

@schedule_bp.route('/admin/live-classes/create', methods=['GET', 'POST'])
@admin_login_required
def create_live_class():
    """Create a new live class"""
    try:
        client = get_admin_client()
        
        if request.method == 'POST':
            course_id = request.form.get('course_id')
            class_title = request.form.get('class_title')
            instructor = request.form.get('instructor')
            scheduled_date = request.form.get('scheduled_date')
            scheduled_time = request.form.get('scheduled_time')
            duration_minutes = request.form.get('duration_minutes', 60)
            waiting_room_enabled = request.form.get('waiting_room_enabled') == 'on'
            
            # Validation
            if not all([course_id, class_title, instructor, scheduled_date, scheduled_time]):
                flash('All fields are required', 'danger')
                return redirect(url_for('schedule.create_live_class'))
            
            # Create Zoom meeting
            access_token = get_zoom_access_token()
            if not access_token:
                flash('Error connecting to Zoom API', 'danger')
                return redirect(url_for('schedule.create_live_class'))
            
            zoom_meeting = create_zoom_meeting(
                access_token, 
                class_title, 
                int(duration_minutes),
                waiting_room_enabled
            )
            
            if not zoom_meeting:
                flash('Error creating Zoom meeting', 'danger')
                return redirect(url_for('schedule.create_live_class'))
            
            # Save to database
            res = client.from_("live_classes").insert({
                "course_id": course_id,
                "class_title": class_title,
                "instructor": instructor,
                "scheduled_date": scheduled_date,
                "scheduled_time": scheduled_time,
                "duration_minutes": duration_minutes,
                "zoom_meeting_id": zoom_meeting.get("id"),
                "zoom_join_url": zoom_meeting.get("join_url"),
                "zoom_start_url": zoom_meeting.get("start_url"),
                "waiting_room_enabled": waiting_room_enabled,
                "is_active": True
            }).execute()
            
            if res.data:
                flash('Live class scheduled successfully!', 'success')
                return redirect(url_for('schedule.live_classes'))
            else:
                flash('Error saving live class to database', 'danger')
        
        # GET request - load courses for dropdown
        courses_res = client.from_("courses").select("id, title").execute()
        courses = courses_res.data if courses_res.data else []
        
        return render_template('schedule/create_live_class.html', courses=courses)
    
    except Exception as e:
        print(f"Error creating live class: {e}")
        flash('Error creating live class', 'danger')
        return redirect(url_for('schedule.live_classes'))

@schedule_bp.route('/admin/live-classes/<int:class_id>/toggle', methods=['POST'])
@admin_login_required
def toggle_live_class(class_id):
    """Toggle live class active status - Manual override"""
    try:
        client = get_admin_client()
        
        # Get current status
        current_res = client.from_("live_classes").select("is_active").eq("id", class_id).execute()
        if not current_res.data:
            return jsonify({"success": False, "error": "Class not found"}), 404
        
        current_status = current_res.data[0]['is_active']
        new_status = not current_status
        
        # Update status
        res = client.from_("live_classes").update({
            "is_active": new_status,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", class_id).execute()
        
        if res.data:
            return jsonify({
                "success": True, 
                "message": f"Class {'activated' if new_status else 'deactivated'}",
                "new_status": new_status
            })
        else:
            return jsonify({"success": False, "error": "Failed to update class"}), 500
    
    except Exception as e:
        print(f"Error toggling live class: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@schedule_bp.route('/admin/live-classes/<int:class_id>', methods=['DELETE'])
@admin_login_required
def delete_live_class(class_id):
    """Delete a live class"""
    try:
        client = get_admin_client()
        
        # Delete from database
        res = client.from_("live_classes").delete().eq("id", class_id).execute()
        
        if res.data:
            return jsonify({"success": True, "message": "Live class deleted successfully"})
        else:
            return jsonify({"success": False, "error": "Class not found"}), 404
    
    except Exception as e:
        print(f"Error deleting live class: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@schedule_bp.route('/admin/live-classes/<int:class_id>/edit', methods=['POST'])
@admin_login_required
def edit_live_class(class_id):
    """Edit a live class - POST only for modal"""
    try:
        client = get_admin_client()
        
        class_title = request.form.get('class_title')
        instructor = request.form.get('instructor')
        scheduled_date = request.form.get('scheduled_date')
        scheduled_time = request.form.get('scheduled_time')
        duration_minutes = request.form.get('duration_minutes')
        waiting_room_enabled = request.form.get('waiting_room_enabled') == 'true'
        
        if not all([class_title, instructor, scheduled_date, scheduled_time, duration_minutes]):
            return jsonify({"success": False, "error": "All fields are required"}), 400
        
        # Update in database
        res = client.from_("live_classes").update({
            "class_title": class_title,
            "instructor": instructor,
            "scheduled_date": scheduled_date,
            "scheduled_time": scheduled_time,
            "duration_minutes": duration_minutes,
            "waiting_room_enabled": waiting_room_enabled,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", class_id).execute()
        
        if res.data:
            return jsonify({"success": True, "message": "Live class updated successfully!"})
        else:
            return jsonify({"success": False, "error": "Error updating live class"}), 500
    
    except Exception as e:
        print(f"Error editing live class: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------- API Endpoints --------------------
@schedule_bp.route('/api/live-classes/upcoming')
@admin_login_required
def get_upcoming_classes():
    """API endpoint for upcoming live classes"""
    try:
        update_elapsed_classes_status()
        client = get_admin_client()
        
        # Get upcoming classes (next 7 days)
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        
        res = client.from_("live_classes")\
            .select("""
                *,
                courses(title as course_title)
            """)\
            .gte("scheduled_date", today.isoformat())\
            .lte("scheduled_date", next_week.isoformat())\
            .eq("is_active", True)\
            .order("scheduled_date")\
            .order("scheduled_time")\
            .execute()
        
        return jsonify(res.data if res.data else [])
    
    except Exception as e:
        print(f"Error fetching upcoming classes: {e}")
        return jsonify([])

@schedule_bp.route('/admin/live-classes/<int:class_id>/send-reminder', methods=['POST'])
@admin_login_required
def send_class_reminder(class_id):
    """Send reminder emails to enrolled and active students for a live class"""
    try:
        client = get_admin_client()
        
        # Get admin user ID from session
        admin_id = session.get('admin_id')
        if not admin_id:
            return jsonify({"success": False, "error": "Admin not authenticated"}), 401
        
        # Get live class details
        class_res = client.from_("live_classes")\
            .select("*, courses!inner(title, id)")\
            .eq("id", class_id)\
            .eq("is_active", True)\
            .execute()
        
        if not class_res.data:
            return jsonify({"success": False, "error": "Live class not found"}), 404
        
        live_class = class_res.data[0]
        course_id = live_class['courses']['id']
        course_title = live_class['courses']['title']
        
        print(f"Processing live class: {live_class['class_title']} for course: {course_title}")
        
        # Get enrolled students
        enrollments_res = client.from_("enrollments")\
            .select("user_id")\
            .eq("course_id", course_id)\
            .eq("active", True)\
            .execute()
        
        if not enrollments_res.data:
            return jsonify({"success": False, "error": "No active enrollments found for this course"}), 404
        
        user_ids = [enrollment['user_id'] for enrollment in enrollments_res.data]
        print(f"Found {len(user_ids)} enrolled students")
        
        # Get student details
        students_res = client.from_("students")\
            .select("id, email, full_name, status")\
            .in_("id", user_ids)\
            .eq("status", "active")\
            .execute()
        
        if not students_res.data:
            return jsonify({"success": False, "error": "No active students found"}), 404
        
        # Filter students with valid email addresses
        valid_students = []
        for student in students_res.data:
            if student.get('email') and '@' in student['email']:
                valid_students.append({
                    'email': student['email'].strip(),
                    'name': student.get('full_name', 'Student').strip() or 'Student',
                    'user_id': student['id']
                })
        
        if not valid_students:
            return jsonify({"success": False, "error": "No students with valid email addresses found"}), 404
        
        print(f"Preparing to send reminders to {len(valid_students)} students")
     
        
        # Send emails
        successful_sends = 0
        failed_sends = []
        
        for student in valid_students:
            try:
                subject = f"Capital College - Live Class Reminder: {live_class['class_title']}"
                
                print(f"Sending reminder to: {student['email']}")
                
                send_class_invite_html(
                    sender_email=sender_email,
                    sender_password=sender_password,
                    recipient_email=student['email'],
                    student_name=student['name'],
                    class_link=live_class['zoom_join_url'],
                    subject=subject
                )
                successful_sends += 1
                
                # Small delay to avoid rate limiting
                import time
                time.sleep(0.5)
                
            except Exception as e:
                error_msg = f"{student['email']}: {str(e)}"
                failed_sends.append(error_msg)
                print(f"Failed to send to {student['email']}: {e}")
        
        # Log the activity
        try:
            client.from_("reminder_logs").insert({
                "live_class_id": class_id,
                "sent_by": admin_id,
                "students_count": len(valid_students),
                "successful_sends": successful_sends,
                "failed_sends": len(failed_sends),
                "sent_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as log_error:
            print(f"Failed to log activity: {log_error}")
        
        # Prepare response
        response_data = {
            "success": successful_sends > 0,
            "message": f"Reminders sent: {successful_sends} successful, {len(failed_sends)} failed",
            "stats": {
                "total_students": len(valid_students),
                "successful": successful_sends,
                "failed": len(failed_sends)
            }
        }
        
        if failed_sends:
            response_data["failed_details"] = failed_sends[:5]  # Include first 5 failures
        
        return jsonify(response_data)
            
    except Exception as e:
        print(f"Error in send_class_reminder: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@schedule_bp.route('/admin/live-classes/enhanced')
@admin_login_required
def enhanced_live_classes():
    """Enhanced live classes management with search and sorting"""
    try:
        client = get_admin_client()
        
        # Update status of elapsed classes first
        update_elapsed_classes_status()
        
        # Get live classes with course information
        res = client.from_("live_classes")\
            .select("*, courses!inner(title)")\
            .order("scheduled_date", desc=True)\
            .order("scheduled_time", desc=True)\
            .execute()
        
        # Format the data properly
        live_classes = []
        if res.data:
            for class_data in res.data:
                formatted_class = class_data.copy()
                formatted_class['course_title'] = class_data.get('courses', {}).get('title', 'N/A')
                live_classes.append(formatted_class)
        
        return render_template('admin/courses/enhanced_live_classes.html', live_classes=live_classes)
    
    except Exception as e:
        print(f"Error fetching live classes: {e}")
        flash('Error loading live classes', 'danger')
        return render_template('admin/courses/enhanced_live_classes.html', live_classes=[])

@schedule_bp.route('/api/live-classes/search')
@admin_login_required
def search_live_classes():
    """API endpoint for searching and filtering live classes"""
    try:
        client = get_admin_client()
        
        search_query = request.args.get('q', '')
        status_filter = request.args.get('status', '')
        sort_by = request.args.get('sort', 'scheduled_date')
        sort_order = request.args.get('order', 'desc')
        
        # Build query
        query = client.from_("live_classes")\
            .select("*, courses!inner(title)")\
            .order(sort_by, desc=(sort_order == 'desc'))
        
        # Apply search filter
        if search_query:
            query = query.or_(f"class_title.ilike.%{search_query}%,instructor.ilike.%{search_query}%,courses.title.ilike.%{search_query}%")
        
        # Apply status filter
        if status_filter:
            if status_filter == 'active':
                query = query.eq("is_active", True)
            elif status_filter == 'inactive':
                query = query.eq("is_active", False)
            elif status_filter == 'upcoming':
                today = datetime.now().date()
                query = query.gte("scheduled_date", today.isoformat())
            elif status_filter == 'past':
                today = datetime.now().date()
                query = query.lt("scheduled_date", today.isoformat())
        
        res = query.execute()
        
        # Format response
        formatted_classes = []
        for class_data in res.data:
            formatted_class = class_data.copy()
            formatted_class['course_title'] = class_data.get('courses', {}).get('title', 'N/A')
            formatted_classes.append(formatted_class)
        
        return jsonify(formatted_classes)
        
    except Exception as e:
        print(f"Error searching live classes: {e}")
        return jsonify([])