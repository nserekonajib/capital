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