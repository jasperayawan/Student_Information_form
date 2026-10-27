"""Role -> permission map. Every protected endpoint checks one of these
permission names on the server, so hiding a button is never the only guard."""

ROLES = ("student", "instructor", "admin", "college_admin")

ADMIN_PERMISSIONS = {
    "dashboard.view", "reports.view",
    "students.view", "students.manage",
    "instructors.view", "instructors.manage",
    "courses.view", "courses.manage",
    "subjects.view", "subjects.manage",
    "sections.view", "sections.manage",
    "classrooms.view", "classrooms.manage",
    "enrollments.view", "enrollments.manage",
    "users.manage",
    "settings.view", "settings.manage",
}

# IT administrators (role key "college_admin", shown as "IT Administrator")
# have oversight: they can see every record and report but cannot change
# data. Add "*.manage" entries here if they should edit specific modules.
COLLEGE_ADMIN_PERMISSIONS = {
    "dashboard.view", "reports.view",
    "students.view", "instructors.view", "courses.view", "subjects.view",
    "sections.view", "classrooms.view", "enrollments.view", "settings.view",
}

INSTRUCTOR_PERMISSIONS = {
    "dashboard.view", "courses.view", "subjects.view", "sections.view",
    "self.teaching",
}

STUDENT_PERMISSIONS = {
    "dashboard.view", "courses.view", "subjects.view", "sections.view",
    "self.profile", "self.enroll",
}

ROLE_PERMISSIONS = {
    "admin": ADMIN_PERMISSIONS,
    "college_admin": COLLEGE_ADMIN_PERMISSIONS,
    "instructor": INSTRUCTOR_PERMISSIONS,
    "student": STUDENT_PERMISSIONS,
}
