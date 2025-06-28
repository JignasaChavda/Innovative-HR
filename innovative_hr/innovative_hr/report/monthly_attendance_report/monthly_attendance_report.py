# Copyright (c) 2025, jignasha chavda and contributors
# For license information, please see license.txt


# * ------------------------- Imports -------------------------
import frappe
from frappe import _
from frappe.utils import cstr
from frappe.utils.nestedset import get_descendants_of
from hrms.hr.report.monthly_attendance_sheet.monthly_attendance_sheet import (
    get_attendance_map,
    get_chart_data,
    get_message,
    get_columns,
    set_defaults_for_summarized_view,
    get_attendance_records,
    get_attendance_status_for_summarized_view,
    get_entry_exits_summary,
    get_leave_summary,
    get_holiday_status,
    get_total_days_in_month,
    get_employee_related_details,
    get_holiday_map,
)

# * ------------------------ Constants ------------------------
Filters = frappe._dict

status_map = {
    "Present": "P",
    "Absent": "A",
    "Half Day": "HD",
    "Work From Home": "WFH",
    "On Leave": "L",
    "Holiday": "H",
    "Weekly Off": "WO",
}

day_abbr = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# * ------------------- Main Entry Function -------------------
def execute(filters: Filters | None = None) -> tuple:
    filters = frappe._dict(filters or {})

    # ! Validate required filters
    if not (filters.month and filters.year):
        frappe.throw(_("Please select month and year."))

    if not filters.company:
        frappe.throw(_("Please select company."))

    # * Prepare company list with optional descendants
    filters.companies = [filters.company]
    if filters.include_company_descendants:
        filters.companies.extend(get_descendants_of("Company", filters.company))

    # * Fetch attendance data with and without shift
    attendance_map = get_attendance_map(filters)
    attendance_map_without_shift = get_attendance_map_without_shift(filters)

    if not attendance_map:
        frappe.msgprint(_("No attendance records found."), alert=True, indicator="orange")
        return [], [], None, None

    # * Build columns for report
    columns = [col for col in get_columns(filters) if col.get("fieldname") != "shift"]
    columns += [
        {"label": _(label), "fieldname": field, "fieldtype": field_type, "width": width}
        for label, field, field_type, width in [
            ("Total Weekoffs", "total_weekoff", "Int", 120),
            ("Worked Weekoffs", "worked_week_offs", "float", 120),
            ("Total Holidays", "total_holiday", "Int", 120),
            ("Worked Holidays", "worked_holidays", "float", 120),
            ("Total Leaves", "total_leaves","float", 120),
            ("Total Work Hours", "total_work_hours", "Data", 200),
            ("Total Applicable Overtime", "total_applicable_overtime", "Data", 200),
            ("Total Remaining Overtime", "total_remaining_overtime", "Data", 200)
        ]
    ]

    # * Fetch report data
    data = get_data(filters, attendance_map_without_shift)

    if not data:
        frappe.msgprint(_("No attendance records found for this criteria."), alert=True, indicator="orange")
        return columns, [], None, None

    message = get_message() if not filters.summarized_view else ""
    chart = get_chart_data(attendance_map, filters)

    return columns, data, message, chart

# * ------------------- Data Preparation ----------------------
def get_data(filters: Filters, attendance_map: dict) -> list[dict]:
    employee_details, group_by_values = get_employee_related_details(filters)
    holiday_map = get_holiday_map(filters)
    data = []

    if filters.group_by:
        group_by_column = frappe.scrub(filters.group_by)
        for value in group_by_values:
            if not value:
                continue
            records = get_rows(employee_details[value], filters, holiday_map, attendance_map)
            if records:
                data.append({group_by_column: value})
                data.extend(records)
    else:
        data = get_rows(employee_details, filters, holiday_map, attendance_map)

    return data

# * -------------- Attendance Without Shift Map ---------------
def get_attendance_map_without_shift(filters: Filters) -> dict:
    attendance_list = get_attendance_records(filters)
    attendance_map = {}
    leave_map = {}

    for d in attendance_list:
        if d.status == "On Leave":
            leave_map.setdefault(d.employee, {}).setdefault(d.day_of_month, []).append(d.day_of_month)
            continue
        attendance_map.setdefault(d.employee, {})[d.day_of_month] = d.status

    # ^ Fill leave records even when no shift present
    for employee, leave_days in leave_map.items():
        attendance_map.setdefault(employee, {})
        for day_list in leave_days:
            for day in day_list:
                attendance_map[employee][day] = "On Leave"

    return attendance_map

# * ------------------ Row-wise Data Prep ---------------------
def get_rows(employee_details: dict, filters: Filters, holiday_map: dict, attendance_map: dict) -> list[dict]:
    records = []
    default_holiday_list = frappe.get_cached_value("Company", filters.company, "default_holiday_list")

    for employee, details in employee_details.items():
        emp_holiday_list = details.holiday_list or default_holiday_list
        holidays = holiday_map.get(emp_holiday_list)
        total_weekoffs = 0
        total_holidays = 0
        for holiday in holidays:
            if holiday.get("weekly_off"):
                total_weekoffs += 1
            else:
                total_holidays += 1

        if filters.summarized_view:
            # * Summarized view: Combine attendance, leave & entry/exit summary
            attendance = get_attendance_status_for_summarized_view(employee, filters, holidays)
            if not attendance:
                continue

            row = {"employee": employee, "employee_name": details.employee_name}
            row.update(attendance)
            row.update(get_leave_summary(employee, filters))
            row.update(get_entry_exits_summary(employee, filters))
            set_defaults_for_summarized_view(filters, row)

            records.append(row)
        else:
            # * Detailed view: Attendance day-wise + OT hours
            employee_attendance = attendance_map.get(employee)
            if not employee_attendance:
                continue

            attendance_for_employee = custom_get_attendance_status_for_detailed_view(
                employee, filters, employee_attendance,holidays, total_weekoffs, total_holidays
            )

            attendance_for_employee[0].update({
                "employee": employee,
                "employee_name": details.employee_name
            })

            # * Add Overtime and Work Hour Summaries
            hours_data = get_employee_attendance_records(employee, filters)
            total_hours = sum(row.get("custom_total_hours", 0) for row in hours_data)
            total_ot = sum(row.get("custom_overtime", 0) for row in hours_data)
            total_remaining_ot = sum(row.get("custom_remaining_overtime", 0) for row in hours_data)

            attendance_for_employee[0].update({
                "total_work_hours": total_hours,
                "total_applicable_overtime": total_ot,
                "total_remaining_overtime": total_remaining_ot
            })

            records.extend(attendance_for_employee)

    return records

# * ----------- Format Attendance Row (Detailed) -------------
def custom_get_attendance_status_for_detailed_view(
    employee: str, filters: Filters, employee_attendance: dict, holidays: list, total_weekoffs, total_holidays
) -> list[dict]:
    total_days = get_total_days_in_month(filters)
    row = {}
    worked_week_offs = 0
    worked_holidays = 0
    total_leaves = 0

    for day in range(1, total_days + 1):
        status = employee_attendance.get(day)
        if status is None and holidays:
            status = get_holiday_status(day, holidays)

        abbr = status_map.get(status, "")
        row[cstr(day)] = abbr

        # ! Track totals for worked weekoffs and holidays
        if abbr == "P" or abbr=="WFH":
            new_status = get_holiday_status(day, holidays)
            if new_status == "Weekly Off":
                worked_week_offs += 1
            elif new_status == "Holiday":
                worked_holidays += 1
        
        elif abbr == "HD":
            new_status = get_holiday_status(day, holidays)
            if new_status == "Weekly Off":
                worked_week_offs += 0.5
            elif new_status == "Holiday":
                worked_holidays += 0.5
            else:
                attendance  = frappe.get_all("Attendance", filters={"employee": employee, "attendance_date": f"{filters.year}-{filters.month}-{day}"}, fields=["leave_type"])
                if attendance[0].leave_type:
                    total_leaves += 0.5

        elif abbr == "L":
            total_leaves += 1

    row.update({
        "total_weekoff": total_weekoffs,
        "total_holiday": total_holidays,
        "worked_week_offs":worked_week_offs,
        "worked_holidays":worked_holidays,
        "total_leaves": total_leaves
    })

    return [row]

# * ----------- Fetch Employee OT/Hours Summary --------------
def get_employee_attendance_records(employee, filters):
    month_str = str(filters.month).zfill(2)
    from_date = f"{filters.year}-{month_str}-01"
    to_date = frappe.utils.get_last_day(from_date)

    return frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "docstatus": 1,
            "company": ["in", filters.companies],
            "attendance_date": ["between", [from_date, to_date]],
        },
        fields=["custom_total_hours", "custom_overtime", "custom_remaining_overtime"],
        order_by="attendance_date asc"
    )
