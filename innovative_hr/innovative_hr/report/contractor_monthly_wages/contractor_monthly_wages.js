// Copyright (c) 2025, jignasha chavda and contributors
// For license information, please see license.txt

frappe.query_reports["Contractor Monthly Wages"] = {
	"filters": [
        {
            "fieldname": "from_date",
            "label": "From Date",
            "fieldtype": "Date",
            "reqd": 1
        },
        {
            "fieldname": "to_date",
            "label": "To Date",
            "fieldtype": "Date",
            "reqd": 1
        },
		
    ]
};
