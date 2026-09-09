import uuid
from flask import Blueprint, request, render_template, jsonify, session
from routes.admin_utils import admin_supabase, get_admin_client
from routes.adminauth import admin_login_required
import datetime

def create_invoice_for_student(user_id, course, student):
    """Auto-create an invoice when a student is enrolled or approved."""
    try:
        course_fees = course.get("fees", 0)
        if course_fees is None or course_fees == "":
            course_fees = 0
        
        fees_float = float(course_fees)
        invoice_number = f"INV-{datetime.datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        invoice_data = {
            "user_id": user_id,
            "course_id": course.get("id"),
            "invoice_number": invoice_number,
            "amount": fees_float,
            "balance": fees_float,
            "status": "unpaid",
            "due_date": (datetime.datetime.utcnow() + datetime.timedelta(days=14)).date().isoformat(),
            "description": f"Tuition for {course.get('title', 'Course')} - CPA Level {course.get('cpa_level', '')}",
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat()
        }

        res = admin_supabase.from_("invoices").insert(invoice_data).execute()
        
        if not res.data:
            raise Exception("Failed to insert invoice")

        return res.data[0]
    except Exception as e:
        print(f"Error creating invoice: {e}")
        return None

requests_bp = Blueprint("admin_requests", __name__)

# -------------------- 1. REQUESTS MANAGEMENT PAGE --------------------
@requests_bp.route("/admin/requests")
@admin_login_required
def manage_requests():
    """Render the requests management page"""
    return render_template("admin/requests/manage.html")

# -------------------- 2. FETCH ALL REQUESTS --------------------
@requests_bp.route("/admin/requests/data")
@admin_login_required
def get_requests():
    """Fetch all course requests with student and course details - Optimized with batch loading"""
    try:
        client = get_admin_client()
        
        # Get requests with student and course details in a single query
        response = client.from_("requests")\
            .select('''
                *,
                students (id, full_name, email, cpa_level),
                courses (id, title, instructor, cpa_level, fees)
            ''')\
            .order('requested_at', desc=True)\
            .execute()
        
        requests = response.data if response.data else []
        
        return jsonify(requests)
        
    except Exception as e:
        print(f"Error fetching requests: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------- 3. UPDATE REQUEST STATUS --------------------
@requests_bp.route("/admin/requests/<int:request_id>/status", methods=["POST"])
@admin_login_required
def update_request_status(request_id):
    """Update request status and automatically enroll student if approved"""
    try:
        client = get_admin_client()
        data = request.get_json()
        status = data.get('status')
        admin_id = session.get('admin_id')
        
        if status not in ['pending', 'approved', 'declined']:
            return jsonify({"success": False, "error": "Invalid status"}), 400
        
        # Get the request details with student and course data
        request_response = client.from_("requests")\
            .select('''
                *,
                students (id, full_name, email, cpa_level),
                courses (id, title, fees, cpa_level)
            ''')\
            .eq('id', request_id)\
            .single()\
            .execute()
        
        if not request_response.data:
            return jsonify({"success": False, "error": "Request not found"}), 404
        
        request_data = request_response.data
        user_id = request_data['user_id']
        course_id = request_data['course_id']
        student_data = request_data.get('students', {})
        course_data = request_data.get('courses', {})
        previous_status = request_data.get('status')

        # Prepare update data
        if status == 'pending':
            update_data = {
                'status': status,
                'reviewed_at': None,
                'reviewed_by': None,
                'notes': data.get('notes', 'Reset to pending')
            }
        else:
            update_data = {
                'status': status,
                'reviewed_at': datetime.datetime.utcnow().isoformat(),
                'reviewed_by': admin_id
            }
            if 'notes' in data:
                update_data['notes'] = data['notes']
        
        # Update the request
        update_response = client.from_("requests")\
            .update(update_data)\
            .eq('id', request_id)\
            .execute()
        
        if not update_response.data:
            return jsonify({"success": False, "error": "Failed to update request"}), 500
        
        # Handle enrollments and invoices based on status changes
        invoice_created = False
        invoice_deleted = False
        
        if status == 'approved':
            # Check if enrollment exists
            existing_enrollment = client.from_("enrollments")\
                .select('*')\
                .eq('user_id', user_id)\
                .eq('course_id', course_id)\
                .execute()
            
            if not existing_enrollment.data:
                # Create new enrollment
                client.from_("enrollments")\
                    .insert({
                        'user_id': user_id,
                        'course_id': course_id,
                        'active': True,
                        'enrolled_at': datetime.datetime.utcnow().isoformat()
                    })\
                    .execute()
            else:
                # Update existing enrollment to active
                client.from_("enrollments")\
                    .update({'active': True})\
                    .eq('user_id', user_id)\
                    .eq('course_id', course_id)\
                    .execute()
            
            # Create invoice if doesn't exist
            invoice_check = client.from_("invoices")\
                .select("id")\
                .eq("user_id", user_id)\
                .ilike("description", f"%{course_data.get('title', '')}%")\
                .execute()
            
            if not invoice_check.data:
                invoice_result = create_invoice_for_student(user_id, course_data, student_data)
                if invoice_result:
                    invoice_created = True
        
        elif status == 'pending' and previous_status == 'approved':
            # Delete invoice when resetting from approved to pending
            invoice_check = client.from_("invoices")\
                .select("id")\
                .eq("user_id", user_id)\
                .ilike("description", f"%{course_data.get('title', '')}%")\
                .execute()
            
            if invoice_check.data:
                for invoice in invoice_check.data:
                    client.from_("invoices")\
                        .delete()\
                        .eq("id", invoice['id'])\
                        .execute()
                    invoice_deleted = True
            
            # Deactivate enrollment
            client.from_("enrollments")\
                .update({'active': False})\
                .eq('user_id', user_id)\
                .eq('course_id', course_id)\
                .execute()
        
        elif previous_status == 'approved' and status == 'declined':
            # Delete invoice when changing from approved to declined
            invoice_check = client.from_("invoices")\
                .select("id")\
                .eq("user_id", user_id)\
                .ilike("description", f"%{course_data.get('title', '')}%")\
                .execute()
            
            if invoice_check.data:
                for invoice in invoice_check.data:
                    client.from_("invoices")\
                        .delete()\
                        .eq("id", invoice['id'])\
                        .execute()
                    invoice_deleted = True
            
            # Deactivate enrollment
            client.from_("enrollments")\
                .update({'active': False})\
                .eq('user_id', user_id)\
                .eq('course_id', course_id)\
                .execute()
        
        return jsonify({
            "success": True,
            "message": f"Request {status} successfully",
            "status": status,
            "invoice_created": invoice_created,
            "invoice_deleted": invoice_deleted
        })
        
    except Exception as e:
        print(f"Error updating request status: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------- 4. BULK ACTIONS --------------------
@requests_bp.route("/admin/requests/bulk-action", methods=["POST"])
@admin_login_required
def bulk_action():
    """Handle bulk approve/decline actions"""
    try:
        client = get_admin_client()
        data = request.get_json()
        action = data.get('action')
        request_ids = data.get('request_ids', [])
        admin_id = session.get('admin_id')
        
        if action not in ['approve', 'decline']:
            return jsonify({"success": False, "error": "Invalid action"}), 400
        
        if not request_ids:
            return jsonify({"success": False, "error": "No requests selected"}), 400
        
        status = 'approved' if action == 'approve' else 'declined'
        invoices_created = 0
        processed = 0
        
        # Get all request data in one query
        requests_data = client.from_("requests")\
            .select('''
                *,
                students (id, full_name, email, cpa_level),
                courses (id, title, fees, cpa_level)
            ''')\
            .in_('id', request_ids)\
            .execute()
        
        if not requests_data.data:
            return jsonify({"success": False, "error": "No valid requests found"}), 404
        
        for request_data in requests_data.data:
            user_id = request_data['user_id']
            course_id = request_data['course_id']
            student_data = request_data.get('students', {})
            course_data = request_data.get('courses', {})
            
            # Update request status
            client.from_("requests")\
                .update({
                    'status': status,
                    'reviewed_at': datetime.datetime.utcnow().isoformat(),
                    'reviewed_by': admin_id
                })\
                .eq('id', request_data['id'])\
                .execute()
            
            # If approved, create enrollment and invoice
            if action == 'approve':
                # Check if enrollment exists
                existing = client.from_("enrollments")\
                    .select('id')\
                    .eq('user_id', user_id)\
                    .eq('course_id', course_id)\
                    .execute()
                
                if not existing.data:
                    client.from_("enrollments")\
                        .insert({
                            'user_id': user_id,
                            'course_id': course_id,
                            'active': True,
                            'enrolled_at': datetime.datetime.utcnow().isoformat()
                        })\
                        .execute()
                
                # Create invoice
                invoice_check = client.from_("invoices")\
                    .select("id")\
                    .eq("user_id", user_id)\
                    .ilike("description", f"%{course_data.get('title', '')}%")\
                    .execute()
                
                if not invoice_check.data:
                    invoice_result = create_invoice_for_student(user_id, course_data, student_data)
                    if invoice_result:
                        invoices_created += 1
            
            processed += 1
        
        return jsonify({
            "success": True,
            "message": f"Successfully {action}d {processed} requests",
            "invoices_created": invoices_created,
            "processed": processed
        })
        
    except Exception as e:
        print(f"Error in bulk action: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------- 5. GET REQUEST STATS --------------------
@requests_bp.route("/admin/requests/stats")
@admin_login_required
def get_request_stats():
    """Get statistics for requests"""
    try:
        client = get_admin_client()
        
        # Get all requests and count manually
        response = client.from_("requests")\
            .select('id, status')\
            .execute()
        
        stats = {
            'total': 0,
            'pending': 0,
            'approved': 0,
            'declined': 0
        }
        
        if response.data:
            for request in response.data:
                status = request.get('status', 'pending')
                stats['total'] += 1
                if status in stats:
                    stats[status] += 1
        
        return jsonify(stats)
        
    except Exception as e:
        print(f"Error fetching request stats: {e}")
        return jsonify({"error": str(e)}), 500