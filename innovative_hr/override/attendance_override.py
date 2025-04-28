import frappe
from frappe import _
from frappe.model.document import Document
from hrms.hr.doctype.attendance.attendance import Attendance
from erpnext.controllers.status_updater import validate_status


class Attendance(Attendance):
    def validate(self):
        # You can add your custom status validation logic here
        valid_statuses = ["Present", "Absent", "Mispunch", "On Leave", "Half Day", "Work From Home"]
        
        if self.status not in valid_statuses:
            frappe.throw(_("Invalid status: {0}".format(self.status)))
        
        # You can call the original validate_status or modify it based on your logic
        validate_status(self.status, valid_statuses)