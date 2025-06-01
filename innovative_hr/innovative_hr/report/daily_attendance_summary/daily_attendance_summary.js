frappe.query_reports["Daily Attendance Summary"] = {
    "filters": [
        {
            "fieldname":"attendance_date",
            "label": __("Attendance Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 1
        },
        {
            "fieldname":"department",
            "label": __("Department"),
            "fieldtype": "Link",
            "options": "Department"
        },
        {
            "fieldname":"employment_type",
            "label": __("Employment Type"),
            "fieldtype": "Link",
            "options": "Employment Type"
        }
    ],
    "formatter": function(value, row, column, data, default_formatter){
        // Prevent total row summing date/time fields
        if(column.fieldname === "custom_total_hours" && data && data.total_row){
            return `<b>${value}</b>`;  // Bold total row for hours
        }
        return default_formatter(value, row, column, data);
    }
};
