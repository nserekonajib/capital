from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from werkzeug.security import generate_password_hash
from routes.admin_utils import get_admin_client
from functools import wraps

# Blueprint
students_bp = Blueprint('students', __name__)

# ---------------- Helpers ----------------
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash("Please log in as admin", "danger")
            return redirect(url_for("adminauth.login"))
        return f(*args, **kwargs)
    return decorated_function

def create_student(data):
    """Insert student into Supabase with default password"""
    client = get_admin_client()  # <-- use Supabase client
    try:
        hashed_pw = generate_password_hash("123")  # default password
        student_data = {
            "full_name": data.get("full_name"),
            "cpa_level": data.get("cpa_level"),
            "email": data.get("email"),
            "phone_number": data.get("phone_number"),
            "status": data.get("status", "active"),
            "password_hash": hashed_pw
        }
        res = client.from_("students").insert(student_data).execute()
        print(res)
        return res
    except Exception as e:
        print(f"Error creating student: {e}")
        return None

def search_students(query=""):
    """Search students by name or email"""
    client = get_admin_client()  # <-- use Supabase client
    try:
        res = client.from_("students").select("*").or_(
            f"full_name.ilike.%{query}%,email.ilike.%{query}%"
        ).execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"Error searching students: {e}")
        return []

# ---------------- Routes ----------------
@students_bp.route("/admin/students", methods=["GET", "POST"])
@admin_login_required
def students_management():
    if request.method == "POST":
        data = request.form
        result = create_student(data)
        if result and not getattr(result, "error", None):
            flash("Student registered successfully! Default password is 123.", "success")
        else:
            flash("Failed to register student.", "danger")
        return redirect(url_for("students.students_management"))

    # default search query
    search_query = request.args.get("q", "")
    students = search_students(search_query)
    return render_template("admin/students.html", students=students, search_query=search_query)

# ---------------- AJAX endpoint for live search ----------------
@students_bp.route("/admin/students/search")
@admin_login_required
def ajax_search_students():
    query = request.args.get("q", "")
    students = search_students(query)
    return jsonify(students)

@students_bp.route("/admin/students/toggle_status/<int:student_id>", methods=["POST"])
@admin_login_required
def toggle_student_status(student_id):
    client = get_admin_client()
    try:
        new_status = request.json.get("status")
        res = client.from_("students").update({"status": new_status}).eq("id", student_id).execute()
        if getattr(res, "error", None):
            return jsonify({"success": False})
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error toggling status: {e}")
        return jsonify({"success": False})

# ---------------- Edit student endpoints ----------------
@students_bp.route("/admin/students/get/<int:student_id>")
@admin_login_required
def get_student(student_id):
    client = get_admin_client()
    try:
        res = client.from_("students").select("*").eq("id", student_id).execute()
        if res.data:
            return jsonify(res.data[0])
        return jsonify(None)
    except Exception as e:
        print(f"Error getting student: {e}")
        return jsonify(None)


@students_bp.route("/admin/students/update", methods=["POST"])
@admin_login_required
def update_student():
    client = get_admin_client()
    try:
        data = request.json
        student_id = data.get("id")
        update_data = {
            "full_name": data.get("full_name"),
            "cpa_level": data.get("cpa_level"),
            "email": data.get("email"),
            "phone_number": data.get("phone_number")
        }
        res = client.from_("students").update(update_data).eq("id", student_id).execute()
        if getattr(res, "error", None):
            return jsonify({"success": False})
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error updating student: {e}")
        return jsonify({"success": False})
    
    
@students_bp.route("/admin/students/reset-password", methods=["POST"])
@admin_login_required
def reset_student_password():
    """Reset a student's password (admin only)"""
    client = get_admin_client()
    try:
        data = request.json
        student_id = data.get("student_id")
        new_password = data.get("new_password")
        
        # Validate input
        if not student_id or not new_password:
            return jsonify({
                "success": False, 
                "message": "Student ID and new password are required"
            })
        
        # Validate password strength (optional)
        if len(new_password) < 6:
            return jsonify({
                "success": False, 
                "message": "Password must be at least 6 characters long"
            })
        
        # Hash the new password
        hashed_pw = generate_password_hash(new_password)
        
        # Update the student's password
        res = client.from_("students").update(
            {"password_hash": hashed_pw}
        ).eq("id", student_id).execute()
        
        # Check for errors
        if hasattr(res, 'error') and res.error:
            return jsonify({
                "success": False, 
                "message": f"Database error: {res.error}"
            })
        
        # Optional: Log the password reset action
        admin_id = session.get('admin_id')
        print(f"Admin {admin_id} reset password for student {student_id}")
        
        return jsonify({
            "success": True, 
            "message": "Password reset successfully"
        })
        
    except Exception as e:
        print(f"Error resetting password: {e}")
        return jsonify({
            "success": False, 
            "message": f"Server error: {str(e)}"
        })

# Alternative: Route with form for password reset (GET)
@students_bp.route("/admin/students/reset-password-form/<int:student_id>")
@admin_login_required
def reset_password_form(student_id):
    """Display password reset form for a specific student"""
    client = get_admin_client()
    try:
        # Get student details
        res = client.from_("students").select("id, full_name, email").eq("id", student_id).execute()
        
        if not res.data:
            flash("Student not found", "danger")
            return redirect(url_for("students.students_management"))
        
        student = res.data[0]
        return render_template("admin/reset_password.html", student=student)
        
    except Exception as e:
        print(f"Error loading reset password form: {e}")
        flash("Error loading student data", "danger")
        return redirect(url_for("students.students_management"))

# Alternative: Form submission endpoint
@students_bp.route("/admin/students/reset-password-submit", methods=["POST"])
@admin_login_required
def reset_password_submit():
    """Handle password reset form submission"""
    client = get_admin_client()
    try:
        student_id = request.form.get("student_id")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        # Validate
        if not student_id or not new_password:
            flash("Student ID and new password are required", "danger")
            return redirect(request.referrer or url_for("students.students_management"))
        
        if new_password != confirm_password:
            flash("Passwords do not match", "danger")
            return redirect(request.referrer)
        
        if len(new_password) < 6:
            flash("Password must be at least 6 characters long", "danger")
            return redirect(request.referrer)
        
        # Hash and update
        hashed_pw = generate_password_hash(new_password)
        res = client.from_("students").update(
            {"password_hash": hashed_pw}
        ).eq("id", student_id).execute()
        
        if hasattr(res, 'error') and res.error:
            flash(f"Error resetting password: {res.error}", "danger")
        else:
            flash("Password reset successfully!", "success")
            
        return redirect(url_for("students.students_management"))
        
    except Exception as e:
        print(f"Error resetting password: {e}")
        flash(f"Server error: {str(e)}", "danger")
        return redirect(url_for("students.students_management"))
