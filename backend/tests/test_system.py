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


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class StudentPhotoTests(unittest.TestCase):
    def test_account_badge_shows_student_photo_and_name(self):
        student = create_student(course_ids()[0], name="Badge Student")
        name = unique("badge")
        make_user(name, "student", student_id=student["id"])
        headers = login(name)
        me = client.get("/auth/me", headers=headers).json()["data"]
        self.assertEqual((me["display_name"], me["photo"]), ("Badge Student", None))
        client.put(f"/students/{student['id']}/photo", files={"photo": ("p.png", PNG_BYTES, "image/png")}, headers=ADMIN)
        me = client.get("/auth/me", headers=headers).json()["data"]
        self.assertTrue(me["photo"])
        self.assertEqual(client.get(f"/students/{student['id']}/photo", headers=headers).status_code, 200)
        admin = client.get("/auth/me", headers=ADMIN).json()["data"]
        self.assertEqual((admin["display_name"], admin["photo"]), ("admin", None))

    def test_upload_view_replace_and_delete(self):
        from core.uploads import PHOTO_DIR
        course = course_ids()[0]
        student, other = create_student(course), create_student(course)
        url = f"/students/{student['id']}/photo"
        self.assertEqual(client.get(url, headers=ADMIN).status_code, 404)

        res = client.put(url, files={"photo": ("me.png", PNG_BYTES, "image/png")}, headers=ADMIN)
        self.assertEqual(res.status_code, 200, res.text)
        first = res.json()["data"]["photo"]
        self.assertTrue((PHOTO_DIR / first).is_file())
        res = client.get(url, headers=ADMIN)
        self.assertEqual((res.status_code, res.headers["content-type"], res.content), (200, "image/png", PNG_BYTES))

        # The student may see their own photo; other students and instructors may not.
        def account(role, **link):
            name = unique("photo")
            make_user(name, role, **link)
            return login(name)
        own = account("student", student_id=student["id"])
        stranger = account("student", student_id=other["id"])
        teacher = account("instructor", instructor_id=create_instructor()["id"])
        self.assertEqual(client.get(url, headers=own).status_code, 200)
        self.assertEqual(client.get(url, headers=stranger).status_code, 403)
        self.assertEqual(client.get(url, headers=teacher).status_code, 403)
        self.assertEqual(client.put(url, files={"photo": ("x.png", PNG_BYTES, "image/png")},
                                    headers=own).status_code, 403)

        # Content is checked, not the file name or declared type.
        fake = client.put(url, files={"photo": ("evil.png", b"<script>alert(1)</script>", "image/png")}, headers=ADMIN)
        self.assertEqual(fake.status_code, 422)
        big = client.put(url, files={"photo": ("big.png", PNG_BYTES + b"0" * (2 * 1024 * 1024), "image/png")},
                         headers=ADMIN)
        self.assertEqual(big.status_code, 413)

        # Replacing removes the old file; editing details keeps the photo.
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
        second = client.put(url, files={"photo": ("me.jpg", jpeg, "image/jpeg")}, headers=ADMIN).json()["data"]["photo"]
        self.assertFalse((PHOTO_DIR / first).exists())
        update = student_payload(course, email=student["email"])
        self.assertEqual(client.put(f"/students/{student['id']}", json=update, headers=ADMIN).json()["data"]["photo"], second)

        self.assertEqual(client.delete(url, headers=ADMIN).status_code, 200)
        self.assertFalse((PHOTO_DIR / second).exists())
        self.assertEqual(client.get(url, headers=ADMIN).status_code, 404)

        third = client.put(url, files={"photo": ("me.png", PNG_BYTES, "image/png")}, headers=ADMIN).json()["data"]["photo"]
        self.assertEqual(client.delete(f"/students/{student['id']}", headers=ADMIN).status_code, 200)
        self.assertFalse((PHOTO_DIR / third).exists())


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
        self.assertEqual(client.get("/courses/", headers=h).status_code, 403)

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

    def test_student_sees_only_enrolled_subjects(self):
        h = self.student_headers
        other_subject = create_subject(self.course)
        create_section(other_subject, pattern="TTH")
        enrolled = {e["subject_id"] for e in client.get("/enrollments/me", headers=h).json()["data"]}
        listed = {s["id"]: s for s in client.get("/subjects/", headers=h).json()["data"]}
        self.assertEqual(set(listed), enrolled)
        self.assertNotIn(other_subject, listed)
        self.assertEqual(client.get(f"/subjects/{other_subject}", headers=h).status_code, 404)
        for subject_id in listed:
            sections = client.get(f"/subjects/{subject_id}", headers=h).json()["data"]["sections"]
            mine = {e["id"] for e in client.get("/enrollments/me", headers=h).json()["data"]}
            self.assertTrue(sections and {s["id"] for s in sections} <= mine)

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

    def test_instructor_sees_only_assigned_subjects(self):
        h = self.instructor_headers
        unassigned = create_subject(self.course)
        codes = {s["id"]: s for s in client.get("/subjects/", headers=h).json()["data"]}
        self.assertIn(self.subject, codes)
        self.assertNotIn(unassigned, codes)
        # Every listed subject really has a section taught by this instructor.
        mine = {s["subject_id"] for s in client.get("/instructors/me", headers=h).json()["data"]["sections"]}
        self.assertEqual(set(codes), mine)
        # Only their own section of that subject is counted and listed.
        self.assertEqual(codes[self.subject]["section_count"], 1)
        detail = client.get(f"/subjects/{self.subject}", headers=h).json()["data"]
        self.assertEqual([s["id"] for s in detail["sections"]], [self.own_section["id"]])
        self.assertEqual(client.get(f"/subjects/{unassigned}", headers=h).status_code, 404)
        # Instructors have no Courses module.
        self.assertEqual(client.get("/courses/", headers=h).status_code, 403)
        # Administrators still see every subject.
        all_ids = {s["id"] for s in client.get("/subjects/", headers=ADMIN).json()["data"]}
        self.assertTrue({self.subject, unassigned} <= all_ids)

    def test_instructor_sees_enrolled_students_of_own_sections(self):
        h = self.instructor_headers
        subject = create_subject(self.course)
        mine = create_section(subject, instructor_id=self.instructor["id"], pattern="TTH")
        other = create_section(subject)
        a, b = create_student(self.course), create_student(self.course)
        for student, section in ((a, mine), (b, other)):
            res = client.post("/enrollments/", json={"student_id": student["id"], "section_id": section["id"]},
                              headers=ADMIN)
            self.assertEqual(res.status_code, 201, res.text)

        row = next(s for s in client.get("/subjects/", headers=h).json()["data"] if s["id"] == subject)
        self.assertEqual(row["enrolled_count"], 1)
        students = client.get(f"/subjects/{subject}/students", headers=h).json()["data"]
        self.assertEqual([s["student_id"] for s in students], [a["id"]])
        # Administrators see every enrolled student; students may not look.
        all_students = client.get(f"/subjects/{subject}/students", headers=ADMIN).json()["data"]
        self.assertEqual({s["student_id"] for s in all_students}, {a["id"], b["id"]})
        self.assertEqual(client.get(f"/subjects/{subject}/students", headers=self.student_headers).status_code, 403)

    def test_it_admin_can_schedule_but_not_manage_records(self):
        self.assertEqual(client.get("/students/", headers=COLLEGE).status_code, 200)
        self.assertEqual(client.get("/reports/room-utilization", headers=COLLEGE).status_code, 200)
        self.assertEqual(client.post("/students/", json=student_payload(self.course),
                                     headers=COLLEGE).status_code, 403)
        self.assertEqual(client.get("/users/", headers=COLLEGE).status_code, 403)
        self.assertEqual(client.post("/subjects/", json={"code": "ITADM1", "title": "Test", "units": 3,
                                                         "course_id": self.course}, headers=COLLEGE).status_code, 403)
        self.assertEqual(client.put("/settings", json={}, headers=COLLEGE).status_code, 403)

        # Scheduling: create a class, then reassign its instructor and room.
        teacher, other_teacher = create_instructor(), create_instructor()
        room, other_room = next_room(), next_room()
        body = {"subject_id": self.subject, "section_code": unique("IT"), "time_slot_id": slot_id("TTH"),
                "instructor_id": teacher["id"], "classroom_id": room, "capacity": 30}
        res = client.post("/sections", json=body, headers=COLLEGE)
        self.assertEqual(res.status_code, 201, res.text)
        section_id = res.json()["data"]["id"]
        body.update(instructor_id=other_teacher["id"], classroom_id=other_room)
        res = client.put(f"/sections/{section_id}", json=body, headers=COLLEGE)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual((res.json()["data"]["instructor_id"], res.json()["data"]["classroom_id"]),
                         (other_teacher["id"], other_room))
        # The same conflict rules apply to them as to administrators.
        clash = dict(body, section_code=unique("IT"), classroom_id=next_room())
        self.assertEqual(client.post("/sections", json=clash, headers=COLLEGE).status_code, 409)
        slot = {"pattern": "MWF", "start_time": "13:00", "end_time": "14:00", "note": "IT admin"}
        self.assertIn(client.post("/time-slots", json=slot, headers=COLLEGE).status_code, (201, 409))
        self.assertEqual(client.delete(f"/sections/{section_id}", headers=COLLEGE).status_code, 200)

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
