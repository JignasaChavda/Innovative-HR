import frappe
from frappe.utils import add_days, today, get_time, add_to_date, get_datetime, time_diff_in_seconds

def get_shift_timings(today_date, yesterday_date):
    shifts = frappe.get_all("Shift Type", fields=[
        "name", "start_time", "end_time", "custom_shift_type",
        "begin_check_in_before_shift_start_time", 
        "custom_allow_checkout_after_shift_start_time",
        "allow_check_out_after_shift_end_time",
        "custom_allow_checkout_before_shift_end_time"
    ])
    
    shift_data = []
    for shift in shifts:
        shift_start = get_time(shift["start_time"])
        shift_end = get_time(shift["end_time"])
        shift_type = shift.get("custom_shift_type", "Day")  # Default to 'Day' if not set

        shift_date = today_date

        before_shift_start_grace = shift.get("begin_check_in_before_shift_start_time", 0) or 0
        after_shift_start_grace = shift.get("custom_allow_checkout_after_shift_start_time", 0) or 0
        before_shift_end_grace = shift.get("custom_allow_checkout_before_shift_end_time", 0) or 0
        after_shift_end_grace = shift.get("allow_check_out_after_shift_end_time", 0) or 0

        shift_start = get_datetime(f"{shift_date} {shift_start}")
        shift_end = get_datetime(f"{shift_date} {shift_end}")
        shift_actual_start = add_to_date(shift_start, minutes=-before_shift_start_grace)
        shift_actual_end = add_to_date(shift_start, minutes=+after_shift_end_grace)
        grace_after_shift_actual_start = add_to_date(shift_start, minutes=after_shift_start_grace)
        grace_before_shift_actual_end = add_to_date(shift_end, minutes=-after_shift_start_grace)

        shift_data.append({
            "shift_name": shift["name"],
            "shift_type": shift_type,
            "shift_start": shift_start,
            "shift_end": shift_end,
            "actual_start": shift_actual_start,
            "actual_end": shift_actual_end,
            "grace_after_shift_start": grace_after_shift_actual_start,
            "grace_before_shift_end": grace_before_shift_actual_end
        })
    
    return shift_data

def is_in_time_within_shift(in_time, shift_actual_start, grace_after_shift_start):
    return shift_actual_start <= in_time <= grace_after_shift_start

def before_save(self, method=None):
    date_time = get_datetime(self.time)
    self.custom_date = date_time.date()
    today_date = date_time.date()
    yesterday_date = add_days(date_time.date(), -1)

    if self.log_type == "IN":
        # Check if an IN log already exists for the day
        first_log = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "log_type": "IN",
            "custom_date": self.custom_date
        }, order_by="time ASC", limit=1)

        if not first_log:  # If no IN log exists, it's the first log of the day
            
            shift_data = get_shift_timings(today_date, yesterday_date)

            for shift in shift_data:
                if is_in_time_within_shift(date_time, shift["actual_start"], shift["grace_after_shift_start"]):
                    self.shift = shift["shift_name"]
                    break

    elif self.log_type == "OUT":
        # Check if an IN log exists for the same day
        in_log = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "log_type": "IN",
            "custom_date": self.custom_date
        }, fields=["name", "shift", "time"], order_by="time ASC", limit=1)

        if in_log:
            # Check if OUT log time is before 00:00:00
            midnight_time = get_datetime(f"{self.custom_date} 23:59:59")
            
            
            if self.time <= midnight_time:
                self.shift = in_log[0]["shift"]
            
        yesterday_in = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "log_type": "IN",
            "custom_date": yesterday_date
        }, fields=["name", "shift", "time"], order_by="time ASC", limit=1)

        

        if yesterday_in:
            self.shift = yesterday_in[0]["shift"]
        else:
            shift_data = get_shift_timings(today_date, yesterday_date)

            for shift in shift_data:
                if is_in_time_within_shift(date_time, shift["grace_before_shift_end"], shift["actual_end"]):
                    self.shift = shift["shift_name"]
                    break

