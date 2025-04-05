import frappe
from frappe import _
from frappe.auth import today
from hrms.hr.doctype.leave_application.leave_application import validate_active_employee
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip as TransactionBase, sanitize_expression

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

        self.set_new_working_days()
        self.calculate_overtime()
        self.set_salary_structure_assignment()
        if self.is_new():
            self.calculate_net_pay()
        self.compute_year_to_date()
        self.compute_month_to_date()
        self.compute_component_wise_year_to_date()

        self.add_leave_balances()
        self.generate_additional_salary()

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
        
    def calculate_overtime(self):
        """
        Method to Calculate Overtime based on the Attendance Records,
        excluding holidays.
        """
        try:
            emp_id = self.employee
            emp_type = self.custom_employment_type
            start_date = self.start_date
            end_date = self.end_date

            # Get list of holidays for the employee's holiday list
            holiday_dates = frappe.get_all("Holiday", 
                filters={
                    "holiday_date": ["between", [start_date, end_date]],
                },
                fields=["holiday_date"]
            )
            holiday_list = [d.holiday_date for d in holiday_dates]

            # Common filters excluding holidays
            filters = {
                "employee": emp_id,
                "attendance_date": ["between", [start_date, end_date]],
                "status": "Present",
                "attendance_date": ["not in", holiday_list] if holiday_list else ["between", [start_date, end_date]]
            }

            if emp_type == 'Worker':
                # Fetch attendance records manually and sum values
                records = frappe.get_all("Attendance",
                    filters={
                        "employee": emp_id,
                        "status": "Present",
                        "attendance_date": ["between", [start_date, end_date]]
                    },
                    fields=["custom_overtime", "custom_remaining_overtime", "attendance_date"]
                )

                applicable_ot = 0
                remaining_ot = 0
                for row in records:
                    if row.attendance_date not in holiday_list:
                        applicable_ot += row.custom_overtime or 0
                        remaining_ot += row.custom_remaining_overtime or 0

                self.custom_applicable_overtime = applicable_ot
                self.custom_remaining_overtime = remaining_ot

            elif emp_type == 'Contract':
                # Fetch total worked hours excluding holidays
                records = frappe.get_all("Attendance",
                    filters={
                        "employee": emp_id,
                        "status": "Present",
                        "attendance_date": ["between", [start_date, end_date]]
                    },
                    fields=["custom_total_hours", "attendance_date"]
                )

                total_hours = 0
                for row in records:
                    if row.attendance_date not in holiday_list:
                        total_hours += row.custom_total_hours or 0

                self.custom_total_worked_hours = total_hours

        except Exception as e:
            frappe.throw(str(e))
    
    def generate_additional_salary(self):
        if self.custom_employment_type == "Worker":
            holiday_list = frappe.db.get_value("Employee", self.employee, "holiday_list")
            per_day_wage = frappe.db.get_value('Employee', self.employee, 'custom_per_day_wages')
            per_hour_wage = frappe.db.get_value('Employee', self.employee, 'custom_per_hour_wages')

            # For Remaining Overtime
            try:
                existing_remaining_ot_incentive = frappe.db.exists(
                    "Employee Incentive",
                    {
                        "employee": self.employee,
                        "custom_reference_salary_slip": self.name,
                        "custom_incentive_paid_for": "Remaining Overtime"
                    }
                )
                
                if not existing_remaining_ot_incentive:
                    for_remaining_ot = frappe.new_doc("Employee Incentive")
                    for_remaining_ot.employee = self.employee
                    for_remaining_ot.custom_posting_date = today()
                    for_remaining_ot.custom_include_in_salary_slip = 0
                    for_remaining_ot.custom_incentive_paid_for = "Remaining Overtime"
                    for_remaining_ot.custom_remaining_overtime_hours = self.custom_remaining_overtime
                    for_remaining_ot.salary_component = "Remaining Overtime Payment"  
                    for_remaining_ot.incentive_amount = round(per_hour_wage * self.custom_remaining_overtime)
                    for_remaining_ot.custom_incentive_payable = round(per_hour_wage * self.custom_remaining_overtime)
                    for_remaining_ot.custom_reference_salary_slip = self.name
                
                    for_remaining_ot.insert(ignore_permissions=True)

            except Exception as e:
                frappe.throw(str(e))

            # For Weekoff Payment
            try:
                total_weekoff_wage = 0
                weekoff_count = 0  # <-- To track total equivalent weekoff days worked

                if holiday_list:
                    # Get dates marked as weekoff in the holiday list
                    weekoff_dates = frappe.get_all("Holiday",
                        filters={
                            "parent": holiday_list,
                            "weekly_off": 1  # assuming there's a checkbox field named 'weekly_off'
                        },
                        fields=["holiday_date"]
                    )
                    weekoff_dates = [d.holiday_date for d in weekoff_dates]

                    # Check attendance records on weekoff dates
                    if weekoff_dates:
                        worked_on_weekoff = frappe.get_all("Attendance",
                            filters={
                                "employee": self.employee,
                                "status": ["in", ["Present", "Half Day"]],
                                "attendance_date": ["in", weekoff_dates],
                                "docstatus": 1
                            },
                            fields=["name", "attendance_date", "status", "custom_work_hours", "custom_total_hours"]
                        )
                        
                        for att in worked_on_weekoff:
                            total_hours = float(att.custom_total_hours or 0)
                            work_hours = float(att.custom_work_hours or 0)

                            # Count logic: Present = 1, Half Day = 0.5
                            if att.status == "Present":
                                weekoff_count += 1
                                if total_hours > work_hours:
                                    extra_hours = total_hours - work_hours
                                    wage = per_day_wage + (per_hour_wage * extra_hours)
                                else:
                                    wage = per_day_wage
                            elif att.status == "Half Day":
                                weekoff_count += 0.5
                                wage = per_day_wage / 2
                            else:
                                wage = 0

                            total_weekoff_wage += wage

                        total_weekoff_wage = round(total_weekoff_wage)

                        # Check if incentive already exists
                        existing_weekoff_incentive = frappe.db.exists(
                            "Employee Incentive",
                            {
                                "employee": self.employee,
                                "custom_reference_salary_slip": self.name,
                                "custom_incentive_paid_for": "Worked on WeekOff"
                            }
                        )
                        if not existing_weekoff_incentive and weekoff_count > 0:
                            for_weekoff = frappe.new_doc("Employee Incentive")
                            for_weekoff.employee = self.employee
                            for_weekoff.custom_posting_date = today()
                            for_weekoff.custom_include_in_salary_slip = 0
                            for_weekoff.custom_incentive_paid_for = "Worked on WeekOff"
                            for_weekoff.custom_worked_weekoff_count = weekoff_count  # <-- now includes 0.5 for Half Day
                            for_weekoff.salary_component = "WeekOff Incentive"
                            for_weekoff.incentive_amount = total_weekoff_wage
                            for_weekoff.custom_incentive_payable = total_weekoff_wage
                            for_weekoff.custom_reference_salary_slip = self.name

                            for_weekoff.insert(ignore_permissions=True)

            except Exception as e:
                frappe.throw(str(e))
            

            # For General Holiday Payment
            try:
                total_holiday_wage = 0
                holiday_count = 0  # <-- To track total equivalent weekoff days worked

                if holiday_list:
                    # Get dates marked as weekoff in the holiday list
                    holiday_dates = frappe.get_all("Holiday",
                        filters={
                            "parent": holiday_list,
                            "weekly_off": 0  # assuming there's a checkbox field named 'weekly_off'
                        },
                        fields=["holiday_date"]
                    )
                    holiday_dates = [d.holiday_date for d in holiday_dates]

                    # Check attendance records on weekoff dates
                    if holiday_dates:
                        worked_on_holiday = frappe.get_all("Attendance",
                            filters={
                                "employee": self.employee,
                                "status": ["in", ["Present", "Half Day"]],
                                "attendance_date": ["in", holiday_dates],
                                "docstatus": 1
                            },
                            fields=["name", "attendance_date", "status", "custom_work_hours", "custom_total_hours"]
                        )
                       

                        for att in worked_on_holiday:
                            total_hours = float(att.custom_total_hours or 0)
                            work_hours = float(att.custom_work_hours or 0)

                            # Count logic: Present = 1, Half Day = 0.5
                            if att.status == "Present":
                                holiday_count += 1
                                if total_hours > work_hours:
                                    extra_hours = total_hours - work_hours
                                    wage = per_day_wage + (per_hour_wage * extra_hours)
                                else:
                                    wage = per_day_wage
                            elif att.status == "Half Day":
                                holiday_count += 0.5
                                wage = per_day_wage / 2
                            else:
                                wage = 0

                            total_holiday_wage += wage

                        total_holiday_wage = round(total_holiday_wage*2)

                        # Check if incentive already exists
                        existing_holiday_incentive = frappe.db.exists(
                            "Employee Incentive",
                            {
                                "employee": self.employee,
                                "custom_reference_salary_slip": self.name,
                                "custom_incentive_paid_for": "Worked on Holiday"
                            }
                        )
                        if not existing_holiday_incentive and weekoff_count > 0:
                            for_holiday = frappe.new_doc("Employee Incentive")
                            for_holiday.employee = self.employee
                            for_holiday.custom_posting_date = today()
                            for_holiday.custom_include_in_salary_slip = 0
                            for_holiday.custom_incentive_paid_for = "Worked on Holiday"
                            for_holiday.custom_worked_holiday_count = holiday_count  # <-- now includes 0.5 for Half Day
                            for_holiday.salary_component = "Holiday Incentive"
                            for_holiday.incentive_amount = total_holiday_wage
                            for_holiday.custom_incentive_payable = total_holiday_wage
                            for_holiday.custom_reference_salary_slip = self.name

                            for_holiday.insert(ignore_permissions=True)

            except Exception as e:
                frappe.throw(str(e))



