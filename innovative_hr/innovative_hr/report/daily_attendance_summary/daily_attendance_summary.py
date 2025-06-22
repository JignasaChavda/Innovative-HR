import frappe
from frappe.utils import getdate

def execute(filters=None):
    if not filters:
        filters = {}

    attendance_date = getdate(filters.get("attendance_date"))
    department = filters.get("department")
    employment_type = filters.get("employment_type")
    contractor = filters.get("contractor")

    columns = [
        {"label": "Employee",            "fieldname": "employee_code",        "fieldtype": "Data",      "width": 150},
        {"label": "Employee Name",       "fieldname": "employee_name",        "fieldtype": "Data",      "width": 300},
        {"label": "Department",          "fieldname": "department",           "fieldtype": "Link",      "options": "Department",         "width": 200},
        {"label": "Employment Type",     "fieldname": "custom_employment_type","fieldtype": "Link",     "options": "Employment Type",    "width": 200},
        {"label": "Contractor",          "fieldname": "contractor",           "fieldtype": "Link",      "options": "Contractor Company", "width": 200},
        {"label": "Date",                "fieldname": "attendance_date",      "fieldtype": "Data",      "width": 150},
        {"label": "Status",              "fieldname": "status",               "fieldtype": "Data",      "width": 100},
        {"label": "Total Working Hours", "fieldname": "custom_total_hours",   "fieldtype": "Float",     "width": 120, "precision": 0},
        {"label": "Per Hour Rate",       "fieldname": "custom_per_hour_wages","fieldtype": "Currency",  "width": 150},
        {"label": "Daily Wage",          "fieldname": "daily_wage",           "fieldtype": "Currency",  "width": 150},
        {"label": "Shift",               "fieldname": "shift",                "fieldtype": "Data",      "width": 100},
        {"label": "Check-In",            "fieldname": "in_time",              "fieldtype": "Time",      "width": 100},
        {"label": "Check-Out",           "fieldname": "out_time",             "fieldtype": "Time",      "width": 100},
        {"label": "Penalty Type",        "fieldname": "penalty_type",         "fieldtype": "Data",      "width": 230},
        {"label": "Penalty Amount",      "fieldname": "penalty_amount",       "fieldtype": "Currency",  "width": 150},
    ]

    attendance_filters = {
        "attendance_date": attendance_date,
        "docstatus": 1
    }

    if department:
        attendance_filters["department"] = department
    if employment_type:
        attendance_filters["custom_employment_type"] = employment_type
    if contractor:
        attendance_filters["custom_contractor"] = contractor

    data = frappe.db.get_all(
        "Attendance",
        filters=attendance_filters,
        fields=[
            "employee", "employee_name", "department", "custom_employment_type",
            "custom_contractor", "attendance_date", "status", "custom_total_hours",
            "shift", "in_time", "out_time"
        ]
    )

    total_hours = 0.0
    total_daily_wage = 0.0

    for row in data:
        if row.get("attendance_date"):
            date_obj = row["attendance_date"]
            row["attendance_date"] = date_obj.strftime("%d-%m-%Y")
        else:
            date_obj = None

        row["contractor"] = row.get("custom_contractor")
        row["employee_code"] = row.get("employee")

        try:
            hours = float(row.get("custom_total_hours") or 0.0)
        except (ValueError, TypeError):
            hours = 0.0
        row["custom_total_hours"] = hours
        total_hours += hours

        emp_type = row.get("custom_employment_type", "").strip().lower()
        status = row.get("status", "").strip().lower()
        daily_wage = 0.0

        if emp_type in ["staff", "staff trainee"]:
            per_day_rate = frappe.db.get_value("Employee", row["employee"], "custom_per_day_wages") or 0.0
            row["custom_per_hour_wages"] = 0

            if status == "present":
                daily_wage = per_day_rate
            elif status == "half day":
                daily_wage = per_day_rate / 2
            elif status == "absent":
                daily_wage = 0.0
        else:
            per_hour_rate = frappe.db.get_value("Employee", row["employee"], "custom_per_hour_wages") or 0.0
            row["custom_per_hour_wages"] = per_hour_rate
            daily_wage = round(hours * per_hour_rate)

        row["daily_wage"] = round(daily_wage)
        total_daily_wage += row["daily_wage"]

        # --- Fetch Penalty from Additional Salary ---
        penalty = frappe.db.get_value(
            "Additional Salary",
            {
                "employee": row["employee"],
                "payroll_date": date_obj,
                "docstatus": 1  # Only submitted records
            },
            ["custom_penalty_type", "amount"]
        )

        if penalty:
            row["penalty_type"] = penalty[0]
            row["penalty_amount"] = penalty[1]
        else:
            row["penalty_type"] = ""
            row["penalty_amount"] = ""

        row["in_time"] = row["in_time"].strftime('%H:%M:%S') if row.get("in_time") else ""
        row["out_time"] = row["out_time"].strftime('%H:%M:%S') if row.get("out_time") else ""

    data.append({
        "employee_code":          "",
        "employee_name":         "<b>Total</b>",
        "department":            "",
        "custom_employment_type":"",
        "contractor":            "",
        "attendance_date":       "",
        "status":                "",
        "custom_total_hours":    total_hours,
        "custom_per_hour_wages": "",
        "daily_wage":            total_daily_wage,
        "penalty_type":          "",
        "penalty_amount":        "",
        "shift":                 "",
        "in_time":               "",
        "out_time":              "",
        "total_row":             True
    })

    return columns, data
