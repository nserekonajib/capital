from flask import Blueprint, flash, redirect, render_template, request, jsonify, session, url_for
from datetime import datetime, timedelta
import logging
import pandas as pd

import os
import tempfile
import uuid
from supabase import Client

# Define a custom `desc` function if not available in the library
def desc(column_name):
    return {"column": column_name, "order": "desc"}
from routes.adminauth import admin_login_required
from routes.admin_utils import get_admin_client
from routes.library_utils import upload_excel

logger = logging.getLogger(__name__)

admin_payments_bp = Blueprint("admin_payments", __name__)

def get_payments_summary(time_frame=None):
    """Get payments summary for admin dashboard"""
    try:
        supabase = get_admin_client()
        
        # Build query based on time frame
        query = supabase.table('payments').select('*')
        
        if time_frame and time_frame != 'all':
            if time_frame == 'today':
                start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            elif time_frame == 'week':
                start_date = datetime.now() - timedelta(days=7)
            elif time_frame == 'month':
                start_date = datetime.now() - timedelta(days=30)
            else:
                start_date = datetime.now() - timedelta(days=365)
            
            query = query.gte('created_at', start_date.isoformat())
        
        payments_res = query.execute()
        payments = payments_res.data if payments_res.data else []
        
        # Calculate summary statistics
        total_transactions = len(payments)
        successful_transactions = len([p for p in payments if p.get('status') in ['completed', 'COMPLETED', '200']])
        total_revenue = sum(float(p['amount']) for p in payments if p.get('status') in ['completed', 'COMPLETED', '200'])
        
        # Get total invoice amount
        invoices_query = supabase.table('invoices').select('amount, status')
        if time_frame and time_frame != 'all':
            invoices_query = invoices_query.gte('created_at', start_date.isoformat())
        
        invoices_res = invoices_query.execute()
        invoices = invoices_res.data if invoices_res.data else []
        total_invoice_amount = sum(float(inv['amount']) for inv in invoices)
        
        return {
            'total_transactions': total_transactions,
            'successful_transactions': successful_transactions,
            'total_revenue': total_revenue,
            'total_invoice_amount': total_invoice_amount,
            'success_rate': (successful_transactions / total_transactions * 100) if total_transactions > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting payments summary: {e}")
        return {
            'total_transactions': 0,
            'successful_transactions': 0,
            'total_revenue': 0,
            'total_invoice_amount': 0,
            'success_rate': 0
        }

def get_payments_with_students(filters=None):
    """Get payments with student information"""
    try:
        supabase = get_admin_client()
        
        # Build query - by default show all payments
        query = supabase.table('payments')\
            .select('''
                *,
                students!inner(full_name, email, cpa_level, phone_number),
                invoices(invoice_number, description)
            ''')\
            .order('created_at', desc=True)
        
        # Apply filters if provided
        if filters:
            status = filters.get('status')
            if status and status != 'all':
                # Normalize status for query
                if status == 'completed':
                    status_query = ['completed', 'COMPLETED', '200']
                elif status == 'pending':
                    status_query = ['pending', 'PENDING']
                elif status == 'failed':
                    status_query = ['failed', 'FAILED', 'error']
                else:
                    status_query = [status]
                
                query = query.in_('status', status_query)
            
            payment_method = filters.get('payment_method')
            if payment_method and payment_method != 'all':
                query = query.eq('payment_method', payment_method)
            
            start_date = filters.get('start_date')
            end_date = filters.get('end_date')
            if start_date:
                query = query.gte('created_at', start_date)
            if end_date:
                # Add one day to include the end date fully
                end_date_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00')) + timedelta(days=1)
                query = query.lt('created_at', end_date_dt.isoformat())
            
            search = filters.get('search')
            if search:
                # Search in student name, reference ID, or order tracking ID
                query = query.or_(f"students.full_name.ilike.%{search}%,reference_id.ilike.%{search}%,order_tracking_id.ilike.%{search}%")
        
        payments_res = query.execute()
        logger.info(f"🔍 DEBUG: Fetched {len(payments_res.data) if payments_res.data else 0} payments")
        
        if not payments_res.data:
            return []
        
        # Format the data for display
        formatted_payments = []
        for payment in payments_res.data:
            student_info = payment.get('students', {})
            
            # Handle invoices - could be list or single object
            invoice_info = {}
            if payment.get('invoices'):
                if isinstance(payment['invoices'], list) and len(payment['invoices']) > 0:
                    invoice_info = payment['invoices'][0]
                elif isinstance(payment['invoices'], dict):
                    invoice_info = payment['invoices']
            
            # Normalize payment status for display
            status = payment.get('status', '').lower()
            if status in ['completed', 'complete', '200', 'success']:
                display_status = 'completed'
            elif status in ['pending', 'pending_confirmation']:
                display_status = 'pending'
            elif status in ['failed', 'error', 'cancelled']:
                display_status = 'failed'
            else:
                display_status = status
            
            formatted_payment = {
                'id': payment['id'],
                'reference_id': payment.get('reference_id', 'N/A'),
                'order_tracking_id': payment.get('order_tracking_id', 'N/A'),
                'student_name': student_info.get('full_name', 'N/A'),
                'student_email': student_info.get('email', 'N/A'),
                'cpa_level': student_info.get('cpa_level', 'N/A'),
                'phone_number': student_info.get('phone_number', 'N/A'),
                'amount': float(payment.get('amount', 0)),
                'currency': payment.get('currency', 'UGX'),
                'status': display_status,
                'payment_method': payment.get('payment_method', 'Unknown'),
                'created_at': payment.get('created_at', ''),
                'completed_at': payment.get('completed_at'),
                'invoice_number': invoice_info.get('invoice_number', 'N/A'),
                'invoice_description': invoice_info.get('description', '')
            }
            formatted_payments.append(formatted_payment)
        
        logger.info(f"✅ DEBUG: Successfully formatted {len(formatted_payments)} payments")
        return formatted_payments
        
    except Exception as e:
        logger.error(f"❌ ERROR getting payments with students: {str(e)}")
        import traceback
        logger.error(f"❌ TRACEBACK: {traceback.format_exc()}")
        return []

def get_payment_analytics(time_frame='month'):
    """Get payment analytics for charts"""
    try:
        supabase = get_admin_client()
        
        # Determine date range
        if time_frame == 'week':
            days = 7
        elif time_frame == 'month':
            days = 30
        else:  # year
            days = 365
            
        start_date = datetime.now() - timedelta(days=days)
        
        # Get payment data
        payments_res = supabase.table('payments')\
            .select('amount, status, created_at, payment_method')\
            .gte('created_at', start_date.isoformat())\
            .execute()
        
        payments = payments_res.data if payments_res.data else []
        
        # Process data for charts
        daily_data = {}
        status_data = {'completed': 0, 'pending': 0, 'failed': 0}
        method_data = {}
        
        for payment in payments:
            # Daily data
            try:
                payment_date = datetime.fromisoformat(payment['created_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d')
                if payment_date not in daily_data:
                    daily_data[payment_date] = {'completed': 0, 'total': 0}
                
                amount = float(payment['amount'])
                daily_data[payment_date]['total'] += amount
                
                # Normalize status for counting
                status = payment.get('status', '').lower()
                if status in ['completed', 'complete', '200', 'success']:
                    daily_data[payment_date]['completed'] += amount
                    status_data['completed'] += 1
                elif status in ['pending', 'pending_confirmation']:
                    status_data['pending'] += 1
                elif status in ['failed', 'error', 'cancelled']:
                    status_data['failed'] += 1
                else:
                    status_data['pending'] += 1
                
                # Payment method data
                method = payment.get('payment_method', 'Unknown')
                method_data[method] = method_data.get(method, 0) + 1
            except Exception as e:
                logger.error(f"Error processing payment data: {e}")
                continue
        
        # Format for charts - ensure we have data for all days in range
        dates = []
        current_date = start_date
        while current_date <= datetime.now():
            date_str = current_date.strftime('%Y-%m-%d')
            dates.append(date_str)
            if date_str not in daily_data:
                daily_data[date_str] = {'completed': 0, 'total': 0}
            current_date += timedelta(days=1)
        
        revenue_data = [daily_data[date]['completed'] for date in dates[-30:]]  # Last 30 days
        transaction_data = [daily_data[date]['total'] for date in dates[-30:]]
        
        return {
            'dates': dates[-30:],  # Last 30 days
            'revenue_data': revenue_data,
            'transaction_data': transaction_data,
            'status_distribution': status_data,
            'method_distribution': method_data
        }
        
    except Exception as e:
        logger.error(f"Error getting payment analytics: {e}")
        return {
            'dates': [],
            'revenue_data': [],
            'transaction_data': [],
            'status_distribution': {'completed': 0, 'pending': 0, 'failed': 0},
            'method_distribution': {}
        }

@admin_payments_bp.route("/admin/payments", methods=["GET"])
@admin_login_required
def admin_payments_dashboard():
    """Admin payments dashboard - shows all transactions by default"""
    try:
        # Get filters from request
        time_frame = request.args.get('time_frame', 'all')
        status_filter = request.args.get('status', 'all')
        payment_method_filter = request.args.get('payment_method', 'all')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search', '')
        
        filters = {
            'status': status_filter,
            'payment_method': payment_method_filter,
            'start_date': start_date,
            'end_date': end_date,
            'search': search
        }
        
        logger.info(f"🔍 DEBUG: Fetching data with filters: {filters}")
        
        # Get data
        summary = get_payments_summary(time_frame)
        payments = get_payments_with_students(filters)
        analytics = get_payment_analytics('month')
        
        logger.info(f"✅ DEBUG: Loaded {len(payments)} payments for display")
        
        return render_template(
            "admin/admin_payments.html",
            summary=summary,
            payments=payments,
            analytics=analytics,
            filters=filters,
            time_frame=time_frame
        )
        
    except Exception as e:
        logger.error(f"❌ ERROR in admin payments dashboard: {e}")
        import traceback
        logger.error(f"❌ TRACEBACK: {traceback.format_exc()}")
        # Return empty data on error
        return render_template(
            "admin/admin_payments.html",
            summary={
                'total_transactions': 0,
                'successful_transactions': 0,
                'total_revenue': 0,
                'total_invoice_amount': 0,
                'success_rate': 0
            },
            payments=[],
            analytics={
                'dates': [],
                'revenue_data': [],
                'transaction_data': [],
                'status_distribution': {'completed': 0, 'pending': 0, 'failed': 0},
                'method_distribution': {}
            },
            filters={},
            time_frame='all'
        )
@admin_payments_bp.route("/payments/cash/submit", methods=["POST"])
@admin_login_required
def submit_cash_payment():
    """
    Admin-side: Record a cash payment for a student's invoice.
    Automatically updates invoice balance and payment records.
    """
    admin_supabase = get_admin_client()

    try:
        data = request.get_json(silent=True) or {}
        student_id = data.get("student_id")
        invoice_id = data.get("invoice_id")
        amount = float(data.get("amount", 0))

        # ✅ Validate inputs
        if not student_id or not invoice_id or amount <= 0:
            return jsonify({
                "success": False,
                "message": "Missing or invalid fields. Ensure student_id, invoice_id, and amount are provided."
            }), 400

        # ✅ Fetch invoice details
        invoice_res = (
            admin_supabase.table("invoices")
            .select("id, balance, amount")
            .eq("id", invoice_id)
            .single()
            .execute()
        )

        if not invoice_res.data:
            return jsonify({"success": False, "message": "Invoice not found."}), 404

        current_balance = float(invoice_res.data.get("balance", 0))
        if amount > current_balance:
            return jsonify({
                "success": False,
                "message": f"Payment amount UGX {amount:,.0f} exceeds invoice balance UGX {current_balance:,.0f}"
            }), 400

        # ✅ Compute new invoice status
        new_balance = max(0, current_balance - amount)
        invoice_status = "paid" if new_balance == 0 else "partially_paid"

        # ✅ Update invoice
        admin_supabase.table("invoices").update({
            "balance": new_balance,
            "status": invoice_status,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", invoice_id).execute()

        # ✅ Generate IDs
        order_tracking_id = f"ORD-{uuid.uuid4().hex[:10].upper()}"
        reference_id = f"REF-{uuid.uuid4().hex[:8].upper()}"

        # ✅ Fetch student's email (optional if you store in students table)
        student_data = (
            admin_supabase.table("students")
            .select("email, full_name")
            .eq("id", student_id)
            .single()
            .execute()
        )
        student_email = student_data.data.get("email") if student_data.data else "unknown@student.com"
        student_name = student_data.data.get("full_name") if student_data.data else "Unknown Student"

        # ✅ Insert payment
        payment_data = {
            "user_id": student_id,
            "invoice_id": invoice_id,
            "order_tracking_id": order_tracking_id,
            "reference_id": reference_id,
            "amount": amount,
            "currency": "UGX",
            "status": "completed",
            "payment_method": "cash",
            "full_name": student_name,
            "email": student_email,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat()
        }

        payment_res = admin_supabase.table("payments").insert(payment_data).execute()

        if not payment_res.data:
            raise Exception("Failed to record payment in Supabase.")

        return jsonify({
            "success": True,
            "message": f"✅ Cash payment of UGX {amount:,.0f} recorded successfully for {student_name}.",
            "invoice_status": invoice_status,
            "order_tracking_id": order_tracking_id
        }), 200

    except Exception as e:
        print(f"❌ Error processing cash payment: {e}")
        return jsonify({
            "success": False,
            "message": f"Error processing cash payment: {str(e)}"
        }), 500


@admin_payments_bp.route("/search_students", methods=["GET"])
@admin_login_required
def search_students():
    """Search students for cash payment"""
    try:
        search_term = request.args.get('q', '')
        logger.info(f"🔍 Searching students with term: {search_term}")
        
        supabase = get_admin_client()
        
        query = supabase.table('students').select('id, full_name, email, cpa_level, phone_number')
        
        if search_term:
            query = query.or_(f"full_name.ilike.%{search_term}%,email.ilike.%{search_term}%,phone_number.ilike.%{search_term}%")
        
        students_res = query.execute()
        logger.info(f"✅ Found {len(students_res.data) if students_res.data else 0} students")
        
        return jsonify({
            "success": True,
            "data": students_res.data if students_res.data else []
        })
        
    except Exception as e:
        logger.error(f"❌ Error searching students: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
        
@admin_payments_bp.route("/student_invoices/<int:student_id>", methods=["GET"])
@admin_login_required
def get_student_invoices(student_id):
    """Get invoices for a specific student"""
    try:
        logger.info(f"🔍 Getting invoices for student: {student_id}")
        
        supabase = get_admin_client()
        
        invoices_res = supabase.table('invoices')\
            .select('*')\
            .eq('user_id', student_id)\
            .in_('status', ['unpaid', 'pending', 'partially_paid'])\
            .order('created_at', desc=True)\
            .execute()
            
        
        
        formatted_invoices = [{
            'id': inv['id'],
            'invoice_number': inv.get('invoice_number', 'N/A'),
            'amount': float(inv.get('amount', 0)),
            'balance': float(inv.get('balance', inv.get('amount', 0))),
            'description': inv.get('description', 'No description'),
            'due_date': inv.get('due_date', 'N/A'),
            'status': inv.get('status', 'unpaid'),
            'created_at': inv.get('created_at', '')
        } for inv in invoices_res.data or []]
        
        return jsonify({"success": True, "data": formatted_invoices})
        
    except Exception as e:
        logger.error(f"❌ Error getting student invoices: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    
        
@admin_payments_bp.route("/payments/export-excel", methods=["POST"])
@admin_login_required
def export_payments_excel():
    """Export payments data to Excel and upload to Google Drive"""
    try:
        # Get filters from form data instead of JSON
        time_frame = request.form.get('time_frame', 'all')
        status_filter = request.form.get('status', 'all')
        payment_method_filter = request.form.get('payment_method', 'all')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        search = request.form.get('search', '')
        
        filters = {
            'status': status_filter,
            'payment_method': payment_method_filter,
            'start_date': start_date,
            'end_date': end_date,
            'search': search
        }
        
        logger.info(f"🔍 DEBUG: Exporting to Excel with filters: {filters}")
        
        # Get filtered payments data
        payments = get_payments_with_students(filters)
        
        if not payments:
            flash('No data to export with the current filters', 'error')
            return redirect(url_for('admin_payments.admin_payments_dashboard'))
        
        # Create DataFrame
        df_data = []
        for payment in payments:
            df_data.append({
                'Transaction Reference': payment['reference_id'],
                'Order Tracking ID': payment['order_tracking_id'],
                'Student Name': payment['student_name'],
                'Student Email': payment['student_email'],
                'CPA Level': payment['cpa_level'],
                'Phone Number': payment['phone_number'],
                'Amount (UGX)': f"{payment['amount']:.2f}",
                'Status': payment['status'].upper(),
                'Payment Method': payment['payment_method'],
                'Transaction Date': payment['created_at'][:10] if payment['created_at'] else 'N/A',
                'Completed Date': payment['completed_at'][:10] if payment['completed_at'] else 'N/A',
                'Invoice Number': payment['invoice_number'],
                'Invoice Description': payment['invoice_description']
            })
        
        df = pd.DataFrame(df_data)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
            temp_filename = tmp_file.name
        
        # Save to Excel
        with pd.ExcelWriter(temp_filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Payments', index=False)
            
            # Auto-adjust column widths
            worksheet = writer.sheets['Payments']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # Upload to Google Drive
        try:
            drive_link = upload_excel(temp_filename)
            
            # Delete temporary file
            try:
                os.unlink(temp_filename)
            except Exception as e:
                logger.warning(f"Could not delete temporary file: {e}")
            
            flash(f'Excel export completed successfully! Download link: {drive_link}', 'success')
            return redirect(url_for('admin_payments.admin_payments_dashboard', 
                                  time_frame=time_frame,
                                  status=status_filter,
                                  payment_method=payment_method_filter,
                                  start_date=start_date,
                                  end_date=end_date,
                                  search=search))
            
        except Exception as upload_error:
            # Clean up temp file on upload error
            try:
                os.unlink(temp_filename)
            except:
                pass
            raise upload_error
        
    except Exception as e:
        logger.error(f"❌ ERROR exporting payments to Excel: {str(e)}")
        flash(f'Export failed: {str(e)}', 'error')
        return redirect(url_for('admin_payments.admin_payments_dashboard'))

@admin_payments_bp.route("/admin/payments/data", methods=["GET"])
@admin_login_required
def get_payments_data():
    """API endpoint for payments data"""
    try:
        # Get filters from request
        status_filter = request.args.get('status', 'all')
        payment_method_filter = request.args.get('payment_method', 'all')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search', '')
        
        filters = {
            'status': status_filter,
            'payment_method': payment_method_filter,
            'start_date': start_date,
            'end_date': end_date,
            'search': search
        }
        
        payments = get_payments_with_students(filters)
        
        return jsonify({
            "success": True,
            "data": payments,
            "total": len(payments)
        })
        
    except Exception as e:
        logger.error(f"Error getting payments data: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@admin_payments_bp.route("/admin/payments/summary", methods=["GET"])
@admin_login_required
def get_payments_summary_api():
    """API endpoint for payments summary"""
    try:
        time_frame = request.args.get('time_frame', 'all')
        summary = get_payments_summary(time_frame)
        
        return jsonify({
            "success": True,
            "data": summary
        })
        
    except Exception as e:
        logger.error(f"Error getting payments summary: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@admin_payments_bp.route("/admin/payments/analytics", methods=["GET"])
@admin_login_required
def get_payments_analytics_api():
    """API endpoint for payment analytics"""
    try:
        time_frame = request.args.get('time_frame', 'month')
        analytics = get_payment_analytics(time_frame)
        
        return jsonify({
            "success": True,
            "data": analytics
        })
        
    except Exception as e:
        logger.error(f"Error getting payment analytics: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@admin_payments_bp.route("/admin/payments/<payment_id>/details", methods=["GET"])
@admin_login_required
def get_payment_details(payment_id):
    """Get detailed payment information"""
    try:
        supabase = get_admin_client()
        
        payment_res = supabase.table('payments')\
            .select('''
                *,
                students(*),
                invoices(*)
            ''')\
            .eq('id', payment_id)\
            .single()\
            .execute()
        
        if not payment_res.data:
            return jsonify({
                "success": False,
                "error": "Payment not found"
            }), 404
        
        return jsonify({
            "success": True,
            "data": payment_res.data
        })
        
    except Exception as e:
        logger.error(f"Error getting payment details: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
        
@admin_payments_bp.route("/admin/payments/cash", methods=["GET"])
@admin_login_required
def cash_payment_page():
    """Render admin cash payment page"""
    return render_template("admin/cash_payment.html")