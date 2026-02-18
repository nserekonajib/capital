from flask import Blueprint, flash, redirect, render_template, request, jsonify, session, url_for
from routes.email_manager import generate_otp, send_otp_email
from werkzeug.security import generate_password_hash, check_password_hash
from routes.utils import supabase
import hashlib
import time
from routes.auth import login_required
from routes.config import Config

profile_bp = Blueprint('profile', __name__)

# In-memory storage for OTPs (in production, use Redis or database)
otp_storage = {}
sender_email = Config.sender_email
sender_password = Config.sender_password

@profile_bp.route('/profile')
@login_required
def profile_page():
    """Render the profile page"""
    return render_template('profile.html')


@profile_bp.route('/send-otp', methods=['POST'])
@login_required
def send_otp():
    """Send OTP for password change verification"""
    try:
        data = request.get_json()
        user_email = session.get('user_email')
        user_name = session.get('user_full_name')
        
        if not user_email:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401
        
        # Generate OTP
        otp = generate_otp(6)
        
        # Store OTP with timestamp (valid for 10 minutes)
        otp_storage[user_email] = {
            'otp': otp,
            'timestamp': time.time(),
            'verified': False
        }
        
        # Send OTP email
        if send_otp_email(
            sender_email=sender_email,
            sender_password=sender_password,
            recipient_email=user_email,
            otp=otp,
            student_name=user_name
        ):
              return jsonify({
        'success': True,
        'message': 'OTP sent successfully to your email'
    })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to send OTP. Please try again.'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error sending OTP: {str(e)}'
        }), 500

@profile_bp.route('/verify-otp', methods=['POST'])
@login_required
def verify_otp():
    """Verify OTP for password change"""
    try:
        data = request.get_json()
        user_otp = data.get('otp')
        user_email = session.get('user_email')
        
        if not user_email:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401
        
        # Check if OTP exists and is valid
        stored_otp_data = otp_storage.get(user_email)
        
        if not stored_otp_data:
            return jsonify({
                'success': False,
                'message': 'OTP not found. Please request a new OTP.'
            }), 400
        
        # Check if OTP is expired (10 minutes)
        if time.time() - stored_otp_data['timestamp'] > 600:  # 10 minutes
            del otp_storage[user_email]
            return jsonify({
                'success': False,
                'message': 'OTP has expired. Please request a new OTP.'
            }), 400
        
        # Verify OTP
        if stored_otp_data['otp'] != user_otp:
            return jsonify({
                'success': False,
                'message': 'Invalid OTP. Please try again.'
            }), 400
        
        # Mark OTP as verified
        otp_storage[user_email]['verified'] = True
        
        return jsonify({
            'success': True,
            'message': 'OTP verified successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error verifying OTP: {str(e)}'
        }), 500

def get_current_user_password_hash(user_id):
    
    """Get current user's password hash from database"""
    try:
        response = supabase.table("students").select("password_hash").eq("id", user_id).limit(1).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]['password_hash']
        return None
    except Exception as e:
        print(f"Error fetching user password hash: {e}")
        return None

def update_user_password(user_id, new_password_hash):
    """Update user password in database"""
    try:
        response = supabase.table("students").update({
            "password_hash": new_password_hash,
            "updated_at": "now()"
        }).eq("id", user_id).execute()
        
        return response.data and len(response.data) > 0
    except Exception as e:
        print(f"Error updating user password: {e}")
        return False
    

@profile_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password after OTP verification"""
    try:
        # Try JSON first, then fallback to form data
        data = request.get_json(silent=True) or request.form

        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        user_otp = data.get('otp')

        user_email = session.get('user_email')
        user_id = session.get('user_id')

        # Debugging helper
        print(f"DEBUG change-password request: {data}")
        print(f"DEBUG user_email: {user_email}")
        print(f"DEBUG user_id: {user_id}")
        print(f"DEBUG otp_storage keys: {list(otp_storage.keys())}")

        # Check all required fields
        if not all([current_password, new_password, confirm_password, user_otp]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        # Validate password match
        if new_password != confirm_password:
            return jsonify({'success': False, 'message': 'New passwords do not match'}), 400

        # Validate password strength
        if len(new_password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters long'}), 400

        # Verify OTP
        stored_otp_data = otp_storage.get(user_email)
        print(f"DEBUG stored_otp_data: {stored_otp_data}")
        
        if not stored_otp_data:
            return jsonify({'success': False, 'message': 'OTP not found. Please request a new one.'}), 400

        # Check if OTP is expired (10 minutes)
        if time.time() - stored_otp_data['timestamp'] > 600:
            del otp_storage[user_email]
            return jsonify({'success': False, 'message': 'OTP has expired. Please request a new OTP.'}), 400

        # Verify OTP code
        if stored_otp_data['otp'] != user_otp:
            print(f"DEBUG OTP mismatch: stored={stored_otp_data['otp']}, received={user_otp}")
            return jsonify({'success': False, 'message': 'Invalid OTP. Please try again.'}), 400

        # Check if OTP is verified
        if not stored_otp_data.get('verified'):
            # Auto-verify if OTP matches but not marked as verified
            if stored_otp_data['otp'] == user_otp:
                stored_otp_data['verified'] = True
                print(f"DEBUG Auto-verified OTP for {user_email}")
            else:
                return jsonify({'success': False, 'message': 'OTP verification required. Please verify OTP first.'}), 400

        # Verify current password
        current_password_hash = get_current_user_password_hash(user_id)
        if not current_password_hash:
            return jsonify({'success': False, 'message': 'Could not fetch current password'}), 400

        if not check_password_hash(current_password_hash, current_password):
            return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400

        # Prevent reusing the same password
        if check_password_hash(current_password_hash, new_password):
            return jsonify({'success': False, 'message': 'New password cannot be the same as current password'}), 400

        # Update password
        new_password_hash = generate_password_hash(new_password)
        if not update_user_password(user_id, new_password_hash):
            return jsonify({'success': False, 'message': 'Failed to update password'}), 500

        # Clear OTP
        otp_storage.pop(user_email, None)

        print(f"✅ Password changed successfully for user {user_id}")

        return jsonify({'success': True, 'message': 'Password changed successfully'}), 200

    except Exception as e:
        print(f"❌ Error in change-password route: {e}")
        return jsonify({'success': False, 'message': f'Error changing password: {str(e)}'}), 500
    
    
@profile_bp.route('/profile-info', methods=['GET'])
@login_required
def get_profile_info():
    """Get current user profile information"""
    try:
        user_info = {
            'full_name': session.get('user_full_name', 'User'),
            'email': session.get('user_email', ''),
            'cpa_level': session.get('cpa_level', '0'),
            'user_id': session.get('user_id', '')
        }
        
        return jsonify({
            'success': True,
            'data': user_info
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching profile info: {str(e)}'
        }), 500

@profile_bp.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    """Update user profile information (name, etc.)"""
    try:
        data = request.get_json()
        full_name = data.get('full_name', '').strip()
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401
        
        if not full_name or len(full_name) < 1 or len(full_name) > 100:
            return jsonify({
                'success': False,
                'message': 'Full name must be between 1 and 100 characters'
            }), 400
        
        # Update user profile in database
        try:
            response = supabase.table("students").update({
                "full_name": full_name,
                "updated_at": "now()"
            }).eq("id", user_id).execute()
            
            if response.data and len(response.data) > 0:
                # Update session
                session['user_full_name'] = full_name
                session.modified = True
                
                return jsonify({
                    'success': True,
                    'message': 'Profile updated successfully',
                    'data': {
                        'full_name': full_name
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Failed to update profile'
                }), 500
                
        except Exception as e:
            print(f"Error updating profile: {e}")
            return jsonify({
                'success': False,
                'message': 'Error updating profile information'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error updating profile: {str(e)}'
        }), 500

@profile_bp.route('/check-session', methods=['GET'])
@login_required
def check_session():
    """Check if user session is valid"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({
                'success': False,
                'message': 'Session expired'
            }), 401
        
        # Verify user still exists and is active
        try:
            response = supabase.table("students").select("id, status").eq("id", user_id).limit(1).execute()
            
            if not response.data or response.data[0].get('status') != 'active':
                return jsonify({
                    'success': False,
                    'message': 'Account not found or inactive'
                }), 401
                
        except Exception as e:
            print(f"Error verifying user session: {e}")
            return jsonify({
                'success': False,
                'message': 'Error verifying session'
            }), 500
        
        return jsonify({
            'success': True,
            'message': 'Session valid',
            'data': {
                'user_id': user_id,
                'full_name': session.get('user_full_name'),
                'email': session.get('user_email')
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error checking session: {str(e)}'
        }), 500
        
        
        
@profile_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Step 1: User requests password reset via email"""
    try:
        
        data = request.get_json(silent=True) or request.form
        user_email = data.get('email')

        if not user_email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400

        # Check if user exists in DB
        response = supabase.table("students").select("id, full_name").eq("email", user_email).limit(1).execute()
        if not response.data:
            return jsonify({'success': False, 'message': 'No account found with this email'}), 404

        user = response.data[0]
        student_name = user.get("full_name", "Student")

        # Generate OTP
        otp = generate_otp(6)
        otp_storage[user_email] = {
            'otp': otp,
            'timestamp': time.time(),
            'verified': False
        }

        # Send OTP email
        if send_otp_email(sender_email, sender_password, user_email, otp, student_name):
            return jsonify({'success': True, 'message': 'OTP sent to your email'})
        else:
            return jsonify({'success': False, 'message': 'Failed to send OTP'}), 500

    except Exception as e:
        print(f"❌ Error in forgot-password: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@profile_bp.route('/forgot-password/verify', methods=['POST'])
def forgot_password_verify():
    """Step 2: Verify OTP for forgot password"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request format'}), 400

        user_email = data.get('email')
        user_otp = data.get('otp')

        if not user_email or not user_otp:
            return jsonify({'success': False, 'message': 'Email and OTP are required'}), 400

        stored_otp_data = otp_storage.get(user_email)
        if not stored_otp_data:
            return jsonify({'success': False, 'message': 'No OTP found. Request again'}), 400

        # Check expiration
        if time.time() - stored_otp_data['timestamp'] > 600:
            otp_storage.pop(user_email, None)
            return jsonify({'success': False, 'message': 'OTP expired'}), 400

        if stored_otp_data['otp'] != user_otp:
            return jsonify({'success': False, 'message': 'Invalid OTP'}), 400

        # Mark as verified
        otp_storage[user_email]['verified'] = True
        return jsonify({'success': True, 'message': 'OTP verified successfully'})

    except Exception as e:
        print(f"❌ Error in forgot-password-verify: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500



@profile_bp.route('/forgot-password/reset', methods=['POST'])
def forgot_password_reset():
    """Reset password after OTP verification"""
    try:
        # Support both JSON and form submissions
        data = request.get_json(silent=True) or request.form

        user_email = data.get('email')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')

        # Validate input
        if not all([user_email, new_password, confirm_password]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        if new_password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

        if len(new_password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400

        # OTP verification check
        stored_otp_data = otp_storage.get(user_email)
        if not stored_otp_data or not stored_otp_data.get('verified', False):
            return jsonify({'success': False, 'message': 'OTP verification required'}), 400

        # Update password in DB
        new_password_hash = generate_password_hash(new_password)

        response = supabase.table("students").update({
            "password_hash": new_password_hash,
            "updated_at": "now()"
        }).eq("email", user_email).execute()

        if not response.data:
            return jsonify({'success': False, 'message': 'Failed to reset password'}), 500

        # Clear OTP
        otp_storage.pop(user_email, None)

        print(f"✅ Password reset successfully for {user_email}")
        return jsonify({'success': True, 'message': 'Password reset successfully'})

    except Exception as e:
        print(f"❌ Error in forgot-password-reset: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    
@profile_bp.route('/forgot-password/verify-page')
def forgot_password_verify_page():
    """Render OTP verification page"""
    email = request.args.get('email')
    if not email:
        flash("Missing email parameter", "error")
        return redirect(url_for("profile.forgot_password"))

    return render_template("/verify_otp_forgot.html", email=email)


@profile_bp.route('/forgot-password/reset-page')
def forgot_password_reset_page():
    """Render the password reset page after OTP verification"""
    email = request.args.get('email')
    if not email:
        flash("Missing email parameter", "error")
        return redirect(url_for("profile.forgot_password"))

    return render_template("reset_password.html", email=email)
