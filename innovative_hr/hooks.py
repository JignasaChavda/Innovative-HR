app_name = "innovative_hr"
app_title = "Innovative HR"
app_publisher = "jignasha chavda"
app_description = "Innovative HR Custom App"
app_email = "jignasha@sanskartechnolab.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "innovative_hr",
# 		"logo": "/assets/innovative_hr/logo.png",
# 		"title": "Innovative HR",
# 		"route": "/innovative_hr",
# 		"has_permission": "innovative_hr.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/innovative_hr/css/innovative_hr.css"
# app_include_js = "/assets/innovative_hr/js/innovative_hr.js"

# include js, css files in header of web template
# web_include_css = "/assets/innovative_hr/css/innovative_hr.css"
# web_include_js = "/assets/innovative_hr/js/innovative_hr.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "innovative_hr/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "innovative_hr/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "innovative_hr.utils.jinja_methods",
# 	"filters": "innovative_hr.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "innovative_hr.install.before_install"
# after_install = "innovative_hr.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "innovative_hr.uninstall.before_uninstall"
# after_uninstall = "innovative_hr.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "innovative_hr.utils.before_app_install"
# after_app_install = "innovative_hr.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "innovative_hr.utils.before_app_uninstall"
# after_app_uninstall = "innovative_hr.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "innovative_hr.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Salary Slip": "innovative_hr.override.salary_slip_override.SalarySlip",
    "Attendance": "innovative_hr.override.attendance_override.Attendance",
    "Leave Application": "innovative_hr.override.leave_application_override.CustomLeaveApplication"
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    'Employee Checkin': {
        "before_save": "innovative_hr.public.py.custom_employee_checkin.before_save"
    },
    # 'Attendance':{
    #     # "on_update_after_submit": "innovative_hr.public.py.custom_attendance.update_attendance",
    #     "before_save": "innovative_hr.public.py.custom_attendance.update_attendance"

    # }
}

# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# 

# Scheduled Tasks
# ---------------
scheduler_events = {
    "mark_attendance": {
        "00 11 * * *": [
            "innovative_hr.utils.schedule_mark_attendance"
        ]
    }
    # "daily": [
    #     "clevision.utils.get_last_sync_of_checkin"
    # ]
}
# scheduler_events = {
# 	"all": [
# 		"innovative_hr.tasks.all"
# 	],
# 	"daily": [
# 		"innovative_hr.tasks.daily"
# 	],
# 	"hourly": [
# 		"innovative_hr.tasks.hourly"
# 	],
# 	"weekly": [
# 		"innovative_hr.tasks.weekly"
# 	],
# 	"monthly": [
# 		"innovative_hr.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "innovative_hr.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "innovative_hr.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "innovative_hr.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["innovative_hr.utils.before_request"]
# after_request = ["innovative_hr.utils.after_request"]

# Job Events
# ----------
# before_job = ["innovative_hr.utils.before_job"]
# after_job = ["innovative_hr.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"innovative_hr.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
    "Workflow",
    "Workflow State",
    "Workflow Action Master",
    
    {"dt":"Print Format","filters":[
        [
            "module","in",[
               "Innovative HR"
            ],
        ]
    ]},
    {"dt":"Custom Field","filters":[
        [
            "module","in",[
               "Innovative HR"
            ],
        ]
    ]},
    {"dt":"Property Setter","filters":[
        [
            "module","in",[
               "Innovative HR"
            ],
        ]
    ]},
    {"dt":"Client Script","filters":[
        [
            "module","in",[
               "Innovative HR"
            ],
        ]
    ]},
    {"dt":"Server Script","filters":[
        [
            "module","in",[
               "Innovative HR"
            ],
        ]
    ]},
    {"dt":"Report","filters":[
        [
            "module","in",[
               "Innovative HR"
            ],
        ]
    ]}

]
