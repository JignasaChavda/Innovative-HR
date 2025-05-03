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
    }, order_by="time ASC", limit=1)

    if not first_log:
       
        night_in_yesterday = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "custom_date": yesterday_date,
            "custom_shift_type": "Night",
            "log_type": "IN"
        }, fields=["name", "shift", "custom_shift_type", "time"], limit=1)

        night_out_today = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "custom_date": today_date,
            "custom_shift_type": "Night",
            "log_type": "OUT"
        }, limit=1)

        if night_in_yesterday and not night_out_today:
            # Set current log as OUT for the night shift
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
       
        
        # Get all IN logs for the day
        in_logs = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "log_type": "IN",
            "custom_date": self.custom_date
        }, fields=["name", "shift", "custom_shift_type", "time"], order_by="time ASC")
        
        # Get all OUT logs for the day
        out_logs = frappe.get_all("Employee Checkin", filters={
            "employee": self.employee,
            "log_type": "OUT",
            "custom_date": self.custom_date
        }, fields=["name", "shift", "custom_shift_type", "time"], order_by="time ASC")

        matched = False
        
        if in_logs:
            for in_log in in_logs:
                # Find the first OUT log which is after this IN log and for same shift
                corresponding_out = None
                for out_log in out_logs:
                    if out_log["shift"] == in_log["shift"] and out_log["time"] > in_log["time"]:
                        corresponding_out = out_log
                        break

                if not corresponding_out:
                    # No OUT found yet for this IN
                    midnight_time = get_datetime(f"{self.custom_date} 23:59:59")
                    if self.time <= midnight_time:
                        self.shift = in_log["shift"]
                        self.log_type = "OUT"
                        self.custom_shift_type = in_log["custom_shift_type"]
                        matched = True
                        break

        if not matched:
            # No matching IN-OUT, so it must be a fresh IN entry
            shift_data = get_shift_timings(today_date, yesterday_date)
            for shift in shift_data:
                if is_in_time_within_shift(date_time, shift["actual_start"], shift["grace_after_shift_start"]):
                    self.shift = shift["shift_name"]
                    self.log_type = 'IN'
                    self.custom_shift_type = shift["shift_type"]
                    break


def on_update(self, method=None):
    date_time = get_datetime(self.time)

    # Perform the deletion AFTER the current document has been saved
    last_log = frappe.get_all("Employee Checkin", filters={
        "employee": self.employee,
        "name": ["!=", self.name]
    }, fields=["name", "time", "shift"], order_by="time DESC", limit=1)

    if last_log:
        last_log_time = get_datetime(last_log[0]["time"])
        last_shift = (last_log[0].get("shift") or "").strip()
        current_shift = (self.shift or "").strip()
        # frappe.msgprint(str(last_shift))
        # frappe.msgprint(str(current_shift))

        if (
            date_time.time().hour == last_log_time.time().hour and
            date_time.time().minute == last_log_time.time().minute and
            date_time.time().second != last_log_time.time().second
        ):
            frappe.delete_doc("Employee Checkin", self.name)

