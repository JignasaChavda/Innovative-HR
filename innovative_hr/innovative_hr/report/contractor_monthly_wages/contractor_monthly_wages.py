# File: smk_hrms/smk_hrms/report/contract_salary_slip_report/contract_salary_slip_report.py

import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    # Get all Salary Slips of contract employees within date range
    salary_slips = frappe.db.sql("""
        SELECT ss.name, ss.employee, e.employee_name, e.department,
               ss.start_date, ss.end_date, ss.gross_pay, ss.total_deduction,
               ss.net_pay, ss.status, ss.custom_working_days_for_contractor, ss.custom_total_worked_hours, ss.custom_contractor
        FROM `tabSalary Slip` ss
        JOIN `tabEmployee` e ON ss.employee = e.name
        WHERE e.employment_type = 'Contract'
          AND ss.start_date >= %s
          AND ss.end_date <= %s
    """, (from_date, to_date), as_dict=True)

    # Track dynamic earnings and deductions
    earning_components = set()
    deduction_components = set()
    salary_slip_docs = {}

    for ss in salary_slips:
        doc = frappe.get_doc("Salary Slip", ss.name)
        salary_slip_docs[ss.name] = doc

        for e in doc.earnings:
            earning_components.add(e.salary_component)

        for d in doc.deductions:
            deduction_components.add(d.salary_component)

    # Define columns
    columns = [
        {"label": "Salary Slip ID", "fieldname": "salary_slip", "fieldtype": "Link", "options": "Salary Slip", "width": 150},
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Data", "width": 100},
		{"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 150},
        {"label": "Contractor", "fieldname": "contractor", "fieldtype": "Data", "width": 150},
        {"label": "Department", "fieldname": "department", "fieldtype": "Data", "width": 140},
        {"label": "Start Date", "fieldname": "start_date", "fieldtype": "Date", "width": 120},
        {"label": "End Date", "fieldname": "end_date", "fieldtype": "Date", "width": 120},
        {"label": "Hours Worked", "fieldname": "hours_worked", "fieldtype": "Int", "width": 120},
        {"label": "Days Worked", "fieldname": "days_worked","fieldtype": "Float", "width": 120, "precision": 1}
    ]

    # Add dynamic earnings columns
    for comp in sorted(earning_components):
        columns.append({
            "label": comp,
            "fieldname": f"earning_{comp.lower().replace(' ', '_')}",
            "fieldtype": "Currency",
            "width": 150
        })

    # Add dynamic deductions columns
    for comp in sorted(deduction_components):
        columns.append({
            "label": comp,
            "fieldname": f"deduction_{comp.lower().replace(' ', '_')}",
            "fieldtype": "Currency",
            "width": 150
        })

    # Add totals
    columns += [
        {"label": "Gross Pay", "fieldname": "gross_pay", "fieldtype": "Currency", "width": 120},
        {"label": "Total Deduction", "fieldname": "total_deduction", "fieldtype": "Currency", "width": 150},
        {"label": "Net Pay", "fieldname": "net_pay", "fieldtype": "Currency", "width": 120},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
    ]

    data = []
    for ss in salary_slips:
        doc = salary_slip_docs[ss.name]
        row = {
            "salary_slip": ss.name,
            "employee": ss.employee, 
			"employee_name": ss.employee_name,
            "contractor": ss.custom_contractor,
            "department": ss.department,
            "start_date": ss.start_date,
            "end_date": ss.end_date,
            "hours_worked": ss.custom_total_worked_hours,
            "days_worked": round(ss.custom_working_days_for_contractor or 0, 1),
            "gross_pay": ss.gross_pay,
            "total_deduction": ss.total_deduction,
            "net_pay": ss.net_pay,
            "status": ss.status
        }

        # Add earnings
        for e in doc.earnings:
            field = f"earning_{e.salary_component.lower().replace(' ', '_')}"
            row[field] = e.amount

        # Add deductions
        for d in doc.deductions:
            field = f"deduction_{d.salary_component.lower().replace(' ', '_')}"
            row[field] = d.amount

        data.append(row)

    return columns, data
