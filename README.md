# Student Registration and Scheduling System

> Started as the Student Information Form (student CRUD). Now a student registration, class scheduling and enrollment system built with Python, FastAPI, Pydantic, SQLite and a plain HTML/CSS/JavaScript frontend.

## Features

* **Student registration:** generated, unique student IDs in the form `YYYY-NNNN` (registration year + 4 random digits, e.g. `2026-0101`; up to 10,000 per year); *Personal Background* and *Educational Background* sections; full Create / Read / Update / Delete with search, course filter and pagination.
* **Instructors:** generated, unique 10-digit instructor IDs; contact details; assigned subjects, schedule and classrooms.
* **Courses:** exactly four course offerings (editable names), each with its own subjects. A course is flagged until it has at least 10 subjects.
* **Subjects:** unique subject codes, 2 or 3 units, linked to a course.
* **Class sections (subject offerings):** each section of a subject has its own time slot, instructor, room and up to 30 seats. Enrolled and available slots are always counted from the enrollment records.
* **Scheduling rules (enforced on the server):**
  * MWF classes last 60 minutes and TTH classes 90 minutes. Admins can add other time slots or approve exceptions.
  * Classes must fall within the configurable room operating hours.
  * No instructor, room, or student can be in two overlapping classes.
  * No more than 30 students per section, and inactive instructors or rooms cannot be assigned.
* **Classrooms:** 30 rooms (`RM-01` … `RM-30`) created on first run, availability grid per time slot, utilization report.
* **Enrollment:** admins enroll or drop students per section; students can enroll themselves when self-enrollment is switched on.
* **Roles:** Administrator, IT Administrator (views everything; manages class scheduling: instructors, rooms and time slots), Instructor and Student. Permissions are checked on every API request.
* **Dashboard:** live statistics, requirement checks (4 courses, 10 subjects per course, 4 offerings per day), room utilization and instructor assignments.

## Prerequisites

* [Python](https://www.python.org/) (v3.10 or higher)
* `pip` (Python package manager)

## Installation & Setup

```
1. Clone Repository
git clone https://github.com/jasperayawan/Student_Information_form

2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

3. Install dependencies
pip install -r requirements.txt
```

## Create the first administrator

```
cd backend
python create_admin.py admin
```

You will be asked for a password (at least 8 characters). Other accounts (students, instructors, IT administrators) are created from **Users & Roles** in the app.

## Start the development server

```
cd backend
uvicorn app:app --reload
```

Open **http://127.0.0.1:8000/app/** and log in. (Opening `frontend/index.html` with Live Server on port 5500 also works.)

## Database upgrades

On startup the app checks the database version (`PRAGMA user_version`) and upgrades it if needed:

* A copy of the old database is saved first in `backend/database/backups/`.
* Existing students keep their record IDs and receive a generated `YYYY-NNNN` student ID based on the year they were registered (database version 4).
* The old free-text course values (e.g. BSIT, BSBA, CRIM) become course records, plus placeholders up to four courses.
* Old contact numbers get back their leading 0.
* Migrated students have no email, sex, or previous-school data yet. The list marks them as *Incomplete record* until an administrator edits them.

## Running the tests

```
cd backend
..\.venv\Scripts\python -m unittest discover tests -v
```

The tests use a temporary database and never touch `students.db`.

## Things to confirm with the school

* **Room operating hours:** the default is an 8-hour window, 1:00 PM–9:00 PM, chosen so the example evening classes fit. Set the real hours under **Settings**.
* **Course names:** one course is a placeholder (`COURSE4`). Rename it under **Course Management**.
* **"Offered at least four times per day":** interpreted as at least 4 sections of a subject on each weekday the subject meets. It is reported on the dashboard, not blocked.
* **IT administrator permissions:** currently read-only for everything. Adjust in `backend/core/permissions.py`.
