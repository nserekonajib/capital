from flask import Blueprint, render_template, request, send_file, jsonify
from routes.admin_utils import get_admin_client
from routes.adminauth import admin_login_required
import pandas as pd
from io import BytesIO
from datetime import datetime

admin_reports_bp = Blueprint('admin_reports', __name__)

def get_report_data(client, filters):
    """Return list of report rows based on filters dict"""
    report_type = filters.get('report_type', 'fee_collection')
    start_date = filters.get('start_date')
    end_date = filters.get('end_date')
    status = filters.get('status')
    payment_method = filters.get('payment_method')
    class_id = filters.get('class_id')
    student_search = filters.get('student_search')

    rows = []

    try:
        if report_type == 'fee_collection':
            query = client.from_("payments").select(
                "id, user_id, invoice_id, amount, payment_method, status, created_at,"
                "invoices(amount, balance, invoice_number, due_date, course_id), students(full_name)"
            )
            if start_date:
                query = query.gte("created_at", start_date)
            if end_date:
                query = query.lte("created_at", end_date)
            if status:
                query = query.eq("status", status)
            if payment_method:
                query = query.eq("payment_method", payment_method)
            if class_id:
                query = query.eq("invoices.course_id", int(class_id))
            if student_search:
                query = query.ilike("students.full_name", f"%{student_search}%")

            for r in query.execute().data or []:
                invoice = r.get('invoices') or {}
                student = r.get('students') or {}
                rows.append({
                    "Invoice #": invoice.get('invoice_number'),
                    "Student ID": r.get('user_id'),
                    "Name": student.get('full_name'),
                    "Amount Due": invoice.get('amount'),
                    "Amount Paid": r.get('amount'),
                    "Balance": invoice.get('balance'),
                    "Payment Method": r.get('payment_method'),
                    "Status": r.get('status'),
                    "Date Paid": r.get('created_at')
                })

        elif report_type == 'pending_invoices':
            query = client.from_("invoices").select(
                "id, invoice_number, amount, balance, due_date, course_id, students(full_name)"
            ).lt("balance", "amount")  # unpaid/partial

            if start_date:
                query = query.gte("due_date", start_date)
            if end_date:
                query = query.lte("due_date", end_date)
            if class_id:
                query = query.eq("course_id", int(class_id))
            if student_search:
                query = query.ilike("students.full_name", f"%{student_search}%")

            for r in query.execute().data or []:
                student = r.get('students') or {}
                due_date = r.get('due_date')
                balance_days = (datetime.now() - datetime.fromisoformat(due_date)).days if due_date else None
                rows.append({
                    "Invoice #": r.get('invoice_number'),
                    "Student": student.get('full_name'),
                    "Class ID": r.get('course_id'),
                    "Amount Due": r.get('amount'),
                    "Balance": r.get('balance'),
                    "Due Date": due_date,
                    "Days Overdue": balance_days
                })

        elif report_type == 'student_ledger':
            query = client.from_("payments").select(
                "id, user_id, invoice_id, amount, payment_method, status, created_at, students(full_name)"
            )
            if start_date:
                query = query.gte("created_at", start_date)
            if end_date:
                query = query.lte("created_at", end_date)
            if student_search:
                query = query.ilike("students.full_name", f"%{student_search}%")

            for r in query.execute().data or []:
                student = r.get('students') or {}
                rows.append({
                    "Date": r.get('created_at'),
                    "Invoice ID": r.get('invoice_id'),
                    "Student": student.get('full_name'),
                    "Amount Paid": r.get('amount'),
                    "Payment Method": r.get('payment_method'),
                    "Status": r.get('status')
                })

        elif report_type == 'revenue':
            query = client.from_("payments").select(
                "amount, created_at, payment_method"
            )
            if start_date:
                query = query.gte("created_at", start_date)
            if end_date:
                query = query.lte("created_at", end_date)

            for r in query.execute().data or []:
                rows.append({
                    "Amount": r.get('amount'),
                    "Date": r.get('created_at'),
                    "Payment Method": r.get('payment_method')
                })

        elif report_type == 'student_balance_summary':
            query = client.from_("students").select(
                "id, full_name, invoices(amount, balance, course_id)"
            )
            if class_id:
                query = query.eq("course_id", int(class_id))
            for r in query.execute().data or []:
                invoices = r.get('invoices') or []
                total_due = sum(inv.get('amount', 0) for inv in invoices)
                total_balance = sum(inv.get('balance', 0) for inv in invoices)
                rows.append({
                    "Student ID": r.get('id'),
                    "Name": r.get('full_name'),
                    "Total Amount Due": total_due,
                    "Total Balance": total_balance
                })

    except Exception as e:
        print(f"❌ Error in get_report_data: {e}")
        raise e

    return rows


# --- Routes ---

@admin_reports_bp.route('/admin/reports', methods=['GET'])
@admin_login_required
def reports_page():
    """Render reports page with filters"""
    client = get_admin_client()
    classes_res = client.from_("courses").select("id, title").execute()
    return render_template(
        'admin/reports.html',
        classes=classes_res.data or []
    )


@admin_reports_bp.route('/data', methods=['GET'])
@admin_login_required
def fetch_report_data():
    """AJAX endpoint to fetch filtered report data"""
    client = get_admin_client()
    filters = request.args.to_dict()
    try:
        rows = get_report_data(client, filters)
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@admin_reports_bp.route('/export-excel', methods=['POST'])
@admin_login_required
def export_reports_excel():
    """Export filtered report to Excel"""
    client = get_admin_client()
    filters = request.form.to_dict()

    try:
        rows = get_report_data(client, filters)
        if not rows:
            return jsonify({"success": False, "message": "No data to export"}), 400

        df = pd.DataFrame(rows)
        output = BytesIO()
        sheet_name = filters.get('report_type', 'Report').replace("_", " ").title()
        df.to_excel(output, index=False, sheet_name=sheet_name)
        output.seek(0)

        filename = f"CAPITAL_COLLEGE_{sheet_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
