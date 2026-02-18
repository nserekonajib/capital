# routes/payments.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash
import os
import json
import uuid
from datetime import datetime
from routes.pesapal import PesaPal
from routes.config import Config
from routes.auth import login_required
from routes.utils import supabase  # Your Supabase client
import logging

logger = logging.getLogger(__name__)

payments_bp = Blueprint("payments", __name__)

# Directory to store payment sessions (temporary until callback)
# Directory to store payment sessions (temporary until callback)
PAYMENT_SESSIONS_DIR = "payment_sessions"

# Ensure directory exists
if not os.path.exists(PAYMENT_SESSIONS_DIR):
    os.makedirs(PAYMENT_SESSIONS_DIR)

def get_student_invoices_and_payments(user_id):
    """Get student's invoices and payment summary"""
    try:
        print(f"🔍 DEBUG: Fetching invoices for user_id: {user_id}")
        
        # First try to get invoices with course information using course_id
        try:
            invoices_res = supabase.table('invoices')\
                .select('''
                    *,
                    courses (title, instructor, thumbnail)
                ''')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .execute()
            
            print("🔍 DEBUG: Successfully fetched invoices with courses relation")
            has_course_info = True
            
        except Exception as relation_error:
            print(f"🔍 DEBUG: No courses relation, falling back to basic query: {relation_error}")
            has_course_info = False
            
            # Fallback: get invoices without course relation
            invoices_res = supabase.table('invoices')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .execute()
        
        print(f"🔍 DEBUG: Found {len(invoices_res.data) if invoices_res.data else 0} invoices")
        
        invoices = []
        total_invoice_amount = 0
        total_balance = 0
        
        if invoices_res.data:
            for invoice in invoices_res.data:
                if has_course_info and invoice.get('courses'):
                    # With course relation
                    course_data = invoice.get('courses', {})
                    course_title = course_data.get('title', 'Unknown Course')
                    course_instructor = course_data.get('instructor', 'N/A')
                    course_thumbnail = course_data.get('thumbnail')
                else:
                    # Without course relation - extract from description
                    description = invoice.get('description', '')
                    course_title = 'Unknown Course'
                    course_instructor = 'N/A'
                    course_thumbnail = None
                    
                    # Try to extract course title from description
                    if 'Tuition for' in description:
                        try:
                            course_title = description.split('Tuition for ')[1].split(' - CPA Level')[0]
                        except:
                            course_title = 'Course'
                
                invoice_data = {
                    'id': invoice['id'],
                    'invoice_number': invoice['invoice_number'],
                    'amount': float(invoice['amount']),
                    'balance': float(invoice['balance']),
                    'status': invoice['status'],
                    'due_date': invoice['due_date'],
                    'description': invoice.get('description', ''),
                    'created_at': invoice['created_at'],
                    'course_title': course_title,
                    'course_instructor': course_instructor,
                    'course_thumbnail': course_thumbnail,
                    'course_id': invoice.get('course_id')  # Include course_id for reference
                }
                invoices.append(invoice_data)
                total_invoice_amount += float(invoice['amount'])
                total_balance += float(invoice['balance'])
        
        # Get payment summary
        payments_res = supabase.table('payments')\
            .select('amount, status, created_at, invoice_id')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .execute()
        
        total_paid = 0
        payment_history = []
        if payments_res.data:
            for payment in payments_res.data:
                if payment['status'] in ['completed', 'COMPLETED', '200']:
                    total_paid += float(payment['amount'])
                payment_history.append(payment)
        
        overall_balance = max(0, total_balance)
        
        result = {
        'invoices': invoices,
        'total_invoice_amount': total_invoice_amount,
        'total_paid': total_paid,
        'overall_balance': overall_balance,
        'payment_history': payment_history[:10],
        'unpaid_invoices': [inv for inv in invoices if inv['balance'] > 0],
        'paid_invoices': [inv for inv in invoices if inv['balance'] == 0]
    }
        
        print(f"🔍 DEBUG: Final result - {len(invoices)} invoices, {len(result['unpaid_invoices'])} unpaid")
        
        return result
        
    except Exception as e:
        print(f"❌ ERROR in get_student_invoices_and_payments: {e}")
        import traceback
        print(f"❌ TRACEBACK: {traceback.format_exc()}")
        return {
            'invoices': [],
            'total_invoice_amount': 0,
            'total_paid': 0,
            'overall_balance': 0,
            'payment_history': [],
            'unpaid_invoices': [],
            'paid_invoices': []
        }
        
def normalize_payment_status(payment_status_response):
    """Normalize payment status from PesaPal response"""
    if not payment_status_response:
        return 'failed'
    
    # Log the full response for debugging
    logger.info(f"🔍 Full response for normalization: {payment_status_response}")
    
    # Check payment_status_description first (most reliable)
    payment_status_desc = payment_status_response.get('payment_status_description', '').upper()
    status_code = payment_status_response.get('status_code')
    raw_status = payment_status_response.get('status', '')
    
    logger.info(f"🔍 Status fields - Description: {payment_status_desc}, Code: {status_code}, Raw: {raw_status}")
    
    # Priority 1: Check payment_status_description
    if 'FAILED' in payment_status_desc:
        return 'failed'
    elif 'COMPLETED' in payment_status_desc or 'SUCCESS' in payment_status_desc:
        return 'completed'
    elif 'PENDING' in payment_status_desc:
        return 'pending'
    
    # Priority 2: Check status_code (numeric)
    if status_code == 1:
        return 'completed'
    elif status_code == 2:
        return 'failed'
    elif status_code == 0:
        return 'pending'
    
    # Priority 3: Check raw status field (but be careful with HTTP status codes)
    status_str = str(raw_status).upper().strip()
    if status_str in ['200', 'COMPLETED', 'SUCCESS']:
        return 'completed'
    elif status_str in ['201', 'PENDING']:
        return 'pending'
    elif status_str in ['FAILED', 'ERROR']:
        return 'failed'
    
    # Default to failed if we can't determine
    logger.warning(f"⚠️ Could not determine payment status from response")
    return 'failed'

def cleanup_payment_file(order_tracking_id):
    """Delete JSON payment file after processing"""
    try:
        for filename in os.listdir(PAYMENT_SESSIONS_DIR):
            if filename.endswith('.json'):
                file_path = os.path.join(PAYMENT_SESSIONS_DIR, filename)
                try:
                    with open(file_path, 'r') as f:
                        payment_data = json.load(f)
                    
                    if payment_data.get('order_tracking_id') == order_tracking_id:
                        os.remove(file_path)
                        logger.info(f"🗑️ Deleted payment file: {filename}")
                        return True
                except Exception as e:
                    logger.error(f"Error reading/removing payment file {filename}: {e}")
                    # Try to remove the file anyway
                    try:
                        os.remove(file_path)
                    except:
                        pass
        return False
    except Exception as e:
        logger.error(f"Error in cleanup_payment_file: {e}")
        return False

def update_invoice_balance(invoice_id, payment_amount):
    """Update invoice balance after successful payment"""
    try:
        # Get current invoice
        invoice_res = supabase.table('invoices')\
            .select('balance, amount')\
            .eq('id', invoice_id)\
            .single()\
            .execute()
        
        if invoice_res.data:
            current_balance = float(invoice_res.data['balance'])
            new_balance = max(0, current_balance - float(payment_amount))
            
            update_data = {
                'balance': new_balance,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            # If balance is 0, mark as paid
            if new_balance == 0:
                update_data['status'] = 'paid'
            
            # Update invoice
            supabase.table('invoices')\
                .update(update_data)\
                .eq('id', invoice_id)\
                .execute()
            
            logger.info(f"💰 Updated invoice {invoice_id} balance: {current_balance} -> {new_balance}")
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error updating invoice balance: {e}")
        return False

@payments_bp.route("/student/payments", methods=["GET"])
@login_required
def student_payments():
    """Render student payments page with dashboard"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in to access payments', 'warning')
            return redirect(url_for('auth.login'))
        
        # Get student data for the template
        student_data = get_student_invoices_and_payments(user_id)
        
        return render_template("student/payments.html", **student_data)
        
    except Exception as e:
        logger.error(f"Error in student_payments: {e}")
        flash('Error loading payment dashboard', 'error')
        return render_template("student/payments.html", 
                             invoices=[], 
                             total_invoice_amount=0, 
                             total_paid=0, 
                             overall_balance=0, 
                             payment_history=[],
                             unpaid_invoices=[],
                             paid_invoices=[])

@payments_bp.route("/student/payments/initiate", methods=["POST"])
@login_required
def initiate_payment():
    """Handle PesaPal payment initiation with invoice linking"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "Please log in first"}), 401

        data = request.get_json()
        amount = data.get("amount")
        email = data.get("email", "")
        full_name = data.get("full_name", "")
        invoice_id = data.get("invoice_id")  # New: specific invoice to pay

        if not amount or float(amount) <= 0:
            return jsonify({"success": False, "message": "Invalid payment amount"}), 400

        # Use session data if not provided
        if not email:
            email = session.get('user_email', '')
        if not full_name:
            full_name = session.get('user_full_name', 'Student')

        # Validate invoice if provided
        if invoice_id:
            invoice_res = supabase.table('invoices')\
                .select('id, balance, user_id')\
                .eq('id', invoice_id)\
                .eq('user_id', user_id)\
                .single()\
                .execute()
            
            if not invoice_res.data:
                return jsonify({"success": False, "message": "Invalid invoice"}), 400
            
            invoice_balance = float(invoice_res.data['balance'])
            if float(amount) > invoice_balance:
                return jsonify({
                    "success": False, 
                    "message": f"Payment amount (UGX {amount}) exceeds invoice balance (UGX {invoice_balance})"
                }), 400

        # Generate unique references
        temp_id = str(uuid.uuid4())
        reference_id = f"TXN-{temp_id[:8].upper()}"
        
        # Prepare student info
        names = full_name.split()
        first_name = names[0] if names else "Student"
        last_name = names[-1] if len(names) > 1 else "User"

        # Initialize PesaPal
        pesapal = PesaPal()
        
        # Get callback URL
        callback_url = url_for('payments.payment_callback', _external=True)
        
        logger.info(f"🔄 Initiating PesaPal payment: UGX {amount} for {full_name}, Invoice: {invoice_id}")

        # Submit order to PesaPal
        order = pesapal.submit_order(
            amount=float(amount),
            reference_id=reference_id,
            callback_url=callback_url,
            email=email,
            first_name=first_name,
            last_name=last_name
        )

        if order and 'redirect_url' in order:
            # Save payment to database with invoice link
            payment_data = {
                "user_id": user_id,
                "order_tracking_id": order['order_tracking_id'],
                "reference_id": reference_id,
                "amount": float(amount),
                "full_name": full_name,
                "email": email,
                "status": "pending",
                "invoice_id": invoice_id,  # Link to specific invoice
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Insert into database
            db_response = supabase.table("payments").insert(payment_data).execute()
            
            if not db_response.data:
                logger.error("❌ Failed to save payment to database")
                return jsonify({
                    "success": False, 
                    "message": "Failed to save payment record"
                }), 500

            # Also save to JSON file as backup (temporary)
            backup_data = {
                **payment_data,
                "temp_id": temp_id,
                "db_id": db_response.data[0]['id'] if db_response.data else None
            }
            
            payment_file_path = os.path.join(PAYMENT_SESSIONS_DIR, f"{temp_id}.json")
            with open(payment_file_path, "w") as f:
                json.dump(backup_data, f, indent=2)

            logger.info(f"✅ Payment initiated successfully. Order ID: {order['order_tracking_id']}, Invoice: {invoice_id}")
            
            return jsonify({
                "success": True, 
                "message": "Payment initiated successfully",
                "redirect_url": order['redirect_url'],
                "order_id": order['order_tracking_id']
            })
        else:
            logger.error("❌ Failed to initiate payment with PesaPal")
            return jsonify({
                "success": False, 
                "message": "Failed to initiate payment. Please try again."
            }), 500

    except Exception as e:
        logger.error(f"❌ Payment initiation error: {e}")
        return jsonify({
            "success": False, 
            "message": f"Error processing payment: {str(e)}"
        }), 500

@payments_bp.route("/student/payments/callback", methods=["GET", "POST"])
@login_required
def payment_callback():
    """Handle PesaPal payment callback with invoice updates"""
    try:
        # Get callback parameters
        order_tracking_id = request.args.get('OrderTrackingId')
        order_merchant_reference = request.args.get('OrderMerchantReference')
        
        logger.info(f"🔄 Payment callback received - Order: {order_tracking_id}, Ref: {order_merchant_reference}")

        if not order_tracking_id:
            flash("Invalid payment callback", "error")
            return redirect(url_for('payments.student_payments'))

        # Get payment record from database
        payment_res = supabase.table("payments")\
            .select("*")\
            .eq("order_tracking_id", order_tracking_id)\
            .single()\
            .execute()
        
        if not payment_res.data:
            flash("Payment record not found", "error")
            return redirect(url_for('payments.student_payments'))

        payment_data = payment_res.data
        user_id = payment_data['user_id']
        amount = payment_data['amount']
        invoice_id = payment_data.get('invoice_id')

        # Verify payment status with PesaPal
        pesapal = PesaPal()
        payment_status_response = pesapal.verify_transaction_status(order_tracking_id)

        if payment_status_response:
            # Log the full response for debugging
            logger.info(f"📄 Full PesaPal response: {payment_status_response}")
            
            # Extract payment method
            payment_method = payment_status_response.get('payment_method', 'Unknown')
            
            # Normalize the status using the full response
            normalized_status = normalize_payment_status(payment_status_response)
            
            logger.info(f"📊 Final Normalized Status: {normalized_status}, Method: {payment_method}")

            # Update payment in database
            update_data = {
                "status": normalized_status,
                "payment_method": payment_method,
                "updated_at": datetime.utcnow().isoformat(),
                "pesapal_response": payment_status_response
            }
            
            # Process completed payments
            if normalized_status == 'completed':
                update_data["completed_at"] = datetime.utcnow().isoformat()
                
                # Update invoice balance if payment is linked to an invoice
                if invoice_id:
                    invoice_updated = update_invoice_balance(invoice_id, amount)
                    if invoice_updated:
                        logger.info(f"✅ Invoice {invoice_id} updated with payment UGX {amount}")
                    else:
                        logger.error(f"❌ Failed to update invoice {invoice_id}")
                
                # Update student's total payments
                student_res = supabase.table("students")\
                    .select("total_payments")\
                    .eq("id", user_id)\
                    .single()\
                    .execute()
                
                current_total = 0
                if student_res.data and student_res.data.get('total_payments'):
                    current_total = float(student_res.data['total_payments'])
                
                new_total = current_total + float(amount)
                
                # Update student record
                update_result = supabase.table("students")\
                    .update({
                        "total_payments": new_total,
                        "last_payment_date": datetime.utcnow().isoformat()
                    })\
                    .eq("id", user_id)\
                    .execute()
                
                if update_result.data:
                    logger.info(f"💰 Updated student total_payments to: {new_total}")
                else:
                    logger.error("❌ Failed to update student total_payments")
            else:
                logger.info(f"🔄 Payment not completed, status: {normalized_status}. Skipping updates.")

            # Update payment record
            db_response = supabase.table("payments")\
                .update(update_data)\
                .eq("order_tracking_id", order_tracking_id)\
                .execute()

            if db_response.data:
                logger.info(f"✅ Payment record updated in database: {normalized_status}")
            else:
                logger.error("❌ Failed to update payment record in database")

            # Show appropriate message to user
            if normalized_status == 'completed':
                if invoice_id:
                    flash(f"Payment completed successfully! Invoice balance updated.", "success")
                else:
                    flash("Payment completed successfully! Thank you for your payment.", "success")
            elif normalized_status == 'pending':
                flash("Payment is pending confirmation. Please wait for confirmation.", "info")
            elif normalized_status == 'failed':
                flash("Payment failed. Please try again.", "error")
            else:
                flash(f"Payment status: {normalized_status}", "info")
                
        else:
            logger.error("❌ No payment status response from PesaPal")
            flash("Unable to verify payment status. Please contact support.", "warning")

        # Clean up JSON file regardless of payment status
        cleanup_payment_file(order_tracking_id)
        
        return redirect(url_for('payments.student_payments'))

    except Exception as e:
        logger.error(f"❌ Payment callback error: {e}")
        flash("Error processing payment callback", "error")
        # Clean up JSON file even on error
        try:
            order_tracking_id = request.args.get('OrderTrackingId')
            if order_tracking_id:
                cleanup_payment_file(order_tracking_id)
        except:
            pass
        return redirect(url_for('payments.student_payments'))

@payments_bp.route("/student/payments/invoices", methods=["GET"])
@login_required
def get_invoices():
    """Get student's invoices for payment selection"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        invoices_res = supabase.table('invoices')\
            .select('''
                id,
                invoice_number,
                amount,
                balance,
                status,
                due_date,
                description,
                courses (title, instructor)
            ''')\
            .eq('user_id', user_id)\
            .eq('status', 'unpaid')\
            .order('created_at', desc=True)\
            .execute()
        
        invoices = invoices_res.data if invoices_res.data else []
        
        return jsonify({
            "success": True,
            "invoices": invoices
        })
    except Exception as e:
        logger.error(f"Error fetching invoices: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ... keep the other routes (pa
    

@payments_bp.route("/student/payments/status/<order_id>", methods=["GET"])
@login_required
def payment_status(order_id):
    """Check payment status"""
    try:
        pesapal = PesaPal()
        status_response = pesapal.verify_transaction_status(order_id)
        
        if status_response:
            raw_status = status_response.get('status', 'PENDING')
            normalized_status = normalize_payment_status(raw_status)
            
            return jsonify({
                "success": True,
                "status": normalized_status,
                "raw_response": status_response
            })
        else:
            return jsonify({
                "success": False,
                "error": "Could not verify payment status"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@payments_bp.route("/student/payments/history", methods=["GET"])
@login_required
def payment_history():
    """Get payment history for current student"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        payments_res = supabase.table("payments")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .execute()
        
        payments = payments_res.data if payments_res.data else []
        
        return jsonify({
            "success": True,
            "payments": payments
        })
    except Exception as e:
        logger.error(f"Error fetching payment history: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@payments_bp.route("/student/payments/summary", methods=["GET"])
@login_required
def payment_summary():
    """Get payment summary for dashboard"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        summary = get_student_invoices_and_payments(user_id)
        
        return jsonify({
            "success": True,
            "data": summary
        })
    except Exception as e:
        logger.error(f"Error fetching payment summary: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Add a cleanup route for old JSON files (optional maintenance)
@payments_bp.route("/student/payments/cleanup", methods=["POST"])
@login_required
def cleanup_old_files():
    """Clean up old payment JSON files (admin/maintenance)"""
    try:
        deleted_count = 0
        for filename in os.listdir(PAYMENT_SESSIONS_DIR):
            if filename.endswith('.json'):
                file_path = os.path.join(PAYMENT_SESSIONS_DIR, filename)
                try:
                    # Delete files older than 24 hours
                    file_time = os.path.getmtime(file_path)
                    if (datetime.now().timestamp() - file_time) > 86400:  # 24 hours
                        os.remove(file_path)
                        deleted_count += 1
                        logger.info(f"🗑️ Cleaned up old file: {filename}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {filename}: {e}")
        
        return jsonify({
            "success": True,
            "message": f"Cleaned up {deleted_count} old payment files"
        })
    except Exception as e:
        logger.error(f"Error in cleanup_old_files: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500