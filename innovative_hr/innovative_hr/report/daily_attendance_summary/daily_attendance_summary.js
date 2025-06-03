frappe.query_reports["Daily Attendance Summary"] = {
    "filters": [
        {
            "fieldname":"attendance_date",
            "label": __("Attendance Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_days(frappe.datetime.get_today(), -1),
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
        },
        {
            "fieldname": "contractor",
            "label": __("Contractor"),
            "fieldtype": "Link",
            "options": "Contractor Company"  // Ensure "Contractor" is a Doctype
        }
    ],
    "formatter": function(value, row, column, data, default_formatter){
        if(column.fieldname === "custom_total_hours" && data && data.total_row){
            return `<b>${value}</b>`;
        }
        return default_formatter(value, row, column, data);
    }
};
