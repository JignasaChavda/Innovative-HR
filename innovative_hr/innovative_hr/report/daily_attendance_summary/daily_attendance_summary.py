import frappe
from frappe.utils import getdate

def execute(filters=None):
    if not filters:
        filters = {}

    attendance_date = getdate(filters.get("attendance_date"))
    department = filters.get("department")
    employment_type = filters.get("employment_type")

    columns = [
        {"label": "Employee",            "fieldname": "employee",            "fieldtype": "Link",     "options": "Employee",        "width": 150},
        {"label": "Employee Name",       "fieldname": "employee_name",       "fieldtype": "Data",     "width": 300},
        {"label": "Department",          "fieldname": "department",          "fieldtype": "Link",     "options": "Department",      "width": 200},
        {"label": "Employment Type",     "fieldname": "custom_employment_type","fieldtype":"Link",     "options": "Employment Type","width": 200},
        {"label": "Date",                "fieldname": "attendance_date",     "fieldtype": "Data",     "width": 150},
        {"label": "Status",              "fieldname": "status",             "fieldtype": "Data",     "width": 100},
        {"label": "Total Working Hours", "fieldname": "custom_total_hours",  "fieldtype": "Float",    "width": 120,   "precision": 0},
        {"label": "Per Hour Rate",       "fieldname": "custom_per_hour_wages","fieldtype":"Currency","width": 150},
        {"label": "Daily Wage",          "fieldname": "daily_wage",         "fieldtype": "Currency","width": 150},
        {"label": "Shift",               "fieldname": "shift",              "fieldtype": "Data",     "width": 100},
        {"label": "Check-In",            "fieldname": "in_time",            "fieldtype": "Time",     "width": 100},
        {"label": "Check-Out",           "fieldname": "out_time",           "fieldtype": "Time",     "width": 100},
    ]

    attendance_filters = {
        "attendance_date": attendance_date,
        "docstatus": 1
    }
    if department:
        attendance_filters["department"] = department
    if employment_type:
        attendance_filters["custom_employment_type"] = employment_type

    data = frappe.db.get_all(
        "Attendance",
        filters=attendance_filters,
        fields=[
            "employee", "employee_name", "department", "custom_employment_type",
            "attendance_date", "status", "custom_total_hours",
            "shift", "in_time", "out_time"
        ]
    )

    total_hours = 0.0
    total_daily_wage = 0.0

    for row in data:
        if row.get("attendance_date"):
            row["attendance_date"] = row["attendance_date"].strftime("%d-%m-%Y")

        try:
            hours = float(row.get("custom_total_hours") or 0.0)
        except (ValueError, TypeError):
            hours = 0.0
        row["custom_total_hours"] = hours
        total_hours += hours

        per_hour_rate = frappe.db.get_value("Employee", row["employee"], "custom_per_hour_wages") or 0.0
        row["custom_per_hour_wages"] = per_hour_rate

        daily_wage = round(hours * per_hour_rate)
        row["daily_wage"] = daily_wage
        total_daily_wage += daily_wage

    # Append Total row with both sums
    data.append({
        "employee":              "",
        "employee_name":         "<b>Total</b>",
        "department":            "",
        "custom_employment_type":"",
        "attendance_date":       "",
        "status":                "",
        "custom_total_hours":    total_hours,
        "custom_per_hour_wages": "",
        "daily_wage":            total_daily_wage,
        "shift":                 "",
        "in_time":               "",
        "out_time":              ""
    })

    return columns, data
