import frappe
from datetime import datetime, timedelta
from frappe.utils import add_days, today, time_diff

@frappe.whitelist(allow_guest=True)
def mark_attendance(date=None, shift=None):
    if date:
        # If date is provided, parse it
        date = datetime.strptime(date, '%Y-%m-%d').date()
    else:
        # If no date is provided, use yesterday
        date = datetime.strptime(today(), '%Y-%m-%d').date()
        date = add_days(date, -1)

    yesterday_date = add_days(date, -1)
    tomorrow_date = add_days(date, 1)

    # frappe.msgprint(f"Yesterday Date: {yesterday_date}")
    # frappe.msgprint(f"Today Date: {date}")
    # frappe.msgprint(f"Tomorrow Date: {tomorrow_date}")


    shift_hours = frappe.db.get_value("Shift Type", shift, "custom_shift_hours")
    OT_calculation_criteria = frappe.db.get_value("Shift Type", shift, "custom_overtime_calculate_criteria")
    
    active_employees = frappe.db.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "date_of_joining", "employment_type", "holiday_list"]
    )

    final_messages = []
    existing_attendances = []

    results = {}  # Dictionary to store results for each employee
    first_checkin = None
    last_checkout = None
    last_checkout_time = None
    first_checkin_time = None
    formatted_total_work_hours = '0.0'
    total_OT = '0.0'
    att_early_exit = 0
    att_late_entry = 0
    late_entry_hours_final = '0'
    early_exit_hours_final = '0'
    att_remarks = ''

    for emp in active_employees:
        emp_name = emp["name"]
        emp_type = emp["employment_type"]
        emp_full_name = emp["employee_name"]
        emp_joining_date = emp.get("date_of_joining")
        holiday_list = emp.get("holiday_list")

        if emp_joining_date and emp_joining_date > date:
            continue

        # Step 1: Get all IN records for the current day
        in_records = frappe.db.get_all(
            "Employee Checkin",
            filters={
                "employee": emp_name,
                "custom_date": date,
                "log_type": "IN"
            },
            fields=["name", "custom_date", "log_type", "time", "shift", "custom_shift_type"],
            order_by="time asc"
        )

        if not in_records:
            continue  # Skip if no IN record

        # Step 2: Pick the first IN log
        first_in = in_records[0]
        first_checkin = first_in['name']
        first_checkin_time = first_in['time']
        shift = first_in['shift']
        shift_type = first_in.get('custom_shift_type')

        # Step 3: Determine which date to search OUT records from
        if shift_type == "Night":
            out_log_date = add_days(date, 1)
        else:
            out_log_date = date

        # Step 4: Fetch OUT records from the decided date
        out_records = frappe.db.get_all(
            "Employee Checkin",
            filters={
                "employee": emp_name,
                "custom_date": out_log_date,
                "log_type": "OUT"
            },
            fields=["name", "custom_date", "log_type", "time", "shift", "custom_shift_type"],
            order_by="time asc"
        )

        if out_records:
            last_out = out_records[-1]
            last_checkout = last_out['name']
            last_checkout_time = last_out['time']
        else:
            last_checkout = None
            last_checkout_time = None

     
                    
        if emp_name not in results:
            results[emp_name] = []

        results[emp_name].append({
            'emp_name': emp_name,
            'emp_type': emp_type,
            'date': date,
            'shift': shift,
            'first_checkin': first_checkin,
            'last_checkout': last_checkout,
            'first_checkin_time': first_checkin_time,
            'last_checkout_time': last_checkout_time
        })

               

    # frappe.msgprint(str(results))                
   
    for emp_name, emp_results in results.items():
        for result in emp_results:
            # # frappe.msgprint(str(result))
            # frappe.msgprint(f"Employee: {result['emp_name']}, Date: {result['date']}, Shift: {result['shift']}, First Check-in time: {result['first_checkin_time']}, Last Checkout time: {result['last_checkout_time']}, first_checkin {result['first_checkin']}, last_checkout {result['last_checkout']}")
            
            emp_type = result.get('emp_type')
            
            first_checkin = result.get('first_checkin')
            last_checkout = result.get('last_checkout')
            first_checkin_time = result.get('first_checkin_time')
            last_checkout_time = result.get('last_checkout_time')
            shift = result.get('shift')
            shift_hours = frappe.db.get_value('Shift Type', result.get('shift'), 'custom_shift_hours')
            
            OT_calculation_criteria = frappe.db.get_single_value('HR Settings', 'custom_show_overtime_in_salary_slip')
            
            if first_checkin_time and last_checkout_time:
                
                
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

                # Work Hours (Capped at shift hours)
                work_hours = min(work_hours_timedelta, shift_hours)

                # Convert OT calculation criteria to seconds
                OT_calculation_criteria_seconds = OT_calculation_criteria * 60

                # Fetch employee overtime eligibility and show limit
                emp_overtime_consent = frappe.db.get_value('Employee', emp_name, 'custom_overtime_applicable')
                show_ot_in_salslip = frappe.db.get_single_value('HR Settings', 'custom_show_overtime_in_salary_slip')

                # Ensure show_ot_in_salslip is a valid number
                show_ot_limit = float(show_ot_in_salslip) if show_ot_in_salslip else 0.0

                # Initialize values
                applicable_OT = "00.00"
                remaining_OT = "00.00"

                # Calculate Overtime if applicable
                if emp_overtime_consent == 1 and work_hours_timedelta > shift_hours:
                    overtime_timedelta = work_hours_timedelta - shift_hours
                    total_OT_seconds = overtime_timedelta.total_seconds()

                    if total_OT_seconds > OT_calculation_criteria_seconds:
                        # Convert overtime to hours and minutes
                        OT_hours, OT_remainder = divmod(total_OT_seconds, 3600)
                        OT_minutes, _ = divmod(OT_remainder, 60)

                        # Apply rounding rule
                        if OT_minutes >= 30:
                            OT_hours += 1
                            OT_minutes = 0
                        else:
                            OT_minutes = 0

                        total_OT = OT_hours  # Only integer hours considered

                        # Ensure OT does not exceed the allowed limit
                        if total_OT > show_ot_limit:
                            applicable_OT = f"{int(show_ot_limit):02}.00"
                            remaining_OT_hours = int(total_OT - show_ot_limit)
                            remaining_OT = f"{remaining_OT_hours:02}.00"
                        else:
                            applicable_OT = f"{int(OT_hours):02}.00"

                # Convert work_hours to HH.MM format
                work_hours_hours, work_hours_remainder = divmod(work_hours.total_seconds(), 3600)
                work_hours_minutes, _ = divmod(work_hours_remainder, 60)

                # Apply rounding rule
                if work_hours_minutes >= 30:
                    work_hours_hours += 1
                    work_hours_minutes = 0
                else:
                    work_hours_minutes = 0

                final_work_hours = f"{int(work_hours_hours):02}.00"

                # Convert total_work_hours to HH.MM format
                total_hours_hours, total_hours_remainder = divmod(work_hours_timedelta.total_seconds(), 3600)
                total_hours_minutes, _ = divmod(total_hours_remainder, 60)

                # Apply rounding rule
                if total_hours_minutes >= 30:
                    total_hours_hours += 1
                    total_hours_minutes = 0
                else:
                    total_hours_minutes = 0

                final_total_hours = f"{int(total_hours_hours):02}.00"

                # === Holiday Check ===
                # Assuming 'date' is the date being processed (datetime.date object)
                # Assuming 'holiday_list' is the name of the Holiday List assigned to the employee
                # Assuming 'remaining_OT' is already initialized or tracked elsewhere

                holiday = frappe.db.exists('Holiday', {
                    'holiday_date': date,
                    'parent': holiday_list,
                    'weekly_off': 0  # General holiday only
                })

                if holiday:
                    # Add total work hours as OT (on general holiday)
                    remaining_OT_hours = float(final_total_hours)
                    applicable_OT = 0
                    remaining_OT = f"{remaining_OT_hours:02.2f}"


                # frappe.msgprint(f"Work Hours {final_work_hours}")
                # frappe.msgprint(f"Total Hours {final_total_hours}")
                # frappe.msgprint(f"Applicable Hours {applicable_OT}")
                # frappe.msgprint(f"Remaining Hours {remaining_OT}")

            

        

                # Calculate late entry, early exit
                half_day_hour = frappe.db.get_value('Shift Type', shift, 'working_hours_threshold_for_half_day')
                absent_hour = frappe.db.get_value('Shift Type', shift, 'working_hours_threshold_for_absent')

                shift_start_time = frappe.db.get_value('Shift Type', shift, 'start_time')
                late_entry_grace_period = frappe.db.get_value('Shift Type', shift, 'late_entry_grace_period')
                shift_start_time = frappe.utils.get_time(shift_start_time)
                shift_start_datetime = datetime.combine(date, shift_start_time)
                grace_late_datetime = frappe.utils.add_to_date(shift_start_datetime, minutes=late_entry_grace_period)
                grace_late_time = grace_late_datetime.time()
                

                shift_end_time = frappe.db.get_value('Shift Type', shift, 'end_time')
                early_exit_grace_period = frappe.db.get_value('Shift Type', shift, 'early_exit_grace_period')
                shift_end_time = frappe.utils.get_time(shift_end_time)
                if shift_type == 'Night':
                    shift_end_datetime = datetime.combine(date, shift_end_time)
                else:
                    shift_end_datetime = datetime.combine(tomorrow_date, shift_end_time)
                grace_early_datetime = frappe.utils.add_to_date(shift_end_datetime, minutes=-early_exit_grace_period)
                grace_early_time = grace_early_datetime.time()
                
                
                
                if first_checkin_time and first_checkin_time.time() > grace_late_time:
                    late_entry_timedelta = frappe.utils.time_diff(str(first_checkin_time), str(grace_late_time))
                    total_late_entry_seconds = late_entry_timedelta.total_seconds()
                    late_entry_hour = int(total_late_entry_seconds // 3600)
                    late_entry_minute = int((total_late_entry_seconds % 3600) // 60)
                    late_entry_hours_final = f"{late_entry_hour:02d}.{late_entry_minute:02d}"
                    att_late_entry = 1


                if last_checkout_time and last_checkout_time.time() < grace_early_time:
                    early_exit_timedelta = frappe.utils.time_diff(str(grace_early_time), str(last_checkout_time))
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
                exists_atte = frappe.db.get_value('Attendance', {'employee': emp_name, 'attendance_date': date, 'docstatus': 1}, ['name'])
                if exists_atte:
                    formatted_date = date.strftime("%d-%m-%Y")
                    attendance_link = frappe.utils.get_link_to_form("Attendance", exists_atte)
                    existing_attendances.append(f'Employee {emp_name}-{emp_full_name} for Date {formatted_date}: {attendance_link} \n')
                else:
                    
                    
                    attendance = frappe.new_doc("Attendance")
                    attendance.employee = emp_name
                    attendance.attendance_date = date
                    attendance.shift = shift
                    attendance.in_time = first_checkin_time
                    attendance.out_time = last_checkout_time
                    attendance.custom_employee_checkin = first_checkin
                    attendance.custom_employee_checkout = last_checkout
                    attendance.custom_total_hours = final_total_hours
                    attendance.custom_work_hours = final_work_hours
                    if emp_type == "Worker":
                        attendance.custom_overtime = applicable_OT
                        attendance.custom_remaining_overtime = remaining_OT
                    attendance.status = att_status
                    # attendance.custom_late_entry_hours = late_entry_hours_final
                    # attendance.custom_early_exit_hours = early_exit_hours_final
                    # attendance.late_entry = att_late_entry
                    # attendance.early_exit = att_early_exit
                    attendance.custom_remarks = att_remarks

                    attendance.insert(ignore_permissions=True)
                    attendance.submit()
                    frappe.db.commit()

                   
            
            elif first_checkin or last_checkout:
                exists_atte = frappe.db.get_value('Attendance', {'employee': emp_name, 'attendance_date': date, 'docstatus': 1}, ['name'])
                if exists_atte:
                    formatted_date = date.strftime("%d-%m-%Y")
                    attendance_link = frappe.utils.get_link_to_form("Attendance", exists_atte)
                    existing_attendances.append(f'Employee {emp_name}-{emp_full_name} for Date {formatted_date}: {attendance_link} \n')
                    
                else:
                    
                    attendance = frappe.new_doc("Attendance")
                    attendance.employee = emp_name
                    attendance.attendance_date = date
                    attendance.shift = shift

                    if first_checkin_time:
                        attendance.in_time = first_checkin_time
                        attendance.custom_employee_checkin = first_checkin
                        attendance.custom_remarks = 'No Checkout record found'
                    if last_checkout_time:
                        attendance.out_time = first_checkin_time
                        attendance.custom_employee_checkout = last_checkout
                        attendance.custom_remarks = 'No Checkin record found'
                    attendance.custom_total_hours = 0
                    attendance.custom_work_hours = 0
                    attendance.custom_overtime = 0
                    attendance.custom_remaining_overtime = 0
                    attendance.status = 'Mispunch'
                    # attendance.custom_late_entry_hours = 0
                    # attendance.custom_early_exit_hours = 0
                    # attendance.late_entry = 0
                    # attendance.early_exit = 0
                    

                    attendance.insert(ignore_permissions=True)
                    attendance.submit()
                    frappe.db.commit()

                    
    if existing_attendances:
        final_messages.append("Attendance already exists for:")
        final_messages.extend(existing_attendances)
    else:
        final_messages.append ("Attendance marked successfully")
    return final_messages        
        


@frappe.whitelist()
def schedule_mark_attendance(attendance_date=None):
    """Scheduled job to mark attendance for a date range, or for yesterday if no dates are provided."""
    
    # If from_date and to_date are not passed, default to yesterday's date
    if not attendance_date:
        attendance_date = frappe.utils.add_days(frappe.utils.nowdate(), -1)
    
    messages = mark_attendance(date=attendance_date)
    return messages
