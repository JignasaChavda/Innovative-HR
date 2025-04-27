from datetime import datetime, timedelta
import frappe
from frappe.utils import add_days, get_time, time_diff


def before_save(self, method=None):
    
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
    

    date = self.attendance_date
    if isinstance(date, str):
        date = datetime.strptime(date, "%Y-%m-%d").date()

    yesterday_date = date - timedelta(days=1)
    tomorrow_date = date + timedelta(days=1)

    emp = self.employee
    date = self.attendance_date
    holiday_list = frappe.db.set_value('Employee', emp, 'holiday_list')
    first_checkin_time = self.in_time
    first_in_time = get_time(first_checkin_time) if first_checkin_time else None
    
    last_checkout_time = self.out_time
    last_out_time = get_time(last_checkout_time) if last_checkout_time else None
    shift = self.shift
    shift_hours = frappe.db.get_value("Shift Type", shift, "custom_shift_hours")
    shift_type = frappe.db.get_value("Shift Type", shift, "custom_shift_type")
    OT_calculation_criteria = frappe.db.get_value("Shift Type", shift, "custom_overtime_calculate_criteria")


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
        emp_overtime_consent = frappe.db.get_value('Employee', emp, 'custom_overtime_applicable')
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

        # Update the attendance
        self.shift = shift
        self.in_time = first_checkin_time
        self.out_time = last_checkout_time
        self.custom_total_hours = final_total_hours
        self.custom_work_hours = final_work_hours
        if self.custom_employment_type == "Worker":
            self.custom_overtime = applicable_OT
            self.custom_remaining_overtime = remaining_OT
        self.status = att_status
        self.custom_late_entry_hours = late_entry_hours_final
        self.custom_early_exit_hours = early_exit_hours_final
        self.late_entry = att_late_entry
        self.early_exit = att_early_exit
        self.custom_remarks = att_remarks
    

           