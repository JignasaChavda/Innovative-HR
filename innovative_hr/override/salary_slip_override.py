import frappe
from frappe import _
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
        
        self.calculate_overtime()
        
        
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
        Method to Calculate Overtime based on the Attendance Records
        """
        try:
            
            emp_id = self.employee
            start_date = self.start_date
            end_date = self.end_date
            
            
            total_overtime = frappe.db.get_value("Attendance", {"employee": emp_id, "attendance_date": ["between", (start_date, end_date)], "status": "Present"}, ["sum(custom_overtime)"])
            
            self.custom_ot_hours = total_overtime if total_overtime else 0.0
            
        except Exception as e: 
            frappe.throw(str(e))
            return {"error": 1, "message": str(e)}