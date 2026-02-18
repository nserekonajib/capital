import uuid
from flask import Blueprint, request, render_template, jsonify, session
from routes.admin_utils import admin_supabase, get_admin_client
from routes.adminauth import admin_login_required
import datetime

def create_invoice_for_student(user_id, course, student):
    """
    Auto-create an invoice when a student is enrolled or approved.
    """
    try:
        # Debug: Check what data we're receiving
        print(f"DEBUG INVOICE - Creating invoice for user {user_id}")
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
requests_bp = Blueprint("admin_requests", __name__)

# -------------------- 1. REQUESTS MANAGEMENT PAGE --------------------
@requests_bp.route("/admin/requests")
@admin_login_required
def manage_requests():
    """
    Render the requests management page
    """
    return render_template("admin/requests/manage.html")

# -------------------- 2. FETCH ALL REQUESTS --------------------
@requests_bp.route("/admin/requests/data")
@admin_login_required
def get_requests():
    """
    Fetch all course requests with student and course details
    """
    try:
        client = get_admin_client()
        
        # Get requests with student and course details
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
# -------------------- 3. UPDATE REQUEST STATUS --------------------
@requests_bp.route("/admin/requests/<int:request_id>/status", methods=["POST"])
@admin_login_required
def update_request_status(request_id):
    """
    Update request status and automatically enroll student if approved
    """
    try:
        client = get_admin_client()
        data = request.get_json()
        status = data.get('status')
        admin_id = session.get('admin_id')
        
        if status not in ['pending', 'approved', 'declined']:
            return jsonify({"success": False, "error": "Invalid status"}), 400
        
        # Get the request details first
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
        
        print(f"DEBUG REQUEST STATUS - Request: {request_id}, Status: {status}")
        print(f"DEBUG REQUEST STATUS - Previous Status: {previous_status}")
        print(f"DEBUG REQUEST STATUS - Student: {student_data.get('full_name')}")
        print(f"DEBUG REQUEST STATUS - Course: {course_data.get('title')}")
        print(f"DEBUG REQUEST STATUS - Course fees: {course_data.get('fees')}")

        # Prepare update data
        if status == 'pending':
            # For pending status, clear reviewed fields
            update_data = {
                'status': status,
                'reviewed_at': None,
                'reviewed_by': None,
                'notes': data.get('notes', 'Reset to pending')
            }
        else:
            # For approved/declined, set reviewed fields
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
            # Check if enrollment already exists
            existing_enrollment = client.from_("enrollments")\
                .select('*')\
                .eq('user_id', user_id)\
                .eq('course_id', course_id)\
                .execute()
            
            if not existing_enrollment.data:
                # Create new enrollment
                enrollment_res = client.from_("enrollments")\
                    .insert({
                        'user_id': user_id,
                        'course_id': course_id,
                        'active': True,
                        'enrolled_at': datetime.datetime.utcnow().isoformat()
                    })\
                    .execute()
                print(f"DEBUG REQUEST STATUS - New enrollment created: {enrollment_res.data}")
            else:
                # Update existing enrollment to active
                client.from_("enrollments")\
                    .update({'active': True})\
                    .eq('user_id', user_id)\
                    .eq('course_id', course_id)\
                    .execute()
                print(f"DEBUG REQUEST STATUS - Existing enrollment activated")
            
            # CREATE INVOICE FOR APPROVED REQUEST
            print("DEBUG REQUEST STATUS - Creating invoice for approved request...")
            
            # Check if invoice already exists
            invoice_check = client.from_("invoices")\
                .select("id, description, amount, status")\
                .eq("user_id", user_id)\
                .ilike("description", f"%{course_data.get('title', '')}%")\
                .execute()
            
            print(f"DEBUG REQUEST STATUS - Existing invoices found: {len(invoice_check.data) if invoice_check.data else 0}")
            
            if not invoice_check.data:
                # Create the invoice
                invoice_result = create_invoice_for_student(user_id, course_data, student_data)
                if invoice_result:
                    print("DEBUG REQUEST STATUS - Invoice created successfully")
                    invoice_created = True
                else:
                    print("DEBUG REQUEST STATUS - Invoice creation failed")
                    invoice_created = False
            else:
                print("DEBUG REQUEST STATUS - Invoice already exists, skipping creation")
                invoice_created = False
        
        elif status == 'pending' and previous_status == 'approved':
            # If resetting from approved to pending, DELETE THE INVOICE
            print("DEBUG REQUEST STATUS - Resetting from approved to pending, deleting invoice...")
            
            # Find and delete the associated invoice
            invoice_check = client.from_("invoices")\
                .select("id, description, amount, status")\
                .eq("user_id", user_id)\
                .ilike("description", f"%{course_data.get('title', '')}%")\
                .execute()
            
            if invoice_check.data:
                for invoice in invoice_check.data:
                    delete_result = client.from_("invoices")\
                        .delete()\
                        .eq("id", invoice['id'])\
                        .execute()
                    if delete_result.data:
                        print(f"DEBUG REQUEST STATUS - Invoice {invoice['id']} deleted successfully")
                        invoice_deleted = True
                    else:
                        print(f"DEBUG REQUEST STATUS - Failed to delete invoice {invoice['id']}")
            
            # Also deactivate enrollment when resetting to pending
            client.from_("enrollments")\
                .update({'active': False})\
                .eq('user_id', user_id)\
                .eq('course_id', course_id)\
                .execute()
            print(f"DEBUG REQUEST STATUS - Enrollment deactivated when reset to pending")
        
        elif previous_status == 'approved' and status != 'approved':
            # If changing from approved to declined, DELETE THE INVOICE
            print("DEBUG REQUEST STATUS - Changing from approved to declined, deleting invoice...")
            
            # Find and delete the associated invoice
            invoice_check = client.from_("invoices")\
                .select("id, description, amount, status")\
                .eq("user_id", user_id)\
                .ilike("description", f"%{course_data.get('title', '')}%")\
                .execute()
            
            if invoice_check.data:
                for invoice in invoice_check.data:
                    delete_result = client.from_("invoices")\
                        .delete()\
                        .eq("id", invoice['id'])\
                        .execute()
                    if delete_result.data:
                        print(f"DEBUG REQUEST STATUS - Invoice {invoice['id']} deleted successfully")
                        invoice_deleted = True
                    else:
                        print(f"DEBUG REQUEST STATUS - Failed to delete invoice {invoice['id']}")
            
            # Deactivate enrollment
            client.from_("enrollments")\
                .update({'active': False})\
                .eq('user_id', user_id)\
                .eq('course_id', course_id)\
                .execute()
            print(f"DEBUG REQUEST STATUS - Enrollment deactivated")
        
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
# -------------------- 4. BULK ACTIONS --------------------
@requests_bp.route("/admin/requests/bulk-action", methods=["POST"])
@admin_login_required
def bulk_action():
    """
    Handle bulk approve/decline actions
    """
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
        
       
        
        # Update all selected requests
        for request_id in request_ids:
            # Get request details first to get student and course data
            request_data = client.from_("requests")\
                .select('''
                    *,
                    students (id, full_name, email, cpa_level),
                    courses (id, title, fees, cpa_level)
                ''')\
                .eq('id', request_id)\
                .single()\
                .execute()
            
            if request_data.data:
                user_id = request_data.data['user_id']
                course_id = request_data.data['course_id']
                student_data = request_data.data.get('students', {})
                course_data = request_data.data.get('courses', {})
                
                # Update request status
                client.from_("requests")\
                    .update({
                        'status': status,
                        'reviewed_at': datetime.datetime.utcnow().isoformat(),
                        'reviewed_by': admin_id
                    })\
                    .eq('id', request_id)\
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
        
        return jsonify({
            "success": True,
            "message": f"Successfully {action}d {len(request_ids)} requests",
            "invoices_created": invoices_created
        })
        
    except Exception as e:
        print(f"Error in bulk action: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------- 5. GET REQUEST STATS --------------------
# -------------------- 5. GET REQUEST STATS --------------------
@requests_bp.route("/admin/requests/stats")
@admin_login_required
def get_request_stats():
    """
    Get statistics for requests
    """
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