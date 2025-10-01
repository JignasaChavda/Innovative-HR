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
        shift_actual_end = add_to_date(shift_end, minutes=after_shift_end_grace)
        grace_after_shift_actual_start = add_to_date(shift_start, minutes=after_shift_start_grace)
        grace_before_shift_actual_end = add_to_date(shift_end, minutes=-before_shift_end_grace)

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
    if getattr(self.flags, "skip_custom_logic", False):
        return  # Skip logic for auto attendance
        
    date_time = get_datetime(self.time)
    self.custom_date = date_time.date()
    today_date = date_time.date()
    yesterday_date = add_days(date_time.date(), -1)

    # Determine IN/OUT based on shift logic
    first_log = frappe.get_all("Employee Checkin", filters={
        "employee": self.employee,
        "log_type": "IN",
        "custom_date": self.custom_date
    }, fields=["name", "shift", "custom_shift_type", "time"], order_by="time ASC", limit=1)
    
    if not first_log:
    # Fetch records for yesterday's night shift logs
        night_in_yesterday = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "custom_date": yesterday_date,
            "custom_shift_type": "Night",
            "log_type": "IN"
        }, fields=["name", "shift", "custom_shift_type", "time"], limit=1)
        
        night_out_yesterday = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "custom_date": yesterday_date,
            "custom_shift_type": "Night",
            "log_type": "OUT"
        }, fields=["name", "shift", "custom_shift_type", "time"], limit=1, order_by="time DESC")

        night_out_today = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "custom_date": today_date,
            "custom_shift_type": "Night",
            "log_type": "OUT"
        }, limit=1)

       

        # Check if there is a 'night_in_yesterday' record
        if night_in_yesterday:
            
            
            # Extract the time for comparison
            night_in_time = night_in_yesterday[0]["time"] if night_in_yesterday else None
            night_out_time_yesterday = night_out_yesterday[0]["time"] if night_out_yesterday else None

            # Check if the night shift from yesterday was completed
            if night_out_yesterday and night_in_time < night_out_time_yesterday:
               
                
                # Night shift is complete, check for day shift
                shift_data = get_shift_timings(today_date, yesterday_date)
                for shift in shift_data:
                    if is_in_time_within_shift(date_time, shift["actual_start"], shift["grace_after_shift_start"]):
                      
                        self.shift = shift["shift_name"]
                        self.log_type = 'IN'
                        self.custom_shift_type = shift["shift_type"]
                        break

            # Night shift from yesterday is NOT complete yet
            elif (not night_out_yesterday) and (not night_out_today):
               
                self.shift = night_in_yesterday[0]["shift"]
                self.log_type = "OUT"
                self.custom_shift_type = night_in_yesterday[0]["custom_shift_type"]
            
            else:
                
                shift_data = get_shift_timings(today_date, yesterday_date)
                for shift in shift_data:
                    if is_in_time_within_shift(date_time, shift["actual_start"], shift["grace_after_shift_start"]):
                        
                        self.shift = shift["shift_name"]
                        self.log_type = 'IN'
                        self.custom_shift_type = shift["shift_type"]
                        break
        else:
                
                shift_data = get_shift_timings(today_date, yesterday_date)
                for shift in shift_data:
                    if is_in_time_within_shift(date_time, shift["actual_start"], shift["grace_after_shift_start"]):
                       
                        self.shift = shift["shift_name"]
                        self.log_type = 'IN'
                        self.custom_shift_type = shift["shift_type"]
                        break


    else:
        # Get shift data
        shift_data = get_shift_timings(today_date, yesterday_date)
        
        log_marked = False
        
        # Get all IN logs for today (to check for multiple shifts)
        all_in_logs = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "log_type": "IN",
            "custom_date": self.custom_date
        }, fields=["name", "shift", "custom_shift_type", "time"], order_by="time ASC")
        
        # Get all OUT logs for today
        all_out_logs = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "log_type": "OUT",
            "custom_date": self.custom_date
        }, fields=["name", "shift", "custom_shift_type", "time"], order_by="time ASC")
        
       
        # First priority: Check if there's any shift with IN but no OUT
        # This should be marked as OUT for that shift
        for in_log in all_in_logs:
            has_corresponding_out = False
            for out_log in all_out_logs:
                if out_log["shift"] == in_log["shift"] and out_log["time"] > in_log["time"]:
                    has_corresponding_out = True
                    break
            
            if not has_corresponding_out:
                # Found an IN without OUT - mark current punch as OUT
                self.shift = in_log["shift"]
                self.log_type = 'OUT'
                self.custom_shift_type = in_log["custom_shift_type"]
                log_marked = True
                break
        
        # Second priority: If all existing shifts are complete (have IN and OUT)
        # Check if current time falls within a new shift's IN window
        if not log_marked:
            for shift in shift_data:
                
                
                if is_in_time_within_shift(date_time, shift["actual_start"], shift["grace_after_shift_start"]):
                    
                    
                    # Check if this specific shift already has an IN log
                    shift_has_in = False
                    shift_has_out = False
                    
                    for in_log in all_in_logs:
                        if in_log["shift"] == shift["shift_name"]:
                            shift_has_in = True
                            # Check if this IN has a corresponding OUT
                            for out_log in all_out_logs:
                                if out_log["shift"] == shift["shift_name"] and out_log["time"] > in_log["time"]:
                                    shift_has_out = True
                                    break
                            break
                    
                   
                    
                    # Only mark as IN if:
                    # 1. This shift has no IN yet, OR
                    # 2. This shift has both IN and OUT (completed cycle)
                    if not shift_has_in or (shift_has_in and shift_has_out):
                        self.shift = shift["shift_name"]
                        self.log_type = 'IN'
                        self.custom_shift_type = shift["shift_type"]
                        log_marked = True
                       
                        break
        
      
        
        # If still not marked, default to OUT for the first shift
        if not log_marked:
            self.shift = first_log[0]["shift"]
            self.custom_shift_type = first_log[0]["custom_shift_type"]
            self.log_type = "OUT"
          