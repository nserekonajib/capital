from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from routes.admin_utils import get_admin_client
import pandas as pd
import io
from datetime import datetime
import asyncio
import os
import traceback

# Blueprint
adminauth_bp = Blueprint('adminauth', __name__)

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
BATCH_SIZE = 50

# ---------------- Helpers ----------------
def get_admin_by_email(email):
    """Fetch admin from Supabase (admins table)"""
    client = get_admin_client()
    try:
        res = client.from_("adminusers").select("*").eq("email", email).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        print(f"Error fetching admin: {e}")
        return None

def create_admin(email, password, role="viewer"):
    """Create admin with hashed password"""
    client = get_admin_client()
    try:
        hashed = generate_password_hash(password)
        res = client.from_("adminusers").insert({
            "email": email,
            "password_hash": hashed,
            "role": role
        }).execute()
        return res
    except Exception as e:
        print(f"Error creating admin: {e}")
        return None

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in as admin.', 'danger')
            return redirect(url_for('adminauth.login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    """Ensure admin has the right role"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("admin_role") != role:
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("admin_dashboard.dashboard"))
            return f(*args, **kwargs)
        return wrapper
    return decorator

def detect_encoding(file_content):
    """Detect file encoding for CSV files"""
    try:
        import chardet
        result = chardet.detect(file_content)
        return result.get('encoding', 'utf-8')
    except ImportError:
        return 'utf-8'

async def import_bulk_users_optimized(file_content, filename):
    """
    Optimized bulk user import with batch processing
    Returns: (success_count, error_count, errors_list)
    """
    client = get_admin_client()
    success_count = 0
    error_count = 0
    errors = []
    
    try:
        # Read file
        if filename.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(file_content))
        elif filename.endswith('.csv'):
            encoding = detect_encoding(file_content)
            df = pd.read_csv(io.BytesIO(file_content), encoding=encoding)
        else:
            return 0, 0, ["Unsupported file format"]
        
        # Validate required columns
        required_columns = ['Full Name', 'CPA Level', 'Email', 'Phone', 'Status']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return 0, 0, [f"Missing required columns: {', '.join(missing_columns)}"]
        
        # Clean the dataframe
        df = df.dropna(how='all')  # Remove completely empty rows
        df = df.fillna('')  # Replace NaN with empty strings
        
        # Pre-process and validate data
        valid_users = []
        for index, row in df.iterrows():
            try:
                # Skip empty rows
                if pd.isna(row['Full Name']) and pd.isna(row['Email']):
                    continue
                    
                full_name = str(row['Full Name']).strip()
                cpa_level = str(row['CPA Level']).strip().upper()
                email = str(row['Email']).strip().lower()
                phone = str(row['Phone']).strip()
                status = str(row['Status']).strip().lower() if pd.notna(row['Status']) else 'active'
                
                # Quick validation
                if not all([full_name, cpa_level, email]):
                    errors.append(f"Row {index + 2}: Missing required fields (Name, CPA Level, Email)")
                    error_count += 1
                    continue
                
                if '@' not in email or '.' not in email:
                    errors.append(f"Row {index + 2}: Invalid email format - {email}")
                    error_count += 1
                    continue
                
                if not cpa_level.startswith('CPA'):
                    errors.append(f"Row {index + 2}: Invalid CPA level - {cpa_level}. Must start with 'CPA'")
                    error_count += 1
                    continue
                
                # Normalize status
                status = 'active' if status.lower() in ['active', 'actif', '1', 'yes', 'true'] else 'inactive'
                hashed_password = generate_password_hash("123")
                
                valid_users.append({
                    'full_name': full_name,
                    'cpa_level': cpa_level,
                    'email': email,
                    'phone_number': phone,
                    'status': status,
                    'password_hash': hashed_password,
                    'created_at': datetime.utcnow().isoformat(),
                    'index': index + 2
                })
                
            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")
                error_count += 1
        
        # Check for duplicate emails in batch
        if valid_users:
            emails = [user['email'] for user in valid_users]
            
            try:
                # Batch check existing users
                existing_users_res = client.from_("students")\
                    .select("email")\
                    .in_("email", emails)\
                    .execute()
                
                existing_emails = {user['email'] for user in (existing_users_res.data or [])}
                
                # Filter out existing users
                unique_users = [user for user in valid_users if user['email'] not in existing_emails]
                
                # Add errors for duplicates found
                for user in valid_users:
                    if user['email'] in existing_emails:
                        errors.append(f"Row {user['index']}: User {user['email']} already exists")
                        error_count += 1
                        
            except Exception as e:
                errors.append(f"Database error while checking duplicates: {str(e)}")
                # Continue with all users if duplicate check fails
                unique_users = valid_users
            
            # Insert in batches
            for i in range(0, len(unique_users), BATCH_SIZE):
                batch = unique_users[i:i + BATCH_SIZE]
                batch_data = [{
                    'full_name': user['full_name'],
                    'cpa_level': user['cpa_level'],
                    'email': user['email'],
                    'phone_number': user['phone_number'],
                    'status': user['status'],
                    'password_hash': user['password_hash'],
                    'created_at': user['created_at']
                } for user in batch]
                
                try:
                    result = client.from_("students").insert(batch_data).execute()
                    
                    if result.data:
                        success_count += len(result.data)
                    else:
                        # Individual fallback for failed batch
                        for user in batch:
                            try:
                                individual_result = client.from_("students").insert({
                                    'full_name': user['full_name'],
                                    'cpa_level': user['cpa_level'],
                                    'email': user['email'],
                                    'phone_number': user['phone_number'],
                                    'status': user['status'],
                                    'password_hash': user['password_hash'],
                                    'created_at': user['created_at']
                                }).execute()
                                
                                if individual_result.data:
                                    success_count += 1
                                else:
                                    errors.append(f"Row {user['index']}: Failed to insert {user['email']}")
                                    error_count += 1
                            except Exception as e:
                                errors.append(f"Row {user['index']}: {str(e)}")
                                error_count += 1
                except Exception as e:
                    errors.append(f"Batch insert error: {str(e)}")
                    error_count += len(batch)
        
    except Exception as e:
        errors.append(f"File processing error: {str(e)}")
        print(traceback.format_exc())
    
    return success_count, error_count, errors

def import_bulk_users(file_content, filename):
    """Sync wrapper for the async function"""
    try:
        return asyncio.run(import_bulk_users_optimized(file_content, filename))
    except Exception as e:
        return 0, 1, [f"System error: {str(e)}"]

# ---------------- Routes ----------------
@adminauth_bp.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        admin = get_admin_by_email(email)
        if admin and check_password_hash(admin["password_hash"], password):
            session['admin_id'] = admin["id"]
            session['admin_email'] = admin["email"]
            session['admin_role'] = admin["role"]
            session['admin_logged_in'] = True
            flash("Admin login successful!", "success")
            return redirect(url_for("admin_dashboard.dashboard"))
        else:
            flash("Invalid email or password", "danger")

    return render_template("admin/login.html")

@adminauth_bp.route('/admin/logout')
@admin_login_required
def logout():
    session.pop('admin_id', None)
    session.pop('admin_email', None)
    session.pop('admin_role', None)
    session.pop('admin_logged_in', None)
    session.pop('import_errors', None)
    flash("Admin logged out.", "info")
    return redirect(url_for("adminauth.login"))

@adminauth_bp.route('/admin/bulk-import', methods=['GET'])
@admin_login_required
@role_required("superadmin")
def bulk_import_page():
    """Render the bulk import page"""
    import_errors = session.pop('import_errors', None)
    return render_template('admin/bulk_import.html', import_errors=import_errors)

@adminauth_bp.route('/admin/bulk-import/process', methods=['POST'])
@admin_login_required
@role_required("superadmin")
def process_bulk_import():
    """Process bulk import via AJAX with progress updates"""
    if 'user_file' not in request.files:
        return jsonify({'success': False, 'message': 'No file selected'})
    
    file = request.files['user_file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})
    
    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.csv')):
        return jsonify({'success': False, 'message': 'Invalid file format. Please upload Excel (.xlsx) or CSV (.csv) file'})
    
    try:
        # Check file size
        file_content = file.read()
        if len(file_content) > MAX_FILE_SIZE:
            return jsonify({'success': False, 'message': 'File too large. Maximum size is 10MB'})
        
        success_count, error_count, errors = import_bulk_users(file_content, file.filename)
        
        result = {
            'success': True,
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors[:20]  # Limit errors to prevent huge response
        }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in bulk import: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@adminauth_bp.route('/admin/create', methods=['GET', 'POST'])
@admin_login_required
@role_required("superadmin")
def create_admin_user():
    """Superadmins can create other admins"""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "viewer").strip().lower()

        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("admin/create.html")

        if role not in ["superadmin", "manager", "viewer"]:
            flash("Invalid role selected.", "danger")
            return render_template("admin/create.html")

        result = create_admin(email, password, role)
        if result and not getattr(result, "error", None):
            flash(f"Admin user {email} created successfully!", "success")
            return redirect(url_for("admin_dashboard.dashboard"))
        else:
            #error_msg = getattr(result.error, 'message', 'Failed to create admin')
            flash(f"Failed to create admin")

    return render_template("admin/create.html")