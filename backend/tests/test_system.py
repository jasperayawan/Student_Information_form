"""End-to-end API tests. Run from the backend folder:

    ..\\.venv\\Scripts\\python -m unittest discover tests -v

Each run uses a temporary database, so real data is never touched.
"""
import os
from datetime import date
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TEMP_DIR = tempfile.mkdtemp()
os.environ["STUDENT_DB_PATH"] = str(Path(TEMP_DIR) / "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402
from core.security import hash_password  # noqa: E402
from database import get_connection  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
client = TestClient(app)
_counter = {"n": 0}


def unique(prefix: str) -> str:
    _counter["n"] += 1
    return f"{prefix}{_counter['n']}"


def make_user(username: str, role: str, student_id=None, instructor_id=None, password="password123"):
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (username, password_hash, role, student_id, instructor_id) VALUES (?, ?, ?, ?, ?)",
        (username, hash_password(password), role, student_id, instructor_id),
    )
    conn.commit()
    conn.close()


def login(username: str, password: str = "password123") -> dict:
    res = client.post("/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


make_user("admin", "admin")
make_user("college", "college_admin")
ADMIN = login("admin")
COLLEGE = login("college")


def course_ids() -> list[int]:
    return [c["id"] for c in client.get("/courses/", headers=ADMIN).json()["data"]]


def student_payload(course: int, **overrides) -> dict:
    payload = {
        "name": "Juan Dela Cruz", "age": 19, "birth_date": "2006-05-10", "sex": "Male",
        "address": "Pitogo", "contact_number": "09171234567", "email": f"{unique('s')}@example.com",
        "previous_school": "Pitogo NHS", "previous_attainment": "Senior High School Graduate",
        "course_id": course, "year_level": 1,
    }
    payload.update(overrides)
    return payload


def create_student(course: int, **overrides) -> dict:
    res = client.post("/students/", json=student_payload(course, **overrides), headers=ADMIN)
    assert res.status_code == 201, res.text
    return res.json()["data"]


def create_instructor(**overrides) -> dict:
    body = {"name": unique("Instructor "), "email": f"{unique('i')}@example.com",
            "contact_number": "09181234567", "department": "General Education"}
    body.update(overrides)
    res = client.post("/instructors/", json=body, headers=ADMIN)
    assert res.status_code == 201, res.text
    return res.json()["data"]


def create_subject(course_id: int, units: int = 3) -> int:
    res = client.post("/subjects/", json={"code": unique("SUB"), "title": "Subject", "units": units,
                                          "course_id": course_id}, headers=ADMIN)
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"]


def slot_id(pattern: str) -> int:
    slots = client.get("/time-slots", headers=ADMIN).json()["data"]
    return next(s["id"] for s in slots if s["pattern"] == pattern and s["note"].startswith("From"))


def room_ids() -> list[int]:
    return [r["id"] for r in client.get("/classrooms/", headers=ADMIN).json()["data"]]


_free_rooms = iter(room_ids())


def next_room() -> int:
    """Each test gets rooms nobody else uses, so tests don't clash with each other."""
    global _free_rooms
    try:
        return next(_free_rooms)
    except StopIteration:
        res = client.post("/classrooms/", json={"room_code": unique("TEST-RM-")}, headers=ADMIN)
        return res.json()["data"]["id"]


def create_section(subject_id: int, pattern="MWF", **overrides) -> dict:
    body = {"subject_id": subject_id, "section_code": unique("S"), "time_slot_id": slot_id(pattern),
            "instructor_id": None, "classroom_id": next_room(), "capacity": 30}
    body.update(overrides)
    res = client.post("/sections", json=body, headers=ADMIN)
    assert res.status_code == 201, res.text
    return res.json()["data"]


class StudentTests(unittest.TestCase):
    def test_crud_and_generated_id(self):
        course = course_ids()[0]
        student = create_student(course)
        self.assertRegex(student["student_number"], rf"^{date.today().year}-\d{{4}}$")

        res = client.get(f"/students/{student['id']}", headers=ADMIN)
        self.assertEqual(res.json()["data"]["name"], "Juan Dela Cruz")

        update = student_payload(course, name="Juan Updated", email=student["email"])
        res = client.put(f"/students/{student['id']}", json=update, headers=ADMIN)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["data"]["name"], "Juan Updated")
        self.assertEqual(res.json()["data"]["student_number"], student["student_number"])

        res = client.get("/students/", params={"q": "Juan Updated"}, headers=ADMIN)
        self.assertIn(student["id"], [s["id"] for s in res.json()["data"]])

        self.assertEqual(client.delete(f"/students/{student['id']}", headers=ADMIN).status_code, 200)
        self.assertEqual(client.get(f"/students/{student['id']}", headers=ADMIN).status_code, 404)

    def test_client_cannot_choose_student_id(self):
        body = student_payload(course_ids()[0])
        body["student_number"] = "2026-0001"
        self.assertEqual(client.post("/students/", json=body, headers=ADMIN).status_code, 422)

    def test_ids_are_unique(self):
        numbers = {create_student(course_ids()[0])["student_number"] for _ in range(25)}
        self.assertEqual(len(numbers), 25)

    def test_student_ids_never_repeat_when_a_year_is_nearly_full(self):
        from core.ids import generate_student_number
        conn = get_connection()
        conn.execute("CREATE TEMP TABLE year_probe (student_number TEXT)")
        conn.executemany("INSERT INTO year_probe VALUES (?)",
                         [(f"2099-{n:04d}",) for n in range(10_000) if n != 42])
        self.assertEqual(generate_student_number(conn, 2099, table="year_probe"), "2099-0042")
        conn.execute("INSERT INTO year_probe VALUES ('2099-0042')")
        with self.assertRaises(Exception) as ctx:
            generate_student_number(conn, 2099, table="year_probe")
        self.assertIn("already in use", str(ctx.exception.detail))
        conn.close()

    def test_ids_never_repeat_when_range_is_nearly_full(self):
        from core.ids import generate_unique_number
        conn = get_connection()
        conn.execute("CREATE TEMP TABLE id_probe (n TEXT)")
        conn.executemany("INSERT INTO id_probe VALUES (?)", [(str(n),) for n in range(100, 1000) if n != 777])
        self.assertEqual(generate_unique_number(conn, "id_probe", "n", 3), "777")
        conn.execute("INSERT INTO id_probe VALUES ('777')")
        with self.assertRaises(Exception) as ctx:
            generate_unique_number(conn, "id_probe", "n", 3)
        self.assertIn("already in use", str(ctx.exception.detail))
        conn.close()

    def test_validation(self):
        course = course_ids()[0]
        bad = [
            {"email": "not-an-email"},
            {"contact_number": "abc"},
            {"sex": "X"},
            {"birth_date": "2999-01-01"},
            {"course_id": 99999},
            {"name": ""},
        ]
        for override in bad:
            res = client.post("/students/", json=student_payload(course, **override), headers=ADMIN)
            self.assertIn(res.status_code, (409, 422), override)

    def test_duplicate_email(self):
        course = course_ids()[0]
        first = create_student(course)
        res = client.post("/students/", json=student_payload(course, email=first["email"]), headers=ADMIN)
        self.assertEqual(res.status_code, 409)


class InstructorAndCatalogTests(unittest.TestCase):
    def test_instructor_crud(self):
        instructor = create_instructor()
        self.assertRegex(instructor["instructor_number"], r"^\d{10}$")
        body = {"name": "Renamed", "email": instructor["email"], "contact_number": "09181234567",
                "department": "General Education"}
        self.assertEqual(client.put(f"/instructors/{instructor['id']}", json=body, headers=ADMIN).status_code, 200)
        self.assertEqual(client.delete(f"/instructors/{instructor['id']}", headers=ADMIN).status_code, 200)

    def test_department_must_come_from_list(self):
        options = [d["value"] for d in client.get("/instructors/departments", headers=ADMIN).json()["data"]]
        self.assertIn("General Education", options)
        self.assertFalse(any(v.startswith("COURSE") for v in options))
        res = client.post("/instructors/", json={"name": "No Dept", "email": "nodept@example.com",
                                                 "contact_number": "09181234567", "department": "Astronomy"},
                          headers=ADMIN)
        self.assertEqual(res.status_code, 422)

    def test_exactly_four_courses(self):
        res = client.get("/courses/", headers=ADMIN).json()
        self.assertEqual(len(res["data"]), 4)
        self.assertEqual(client.post("/courses/", json={}, headers=ADMIN).status_code, 405)

    def test_ten_subjects_rule_is_reported(self):
        course = course_ids()[3]
        before = next(c for c in client.get("/courses/", headers=ADMIN).json()["data"] if c["id"] == course)
        for _ in range(max(0, 10 - before["subject_count"])):
            create_subject(course, units=2)
        after = next(c for c in client.get("/courses/", headers=ADMIN).json()["data"] if c["id"] == course)
        self.assertGreaterEqual(after["subject_count"], 10)
        self.assertTrue(after["meets_subject_minimum"])

    def test_subject_rules(self):
        course = course_ids()[0]
        bad_units = client.post("/subjects/", json={"code": "BAD1", "title": "Test", "units": 4,
                                                    "course_id": course}, headers=ADMIN)
        self.assertEqual(bad_units.status_code, 422)
        client.post("/subjects/", json={"code": "DUP101", "title": "Test", "units": 3, "course_id": course},
                    headers=ADMIN)
        dup = client.post("/subjects/", json={"code": "dup101", "title": "Test", "units": 3, "course_id": course},
                          headers=ADMIN)
        self.assertEqual(dup.status_code, 409)

    def test_subject_has_only_descriptive_title(self):
        course = course_ids()[0]
        with_description = client.post("/subjects/", json={"code": "DESC1", "title": "Intro to Computing",
                                                           "description": "extra", "units": 3, "course_id": course},
                                        headers=ADMIN)
        self.assertEqual(with_description.status_code, 422)
        ok = client.post("/subjects/", json={"code": "DESC1", "title": "Intro to Computing", "units": 3,
                                             "course_id": course}, headers=ADMIN)
        self.assertEqual(ok.status_code, 201, ok.text)
        subject = client.get(f"/subjects/{ok.json()['data']['id']}", headers=ADMIN).json()["data"]
        self.assertEqual(subject["title"], "Intro to Computing")
        self.assertNotIn("description", subject)


class SchedulingTests(unittest.TestCase):
    def test_time_slot_rules(self):
        wrong_length = {"pattern": "MWF", "start_time": "14:00", "end_time": "15:30"}
        self.assertEqual(client.post("/time-slots", json=wrong_length, headers=ADMIN).status_code, 422)
        approved = dict(wrong_length, is_exception=True)
        self.assertEqual(client.post("/time-slots", json=approved, headers=ADMIN).status_code, 201)
        outside_hours = {"pattern": "TTH", "start_time": "06:00", "end_time": "07:30"}
        self.assertEqual(client.post("/time-slots", json=outside_hours, headers=ADMIN).status_code, 422)
        ok = {"pattern": "TTH", "start_time": "14:00", "end_time": "15:30"}
        self.assertEqual(client.post("/time-slots", json=ok, headers=ADMIN).status_code, 201)

    def test_instructor_and_room_conflicts(self):
        subject = create_subject(course_ids()[0])
        instructor = create_instructor()
        room = next_room()
        create_section(subject, instructor_id=instructor["id"], classroom_id=room)

        same_teacher = {"subject_id": subject, "section_code": unique("S"), "time_slot_id": slot_id("MWF"),
                        "instructor_id": instructor["id"], "classroom_id": next_room()}
        res = client.post("/sections", json=same_teacher, headers=ADMIN)
        self.assertEqual(res.status_code, 409)
        self.assertIn("already teaching", res.json()["detail"])

        same_room = {"subject_id": subject, "section_code": unique("S"), "time_slot_id": slot_id("MWF"),
                     "classroom_id": room}
        res = client.post("/sections", json=same_room, headers=ADMIN)
        self.assertEqual(res.status_code, 409)
        self.assertIn("already booked", res.json()["detail"])

        # Different days (TTH) never clash with MWF.
        create_section(subject, pattern="TTH", instructor_id=instructor["id"], classroom_id=room)

    def test_capacity_limit_is_30(self):
        subject = create_subject(course_ids()[0])
        body = {"subject_id": subject, "section_code": "BIG", "time_slot_id": slot_id("MWF"), "capacity": 31}
        self.assertEqual(client.post("/sections", json=body, headers=ADMIN).status_code, 422)

    def test_inactive_instructor_cannot_be_assigned(self):
        subject = create_subject(course_ids()[0])
        instructor = create_instructor(is_active=False)
        body = {"subject_id": subject, "section_code": "X", "time_slot_id": slot_id("MWF"),
                "instructor_id": instructor["id"]}
        self.assertEqual(client.post("/sections", json=body, headers=ADMIN).status_code, 409)

    def test_reassign_instructor(self):
        subject = create_subject(course_ids()[0])
        first, second = create_instructor(), create_instructor()
        section = create_section(subject, instructor_id=first["id"])
        body = {k: section[k] for k in ("subject_id", "section_code", "time_slot_id", "classroom_id", "capacity")}
        body["instructor_id"] = second["id"]
        res = client.put(f"/sections/{section['id']}", json=body, headers=ADMIN)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["data"]["instructor_id"], second["id"])
        # The first instructor is now free to be deleted.
        self.assertEqual(client.delete(f"/instructors/{first['id']}", headers=ADMIN).status_code, 200)
        self.assertEqual(client.delete(f"/instructors/{second['id']}", headers=ADMIN).status_code, 409)


class EnrollmentTests(unittest.TestCase):
    def test_capacity_and_available_slots(self):
        course = course_ids()[1]
        section = create_section(create_subject(course))
        students = [create_student(course) for _ in range(31)]
        for student in students[:30]:
            res = client.post("/enrollments/", json={"student_id": student["id"], "section_id": section["id"]},
                              headers=ADMIN)
            self.assertEqual(res.status_code, 201, res.text)
        detail = client.get(f"/sections/{section['id']}", headers=ADMIN).json()["data"]
        self.assertEqual((detail["enrolled_count"], detail["available_slots"]), (30, 0))

        res = client.post("/enrollments/", json={"student_id": students[30]["id"], "section_id": section["id"]},
                          headers=ADMIN)
        self.assertEqual(res.status_code, 409)
        self.assertIn("full", res.json()["detail"])

    def test_student_schedule_conflict_and_course_rule(self):
        course, other_course = course_ids()[1], course_ids()[2]
        a = create_section(create_subject(course))
        b = create_section(create_subject(course))
        foreign = create_section(create_subject(other_course), pattern="TTH")
        student = create_student(course)
        ok = client.post("/enrollments/", json={"student_id": student["id"], "section_id": a["id"]}, headers=ADMIN)
        self.assertEqual(ok.status_code, 201)
        clash = client.post("/enrollments/", json={"student_id": student["id"], "section_id": b["id"]}, headers=ADMIN)
        self.assertEqual(clash.status_code, 409)
        self.assertIn("Schedule conflict", clash.json()["detail"])
        wrong = client.post("/enrollments/", json={"student_id": student["id"], "section_id": foreign["id"]},
                            headers=ADMIN)
        self.assertEqual(wrong.status_code, 422)

    def test_safe_deletes(self):
        course = course_ids()[1]
        section = create_section(create_subject(course))
        student = create_student(course)
        enrollment = client.post("/enrollments/", json={"student_id": student["id"], "section_id": section["id"]},
                                 headers=ADMIN).json()["data"]
        self.assertEqual(client.delete(f"/students/{student['id']}", headers=ADMIN).status_code, 409)
        self.assertEqual(client.delete(f"/sections/{section['id']}", headers=ADMIN).status_code, 409)
        self.assertEqual(client.delete(f"/subjects/{section['subject_id']}", headers=ADMIN).status_code, 409)
        self.assertEqual(client.delete(f"/enrollments/{enrollment['enrollment_id']}", headers=ADMIN).status_code, 200)
        self.assertEqual(client.delete(f"/students/{student['id']}", headers=ADMIN).status_code, 200)


class PermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.course = course_ids()[2]
        cls.student = create_student(cls.course)
        cls.instructor = create_instructor()
        student_login, instructor_login = unique("stu"), unique("ins")
        make_user(student_login, "student", student_id=cls.student["id"])
        cls.student_headers = login(student_login)
        make_user(instructor_login, "instructor", instructor_id=cls.instructor["id"])
        cls.instructor_headers = login(instructor_login)
        cls.subject = create_subject(cls.course)
        cls.own_section = create_section(cls.subject, instructor_id=cls.instructor["id"])
        cls.other_section = create_section(cls.subject, pattern="TTH")

    def test_requires_login(self):
        self.assertEqual(client.get("/students/").status_code, 401)
        self.assertEqual(client.get("/students/", headers={"Authorization": "Bearer nope"}).status_code, 401)
        res = client.post("/auth/login", json={"username": "admin", "password": "wrong-password"})
        self.assertEqual(res.status_code, 401)

    def test_student_permissions(self):
        h = self.student_headers
        self.assertEqual(client.get("/students/", headers=h).status_code, 403)
        self.assertEqual(client.post("/students/", json=student_payload(self.course), headers=h).status_code, 403)
        self.assertEqual(client.get("/instructors/", headers=h).status_code, 403)
        self.assertEqual(client.get("/users/", headers=h).status_code, 403)
        self.assertEqual(client.get("/sections", headers=h).status_code, 200)

        me = client.get("/students/me", headers=h).json()["data"]
        self.assertEqual(me["id"], self.student["id"])
        res = client.put("/students/me", json={"address": "New address", "contact_number": "09170000000",
                                               "email": me["email"]}, headers=h)
        self.assertEqual(res.status_code, 200)
        # Students may not change protected fields such as their course.
        res = client.put("/students/me", json={"address": "x y", "contact_number": "09170000000",
                                               "email": me["email"], "course_id": 1}, headers=h)
        self.assertEqual(res.status_code, 422)

        res = client.post("/enrollments/me", json={"section_id": self.own_section["id"]}, headers=h)
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(len(client.get("/enrollments/me", headers=h).json()["data"]), 1)

    def test_self_enrollment_can_be_closed(self):
        settings = client.get("/settings", headers=ADMIN).json()["data"]
        client.put("/settings", json=dict(settings, student_enrollment_enabled=False), headers=ADMIN)
        try:
            res = client.post("/enrollments/me", json={"section_id": self.other_section["id"]},
                              headers=self.student_headers)
            self.assertEqual(res.status_code, 403)
        finally:
            client.put("/settings", json=settings, headers=ADMIN)

    def test_instructor_permissions(self):
        h = self.instructor_headers
        mine = client.get("/instructors/me", headers=h).json()["data"]
        self.assertEqual([s["id"] for s in mine["sections"]], [self.own_section["id"]])
        self.assertEqual(client.get(f"/sections/{self.own_section['id']}/roster", headers=h).status_code, 200)
        self.assertEqual(client.get(f"/sections/{self.other_section['id']}/roster", headers=h).status_code, 403)
        body = {"subject_id": self.subject, "section_code": "Z", "time_slot_id": slot_id("MWF")}
        self.assertEqual(client.post("/sections", json=body, headers=h).status_code, 403)
        self.assertEqual(client.put("/settings", json={}, headers=h).status_code, 403)

    def test_college_admin_is_read_only(self):
        self.assertEqual(client.get("/students/", headers=COLLEGE).status_code, 200)
        self.assertEqual(client.get("/reports/room-utilization", headers=COLLEGE).status_code, 200)
        self.assertEqual(client.post("/students/", json=student_payload(self.course),
                                     headers=COLLEGE).status_code, 403)
        self.assertEqual(client.get("/users/", headers=COLLEGE).status_code, 403)

    def test_cannot_remove_last_admin(self):
        admin_id = next(u["id"] for u in client.get("/users/", headers=ADMIN).json()["data"]
                        if u["username"] == "admin")
        res = client.put(f"/users/{admin_id}", json={"role": "college_admin"}, headers=ADMIN)
        self.assertEqual(res.status_code, 409)


class DashboardTests(unittest.TestCase):
    def test_stats_come_from_data(self):
        stats = client.get("/dashboard", headers=ADMIN).json()["data"]["stats"]
        conn = get_connection()
        self.assertEqual(stats["students"], conn.execute("SELECT COUNT(*) FROM students").fetchone()[0])
        self.assertEqual(stats["enrollments"], conn.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0])
        expected_free = conn.execute(
            "SELECT COALESCE(SUM(s.capacity), 0) - (SELECT COUNT(*) FROM enrollments) FROM sections s"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(stats["available_slots"], expected_free)
        self.assertEqual(stats["courses"], 4)


class LegacyMigrationTest(unittest.TestCase):
    def test_existing_students_are_preserved(self):
        legacy_db = Path(TEMP_DIR) / "legacy.db"
        conn = sqlite3.connect(legacy_db)
        conn.execute("""CREATE TABLE students(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                        age TEXT NOT NULL, course TEXT NOT NULL, birth_date TEXT NOT NULL,
                        address TEXT NOT NULL, contact_number INTEGER NOT NULL)""")
        conn.executemany(
            "INSERT INTO students VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(16, "Ana", "24", "BSIT", "2001-08-01", "Pitogo", 9633221778),
             (19, "Ben", "19", "bsba ", "2005-08-26", "Molave", 923786234)],
        )
        conn.commit()
        conn.close()

        env = dict(os.environ, STUDENT_DB_PATH=str(legacy_db))
        subprocess.run([sys.executable, "-c", "from models.init_tables import initialize_tables; "
                        "initialize_tables(); initialize_tables()"],
                       cwd=BACKEND_DIR, env=env, check=True)

        conn = sqlite3.connect(legacy_db)
        rows = conn.execute("SELECT s.id, s.name, s.contact_number, c.code, s.student_number GLOB "
                            "'[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]' "
                            "FROM students s JOIN courses c ON c.id = s.course_id ORDER BY s.id").fetchall()
        courses = [r[0] for r in conn.execute("SELECT code FROM courses ORDER BY id")]
        conn.close()
        self.assertEqual(rows, [(16, "Ana", "09633221778", "BSIT", 1), (19, "Ben", "0923786234", "BSBA", 1)])
        self.assertEqual(courses, ["BSBA", "BSIT", "COURSE3", "COURSE4"])
        self.assertTrue(any((Path(TEMP_DIR) / "backups").glob("legacy-before-v1-*.db")))


if __name__ == "__main__":
    unittest.main()
