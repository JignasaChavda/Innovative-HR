import frappe

def execute():
    report_name = "Monthly Attendance Report"

    if frappe.db.exists("Report", report_name):
        frappe.db.set_value("Report", report_name, "prepared_report", 0)
        frappe.db.commit()
