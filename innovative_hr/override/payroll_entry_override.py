import frappe
from hrms.payroll.doctype.payroll_entry.payroll_entry import get_employee_list, PayrollEntry
from frappe import _

class CustomPayrollEntry(PayrollEntry):
    @frappe.whitelist()
    def fill_employee_details(self):
        filters = self.make_filters()
        # ! Add custom employment type filter if available
        if filters:
            filters.update(dict(employment_type=self.custom_employment_type))
        
        employees = get_employee_list(filters=filters, as_dict=True, ignore_match_conditions=True)
        self.set("employees", [])

        if not employees:
            error_msg = _(
                "No employees found for the mentioned criteria:<br>Company: {0}<br> Currency: {1}<br>Payroll Payable Account: {2}"
            ).format(
                frappe.bold(self.company),
                frappe.bold(self.currency),
                frappe.bold(self.payroll_payable_account),
            )
            if self.branch:
                error_msg += "<br>" + _("Branch: {0}").format(frappe.bold(self.branch))
            if self.department:
                error_msg += "<br>" + _("Department: {0}").format(frappe.bold(self.department))
            # ? ADD ERROR MESSAGE FOR EMPLOYMENT TYPE
            if self.custom_employment_type:
                error_msg += "<br>" + _("Employment Type: {0}").format(frappe.bold(self.custom_employment_type))
            if self.designation:
                error_msg += "<br>" + _("Designation: {0}").format(frappe.bold(self.designation))
            if self.start_date:
                error_msg += "<br>" + _("Start date: {0}").format(frappe.bold(self.start_date))
            if self.end_date:
                error_msg += "<br>" + _("End date: {0}").format(frappe.bold(self.end_date))
            frappe.throw(error_msg, title=_("No employees found"))

        self.set("employees", employees)
        self.number_of_employees = len(self.employees)
        self.update_employees_with_withheld_salaries()

        return self.get_employees_with_unmarked_attendance()


def custom_set_filter_conditions(query, filters, qb_object):
    """Append optional filters to employee query"""

    if filters.get("employees"):
        query = query.where(qb_object.name.notin(filters.get("employees")))
        print("employees filter:", filters.get("employees"))

    # ? ADD EMPLOYMENT TYPE in LIST
    for fltr_key in ["branch", "department", "designation", "grade", "employment_type"]:
        if filters.get(fltr_key):
            query = query.where(qb_object[fltr_key] == filters[fltr_key])

    return query
