__version__ = "0.0.1"

import hrms.payroll.doctype.payroll_entry.payroll_entry as PayrollEntryModule
from innovative_hr.override.payroll_entry_override import custom_set_filter_conditions

PayrollEntryModule.set_filter_conditions = custom_set_filter_conditions
