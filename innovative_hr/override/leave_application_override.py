from frappe.utils import formatdate, get_link_to_form
from hrms.hr.doctype.leave_application.leave_application import LeaveApplication as BaseLeaveApplication
import frappe

class CustomLeaveApplication(BaseLeaveApplication):
    def validate_attendance(self):
        attendance_dates = frappe.get_all(
			"Attendance",
			filters={
				"employee": self.employee,
				"attendance_date": ("between", [self.from_date, self.to_date]),
				"status": ("in", ["Present", "Work From Home"]),
				"docstatus": 1,
			},
			fields=["name", "attendance_date"],
			order_by="attendance_date",
		)
        for att in attendance_dates:
            # Cancel the existing submitted Attendance
            existing_att = frappe.get_doc("Attendance", att.name)
            if existing_att.docstatus == 1:
                existing_att.cancel()
                existing_att.delete()
               