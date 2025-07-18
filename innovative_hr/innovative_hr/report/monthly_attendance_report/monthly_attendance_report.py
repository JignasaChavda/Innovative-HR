# Copyright (c) 2025, jignasha chavda and contributors
# For license information, please see license.txt


# * ------------------------- Imports -------------------------
import frappe
from frappe import _
from frappe.utils import cstr
from frappe.utils.nestedset import get_descendants_of
from innovative_hr.override.salary_slip_override import SalarySlip
from itertools import groupby
from hrms.hr.report.monthly_attendance_sheet.monthly_attendance_sheet import (
    get_attendance_map,
    get_columns,
    set_defaults_for_summarized_view,
    get_attendance_records,
    get_attendance_status_for_summarized_view,
    get_entry_exits_summary,
    get_leave_summary,
    get_holiday_status,
    get_total_days_in_month,
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
    "Mispunch": "M",
    "Leave Without Pay": "LOP"
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
    # * Add Employment Type column at 2nd index in the report columns
    columns.insert(2, {
    "label": _("Employment Type"),
    "fieldname": "employment_type",
    "fieldtype": "Link",
    "options": "Employment Type",
    "width": 150
    })
    # * Add Contractor column at 3rd index in the report columns
    columns.insert(3, {
    "label": _("Contractor"),
    "fieldname": "contractor",
    "fieldtype": "Link",
    "options": "Contractor Company",
    "width": 150
    })
    columns += [
        {"label": _(label), "fieldname": field, "fieldtype": field_type, "width": width}
        for label, field, field_type, width in [
            ("Total Working Days", "total_working_days", "float", 200),
            ("Total Present Days", "total_present", "float", 200),
            ("Total Weekoffs", "total_weekoff", "Int", 120),
            ("Worked Weekoffs", "worked_week_offs", "float", 120),
            ("Total Holidays", "total_holiday", "Int", 120),
            ("Worked Holidays", "worked_holidays", "float", 120),
            ("Total Paid Leaves", "total_paid_leaves","float", 120),
            ("Total LOP", "total_lop", "float", 200),
            ("Total Payment Days", "total_payment_day", "float", 200),
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

    return columns, data, message

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
        for day in leave_days:
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
                "employee_name": details.employee_name,
                "employment_type": details.employment_type,
                "contractor": details.custom_contractor
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
    total_paid_leaves = 0
    total_presents = 0
    lop_days = 0
    employment_type = frappe.db.get_value("Employee", employee, "employment_type")
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
                # ? NOT COUNT WORKED WEEKOFF AND HOLIDAY FOR STAFF AND STAFF TRAINEE
                if employment_type in ["Staff", "Staff Trainee"]:
                    total_presents -= 1
                worked_week_offs += 1
            elif new_status == "Holiday":
                if employment_type in ["Staff", "Staff Trainee"]:
                    total_presents -= 1
                worked_holidays += 1
            if abbr == "P":
                total_presents += 1

        elif abbr == "HD":
            total_presents += 0.5
            new_status = get_holiday_status(day, holidays)
            if new_status == "Weekly Off":
                worked_week_offs += 0.5
                # ? NOT COUNT WORKED WEEKOFF AND HOLIDAY FOR STAFF AND STAFF TRAINEE
                if employment_type in ["Staff", "Staff Trainee"]:
                    total_presents -= 0.5
            elif new_status == "Holiday":
                if employment_type in ["Staff", "Staff Trainee"]:
                    total_presents -= 0.5
                worked_holidays += 0.5
            else:
                attendance  = frappe.get_all("Attendance", filters={"employee": employee, "attendance_date": f"{filters.year}-{filters.month}-{day}"}, fields=["leave_type"])
                if attendance[0].leave_type:
                    leave_type = frappe.get_doc("Leave Type", attendance[0].leave_type)
                    if leave_type.is_lwp:
                        lop_days += 0.5
                    else:
                        total_paid_leaves += 0.5

        elif abbr == "L":
            attendance  = frappe.get_all("Attendance", filters={"employee": employee, "attendance_date": f"{filters.year}-{filters.month}-{day}"}, fields=["leave_type"])
            if attendance[0].leave_type:
                leave_type = frappe.get_doc("Leave Type", attendance[0].leave_type)
                if leave_type.is_lwp:
                    lop_days += 1
                    row[cstr(day)] = "LOP"
                else:
                    total_paid_leaves += 1
                
    total_presents = total_presents - worked_week_offs - worked_holidays
    # * Create Parameters To Pass in set_new_working_days Method
    working_days_obj = frappe._dict({
        "employee": employee,
        "start_date": f"{filters.year}-{filters.month}-01",
        "end_date": f"{filters.year}-{filters.month}-{get_total_days_in_month(filters)}",
        "leave_without_pay": lop_days,
        "absent_days": 0,
        "total_working_days": 0,
        "payment_days": 0,
    })

    # * Call method
    SalarySlip.set_new_working_days(working_days_obj)
    # * Set Total Working and Payment Days
    total_working_days = working_days_obj.total_working_days
    # ? SET PAYMENT DAYS FOR CONTRACT EMPLOYEE
    if employment_type == "Contract":
        standard_working_hours = frappe.db.get_value("Employee", employee, "custom_standard_working_hours")
        if not standard_working_hours:
            payment_days = 0
        else:
            hours_data = get_employee_attendance_records(employee, filters)
            total_hours = sum(row.get("custom_total_hours", 0) for row in hours_data)
            payment_days = round(total_hours / standard_working_hours,1)
    else:
        payment_days = total_working_days - lop_days

    row.update({
        "total_present": total_presents,
        "total_weekoff": total_weekoffs,
        "total_holiday": total_holidays,
        "worked_week_offs":worked_week_offs,
        "worked_holidays":worked_holidays,
        "total_paid_leaves": total_paid_leaves,
        "total_lop": lop_days,
        "total_payment_day": payment_days,
        "total_working_days": total_working_days
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

def get_employee_related_details(filters: Filters) -> tuple[dict, list]:
    """Returns
    1. nested dict for employee details
    2. list of values for the group by filter
    """
    Employee = frappe.qb.DocType("Employee")
    query = (
        frappe.qb.from_(Employee)
        .select(
            Employee.name,
            Employee.employee_name,
            Employee.employment_type,
            Employee.designation,
            Employee.grade,
            Employee.department,
            Employee.branch,
            Employee.company,
            Employee.holiday_list,
            Employee.custom_contractor
        )
        .where(Employee.company.isin(filters.companies))
    )

    if filters.employee:
        query = query.where(Employee.name == filters.employee)

    group_by = filters.group_by
    if group_by:
        group_by = group_by.lower()
        query = query.orderby(group_by)

    employee_details = query.run(as_dict=True)

    group_by_param_values = []
    emp_map = {}

    if group_by:
        group_key = lambda d: "" if d[group_by] is None else d[group_by]  # noqa
        for parameter, employees in groupby(sorted(employee_details, key=group_key), key=group_key):
            group_by_param_values.append(parameter)
            emp_map.setdefault(parameter, frappe._dict())

            for emp in employees:
                emp_map[parameter][emp.name] = emp
    else:
        for emp in employee_details:
            emp_map[emp.name] = emp

    return emp_map, group_by_param_values

def get_message() -> str:
	message = ""
	colors = ["green", "red", "orange", "green", "#318AD8", "", "", "orange", "red"]

	count = 0
	for status, abbr in status_map.items():
		message += f"""
			<span style='border-left: 2px solid {colors[count]}; padding-right: 12px; padding-left: 5px; margin-right: 3px;'>
				{status} - {abbr}
			</span>
		"""
		count += 1

	return message