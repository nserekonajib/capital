from flask import Blueprint, redirect, request, render_template, jsonify, session
from routes.admin_utils import admin_supabase
from library_utils import delete_file_from_drive, upload_pdf
import os
from werkzeug.utils import secure_filename
from routes.adminauth import admin_login_required
from routes.auth import login_required


student_library_bp = Blueprint('student_library', __name__)

library_bp = Blueprint('library', __name__)

# Configuration
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_size(file):
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    return size

def format_file_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

# -------------------- ADMIN ROUTES --------------------

@library_bp.route("/admin/library")
@admin_login_required
def manage_library():
    """Library management dashboard"""
    try:
        courses_res = admin_supabase.from_("courses").select("id, title").execute()
        courses = courses_res.data or []
        return render_template("admin/library/manage.html", courses=courses)
    except Exception as e:
        print(f"Error loading library: {e}")
        return render_template("admin/library/manage.html", courses=[])

@library_bp.route("/resources")
@admin_login_required
def get_library_resources():
    """Get all library resources"""
    try:
        # Fix the query to properly join with courses table
        response = admin_supabase.from_("library_resources")\
            .select("*, courses(title)")\
            .order('created_at', desc=True)\
            .execute()
        
        resources = response.data or []
        #print("Raw resources data:", resources)  # Debug print
        
        formatted_resources = []
        for resource in resources:
            #print("Processing resource:", resource)  # Debug print
            
            # Get course title - handle different possible data structures
            course_title = 'General Library'
            if resource.get('courses'):
                if isinstance(resource['courses'], dict) and 'title' in resource['courses']:
                    course_title = resource['courses']['title']
                elif isinstance(resource['courses'], list) and len(resource['courses']) > 0:
                    course_title = resource['courses'][0].get('title', 'General Library')
            
            # If course_id exists but no course title found, it might be a data issue
            elif resource.get('course_id'):
                # Try to fetch course name directly
                try:
                    course_res = admin_supabase.from_("courses")\
                        .select("title")\
                        .eq("id", resource['course_id'])\
                        .execute()
                    if course_res.data:
                        course_title = course_res.data[0].get('title', f"Course {resource['course_id']}")
                    else:
                        course_title = f"Course {resource['course_id']} (Not Found)"
                except Exception as e:
                    print(f"Error fetching course {resource['course_id']}: {e}")
                    course_title = f"Course {resource['course_id']}"
            
            formatted_resources.append({
                'id': resource['id'],
                'title': resource['title'],
                'description': resource.get('description', ''),
                'pdf_url': resource['pdf_url'],
                'file_id': resource.get('file_id'),
                'course_id': resource.get('course_id'),
                'course_title': course_title,
                'uploaded_by': resource.get('uploaded_by', 'System'),
                'file_size': resource.get('file_size', 0),
                'is_active': resource.get('is_active', True),
                'created_at': resource.get('created_at'),
                'formatted_size': format_file_size(resource.get('file_size', 0))
            })
        
        #print("Formatted resources:", formatted_resources)  # Debug print
        return jsonify(formatted_resources)
        
    except Exception as e:
        print(f"Error fetching resources: {e}")
        return jsonify({"error": str(e)}), 500

@library_bp.route("/upload", methods=["POST"])
@admin_login_required
def upload_library_resource():
    """Handle PDF upload to Google Drive and database"""
    print("=== PDF UPLOAD REQUEST RECEIVED ===")
    
    try:
        # Validate file presence
        if 'pdf_file' not in request.files:
            print("No file in request")
            return jsonify({"success": False, "error": "No file uploaded"}), 400
        
        file = request.files['pdf_file']
        if file.filename == '':
            print("Empty filename")
            return jsonify({"success": False, "error": "No file selected"}), 400
        
        # Validate file type
        if not allowed_file(file.filename):
            print(f"Invalid file type: {file.filename}")
            return jsonify({"success": False, "error": "Only PDF files are allowed"}), 400
        
        # Validate file size
        file_size = get_file_size(file)
        print(f"File size: {file_size} bytes")
        
        if file_size > MAX_FILE_SIZE:
            print(f"File too large: {file_size} > {MAX_FILE_SIZE}")
            return jsonify({"success": False, "error": f"File size exceeds {MAX_FILE_SIZE // (1024*1024)}MB limit"}), 400
        
        # Get and validate form data
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        course_id = request.form.get('course_id')
        
        if not title:
            print("Missing title")
            return jsonify({"success": False, "error": "Title is required"}), 400
        
        print(f"Processing upload: '{title}' for course {course_id}")
        
        # Create a cross-platform temporary directory
        import tempfile
        import uuid
        
        # Create a unique filename to avoid conflicts
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        
        # Use system's temp directory (works on both Windows and Linux)
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, unique_filename)
        
        print(f"Saving to temporary location: {temp_path}")
        file.save(temp_path)
        
        # Verify file was saved
        if not os.path.exists(temp_path):
            print("File was not saved successfully")
            return jsonify({"success": False, "error": "Failed to save file temporarily"}), 500
            
        print(f"File saved successfully: {os.path.getsize(temp_path)} bytes")
        
        try:
            # UPLOAD TO GOOGLE DRIVE - CORE FUNCTIONALITY
            print("Calling Google Drive upload function...")
            drive_result = upload_pdf(temp_path)
            print(f"Google Drive upload successful: {drive_result['file_id']}")
            
            # Prepare database record
            resource_data = {
                'title': title,
                'description': description,
                'pdf_url': drive_result['direct_link'],
                'file_id': drive_result['file_id'],
                'file_size': drive_result['file_size'],
                'uploaded_by': session.get('user_id'),
                'is_active': True
            }
            
            if course_id and course_id != '' and course_id != 'null':
                resource_data['course_id'] = int(course_id)
            
            # Save to database
            print("Saving to database...")
            response = admin_supabase.from_("library_resources").insert(resource_data).execute()
            
            if response.data:
                print(f"Resource saved successfully with ID: {response.data[0]['id']}")
                return jsonify({
                    "success": True, 
                    "message": "PDF uploaded successfully!",
                    "resource": response.data[0]
                })
            else:
                print("Database insertion failed")
                return jsonify({"success": False, "error": "Failed to save to database"}), 500
                
        except Exception as upload_error:
            print(f"Error during upload process: {str(upload_error)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return jsonify({"success": False, "error": f"Upload failed: {str(upload_error)}"}), 500
                
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                print("Temporary file cleaned up")
            else:
                print("Temporary file not found for cleanup")
        
    except Exception as e:
        print(f"Unexpected error in upload: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": f"Unexpected error: {str(e)}"}), 500

@library_bp.route("/<int:resource_id>", methods=["DELETE"])
@admin_login_required
def delete_library_resource(resource_id):
    """Delete a library resource from DB and Google Drive."""
    try:
        # 1. Fetch resource
        resource = admin_supabase.from_("library_resources")\
            .select("id, file_id")\
            .eq("id", resource_id)\
            .single()\
            .execute()

        if not resource.data:
            return jsonify({"error": "Resource not found"}), 404

        file_id = resource.data.get("file_id")

        # 2. Delete from Google Drive if file_id exists
        if file_id:
            deleted = delete_file_from_drive(file_id)
            if not deleted:
                return jsonify({"error": "Failed to delete from Google Drive"}), 500

        # 3. Delete record from Supabase DB
        admin_supabase.from_("library_resources")\
            .delete()\
            .eq("id", resource_id)\
            .execute()

        return jsonify({"success": True, "message": "Resource deleted successfully"}), 200

    except Exception as e:
        print(f"Error deleting resource: {e}")
        return jsonify({"error": str(e)}), 500


@library_bp.route("/<int:resource_id>/toggle", methods=["POST"])
@admin_login_required
def toggle_library_resource(resource_id):
    """Toggle resource active status"""
    try:
        data = request.get_json()
        is_active = data.get('is_active', True)
        
        response = admin_supabase.from_("library_resources")\
            .update({"is_active": is_active})\
            .eq("id", resource_id)\
            .execute()
        
        if response.data:
            status = "activated" if is_active else "deactivated"
            return jsonify({"success": True, "message": f"Resource {status} successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to update resource"}), 500
            
    except Exception as e:
        print(f"Toggle error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------- STUDENT ROUTES --------------------

@student_library_bp.route("/library")
@login_required
def student_library():
    """Student library page"""
    if 'user_id' not in session:
        return redirect('/login')
    return render_template("library/student_library.html")

@student_library_bp.route("/student/courses")
@login_required
def get_student_courses():
    """Get courses that the student is enrolled in"""
    if 'user_id' not in session:
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        user_id = session.get('user_id')
        
        # Get student's enrollments - CORRECTED: using user_id instead of student_id
        enrollments_res = admin_supabase.from_("enrollments")\
            .select("course_id, courses(title, cpa_level)")\
            .eq("user_id", user_id)\
            .eq("active", True)\
            .execute()
        
        courses = []
        if enrollments_res.data:
            for enrollment in enrollments_res.data:
                course_data = enrollment.get('courses', {})
                courses.append({
                    'id': enrollment['course_id'],
                    'title': course_data.get('title', f"Course {enrollment['course_id']}"),
                    'cpa_level': course_data.get('cpa_level', '')
                })
        
        return jsonify({"courses": courses})
        
    except Exception as e:
        print(f"Error fetching student courses: {e}")
        return jsonify({"error": str(e)}), 500

@student_library_bp.route("/resources")
@login_required
def get_student_library_resources():
    """Get library resources for students - ONLY their enrolled courses"""
    if 'user_id' not in session:
        return jsonify({"error": "Authentication required"}), 401

    try:
        user_id = session.get('user_id')

        # Get student's enrolled course IDs
        enrollments_res = admin_supabase.from_("enrollments")\
            .select("course_id")\
            .eq("user_id", user_id)\
            .eq("active", True)\
            .execute()

        enrolled_course_ids = [int(enrollment['course_id']) for enrollment in (enrollments_res.data or [])]
        print(f"[DEBUG] Student {user_id} enrolled course IDs: {enrolled_course_ids}")

        # Get all active resources
        query = admin_supabase.from_("library_resources")\
            .select("*, courses(title)")\
            .eq("is_active", True)\
            .order("created_at", desc=True)

        response = query.execute()
        resources = response.data or []
        print(f"[DEBUG] Total active resources fetched: {len(resources)}")

        formatted_resources = []

        for resource in resources:
            course_data = resource.get('courses', {})
            course_title = course_data.get('title', f"Course {resource.get('course_id')}") if course_data else f"Course {resource.get('course_id')}"
            course_id = int(resource['course_id']) if resource.get('course_id') else None

            # DEBUG: print each resource
            print(f"[DEBUG] Resource ID {resource['id']} - Title: {resource['title']} - course_id: {course_id}")

            # Only include resources where course_id is in enrolled courses
            if course_id and course_id in enrolled_course_ids:
                formatted_resources.append({
                    'id': resource['id'],
                    'title': resource['title'],
                    'description': resource.get('description', ''),
                    'pdf_url': resource['pdf_url'],
                    'course_id': course_id,
                    'course_title': course_title,
                    'file_size': resource.get('file_size', 0),
                    'created_at': resource.get('created_at'),
                    'formatted_size': format_file_size(resource.get('file_size', 0))
                })
                print(f"[DEBUG] Resource {resource['id']} added for student access")
            else:
                print(f"[DEBUG] Resource {resource['id']} skipped (course_id={course_id})")

        print(f"[DEBUG] Total resources student has access to: {len(formatted_resources)}")
        return jsonify(formatted_resources)

    except Exception as e:
        print(f"[ERROR] Student resources error: {e}")
        return jsonify({"error": str(e)}), 500

    
    
@library_bp.route("/api/library/debug-resources")
def debug_student_resources():
    """Debug endpoint to see exactly what's being returned"""
    if 'user_id' not in session:
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        user_id = session.get('user_id')
        
        # Get student's enrolled course IDs
        enrollments_res = admin_supabase.from_("enrollments")\
            .select("course_id")\
            .eq("user_id", user_id)\
            .eq("active", True)\
            .execute()
        
        enrolled_course_ids = [enrollment['course_id'] for enrollment in (enrollments_res.data or [])]
        
        # Get all active resources
        query = admin_supabase.from_("library_resources")\
            .select("*, courses(title)")\
            .eq("is_active", True)\
            .order("created_at", desc=True)
        
        response = query.execute()
        resources = response.data or []
        
        debug_info = {
            "student_id": user_id,
            "enrolled_course_ids": enrolled_course_ids,
            "total_resources": len(resources),
            "resources": []
        }
        
        for resource in resources:
            course_data = resource.get('courses', {})
            course_title = course_data.get('title', 'General Library') if course_data else 'General Library'
            course_id = resource.get('course_id')
            
            has_access = not course_id or course_id in enrolled_course_ids
            
            debug_info["resources"].append({
                'id': resource['id'],
                'title': resource['title'],
                'course_id': course_id,
                'course_id_type': type(course_id).__name__ if course_id else 'None',
                'course_title': course_title,
                'has_access': has_access,
                'enrolled_course_ids_type': [type(cid).__name__ for cid in enrolled_course_ids],
                'comparison': f"{course_id} in {enrolled_course_ids} = {has_access}"
            })
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500