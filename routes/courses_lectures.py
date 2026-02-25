from dotenv import load_dotenv
from flask import Blueprint, request, render_template, jsonify
from routes.admin_utils import admin_supabase, get_admin_client
from routes.cloudinary_utils import upload_course_thumbnail, delete_cloudinary_image
import datetime
from routes.adminauth import admin_login_required
from flask import *


load_dotenv()
import uuid
import datetime

def create_invoice_for_student(user_id, course, student):
    """
    Auto-create an invoice when a student is enrolled or approved.
    """
    try:
        # Debug: Check what data we're receiving
        print(f"DEBUG INVOICE - Creating invoice for user {user_id}")
        print(f"DEBUG INVOICE - Course ID: {course.get('id')}")
        print(f"DEBUG INVOICE - Course title: {course.get('title')}")
        print(f"DEBUG INVOICE - Course fees: {course.get('fees')}")
        print(f"DEBUG INVOICE - Course fees type: {type(course.get('fees'))}")
        print(f"DEBUG INVOICE - Student: {student.get('full_name')}")
        
        # Ensure fees is a float and not None/empty
        course_fees = course.get("fees", 0)
        if course_fees is None or course_fees == "":
            course_fees = 0
            print("WARNING: Course fees is None or empty, defaulting to 0")
        
        fees_float = float(course_fees)
        print(f"DEBUG INVOICE - Final fees amount: {fees_float}")
        
        # Generate unique invoice number
        invoice_number = f"INV-{datetime.datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        invoice_data = {
            "user_id": user_id,
            "course_id": course.get("id"),  # ADDED: Link invoice to course
            "invoice_number": invoice_number,
            "amount": fees_float,
            "balance": fees_float,
            "status": "unpaid",
            "due_date": (datetime.datetime.utcnow() + datetime.timedelta(days=14)).date().isoformat(),
            "description": f"Tuition for {course.get('title', 'Course')} - CPA Level {course.get('cpa_level', '')}",
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat()
        }

        print(f"DEBUG INVOICE - Invoice data being inserted: {invoice_data}")

        # Insert into Supabase invoices table
        res = admin_supabase.from_("invoices").insert(invoice_data).execute()
        print(f"DEBUG INVOICE - Supabase insert result: {res}")
        
        if not res.data:
            print("ERROR: Failed to insert invoice - no data returned")
            raise Exception("Failed to insert invoice")

        print(f"SUCCESS: Invoice {invoice_number} created for {student.get('full_name')} with amount {fees_float}")
        return res.data[0]

    except Exception as e:
        print(f"Error creating invoice: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return None

courses_bp = Blueprint("courses", __name__)

# -------------------- 1. MANAGE PAGE --------------------
@courses_bp.route("/admin/courses/manage", methods=["GET"])
@admin_login_required
def manage_courses():
    """
    Render the manage page with courses passed as JSON for JS.
    """
    try:
        # Fetch all courses in one query
        courses_res = admin_supabase.from_("courses").select("*").execute()
        courses = courses_res.data or []
        
        if not courses:
            return render_template("admin/courses/manage.html", courses=[])

        # Get all course IDs for batch counting
        course_ids = [course["id"] for course in courses]

        # Batch count students for all courses
        enrollments_res = admin_supabase.from_("enrollments")\
            .select("course_id")\
            .in_("course_id", course_ids)\
            .execute()
        
        enrollments_data = enrollments_res.data or []
        student_counts = {}
        for enrollment in enrollments_data:
            course_id = enrollment["course_id"]
            student_counts[course_id] = student_counts.get(course_id, 0) + 1

        # Batch count lectures for all courses
        lectures_res = admin_supabase.from_("lectures")\
            .select("course_id")\
            .in_("course_id", course_ids)\
            .execute()
        
        lectures_data = lectures_res.data or []
        lecture_counts = {}
        for lecture in lectures_data:
            course_id = lecture["course_id"]
            lecture_counts[course_id] = lecture_counts.get(course_id, 0) + 1

        # Add counts to courses
        for course in courses:
            course_id = course["id"]
            course["student_count"] = student_counts.get(course_id, 0)
            course["lecture_count"] = lecture_counts.get(course_id, 0)

        return render_template("admin/courses/manage.html", courses=courses)
        
    except Exception as e:
        print(f"Error in manage_courses: {e}")
        return render_template("admin/courses/manage.html", courses=[])

# -------------------- 2. FETCH COURSES (JSON for AJAX) --------------------
@courses_bp.route("/admin/courses", methods=["GET"])
@admin_login_required
def fetch_courses():
    try:
        # Fetch all courses
        courses_res = admin_supabase.from_("courses").select("*").execute()
        courses = courses_res.data or []
        
        if not courses:
            return jsonify([])

        # Get all course IDs for batch counting
        course_ids = [course["id"] for course in courses]

        # Batch count students
        enrollments_res = admin_supabase.from_("enrollments")\
            .select("course_id")\
            .in_("course_id", course_ids)\
            .execute()
        
        student_counts = {}
        for enrollment in (enrollments_res.data or []):
            course_id = enrollment["course_id"]
            student_counts[course_id] = student_counts.get(course_id, 0) + 1

        # Batch count lectures
        lectures_res = admin_supabase.from_("lectures")\
            .select("course_id")\
            .in_("course_id", course_ids)\
            .execute()
        
        lecture_counts = {}
        for lecture in (lectures_res.data or []):
            course_id = lecture["course_id"]
            lecture_counts[course_id] = lecture_counts.get(course_id, 0) + 1

        # Build response
        safe_courses = []
        for course in courses:
            course_id = course["id"]
            safe_courses.append({
                "id": course_id,
                "title": course.get("title", "Untitled"),
                "instructor": course.get("instructor", "Unknown"),
                "cpa_level": course.get("cpa_level", 0),
                "description": course.get("description", ""),
                "fees": float(course.get("fees", 0)),
                "thumbnail": course.get("thumbnail"),
                "created_at": course.get("created_at"),
                "student_count": student_counts.get(course_id, 0),
                "lecture_count": lecture_counts.get(course_id, 0)
            })

        return jsonify(safe_courses)

    except Exception as e:
        print(f"Error in fetch_courses: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------- 3. CREATE COURSE --------------------
@courses_bp.route("/admin/courses/create", methods=["GET", "POST"])
@admin_login_required
def create_course():
    if request.method == "GET":
        return manage_courses()

    try:
        title = request.form.get("title")
        instructor = request.form.get("instructor")
        cpa_level = request.form.get("cpa_level")
        description = request.form.get("description")
        course_fees = float(request.form.get("fees", 0))
        thumbnail_file = request.files.get("thumbnail")
        thumbnail_url = upload_course_thumbnail(thumbnail_file) if thumbnail_file else None

        admin_supabase.from_("courses").insert({
            "title": title,
            "instructor": instructor,
            "cpa_level": cpa_level,
            "description": description,
            "fees": course_fees,
            "thumbnail": thumbnail_url,
            "created_at": datetime.datetime.utcnow().isoformat()
        }).execute()

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- 4. FETCH STUDENTS FOR COURSE --------------------
@courses_bp.route("/admin/courses/<int:course_id>/students", methods=["GET"])
@admin_login_required
def get_course_students(course_id):
    try:
        # Single optimized query with join-like behavior
        enrollments_res = admin_supabase.from_("enrollments")\
            .select("*, students(full_name, email)")\
            .eq("course_id", course_id)\
            .execute()
        
        enrollments = enrollments_res.data or []
        
        response = []
        for enrollment in enrollments:
            student_data = enrollment.get("students", {})
            response.append({
                "id": enrollment["user_id"],
                "name": student_data.get("full_name", "Unknown Student"),
                "email": student_data.get("email", ""),
                "active": enrollment.get("active", True),
                "enrollment_id": enrollment["id"]
            })
            
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in get_course_students: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------- 5. TOGGLE STUDENT ENROLLMENT STATUS --------------------
# -------------------- 5. TOGGLE STUDENT ENROLLMENT STATUS --------------------
@courses_bp.route("/admin/courses/<int:course_id>/students/toggle", methods=["POST"])
@admin_login_required
def toggle_enrollment_status(course_id):
    try:
        data = request.get_json()
        enrollment_id = data.get("enrollment_id")
        active = data.get("active")

        if enrollment_id is None or active is None:
            return jsonify({"success": False, "error": "Missing enrollment_id or active status"}), 400

        # If setting to inactive, DELETE the enrollment completely
        if active is False:
            # First, get student info for logging
            student_info = admin_supabase.from_("enrollments")\
                .select("user_id, courses!inner(title)")\
                .eq("id", enrollment_id)\
                .execute()
            
            # Delete the enrollment
            res = admin_supabase.from_("enrollments").delete().eq("id", enrollment_id).execute()
            
            if not res.data:
                return jsonify({"success": False, "error": "Enrollment not found"}), 404
            
            # Optional: Log the deletion
            if student_info.data:
                student = student_info.data[0]
                course_title = student.get('courses', {}).get('title', 'Unknown')
                print(f"Enrollment {enrollment_id} deleted - Student {student.get('user_id')} removed from course: {course_title}")
            
            return jsonify({
                "success": True,
                "message": "Enrollment deleted successfully",
                "action": "deleted"
            })
        
        # If setting to active, just update the status (for restoring/reactivating)
        else:
            res = admin_supabase.from_("enrollments").update({"active": active}).eq("id", enrollment_id).execute()
            
            if not res.data:
                return jsonify({"success": False, "error": "Enrollment not found"}), 404
            
            enrollment = res.data[0]
            
            return jsonify({
                "success": True,
                "message": "Enrollment activated successfully",
                "action": "activated",
                "new_active": active
            })

    except Exception as e:
        import traceback
        print(f"Error toggling enrollment status: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500






# -------------------- 6. ADD STUDENT TO COURSE --------------------

@courses_bp.route("/admin/courses/<int:course_id>/students/add", methods=["POST"])
@admin_login_required
def manually_add_student(course_id):
    try:
        if not request.json:
            return jsonify({"error": "No JSON data provided"}), 400
            
        user_id = request.json.get("user_id")
        if not user_id:
            return jsonify({"error": "Missing user_id"}), 400
        
        # Check student and course - MAKE SURE TO INCLUDE FEES
        student_check = admin_supabase.from_("students")\
            .select("id, cpa_level, full_name, email")\
            .eq("id", user_id)\
            .execute()
        
        course_check = admin_supabase.from_("courses")\
            .select("id, cpa_level, title, instructor, fees")\
            .eq("id", course_id)  \
            .execute()
        
        if not student_check.data:
            return jsonify({"error": "Student not found"}), 404
        
        if not course_check.data:
            return jsonify({"error": "Course not found"}), 404
        
        student = student_check.data[0]
        course = course_check.data[0]
        
        # Debug the course data
        print(f"DEBUG - Course data retrieved: {course}")
        print(f"DEBUG - Course fees: {course.get('fees')}")
        
        # CPA Level check REMOVED - Now we can enroll any student regardless of their level
        print(f"INFO - Enrolling student at CPA Level {student.get('cpa_level')} into course requiring Level {course.get('cpa_level')}")
        
        # Check if already enrolled
        existing = admin_supabase.from_("enrollments")\
            .select("id")\
            .eq("course_id", course_id)\
            .eq("user_id", user_id)\
            .execute()
            
        if existing.data:
            return jsonify({"error": "Student already enrolled in this course"}), 400

        # Add enrollment
        enrollment_data = {
            "user_id": user_id,
            "course_id": course_id,
            "active": True,
            "enrolled_at": datetime.datetime.utcnow().isoformat()
        }
        
        result = admin_supabase.from_("enrollments").insert(enrollment_data).execute()
        
        if result.data:
            # Create invoice after successful enrollment
            invoice_result = create_invoice_for_student(user_id, course, student)
            if invoice_result:
                return jsonify({
                    "status": "added", 
                    "message": f"Successfully enrolled {student.get('full_name')} in {course.get('title')} and invoice created",
                    "invoice_created": True
                })
            else:
                return jsonify({
                    "status": "added_but_invoice_failed", 
                    "message": f"Successfully enrolled {student.get('full_name')} but invoice creation failed",
                    "invoice_created": False
                }), 207  # 207 Multi-Status
        else:
            return jsonify({"error": "Failed to enroll student"}), 500
            
    except Exception as e:
        print(f"ERROR in manually_add_student: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500
    

# -------------------- 7. FETCH ALL STUDENTS --------------------
@courses_bp.route("/admin/students/all", methods=["GET"])
@admin_login_required
def get_all_students():
    try:
        students = admin_supabase.from_("students").select("id, full_name").execute().data or []
        return jsonify(students)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- 8. DELETE COURSE --------------------
@courses_bp.route('/admin/courses/<int:course_id>', methods=['DELETE'])
@admin_login_required
def delete_course(course_id):
    try:
        # Verify course exists
        course_res = admin_supabase.from_('courses').select('*').eq('id', course_id).execute()
        if not course_res.data:
            return jsonify({'message': 'Course not found'}), 404

        course = course_res.data[0]
        thumbnail_url = course.get('thumbnail_url') or course.get('thumbnail')

        # Delete associated data in optimal order
        tables_to_delete = ["library_resources", "lectures", "enrollments"]
        deleted_counts = {}
        
        for table in tables_to_delete:
            try:
                res = admin_supabase.from_(table).delete().eq('course_id', course_id).execute()
                deleted_counts[table] = len(res.data) if res.data else 0
            except Exception as e:
                print(f"Error deleting {table}: {e}")
                deleted_counts[table] = 0

        # Delete course
        del_res = admin_supabase.from_('courses').delete().eq('id', course_id).execute()
        
        if not del_res.data:
            return jsonify({'message': 'Failed to delete course'}), 500

        # Delete thumbnail if exists
        if thumbnail_url:
            try:
                delete_cloudinary_image(thumbnail_url)
            except Exception as e:
                print(f"Cloudinary deletion error: {e}")

        return jsonify({
            'message': 'Course deleted successfully',
            'deleted_counts': deleted_counts
        }), 200

    except Exception as e:
        print(f"Error deleting course: {e}")
        return jsonify({'message': str(e)}), 500

# -------------------- LECTURE MANAGEMENT --------------------
@courses_bp.route('/admin/courses/<int:course_id>/lectures/add', methods=['POST'])
@admin_login_required
def add_lecture(course_id):
    try:
        data = request.get_json()
        youtube_link = data.get('youtube_link')
        title = data.get('title')

        if not title or not title.strip():
            return jsonify({'error': 'Lecture title is required'}), 400
        if not youtube_link or not youtube_link.strip():
            return jsonify({'error': 'YouTube link is required'}), 400

        # Verify course exists
        course_resp = admin_supabase.from_('courses').select('id').eq('id', course_id).execute()
        if not course_resp.data:
            return jsonify({'error': 'Course not found'}), 404

        # Insert lecture
        insert_resp = admin_supabase.from_('lectures').insert({
            'course_id': course_id,
            'title': title.strip(),
            'youtube_link': youtube_link.strip(),
            'created_at': datetime.datetime.utcnow().isoformat()
        }).execute()

        if not insert_resp.data:
            return jsonify({'error': 'Failed to add lecture'}), 500

        return jsonify({
            'message': 'Lecture added successfully',
            'lecture': insert_resp.data[0]
        }), 201

    except Exception as e:
        print(f"Error adding lecture: {e}")
        return jsonify({'error': str(e)}), 500

@courses_bp.route("/admin/courses/<int:course_id>/lectures", methods=["GET"])
@admin_login_required
def get_course_lectures(course_id):
    try:
        # Verify course exists
        course_check = admin_supabase.from_("courses").select("id").eq("id", course_id).execute()
        if not course_check.data:
            return jsonify({"error": "Course not found"}), 404
        
        # Get lectures
        lectures = admin_supabase.from_("lectures")\
            .select("*")\
            .eq("course_id", course_id)\
            .order("created_at")\
            .execute()
        
        return jsonify(lectures.data if lectures.data else [])
        
    except Exception as e:
        print(f"Error getting course lectures: {e}")
        return jsonify({"error": str(e)}), 500

@courses_bp.route("/admin/courses/<int:course_id>/lectures/<int:lecture_id>", methods=["DELETE"])
@admin_login_required
def delete_lecture(course_id, lecture_id):
    try:
        # Verify and delete in one operation
        result = admin_supabase.from_("lectures")\
            .delete()\
            .eq("id", lecture_id)\
            .eq("course_id", course_id)\
            .execute()
        
        if result.data:
            return jsonify({"success": True, "message": "Lecture deleted successfully"})
        else:
            return jsonify({"error": "Lecture not found"}), 404
            
    except Exception as e:
        print(f"Error deleting lecture: {e}")
        return jsonify({"error": str(e)}), 500

@courses_bp.route("/admin/courses/<int:course_id>/lectures/<int:lecture_id>", methods=["GET"])
@admin_login_required
def get_lecture(course_id, lecture_id):
    try:
        lecture = admin_supabase.from_("lectures")\
            .select("*")\
            .eq("id", lecture_id)\
            .eq("course_id", course_id)\
            .execute()
        
        if not lecture.data:
            return jsonify({"error": "Lecture not found"}), 404
            
        return jsonify(lecture.data[0])
        
    except Exception as e:
        print(f"Error getting lecture: {e}")
        return jsonify({"error": str(e)}), 500

@courses_bp.route("/admin/courses/<int:course_id>/lectures/<int:lecture_id>", methods=["PUT"])
@admin_login_required
def update_lecture(course_id, lecture_id):
    try:
        data = request.get_json()
        title = data.get('title')
        youtube_link = data.get('youtube_link')

        if not title or not title.strip():
            return jsonify({'error': 'Lecture title is required'}), 400
        if not youtube_link or not youtube_link.strip():
            return jsonify({'error': 'YouTube link is required'}), 400

        update_resp = admin_supabase.from_('lectures')\
            .update({
                'title': title.strip(),
                'youtube_link': youtube_link.strip(),
                'updated_at': datetime.datetime.utcnow().isoformat()
            })\
            .eq('id', lecture_id)\
            .eq('course_id', course_id)\
            .execute()

        if not update_resp.data:
            return jsonify({'error': 'Lecture not found or failed to update'}), 404

        return jsonify({
            'message': 'Lecture updated successfully',
            'lecture': update_resp.data[0]
        }), 200

    except Exception as e:
        print(f"Error updating lecture: {e}")
        return jsonify({'error': str(e)}), 500

# -------------------- UTILITY ROUTES --------------------
@courses_bp.route('/api/courses/all')
@admin_login_required
def get_all_courses():
    try:
        res = admin_supabase.from_("courses").select("id, title").order("title").execute()
        return jsonify(res.data if res.data else [])
    except Exception as e:
        print(f"Error fetching courses: {e}")
        return jsonify([])

# -------------------- REVOKE ALL ENROLLMENTS --------------------
@courses_bp.route("/admin/courses/revoke-all-enrollments", methods=["POST"])
@admin_login_required
def revoke_all_enrollments():
    try:
        # Get counts before deletion
        enrollments_count = admin_supabase.from_("enrollments").select("id", count="exact").execute()
        requests_count = admin_supabase.from_("requests").select("id", count="exact").execute()
        
        # Delete all enrollments and requests
        enrollments_res = admin_supabase.from_("enrollments").delete().neq("id", 0).execute()
        requests_res = admin_supabase.from_("requests").delete().neq("id", 0).execute()
        
        return jsonify({
            "success": True,
            "message": "All enrollments and requests cleared successfully",
            "enrollments_deleted": enrollments_count.count or 0,
            "requests_deleted": requests_count.count or 0
        })
        
    except Exception as e:
        print(f"Error revoking all enrollments: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    
@courses_bp.route("/admin/courses/<int:course_id>/update", methods=["PUT"])
@admin_login_required
def update_course(course_id):
    try:
        # Handle form data instead of JSON
        title = request.form.get('title')
        instructor = request.form.get('instructor')
        cpa_level = request.form.get('cpa_level')
        fees = request.form.get('fees')
        description = request.form.get('description')
        
        # Validate required fields
        if not title or not title.strip():
            return jsonify({'error': 'Course title is required'}), 400
        if not instructor or not instructor.strip():
            return jsonify({'error': 'Instructor is required'}), 400
        if not cpa_level:
            return jsonify({'error': 'CPA level is required'}), 400

        # Prepare update data (without updated_at since column doesn't exist)
        update_data = {
            'title': title.strip(),
            'instructor': instructor.strip(),
            'cpa_level': int(cpa_level),
            'fees': float(fees) if fees else 0,
            'description': description.strip() if description else ''
        }

        # Handle thumbnail upload if provided
        if 'thumbnail' in request.files:
            thumbnail_file = request.files['thumbnail']
            if thumbnail_file and thumbnail_file.filename:
                # Upload to Supabase storage
                file_extension = thumbnail_file.filename.split('.')[-1]
                filename = f"course_{course_id}_{int(datetime.datetime.utcnow().timestamp())}.{file_extension}"
                
                # Upload file to Supabase storage
                upload_result = admin_supabase.storage.from_('course-thumbnails').upload(
                    filename, 
                    thumbnail_file.read(),
                    {"content-type": thumbnail_file.content_type}
                )
                
                if not upload_result.error:
                    # Get public URL
                    thumbnail_url = admin_supabase.storage.from_('course-thumbnails').get_public_url(filename)
                    update_data['thumbnail'] = thumbnail_url

        # Update course in database
        update_resp = admin_supabase.from_('courses').update(update_data).eq('id', course_id).execute()

        if not update_resp.data:
            return jsonify({'error': 'Course not found or failed to update'}), 404

        return jsonify({
            'message': 'Course updated successfully',
            'course': update_resp.data[0]
        }), 200

    except Exception as e:
        print(f"Error updating course: {e}")
        return jsonify({'error': str(e)}), 500