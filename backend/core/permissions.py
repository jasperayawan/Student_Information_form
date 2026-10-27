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
# can see every record and report, and manage class scheduling: create
# classes, assign/reassign instructors, rooms and time slots. Everything else
# is view-only. Add "*.manage" entries here to give them more.
COLLEGE_ADMIN_PERMISSIONS = {
    "dashboard.view", "reports.view",
    "students.view", "instructors.view", "courses.view", "subjects.view",
    "sections.view", "sections.manage", "classrooms.view", "enrollments.view", "settings.view",
}

# Instructors see only the subjects they teach (see routers/subjects.py) and
# have no Courses page.
INSTRUCTOR_PERMISSIONS = {
    "dashboard.view", "subjects.view", "sections.view",
    "self.teaching",
}

# Students have no Courses page; their own course shows on My Profile.
STUDENT_PERMISSIONS = {
    "dashboard.view", "subjects.view", "sections.view",
    "self.profile", "self.enroll",
}

ROLE_PERMISSIONS = {
    "admin": ADMIN_PERMISSIONS,
    "college_admin": COLLEGE_ADMIN_PERMISSIONS,
    "instructor": INSTRUCTOR_PERMISSIONS,
    "student": STUDENT_PERMISSIONS,
}
