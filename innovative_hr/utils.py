import frappe
from datetime import datetime, timedelta
from frappe.utils import add_days, today, time_diff, get_datetime, get_time

@frappe.whitelist(allow_guest=True)
def is_holiday(date, holiday_list):
    return frappe.db.get_value("Holiday", {
        "holiday_date": date,
        "parent": holiday_list
    }, ["weekly_off", "name"], as_dict=True)

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

    active_employees = frappe.db.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "date_of_joining", "employment_type", "holiday_list"]
    )

    final_messages = []
    existing_attendances = []
    results = {}  # Dictionary to store results for each employee

    for emp in active_employees:
        emp_name = emp["name"]
        emp_type = emp["employment_type"]
        emp_full_name = emp["employee_name"]
        emp_joining_date = emp.get("date_of_joining")
        holiday_list = emp.get("holiday_list")
        
        if emp_joining_date and emp_joining_date > date:
            continue

        # Get all checkin records for the employee across relevant dates
        all_checkin_records = frappe.db.get_all(
            "Employee Checkin",
            filters={
                "employee": emp_name,
                "custom_date": ["in", [yesterday_date, date, tomorrow_date]]
            },
            fields=["name", "custom_date", "log_type", "time", "shift", "custom_shift_type"],
            order_by="custom_date asc, time asc"
        )

        if not all_checkin_records:
            continue

        # Group records by shift and date
        shift_records = {}
        
        for record in all_checkin_records:
            record_shift = record.get('shift')
            record_date = record.get('custom_date')
            shift_type = record.get('custom_shift_type')
            
            # Only process records for the target date (IN records)
            if record_date == date and record['log_type'] == 'IN':
                if record_shift not in shift_records:
                    shift_records[record_shift] = {
                        'shift_name': record_shift,
                        'shift_type': shift_type,
                        'in_records': [],
                        'out_records': [],
                        'date': date
                    }
                shift_records[record_shift]['in_records'].append(record)
            
            # Handle OUT records based on shift type
            if record['log_type'] == 'OUT':
                # For day shifts, OUT should be on same date
                if shift_type == 'Day' and record_date == date:
                    if record_shift not in shift_records:
                        continue  # Skip if no corresponding IN record
                    shift_records[record_shift]['out_records'].append(record)
                
                # For night shifts, OUT should be on next date
                elif shift_type == 'Night' and ((record_date == tomorrow_date) or (record_date == date)):
                    # Find corresponding IN record from today
                    matching_in_found = False
                    for check_record in all_checkin_records:
                        if (check_record.get('custom_date') == date and 
                            check_record.get('shift') == record_shift and 
                            check_record.get('log_type') == 'IN'):
                            matching_in_found = True
                            break
                    
                    if matching_in_found:
                        if record_shift not in shift_records:
                            shift_records[record_shift] = {
                                'shift_name': record_shift,
                                'shift_type': shift_type,
                                'in_records': [],
                                'out_records': [],
                                'date': date
                            }
                        shift_records[record_shift]['out_records'].append(record)

        if not shift_records:
            continue

        # Determine how to group shifts based on shift types
        shift_combinations = determine_shift_combinations(shift_records)
        
        if emp_name not in results:
            results[emp_name] = []

        # Process each shift combination
        for combination in shift_combinations:
            results[emp_name].append({
                'emp_name': emp_name,
                'emp_type': emp_type,
                'emp_full_name': emp_full_name,
                'date': date,
                'shifts': combination['shifts'],
                'combination_type': combination['type'],
                'holiday_list': holiday_list
            })

    # Process attendance for each employee and shift combination
    for emp_name, emp_results in results.items():
        for result in emp_results:
            if result['combination_type'] == 'combined':
                process_combined_shift_attendance(result, existing_attendances)
            else:
                process_separate_shift_attendance(result, existing_attendances)

    if existing_attendances:
        final_messages.append("Attendance already exists for:")
        final_messages.extend(existing_attendances)
    else:
        final_messages.append("Attendance marked successfully")
    
    return final_messages

def determine_shift_combinations(shift_records):
    """Determine how to combine shifts based on their types"""
    
    if len(shift_records) == 1:
        # Single shift
        shift_name = list(shift_records.keys())[0]
        return [{
            'type': 'single',
            'shifts': [shift_records[shift_name]]
        }]
    
    elif len(shift_records) == 2:
        shifts = list(shift_records.values())
        shift_types = [shift['shift_type'] for shift in shifts]
        
        # Day + Night or Day + Day = Combined attendance
        if ('Day' in shift_types and 'Night' in shift_types and shift_types[0] == 'Day') or \
           (shift_types[0] == 'Day' and shift_types[1] == 'Day'):
            return [{
                'type': 'combined',
                'shifts': shifts
            }]
        
        # Night + Day = Separate attendances
        elif shift_types[0] == 'Night' and shift_types[1] == 'Day':
            return [
                {'type': 'single', 'shifts': [shifts[0]]},
                {'type': 'single', 'shifts': [shifts[1]]}
            ]
    
    # Default: process each shift separately
    return [{'type': 'single', 'shifts': [shift]} for shift in shift_records.values()]

def process_combined_shift_attendance(result, existing_attendances):
    """Process combined attendance for multiple shifts (Day+Night, Day+Day)"""
    
    emp_name = result.get('emp_name')
    emp_full_name = result.get('emp_full_name')
    date = result.get('date')
    shifts = result.get('shifts')
    holiday_list = result.get('holiday_list')
    emp_type = result.get('emp_type')
    
    # Get the first check-in and last check-out across all shifts
    all_in_records = []
    all_out_records = []
    primary_shift = shifts[0]['shift_name']  # Use first shift as primary
    
    for shift in shifts:
        all_in_records.extend(shift['in_records'])
        all_out_records.extend(shift['out_records'])
    
    # Sort by time
    all_in_records.sort(key=lambda x: x['time'])
    all_out_records.sort(key=lambda x: x['time'])
    
    first_checkin = all_in_records[0]['name'] if all_in_records else None
    first_checkin_time = all_in_records[0]['time'] if all_in_records else None
    last_checkout = all_out_records[-1]['name'] if all_out_records else None
    last_checkout_time = all_out_records[-1]['time'] if all_out_records else None
    
    
    # Check if attendance already exists
    exists_atte = frappe.db.get_value('Attendance', {
        'employee': emp_name,
        'attendance_date': date,
        'docstatus': 1
    }, ['name'])

    if exists_atte:
        formatted_date = date.strftime("%d-%m-%Y")
        attendance_link = frappe.utils.get_link_to_form("Attendance", exists_atte)
        existing_attendances.append(
            f'Employee {emp_name}-{emp_full_name} for Date {formatted_date}: {attendance_link} \n'
        )
        return

    # Calculate combined working hours and create attendance - PASS shifts FOR COMBINED CALCULATION
    attendance_data = calculate_attendance_data(
        emp_name, emp_type, date, primary_shift, holiday_list,
        first_checkin, last_checkout, first_checkin_time, last_checkout_time,
        shifts  # Pass shifts data for combined calculation
    )
    
    create_attendance_record(attendance_data)

def process_separate_shift_attendance(result, existing_attendances):
    """Process separate attendance for individual shifts (Night+Day scenario)"""
    
    shifts = result.get('shifts')
    
    for shift in shifts:
        single_result = {
            'emp_name': result.get('emp_name'),
            'emp_type': result.get('emp_type'),
            'emp_full_name': result.get('emp_full_name'),
            'date': result.get('date'),
            'shift': shift['shift_name'],
            'shift_type': shift['shift_type'],
            'holiday_list': result.get('holiday_list'),
            'in_records': shift['in_records'],
            'out_records': shift['out_records']
        }
        
        process_single_shift_attendance(single_result, existing_attendances)

def process_single_shift_attendance(result, existing_attendances):
    """Process attendance for a single shift"""
    
    emp_name = result.get('emp_name')
    emp_type = result.get('emp_type')
    emp_full_name = result.get('emp_full_name')
    date = result.get('date')
    shift = result.get('shift')
    holiday_list = result.get('holiday_list')
    in_records = result.get('in_records', [])
    out_records = result.get('out_records', [])
    
    first_checkin = in_records[0]['name'] if in_records else None
    first_checkin_time = in_records[0]['time'] if in_records else None
    last_checkout = out_records[-1]['name'] if out_records else None
    last_checkout_time = out_records[-1]['time'] if out_records else None

    # Check if attendance already exists for this specific shift
    exists_atte = frappe.db.get_value('Attendance', {
        'employee': emp_name,
        'attendance_date': date,
        'shift': shift,
        'docstatus': 1
    }, ['name'])

    if exists_atte:
        formatted_date = date.strftime("%d-%m-%Y")
        attendance_link = frappe.utils.get_link_to_form("Attendance", exists_atte)
        existing_attendances.append(
            f'Employee {emp_name}-{emp_full_name} for Date {formatted_date} Shift {shift}: {attendance_link} \n'
        )
        return

    # Calculate working hours and create attendance
    attendance_data = calculate_attendance_data(
        emp_name, emp_type, date, shift, holiday_list,
        first_checkin, last_checkout, first_checkin_time, last_checkout_time
    )
    
    create_attendance_record(attendance_data)

def calculate_attendance_data(emp_name, emp_type, date, shift, holiday_list,
                            first_checkin, last_checkout, first_checkin_time, last_checkout_time, shifts=None):
    """Calculate all attendance related data"""
    
    # Initialize default values
    final_total_hours = "0.00"
    final_work_hours = "0.00"
    applicable_OT = "0.00"
    remaining_OT = "0.00"
    att_status = 'Absent'
    att_remarks = ''

    # Get configurations
    standard_hours = frappe.db.get_value('Employee', emp_name, 'custom_standard_working_hours')
    OT_calculation_criteria = frappe.db.get_single_value('HR Settings', 'custom_show_overtime_in_salary_slip')
    
    if first_checkin_time and last_checkout_time:
        # Calculate work hours based on whether it's combined shifts or single shift
        if shifts and len(shifts) > 1:
            # Combined shifts - calculate hours for each shift separately and sum them
            total_work_hours = 0
            
            for shift_data in shifts:
                if shift_data['in_records'] and shift_data['out_records']:
                    shift_in_time = shift_data['in_records'][0]['time']
                    shift_out_time = shift_data['out_records'][-1]['time']
                  
                    # Calculate hours for this shift
                    shift_work_hours = time_diff(shift_out_time, shift_in_time)
                    shift_hours = shift_work_hours.total_seconds() / 3600
                    total_work_hours += shift_hours
                
            
        else:
            # Single shift - calculate normally
            work_hours = time_diff(last_checkout_time, first_checkin_time)
           
            total_work_hours = work_hours.total_seconds() / 3600

        # Convert standard_hours to timedelta if it's not already
        if isinstance(standard_hours, (int, float)):
            standard_hours_td = timedelta(hours=standard_hours)
        else:
            standard_hours_td = standard_hours

        # Convert total_work_hours to timedelta
        work_hours_timedelta = timedelta(hours=total_work_hours)
        
        # Work Hours (Capped at standard hours)
        capped_work_hours = min(work_hours_timedelta, standard_hours_td)

        # Calculate overtime
        emp_overtime_consent = frappe.db.get_value('Employee', emp_name, 'custom_overtime_applicable')
        show_ot_in_salslip = frappe.db.get_single_value('HR Settings', 'custom_show_overtime_in_salary_slip')
        show_ot_limit = float(show_ot_in_salslip) if show_ot_in_salslip else 0.0
        
        # Calculate Overtime if applicable
        if emp_overtime_consent == 1 and work_hours_timedelta > standard_hours_td:
            overtime_timedelta = work_hours_timedelta - standard_hours_td
            total_OT_seconds = overtime_timedelta.total_seconds()
            OT_calculation_criteria_seconds = (OT_calculation_criteria * 60) if OT_calculation_criteria else 0

            if total_OT_seconds > OT_calculation_criteria_seconds:
                # Convert overtime to hours and apply rounding
                OT_hours, OT_remainder = divmod(total_OT_seconds, 3600)
                OT_minutes, _ = divmod(OT_remainder, 60)

                if OT_minutes >= 30:
                    OT_hours += 1

                # Apply OT limit
                if OT_hours > show_ot_limit:
                    applicable_OT = f"{int(show_ot_limit):02}.00"
                    remaining_OT_hours = int(OT_hours - show_ot_limit)
                    remaining_OT = f"{remaining_OT_hours:02}.00"
                else:
                    applicable_OT = f"{int(OT_hours):02}.00"

        # Format work hours
        capped_hours, capped_remainder = divmod(capped_work_hours.total_seconds(), 3600)
        capped_minutes, _ = divmod(capped_remainder, 60)
        if capped_minutes >= 30:
            capped_hours += 1
        final_work_hours = f"{int(capped_hours):02}.00"

        # Format total hours
        total_hours_int, total_remainder = divmod(work_hours_timedelta.total_seconds(), 3600)
        total_minutes, _ = divmod(total_remainder, 60)
        if total_minutes >= 30:
            total_hours_int += 1
        final_total_hours = f"{int(total_hours_int):02}.00"

        # Holiday check
        holiday = frappe.db.exists('Holiday', {
            'holiday_date': date,
            'parent': holiday_list,
            'weekly_off': 0
        })

        if holiday:
            remaining_OT_hours = float(final_total_hours)
            applicable_OT = "0.00"
            remaining_OT = f"{remaining_OT_hours:02.2f}"

        # Determine status based on thresholds
        half_day_hour = frappe.db.get_value('Shift Type', shift, 'working_hours_threshold_for_half_day')
        absent_hour = frappe.db.get_value('Shift Type', shift, 'working_hours_threshold_for_absent')
        
        att_status = 'Present'
        if half_day_hour and total_work_hours < half_day_hour:
            att_status = 'Half Day'
        if absent_hour and total_work_hours < absent_hour:
            att_status = 'Absent'

    return {
        'emp_name': emp_name,
        'emp_type': emp_type,
        'date': date,
        'shift': shift,
        'holiday_list': holiday_list,
        'first_checkin': first_checkin,
        'last_checkout': last_checkout,
        'first_checkin_time': first_checkin_time,
        'last_checkout_time': last_checkout_time,
        'final_total_hours': final_total_hours,
        'final_work_hours': final_work_hours,
        'applicable_OT': applicable_OT,
        'remaining_OT': remaining_OT,
        'att_status': att_status,
        'att_remarks': att_remarks
    }

def create_attendance_record(attendance_data):
    """Create attendance record"""
    
    emp_name = attendance_data['emp_name']
    date = attendance_data['date']
    shift = attendance_data['shift']
    holiday_list = attendance_data['holiday_list']
    emp_type = attendance_data['emp_type']
    
    holiday_info = is_holiday(date, holiday_list)
    custom_weekoff_status = ""
    
    if holiday_info:
        if holiday_info.weekly_off and (attendance_data['first_checkin'] or attendance_data['last_checkout']):
            custom_weekoff_status = "WeekOff"
        elif not holiday_info.weekly_off:
            custom_weekoff_status = "Holiday"

    first_intime = None
    last_outtime = None
    
    if attendance_data['first_checkin_time']:
        first_indatetime = get_datetime(attendance_data['first_checkin_time'])
        first_intime = first_indatetime.time()
    if attendance_data['last_checkout_time']:
        last_indatetime = get_datetime(attendance_data['last_checkout_time'])
        last_outtime = last_indatetime.time()

    # Create attendance record
    attendance = frappe.new_doc("Attendance")
    attendance.employee = emp_name
    attendance.attendance_date = date
    attendance.shift = shift
    attendance.custom_weekoff_status = custom_weekoff_status

    if attendance_data['first_checkin'] and attendance_data['last_checkout']:
        # Regular attendance
        attendance.in_time = attendance_data['first_checkin_time']
        attendance.out_time = attendance_data['last_checkout_time']
        attendance.custom_checkin_time = first_intime
        attendance.custom_checkout_time = last_outtime
        attendance.custom_employee_checkin = attendance_data['first_checkin']
        attendance.custom_employee_checkout = attendance_data['last_checkout']
        attendance.custom_total_hours = attendance_data['final_total_hours']
        attendance.custom_work_hours = attendance_data['final_work_hours']

        if emp_type == "Worker":
            attendance.custom_overtime = attendance_data['applicable_OT']
            attendance.custom_remaining_overtime = attendance_data['remaining_OT']

        attendance.status = attendance_data['att_status']
        attendance.custom_remarks = attendance_data['att_remarks']

    elif attendance_data['first_checkin'] or attendance_data['last_checkout']:
        # Mispunch record
        if attendance_data['first_checkin_time']:
            attendance.in_time = attendance_data['first_checkin_time']
            attendance.custom_checkin_time = first_intime
            attendance.custom_employee_checkin = attendance_data['first_checkin']
            attendance.custom_remarks = 'No Checkout record found'

        if attendance_data['last_checkout_time']:
            attendance.out_time = attendance_data['last_checkout_time']
            attendance.custom_checkout_time = last_outtime
            attendance.custom_employee_checkout = attendance_data['last_checkout']
            if not attendance_data['first_checkin_time']:
                attendance.custom_remarks = 'No Checkin record found'

        attendance.custom_total_hours = "0.00"
        attendance.custom_work_hours = "0.00"
        attendance.custom_overtime = "0.00"
        attendance.custom_remaining_overtime = "0.00"
        attendance.status = 'Mispunch'

    attendance.insert(ignore_permissions=True)
    attendance.submit()
    frappe.db.commit()

@frappe.whitelist()
def schedule_mark_attendance(attendance_date=None):
    """Scheduled job to mark attendance for a date range, or for yesterday if no dates are provided."""
    
    if not attendance_date:
        attendance_date = frappe.utils.add_days(frappe.utils.nowdate(), -1)

    messages = mark_attendance(date=attendance_date)
    return messages