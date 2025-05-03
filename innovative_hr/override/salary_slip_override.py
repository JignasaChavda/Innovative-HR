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
        self.validate_employee_incentive()
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
        
        
    def after_insert(self):
        self.generate_employee_incentive()
        
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
                        "holiday_date": ["between", [start_date, end_date]],
                        "weekly_off": 1
                    },
                    pluck="holiday_date"
                )
            
            weekoffplusholidays = frappe.get_all(
                    "Holiday",
                    filters={
                        "parent": holiday_list,
                        "holiday_date": ["between", [start_date, end_date]],
                        "weekly_off": 1,
                        "custom_is_holiday": 1
                    },
                    pluck="holiday_date"
                )
            duration_in_days = duration_in_days-len(holidays)+len(weekoffplusholidays)
               
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
                            "holiday_date": ["between", [start_date, joining_date]],
                            "weekly_off": 1
                        },
                        pluck="holiday_date"
                    )
                    relieving_holidays = frappe.get_all(
                        "Holiday",
                        filters={
                            "parent": holiday_list,
                            "holiday_date": ["between", [relieving_date, end_date]],
                            "weekly_off": 1
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
                            "holiday_date": ["between", [start_date, joining_date]],
                            "weekly_off": 1
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
                            "holiday_date": ["between", [relieving_date, end_date]],
                            "weekly_off": 1
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
        mapping attendance dates with the holiday list to consider holidays and weekoffs separately.
        """
        try:
            emp_id = self.employee
            emp_type = self.custom_employment_type
            start_date = self.start_date
            end_date = self.end_date

            # Get list of holidays and weekly offs
            holiday_entries = frappe.get_all("Holiday", 
                filters={
                    "holiday_date": ["between", [start_date, end_date]]
                },
                fields=["holiday_date", "custom_is_holiday", "weekly_off"]
            )

            # Create a set of all dates that are holidays or weekoffs
            holiday_dates = {h.holiday_date for h in holiday_entries if h.custom_is_holiday or h.weekly_off}

            if emp_type == 'Worker':
                # Fetch attendance records
                records = frappe.get_all("Attendance",
                    filters={
                        "employee": emp_id,
                        "status": "Present",
                        "attendance_date": ["between", [start_date, end_date]],
                        "docstatus": 1
                    },
                    fields=["custom_overtime", "custom_remaining_overtime", "attendance_date", "custom_total_hours"]
                )

                applicable_ot = 0
                remaining_ot = 0

                for row in records:
                    if row.attendance_date in holiday_dates:
                        continue  # Skip if it's a holiday or weekoff
                    frappe.msgprint(str(row.attendance_date))
                    # Count OT only for working days
                    applicable_ot += (row.custom_overtime or 0)
                    remaining_ot += (row.custom_remaining_overtime or 0)
        
                # Set the calculated overtime values
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

    def validate_employee_incentive(self):
        if self.custom_employment_type == "Worker":
            holiday_list = frappe.db.get_value("Employee", self.employee, "holiday_list")
            per_day_wage = frappe.db.get_value('Employee', self.employee, 'custom_per_day_wages')
            per_hour_wage = frappe.db.get_value('Employee', self.employee, 'custom_per_hour_wages')

            # Check for existing remaining overtime incentive
            try:
                if self.custom_remaining_overtime:
                    remaining_ot_incentive = 0
                    remaining_ot_incentive = round(per_hour_wage * self.custom_remaining_overtime) 

                    existing_remaining_ot_incentive = frappe.db.exists(
                        "Employee Incentive",
                        {
                            "employee": self.employee,
                            "custom_reference_salary_slip": self.name,
                            "custom_incentive_paid_for": "Remaining Overtime",
                            "docstatus": 0 
                        }
                    )
                    
                    if existing_remaining_ot_incentive:
                        incentive_doc = frappe.get_doc("Employee Incentive", existing_remaining_ot_incentive)
                        incentive_doc.custom_posting_date = today()
                        incentive_doc.custom_include_in_salary_slip = 0
                        incentive_doc.custom_remaining_overtime_hours = self.custom_remaining_overtime
                        incentive_doc.salary_component = "Remaining Overtime Payment"
                        incentive_doc.incentive_amount = remaining_ot_incentive
                        incentive_doc.custom_incentive_payable = remaining_ot_incentive
                        incentive_doc.save(ignore_permissions=True)
            except Exception as e:
                frappe.throw(str(e))

            # Check for existing weekoff incentive
            try:
                total_weekoff_wage = 0
                weekoff_count = 0
                extra_hours = 0  # <-- To track total equivalent weekoff days worked

                if holiday_list:
                    # Get dates marked as weekoff in the holiday list
                    weekoff_dates = frappe.get_all("Holiday",
                        filters={
                            "parent": holiday_list,
                            "weekly_off": 1,
                            "holiday_date": ["between", [self.start_date, self.end_date]]
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
                        

                        if weekoff_count > 0:
                            existing_weekoff_incentive = frappe.db.exists(
                                "Employee Incentive",
                                {
                                    "employee": self.employee,
                                    "custom_reference_salary_slip": self.name,
                                    "custom_incentive_paid_for": "Worked on WeekOff",
                                    "custom_worked_weekoff_count": [">", 0],
                                    "docstatus": 0 
                                }
                            )
                            
                            
                            if existing_weekoff_incentive:
                                incentive_doc = frappe.get_doc("Employee Incentive", existing_weekoff_incentive)
                                incentive_doc.custom_posting_date = today()
                                incentive_doc.custom_include_in_salary_slip = 0
                                incentive_doc.custom_worked_weekoff_count = weekoff_count
                                incentive_doc.custom_remaining_overtime_hours = extra_hours
                                incentive_doc.salary_component = "WeekOff Incentive"
                                incentive_doc.incentive_amount = total_weekoff_wage
                                incentive_doc.custom_incentive_payable = total_weekoff_wage
                                incentive_doc.save(ignore_permissions=True)

            except Exception as e:
                frappe.throw(str(e))

                
            
            # Check for existing general holiday incentive
            try:

                total_holiday_wage = 0
                holiday_count = 0
                total_hours = 0  # <-- To track total equivalent weekoff days worked

                if holiday_list:
                    # Get dates marked as weekoff in the holiday list
                    holiday_dates = frappe.get_all("Holiday",
                        filters={
                            "parent": holiday_list,
                            "custom_is_holiday": 1,
                            "weekly_off": 0,
                            "holiday_date": ["between", [self.start_date, self.end_date]]
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
                                wage = per_day_wage
                            elif att.status == "Half Day":
                                holiday_count += 0.5
                                wage = per_day_wage / 2
                            else:
                                wage = 0

                            total_holiday_wage += wage
                        
                        total_holiday_wage = total_holiday_wage + (total_hours*per_hour_wage)
                        total_holiday_wage = round(total_holiday_wage)
                        


                    existing_holiday_incentive = frappe.db.exists(
                        "Employee Incentive",
                        {
                            "employee": self.employee,
                            "custom_reference_salary_slip": self.name,
                            "custom_incentive_paid_for": "Worked on WeekOff",
                            "custom_worked_holiday_count": [">", 0],
                            "docstatus": 0 
                        }
                    )
                    if existing_holiday_incentive:
                        incentive_doc = frappe.get_doc("Employee Incentive", existing_holiday_incentive)
                        incentive_doc.custom_posting_date = today()
                        incentive_doc.custom_include_in_salary_slip = 0
                        incentive_doc.custom_worked_holiday_count = holiday_count
                        incentive_doc.custom_remaining_overtime_hours = total_hours
                        incentive_doc.incentive_amount = total_holiday_wage
                        incentive_doc.salary_component = "WeekOff Incentive"
                        incentive_doc.custom_incentive_payable = total_holiday_wage
                        incentive_doc.save(ignore_permissions=True)


            except Exception as e:
                frappe.throw(str(e))




    def generate_employee_incentive(self):
        if self.custom_employment_type == "Worker":
            holiday_list = frappe.db.get_value("Employee", self.employee, "holiday_list")
            per_day_wage = frappe.db.get_value('Employee', self.employee, 'custom_per_day_wages')
            per_hour_wage = frappe.db.get_value('Employee', self.employee, 'custom_per_hour_wages')
            
            # Generate new remaining overtime payment incentive
            try:
                if self.custom_remaining_overtime:
                    remaining_ot_incentive = 0
                    remaining_ot_incentive = round(per_hour_wage * self.custom_remaining_overtime)                        
                 
                    for_remaining_ot = frappe.new_doc("Employee Incentive")
                    for_remaining_ot.employee = self.employee
                    for_remaining_ot.custom_posting_date = today()
                    for_remaining_ot.custom_include_in_salary_slip = 0
                    for_remaining_ot.custom_incentive_paid_for = "Remaining Overtime"
                    for_remaining_ot.custom_remaining_overtime_hours = self.custom_remaining_overtime
                    for_remaining_ot.salary_component = "Remaining Overtime Payment"
                    for_remaining_ot.incentive_amount = remaining_ot_incentive
                    for_remaining_ot.custom_incentive_payable = remaining_ot_incentive
                    for_remaining_ot.custom_reference_salary_slip = self.name
                    for_remaining_ot.insert(ignore_permissions=True)

            except Exception as e:
                frappe.throw(str(e))

            
            # Generate new weekoff payment incentive
            try:
                total_weekoff_wage = 0
                weekoff_count = 0
                extra_hours = 0  # <-- To track total equivalent weekoff days worked

                if holiday_list:
                    # Get dates marked as weekoff in the holiday list
                    weekoff_dates = frappe.get_all("Holiday",
                        filters={
                            "parent": holiday_list,
                            "weekly_off": 1,
                            "holiday_date": ["between", [self.start_date, self.end_date]]
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
                        

                        if weekoff_count > 0:  

                            # Create new incentive
                            for_weekoff = frappe.new_doc("Employee Incentive")
                            for_weekoff.employee = self.employee
                            for_weekoff.custom_posting_date = today()
                            for_weekoff.custom_include_in_salary_slip = 0
                            for_weekoff.custom_incentive_paid_for = "Worked on WeekOff"
                            for_weekoff.custom_worked_weekoff_count = weekoff_count
                            for_weekoff.custom_remaining_overtime_hours = extra_hours
                            for_weekoff.salary_component = "WeekOff Incentive"
                            for_weekoff.incentive_amount = total_weekoff_wage
                            for_weekoff.custom_incentive_payable = total_weekoff_wage
                            for_weekoff.custom_reference_salary_slip = self.name
                            for_weekoff.insert(ignore_permissions=True)

            except Exception as e:
                frappe.throw(str(e))

            

            # Generate new general holiday payment incentive
            try:

                total_holiday_wage = 0
                holiday_count = 0
                total_hours = 0  # <-- To track total equivalent weekoff days worked

                if holiday_list:
                    # Get dates marked as weekoff in the holiday list
                    holiday_dates = frappe.get_all("Holiday",
                        filters={
                            "parent": holiday_list,
                            "custom_is_holiday": 1,
                            "weekly_off": 0,
                            "holiday_date": ["between", [self.start_date, self.end_date]]
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
                                wage = per_day_wage
                            elif att.status == "Half Day":
                                holiday_count += 0.5
                                wage = per_day_wage / 2
                            else:
                                wage = 0

                            total_holiday_wage += wage

                        total_holiday_wage = total_holiday_wage + (total_hours*per_hour_wage)
                        total_holiday_wage = round(total_holiday_wage)

                        if holiday_count > 0:  
                            # Create new incentive
                            for_holiday = frappe.new_doc("Employee Incentive")
                            for_holiday.employee = self.employee
                            for_holiday.custom_posting_date = today()
                            for_holiday.custom_include_in_salary_slip = 0
                            for_holiday.custom_incentive_paid_for = "Worked on WeekOff"
                            for_holiday.custom_worked_holiday_count = holiday_count
                            for_holiday.custom_remaining_overtime_hours = total_hours
                            for_holiday.salary_component = "WeekOff Incentive"
                            for_holiday.incentive_amount = total_holiday_wage
                            for_holiday.custom_incentive_payable = total_holiday_wage
                            for_holiday.custom_reference_salary_slip = self.name
                            for_holiday.insert(ignore_permissions=True)


            except Exception as e:
                frappe.throw(str(e))

