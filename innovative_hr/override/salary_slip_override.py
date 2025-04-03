import frappe
from frappe import _
from hrms.hr.doctype.leave_application.leave_application import validate_active_employee
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip as TransactionBase, sanitize_expression

def convert_to_hour_minute(decimal_hours):
    if decimal_hours is None:
        return 0, 0  # Return (0 hours, 0 minutes)
    
    hours = int(decimal_hours)  # Extract the integer part as hours
    minutes = round((decimal_hours - hours) * 60)  # Convert decimal part to minutes

    return hours, minutes  # Return tuple (hours, minutes)

def add_hours_and_minutes(time1, time2):
    h1, m1 = time1
    h2, m2 = time2

    total_hours = h1 + h2  # Sum of hours
    total_minutes = m1 + m2  # Sum of minutes

    # Convert minutes into extra hours if >= 60
    if total_minutes >= 60:
        extra_hours = total_minutes // 60  # Get extra hours
        total_hours += extra_hours  # Add extra hours to total hours
        total_minutes %= 60  # Remaining minutes after converting to hours

    return f"{total_hours}.{total_minutes:02d}"  # Ensure two-digit minute format

class SalarySlip(TransactionBase):
    def validate(self):
        self.check_salary_withholding()
        self.status = self.get_status()
        validate_active_employee(self.employee)
        self.validate_dates()
        self.check_existing()
        

        if self.payroll_frequency:
            self.get_date_details()

        if not (len(self.get("earnings")) or len(self.get("deductions"))):
            # get details from salary structure
            self.get_emp_and_working_day_details()
        else:
            self.get_working_days_details(lwp=self.leave_without_pay)
        self.calculate_ot_for_company_workers()
        self.calculate_total_hours_for_contractor()

        self.set_new_working_days()
        self.set_salary_structure_assignment()
        if self.is_new():
            self.calculate_net_pay()
        self.compute_year_to_date()
        self.compute_month_to_date()
        self.compute_component_wise_year_to_date()

        self.add_leave_balances()

        max_working_hours = frappe.db.get_single_value(
            "Payroll Settings", "max_working_hours_against_timesheet"
        )
        
        if max_working_hours:
            if self.salary_slip_based_on_timesheet and (self.total_working_hours > int(max_working_hours)):
                frappe.msgprint(
                    _("Total working hours should not be greater than max working hours {0}").format(
                        max_working_hours
                    ),
                    alert=True,
                )
        
        
        
        
    def set_new_working_days(self):
        
        absent_days = 0.0
        start_date = frappe.utils.getdate(self.start_date)
        end_date = frappe.utils.getdate(self.end_date)
        emp_type = frappe.get_value('Employee', self.employee, 'employment_type')
        holiday_list = frappe.get_value('Employee', self.employee, 'holiday_list')
        joining_date = frappe.db.get_value('Employee', self.employee, 'date_of_joining')
        joining_date = frappe.utils.getdate(joining_date) if joining_date else None
        relieving_date = frappe.db.get_value('Employee', self.employee, 'relieving_date')
        currency = frappe.db.get_value('Employee', self.employee, 'salary_currency')
        duration_in_days = (end_date - start_date).days + 1
        if joining_date:
            joining_duration_days = (joining_date - start_date).days
        if relieving_date:
            relieving_duration_days = (end_date - relieving_date).days 
        
        

        # Calculate working days based on the employement type
        if emp_type in ["Worker"] and holiday_list:
            holidays = frappe.get_all(
                    "Holiday",
                    filters={
                        "parent": holiday_list,
                        "holiday_date": ["between", [start_date, end_date]]
                    },
                    pluck="holiday_date"
                )
            duration_in_days = duration_in_days-len(holidays)
               
        if emp_type in ["Staff", "Staff Trainee"]:
            duration_in_days = duration_in_days
        


        # Calculate absent days for mid-month employee joining
        if joining_date and relieving_date and joining_date.month == relieving_date.month:
            if start_date < joining_date <= end_date and start_date < relieving_date <= end_date:
                if emp_type in ["Worker"] and holiday_list:
                    joining_holidays = frappe.get_all(
                        "Holiday",
                        filters={
                            "parent": holiday_list,
                            "holiday_date": ["between", [start_date, joining_date]]
                        },
                        pluck="holiday_date"
                    )
                    relieving_holidays = frappe.get_all(
                        "Holiday",
                        filters={
                            "parent": holiday_list,
                            "holiday_date": ["between", [relieving_date, end_date]]
                        },
                        pluck="holiday_date"
                    )
                    absent_days = (joining_duration_days - len(joining_holidays)) + (relieving_duration_days - len(relieving_holidays))

                elif emp_type in ["Staff", "Staff Trainee"]:
                    absent_days = joining_duration_days + relieving_duration_days

        else:
            if joining_date and start_date < joining_date <= end_date:
                if emp_type in ["Worker"] and holiday_list:
                    joining_holidays = frappe.get_all(
                        "Holiday",
                        filters={
                            "parent": holiday_list,
                            "holiday_date": ["between", [start_date, joining_date]]
                        },
                        pluck="holiday_date"
                    )
                    absent_days = joining_duration_days - len(joining_holidays)

                elif emp_type in ["Staff", "Staff Trainee"]:
                    absent_days = joining_duration_days

            if relieving_date and start_date < relieving_date <= end_date:
                if emp_type in ["Worker"] and holiday_list:
                    relieving_holidays = frappe.get_all(
                        "Holiday",
                        filters={
                            "parent": holiday_list,
                            "holiday_date": ["between", [relieving_date, end_date]]
                        },
                        pluck="holiday_date"
                    )
                    absent_days = relieving_duration_days - len(relieving_holidays)

                elif emp_type in ["Staff", "Staff Trainee"]:
                    absent_days = relieving_duration_days

    
        self.total_working_days = duration_in_days
        self.absent_days = self.absent_days + absent_days
        self.payment_days = self.total_working_days - (self.leave_without_pay + self.absent_days)
        
    

    def calculate_ot_for_company_workers(self):
        """
        Method to Calculate Overtime based on the Attendance Records
        """
        try:
            emp_id = self.employee
            emp_type = self.custom_employment_type
            start_date = self.start_date
            end_date = self.end_date

            if emp_type == "Worker":
                # Fetch overtime and remaining overtime for all relevant attendances
                attendances = frappe.get_all(
                    "Attendance",
                    filters={
                        "employee": emp_id,
                        "attendance_date": ["between", (start_date, end_date)],
                        "status": "Present",
                    },
                    fields=["custom_overtime", "custom_remaining_overtime"]
                )

                # Initialize total overtime and remaining overtime (in hours & minutes)
                applicable_hours, applicable_minutes = 0, 0
                remaining_hours, remaining_minutes = 0, 0

                for attendance in attendances:
                    # Extract and convert overtime
                    if attendance.custom_overtime:
                        applicable_ot_hours = int(attendance.custom_overtime)
                        applicable_ot_minutes = round((attendance.custom_overtime - applicable_ot_hours) * 60)
                        
                        # Add to total
                        applicable_hours += applicable_ot_hours
                        applicable_minutes += applicable_ot_minutes
                    
                    # Extract and convert remaining overtime
                    if attendance.custom_remaining_overtime:
                        remaining_ot_hours = int(attendance.custom_remaining_overtime)
                        remaining_ot_minutes = round((attendance.custom_remaining_overtime - remaining_ot_hours) * 60)
                        
                        # Add to remaining total
                        remaining_hours += remaining_ot_hours
                        remaining_minutes += remaining_ot_minutes

                # Convert excess minutes to hours
                applicable_hours += applicable_minutes // 60
                applicable_minutes = applicable_minutes % 60

                remaining_hours += remaining_minutes // 60
                remaining_minutes = remaining_minutes % 60


                # applicable_ot_hours = int(applicable_overtime)
                # remaining_ot_hours = int(remaining_overtime)

                # applicable_ot_minutes = round((applicable_overtime - applicable_ot_hours) * 60)
                # remaining_ot_minutes = round((remaining_overtime - remaining_ot_hours) * 60)

                final_applicable_hours = f"{int(applicable_hours):02}.{int(applicable_minutes):02}"
                final_remaining_hours = f"{int(remaining_hours):02}.{int(remaining_minutes):02}"
                
                # self.custom_applicable_overtime = final_applicable_hours or 0
                # self.custom_remaining_overtime = final_remaining_hours or 0

                frappe.msgprint(str(remaining_hours))
                frappe.msgprint(str(remaining_minutes))


        except Exception as e: 
            frappe.throw(str(e))
        
    def calculate_total_hours_for_contractor(self):
        """
        Method to Calculate Overtime based on the Attendance Records
        """
        try:
            
            emp_id = self.employee
            start_date = self.start_date
            end_date = self.end_date
            
            
            total_hours = frappe.db.get_value("Attendance", {"employee": emp_id, "attendance_date": ["between", (start_date, end_date)], "status": "Present"}, ["sum(custom_total_hours)"])
            
            if total_hours is not None:
                rounded_hours = round(total_hours)  # round to 2 decimal places
            else:
                rounded_hours = 0.0
            self.custom_total_worked_hours = rounded_hours
            
        except Exception as e: 
            frappe.throw(str(e))
    
   