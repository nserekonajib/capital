from dotenv import load_dotenv
from flask import render_template, redirect, url_for, flash, request, session, Blueprint, g, jsonify
from functools import wraps
import time
import uuid
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from werkzeug.security import generate_password_hash, check_password_hash
from routes.utils import supabase, send_reset_email

load_dotenv()
# Define Blueprint
auth_bp = Blueprint('auth', __name__)

# Thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=100)

# Session configuration
SESSION_DURATION = 315360000  # 30 days in seconds
SESSION_UPDATE_INTERVAL = 10 * 60  # 10 minutes - update session data every 10 minutes
LAST_UPDATE_KEY = 'last_session_update'

# Rate limiting
rate_limit_store = {}
MAX_REQUESTS_PER_MINUTE = 60

# ---------------- Session Management ----------------
def should_update_session():
    """Check if session data needs to be updated"""
    last_update = session.get(LAST_UPDATE_KEY, 0)
    return (time.time() - last_update) > SESSION_UPDATE_INTERVAL

def update_user_session():
    """Fetch fresh user data and update session"""
    user_id = session.get('user_id')
    if not user_id:
        return False
    
    try:
        print("Updating user session with fresh data...")
        response = supabase.table("students").select(
            "id,email,full_name,password_hash,status,cpa_level"
        ).eq("id", user_id).limit(1).execute()
        
        if response.data:
            user_data = response.data[0]
            
            # Check if account is inactive
            if user_data.get('status') != 'active':
                clear_user_session()
                return None
                
            # Update session with fresh data
            session['user_email'] = user_data['email']
            session['user_full_name'] = user_data['full_name']
            session['cpa_level'] = user_data['cpa_level']
            session[LAST_UPDATE_KEY] = time.time()
            session.permanent = True
            session.modified = True
            print("Session updated successfully")
            return user_data
        return None
    except Exception as e:
        print(f"Session update failed: {e}")
        return None

def create_user_session(student):
    """Create new user session with initial data"""
    # Generate unique session token
    session_token = str(uuid.uuid4())
    current_timestamp = datetime.now().isoformat()
    
    # Update user record with new session token and login time
    try:
        result = supabase.table("students").update({
            "session_token": session_token,
            "last_login": current_timestamp,
            "last_logout": None  # Clear any previous logout
        }).eq("id", student['id']).execute()
        
        if hasattr(result, 'error') and result.error:
            print(f"Supabase error: {result.error}")
            return False
            
    except Exception as e:
        print(f"Error updating session token: {e}")
        return False
    
    # Create permanent session
    session.permanent = True
    session['user_id'] = student['id']
    session['user_email'] = student['email']
    session['user_full_name'] = student['full_name']
    session['cpa_level'] = student['cpa_level']
    session['session_token'] = session_token
    session['logged_in'] = True
    session[LAST_UPDATE_KEY] = time.time()
    session.modified = True
    return True

def clear_user_session():
    """Clear session data"""
    session.clear()

def logout_user(user_id, session_token):
    """Log user out by clearing session token"""
    try:
        # Only clear if the session token matches
        response = supabase.table("students").select("session_token").eq("id", user_id).execute()
        if (response.data and 
            response.data[0].get('session_token') == session_token):
            
            current_timestamp = datetime.now().isoformat()
            result = supabase.table("students").update({
                "session_token": None,
                "last_logout": current_timestamp
            }).eq("id", user_id).execute()
            
            return not (hasattr(result, 'error') and result.error)
        return False
    except Exception as e:
        print(f"Error clearing session token: {e}")
        return False

def validate_session_token(user_id, session_token):
    """Validate if the session token matches the one in database and account is active"""
    if not user_id or not session_token:
        return False
    
    try:
        response = supabase.table("students").select(
            "session_token,status,last_login,last_logout"
        ).eq("id", user_id).limit(1).execute()
        
        if response.data:
            user_data = response.data[0]
            
            # Check if account is active
            if user_data.get('status') != 'active':
                return False
                
            # Check if session token matches
            if user_data.get('session_token') != session_token:
                return False
                
            # Check if user was manually logged out
            last_login = datetime.fromisoformat(user_data['last_login']) if user_data['last_login'] else datetime.min
            last_logout = datetime.fromisoformat(user_data['last_logout']) if user_data['last_logout'] else datetime.min
            
            # If last_logout is after last_login, session is invalid
            if last_logout > last_login:
                return False
                
            return True
        return False
    except Exception as e:
        print(f"Session token validation failed: {e}")
        return False

# ---------------- Rate Limiting ----------------
def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        current_time = time.time()
        rate_limit_store[client_ip] = [
            t for t in rate_limit_store.get(client_ip, [])
            if current_time - t < 60
        ]
        if len(rate_limit_store[client_ip]) >= MAX_REQUESTS_PER_MINUTE:
            flash('Too many requests. Try again later.', 'danger')
            return render_template('rate_limit.html'), 429
        rate_limit_store.setdefault(client_ip, []).append(current_time)
        return f(*args, **kwargs)
    return decorated_function

# ---------------- Login Required ----------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            clear_user_session()
            flash('Please login first.', 'warning')
            return redirect(url_for('auth.login'))

        user_id = session.get('user_id')
        session_token = session.get('session_token')
        
        if not user_id or not session_token:
            flash('Invalid session. Please login again.', 'warning')
            return redirect(url_for('auth.login'))

        # Validate session token and check if account is active
        if not validate_session_token(user_id, session_token):
            flash('Your session has expired. Please login again.', 'warning')
            clear_user_session()
            return redirect(url_for('auth.login'))

        # Check if session needs update
        if should_update_session():
            user_data = update_user_session()
            if not user_data:
                flash('Session validation failed. Please login again.', 'warning')
                clear_user_session()
                return redirect(url_for('auth.login'))

        # Store current user data in request context
        g.current_user = {
            'id': session['user_id'],
            'email': session['user_email'],
            'full_name': session['user_full_name'],
            'cpa_level': session['cpa_level']
        }
       
        return f(*args, **kwargs)
    return decorated_function

# ---------------- Input Validation ----------------
def validate_email(email):
    return '@' in email and len(email) <= 254

def validate_password(password):
    return 6 <= len(password) <= 128

def validate_name(name):
    return 1 <= len(name) <= 100

# ---------------- Register ----------------
@auth_bp.route('/register', methods=['GET', 'POST'])
@rate_limit
def register():
    if session.get('logged_in'):
        return redirect(url_for('dashboards.dashboards'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        phone_number = request.form.get('phone_number', '').strip()
        cpa_level = request.form.get('cpa_level', '').strip()

        # Validate
        if not all([full_name, email, password, phone_number, cpa_level]):
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        if not validate_email(email):
            flash('Enter a valid email address.', 'danger')
            return render_template('register.html')

        if not validate_password(password):
            flash('Password must be between 6 and 128 characters.', 'danger')
            return render_template('register.html')

        if not validate_name(full_name):
            flash('Name must be 1-100 characters.', 'danger')
            return render_template('register.html')

        try:
            # Check if email already exists
            existing_user = supabase.table("students").select("id").eq("email", email).execute()
            if existing_user.data:
                flash('Email already registered. Please use a different email or login.', 'danger')
                return render_template('register.html')

            # Hash password
            hashed_pw = generate_password_hash(password)

            # Insert student
            result = supabase.table("students").insert({
                "full_name": full_name,
                "email": email,
                "password_hash": hashed_pw,
                "phone_number": phone_number,
                "cpa_level": cpa_level,
                "status": "active",
                "session_token": None,
                "last_login": None,
                "last_logout": datetime.now().isoformat()
            }).execute()

            if result.data:
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('Registration failed. Please try again.', 'danger')

        except Exception as e:
            flash('Error during registration. Please try again.', 'danger')
            print(f"[Register] Error: {e}")

    return render_template('register.html')

# ---------------- Login ----------------
@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboards.dashboards'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash('Both email and password are required.', 'danger')
            return render_template('login.html')

        if not validate_email(email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('login.html')

        try:
            # Fetch student by email
            response = supabase.table("students").select("*").eq("email", email).limit(1).execute()

            if not response.data:
                flash('Invalid email or password.', 'danger')
                return render_template('login.html')

            student = response.data[0]

            # Check if account is active
            if student.get('status') != 'active':
                flash('Your account is inactive. Please contact administrator.', 'danger')
                return render_template('login.html')

            # Check password
            if check_password_hash(student['password_hash'], password):
                # Create new session
                if create_user_session(student):
                    flash('Login successful!', 'success')
                    
                    # Check if there's a redirect URL in session
                    next_url = session.pop('next', None)
                    if next_url:
                        return redirect(next_url)
                    return redirect(url_for('dashboards.dashboards'))
                else:
                    flash('Login failed. Please try again.', 'danger')
            else:
                flash('Invalid email or password.', 'danger')

        except Exception as e:
            flash('An error occurred during login. Please try again.', 'danger')
            print(f"[Login] Error: {e}")

    return render_template('login.html')

# ---------------- Logout ----------------
@auth_bp.route('/logout')
@login_required
def logout():
    """Logout user"""
    user_id = session.get('user_id')
    session_token = session.get('session_token')
    
    if user_id and session_token:
        logout_user(user_id, session_token)
    
    clear_user_session()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))

# ---------------- Forgot Password ----------------
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@rate_limit
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not validate_email(email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('forgot_password.html')

        try:
            # Check if email exists
            response = supabase.table("students").select("id,email").eq("email", email).execute()
            if not response.data:
                flash('If this email exists in our system, a reset link will be sent.', 'info')
                return render_template('forgot_password.html')

            # Send reset email
            future = executor.submit(send_reset_email, email)
            result = future.result(timeout=10.0)
            if result:
                flash('Password reset instructions have been sent to your email.', 'success')
            else:
                flash('Failed to send reset email. Please try again later.', 'danger')
        except Exception as e:
            flash('An error occurred. Please try again later.', 'danger')
            print(f"[Forgot Password] Error: {e}")

    return render_template('forgot_password.html')

# ---------------- Session Update Endpoint ----------------
@auth_bp.route('/update-session', methods=['POST'])
@login_required
def update_session():
    """Explicit endpoint to force session update"""
    user_data = update_user_session()
    if user_data:
        return jsonify({'status': 'success', 'message': 'Session updated'})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to update session'}), 500

# ---------------- Health Check ----------------
@auth_bp.route('/health')
def health_check():
    return {'status': 'healthy', 'timestamp': time.time()}

# ---------------- Executor Shutdown ----------------
def shutdown_executor():
    executor.shutdown(wait=False)
