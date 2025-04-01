import frappe
from datetime import datetime, timedelta
from frappe.utils import add_days, time_diff, get_time, today

@frappe.whitelist(allow_guest=True)
def mark_attendance(date=None, shift=None):
    # Use yesterday's date if no date is provided
    if not date:
        today_date = datetime.strptime(today(), '%Y-%m-%d').date()
        date = add_days(today_date, -1)  # Correctly set date to yesterday
    else:
        date = datetime.strptime(date, '%Y-%m-%d').date()  # Ensure date is a date object

    yesterday_date = date
    tomorrow_date = add_days(date, +1)

    if not shift:
        frappe.throw("Please specify a shift type.")

    shift_hours = frappe.db.get_value("Shift Type", shift, "custom_shift_hours")
    OT_calculation_criteria = frappe.db.get_value("Shift Type", shift, "custom_overtime_calculate_criteria")

    # Retrieve all active employees
    active_employees = frappe.db.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "date_of_joining"]
    )

    for emp in active_employees:
        emp_name = emp["name"]
        emp_joining_date = emp["date_of_joining"]

        # Skip if the employee's joining date is after the attendance date
        if emp_joining_date and emp_joining_date > yesterday_date:
            continue

        # Determine the shift type
        shift_type = frappe.db.get_value("Shift Type", shift, "custom_shift_type")

        # Initialize variables for first check-in and last check-out
        first_checkin = None
        last_checkout = None
        last_checkout_time = None
        first_checkin_time = None
        formatted_total_work_hours = '0.0'
        final_OT = '0.0'
        att_early_exit = 0
        att_late_entry = 0
        late_entry_hours_final = '0'
        early_exit_hours_final = '0'
        att_remarks = ''

        # Fetch logs based on shift type
        if shift_type == "Day":
            # Retrieve all check-ins for the employee on the specified date and shift
            checkin_records = frappe.db.get_all(
                "Employee Checkin",
                filters={
                    "employee": emp_name,
                    "shift": shift,
                    "custom_date": yesterday_date
                },
                fields=["name", "custom_date", "log_type", "time"],
                order_by="time"
            )

            # Identify the first "IN" and last "OUT" records
            for log in checkin_records:
                if log["log_type"] == "IN" and not first_checkin:
                    first_checkin = log
                if log["log_type"] == "OUT":
                    last_checkout = log

        elif shift_type == "Night":
            # Retrieve the "IN" log from the previous day
            yesterday_in_record = frappe.db.get_all(
                "Employee Checkin",
                filters={
                    "employee": emp_name,
                    "shift": shift,
                    "custom_date": yesterday_date,
                    "log_type": "IN"
                },
                fields=["name", "custom_date", "log_type", "time"],
                order_by="time"
            )

            # Retrieve the "OUT" log from the current day
            today_out_record = frappe.db.get_all(
                "Employee Checkin",
                filters={
                    "employee": emp_name,
                    "shift": shift,
                    "custom_date": tomorrow_date,
                    "log_type": "OUT"
                },
                fields=["name", "custom_date", "log_type", "time"],
                order_by="time"
            )

            # Assign the first "IN" from the previous day and the last "OUT" from the current day
            if yesterday_in_record:
                first_checkin = yesterday_in_record[0]
            if today_out_record:
                last_checkout = today_out_record[-1]

        if first_checkin:
            first_checkin_time = first_checkin["time"]
            first_in_time = get_time(first_checkin_time)
        
        if last_checkout:
            last_checkout_time = last_checkout["time"]
            last_out_time = get_time(last_checkout_time)

        
   
        if first_checkin and last_checkout:
            # Calculate work hours
            work_hours = time_diff(last_checkout_time, first_checkin_time)
            total_work_hours = work_hours.total_seconds() / 3600

            # Convert to HH.MM format
            hours = int(total_work_hours)
            minutes = int(round((total_work_hours - hours) * 60))

            formatted_total_work_hours = f"{hours:02d}.{minutes:02d}"


                
                

            total_work_hours = float(total_work_hours)

            # Convert shift_hours to timedelta if it's not already
            if isinstance(shift_hours, (int, float)):
                shift_hours = timedelta(hours=shift_hours)

            # Convert total_work_hours to timedelta
            work_hours_timedelta = timedelta(hours=total_work_hours)

            # Calculate Work Hours (should not exceed shift hours)
            work_hours = min(work_hours_timedelta, shift_hours)

            # Calculate Overtime
            OT_calculation_criteria_seconds = OT_calculation_criteria * 60

            emp_overtime_consent = frappe.db.get_value('Employee', emp_name, 'custom_overtime_applicable')

            if emp_overtime_consent == 1 and work_hours_timedelta > shift_hours:
                diff = work_hours_timedelta - shift_hours
                total_seconds = diff.total_seconds()

                if total_seconds > OT_calculation_criteria_seconds:
                    hours, remainder = divmod(total_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    final_OT = f"{int(hours):02}.{int(minutes):02}"
                    
                
            # Convert work_hours to formatted string (hh.mm)
            work_hours_hours, work_hours_remainder = divmod(work_hours.total_seconds(), 3600)
            work_hours_minutes, _ = divmod(work_hours_remainder, 60)
            final_work_hours = f"{int(work_hours_hours):02}.{int(work_hours_minutes):02}"

            # Convert total_work_hours to formatted string (hh.mm)
            total_hours_hours, total_hours_remainder = divmod(work_hours_timedelta.total_seconds(), 3600)
            total_hours_minutes, _ = divmod(total_hours_remainder, 60)
            final_total_hours = f"{int(total_hours_hours):02}.{int(total_hours_minutes):02}"

      

            # Calculate late entry, early exit
            half_day_hour = frappe.db.get_value('Shift Type', shift, 'working_hours_threshold_for_half_day')
            absent_hour = frappe.db.get_value('Shift Type', shift, 'working_hours_threshold_for_absent')

            shift_start_time = frappe.db.get_value('Shift Type', shift, 'start_time')
            late_entry_grace_period = frappe.db.get_value('Shift Type', shift, 'late_entry_grace_period')
            shift_start_time = frappe.utils.get_time(shift_start_time)
            shift_start_datetime = datetime.combine(yesterday_date, shift_start_time)
            grace_late_datetime = frappe.utils.add_to_date(shift_start_datetime, minutes=late_entry_grace_period)
            grace_late_time = grace_late_datetime.time()

            shift_end_time = frappe.db.get_value('Shift Type', shift, 'end_time')
            early_exit_grace_period = frappe.db.get_value('Shift Type', shift, 'early_exit_grace_period')
            shift_end_time = frappe.utils.get_time(shift_end_time)
            if shift_type == 'Night':
                shift_end_datetime = datetime.combine(yesterday_date, shift_end_time)
            else:
                shift_end_datetime = datetime.combine(tomorrow_date, shift_end_time)
            grace_early_datetime = frappe.utils.add_to_date(shift_end_datetime, minutes=-early_exit_grace_period)
            grace_early_time = grace_early_datetime.time()
            
            

            if first_in_time and first_in_time > grace_late_time:
                
                late_entry_timedelta = frappe.utils.time_diff(str(first_in_time), str(grace_late_time))
                total_late_entry_seconds = late_entry_timedelta.total_seconds()
                late_entry_hour = int(total_late_entry_seconds // 3600)
                late_entry_minute = int((total_late_entry_seconds % 3600) // 60)
                late_entry_hours_final = f"{late_entry_hour:02d}.{late_entry_minute:02d}"
                att_late_entry = 1

            if last_out_time and last_out_time < grace_early_time:
                early_exit_timedelta = frappe.utils.time_diff(str(grace_early_time), str(last_out_time))
                total_early_exit_seconds = early_exit_timedelta.total_seconds()
                early_exit_hour = int(total_early_exit_seconds // 3600)
                early_exit_minute = int((total_early_exit_seconds % 3600) // 60)
                early_exit_hours_final = f"{early_exit_hour:02d}.{early_exit_minute:02d}"
                att_early_exit = 1

        
            # Calculate threshold limit wise status
            att_status = 'Present'
            if float(total_work_hours) < half_day_hour:
                att_status = 'Half Day'
            if float(total_work_hours) < absent_hour:
                att_status = 'Absent'

            # Check if attendance already exists
            exists_atte = frappe.db.get_value('Attendance', {'employee': emp_name, 'attendance_date': yesterday_date, 'docstatus': 1}, ['name'])
            if not exists_atte:
                attendance = frappe.new_doc("Attendance")
                attendance.employee = emp_name
                attendance.attendance_date = yesterday_date
                attendance.shift = shift
                attendance.in_time = first_checkin_time
                attendance.out_time = last_checkout_time
                attendance.custom_employee_checkin = first_checkin["name"]
                attendance.custom_employee_checkout = last_checkout["name"]
                attendance.custom_total_hours = final_total_hours
                attendance.custom_work_hours = final_work_hours
                attendance.custom_overtime = final_OT
                attendance.status = att_status
                attendance.custom_late_entry_hours = late_entry_hours_final
                attendance.custom_early_exit_hours = early_exit_hours_final
                attendance.late_entry = att_late_entry
                attendance.early_exit = att_early_exit
                attendance.custom_remarks = att_remarks

                attendance.insert(ignore_permissions=True)
                attendance.submit()
                frappe.db.commit()

                frappe.msgprint("Attendance is Marked Successfully")
            else:
                formatted_date = yesterday_date.strftime("%d-%m-%Y")
                attendance_link = frappe.utils.get_link_to_form("Attendance", exists_atte)
                frappe.msgprint(f"Attendance already marked for Employee:{emp_name} for date {formatted_date}: {attendance_link}")
        
        elif first_checkin or last_checkout:
            exists_atte = frappe.db.get_value('Attendance', {'employee': emp_name, 'attendance_date': yesterday_date, 'docstatus': 1}, ['name'])
            if not exists_atte:
                
                attendance = frappe.new_doc("Attendance")
                attendance.employee = emp_name
                attendance.attendance_date = yesterday_date
                attendance.shift = shift

                if first_checkin_time:
                    attendance.in_time = first_checkin_time
                    attendance.custom_employee_checkin = first_checkin["name"]
                    attendance.custom_remarks = 'No Checkout record found'
                if last_checkout_time:
                    attendance.out_time = first_checkin_time
                    attendance.custom_employee_checkout = last_checkout["name"]
                    attendance.custom_remarks = 'No Checkin record found'
                attendance.custom_total_hours = 0
                attendance.custom_work_hours = 0
                attendance.custom_overtime = 0
                attendance.status = 'Absent'
                attendance.custom_late_entry_hours = 0
                attendance.custom_early_exit_hours = 0
                attendance.late_entry = 0
                attendance.early_exit = 0
                

                attendance.insert(ignore_permissions=True)
                attendance.submit()
                frappe.db.commit()

                frappe.msgprint("Attendance is Marked Successfully")
            else:
                formatted_date = yesterday_date.strftime("%d-%m-%Y")
                attendance_link = frappe.utils.get_link_to_form("Attendance", exists_atte)
                frappe.msgprint(f"Attendance already marked for Employee:{emp_name} for date {formatted_date}: {attendance_link}")

@frappe.whitelist()
def schedule_mark_attendance():
    """Scheduled job to mark attendance for yesterday."""
    shift_types = frappe.db.get_list("Shift Type", pluck="name")
    for shift in shift_types:
        mark_attendance(date=None, shift=shift)
