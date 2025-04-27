// Copyright (c) 2025, jignasha chavda and contributors
// For license information, please see license.txt
frappe.ui.form.on('Mark Attendance', {
    mark_attendance: function(frm) {
        if (!cur_frm.doc.attendance_date) {
            frappe.msgprint(__('Please fill Attendance Date before marking attendance.'));
            return;
        }

        frappe.call({
            method: "innovative_hr.utils.schedule_mark_attendance",
            args: {
                "attendance_date": cur_frm.doc.attendance_date,
                freeze: true,
                freeze_message: "Attendance is marking. Please wait..."
            },
            callback: function(response) {
                if (response.message) {
                    let messages = response.message;

                    // If response is an array of messages, show them nicely
                    frappe.msgprint({
                        title: __("Attendance Result"),
                        message: messages.join("<br>"), // join messages with line breaks
                        indicator: 'green'
                    });
                }
            }
    
        });
    },
    attendance_date: function(frm){
        frm.save();
    }
});

