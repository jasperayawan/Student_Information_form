"""Versioned schema upgrades.

The database version is stored in SQLite's built-in `PRAGMA user_version`.
Each migration runs once, inside a transaction, and the database file is
copied to database/backups/ before any existing data is touched.
"""
import shutil
from datetime import datetime

from core.ids import generate_student_number, is_student_number
from core.scheduling import REQUIRED_COURSE_COUNT
from core.settings import DEFAULT_SETTINGS
from database import DATABASE, get_connection
from models import schema

CLASSROOM_COUNT = 30

# The two schedule patterns given in the requirements. Admins can add more.
EXAMPLE_TIME_SLOTS = [
    ("MWF", "19:30", "20:30"),
    ("TTH", "19:10", "20:40"),
]


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def _columns(conn, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _backup_database(conn, label: str) -> None:
    if not _table_exists(conn, "students"):
        return
    backup_dir = DATABASE.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(DATABASE, backup_dir / f"{DATABASE.stem}-before-{label}-{stamp}.db")


def _legacy_contact(value) -> str:
    # The old schema stored contact numbers as INTEGER, which dropped the
    # leading zero (the old UI displayed it as "0" + number).
    text = str(value).strip()
    if text.isdigit() and not text.startswith("0"):
        text = "0" + text
    return text


def _legacy_age(value):
    text = str(value).strip()
    return int(text) if text.isdigit() else None


def _migrate_legacy_students(conn) -> None:
    """Move rows from the original students table (free-text course,
    integer contact) into the new structure, keeping their ids."""
    conn.execute("ALTER TABLE students RENAME TO students_legacy")
    conn.execute(schema.COURSES_TABLE)
    conn.execute(schema.STUDENTS_TABLE)

    for row in conn.execute(
        "SELECT DISTINCT UPPER(TRIM(course)) AS code FROM students_legacy "
        "WHERE TRIM(course) <> '' ORDER BY code"
    ).fetchall():
        conn.execute(
            "INSERT OR IGNORE INTO courses (code, name) VALUES (?, ?)", (row["code"], row["code"])
        )

    for row in conn.execute("SELECT * FROM students_legacy ORDER BY id").fetchall():
        course = conn.execute(
            "SELECT id FROM courses WHERE code = UPPER(TRIM(?))", (row["course"],)
        ).fetchone()
        if course is None:
            # Blank course text: keep the student under a clearly-named course.
            conn.execute("INSERT OR IGNORE INTO courses (code, name) VALUES ('UNASSIGNED', 'Unassigned')")
            course = conn.execute("SELECT id FROM courses WHERE code = 'UNASSIGNED'").fetchone()
        conn.execute(
            """INSERT INTO students
               (id, student_number, name, age, birth_date, address, contact_number, course_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["id"],
                generate_student_number(conn),
                row["name"].strip(),
                _legacy_age(row["age"]),
                row["birth_date"],
                row["address"],
                _legacy_contact(row["contact_number"]),
                course["id"],
            ),
        )
    conn.execute("DROP TABLE students_legacy")


def _seed_defaults(conn) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    # Course names are not invented: placeholders are created only to reach
    # the required four and are meant to be renamed by an administrator.
    number = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0] + 1
    while conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0] < REQUIRED_COURSE_COUNT:
        conn.execute(
            "INSERT OR IGNORE INTO courses (code, name, description) VALUES (?, ?, ?)",
            (f"COURSE{number}", f"Course {number} (name not set)",
             "Placeholder - rename in Course Management."),
        )
        number += 1

    if conn.execute("SELECT COUNT(*) FROM classrooms").fetchone()[0] == 0:
        for n in range(1, CLASSROOM_COUNT + 1):
            conn.execute(
                "INSERT INTO classrooms (room_code, name) VALUES (?, ?)", (f"RM-{n:02d}", f"Room {n}")
            )

    for pattern, start, end in EXAMPLE_TIME_SLOTS:
        conn.execute(
            "INSERT OR IGNORE INTO time_slots (pattern, start_time, end_time, note) VALUES (?, ?, ?, ?)",
            (pattern, start, end, "From the scheduling requirements"),
        )


def _migrate_to_v1(conn) -> None:
    legacy = _table_exists(conn, "students") and "student_number" not in _columns(conn, "students")
    if legacy:
        _backup_database(conn, "v1")

    conn.isolation_level = None  # manage the transaction ourselves
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        if legacy:
            _migrate_legacy_students(conn)
        for statement in schema.TABLES:
            conn.execute(statement)
        for statement in schema.INDEXES:
            conn.execute(statement)
        conn.execute(schema.SECTIONS_VIEW)
        _seed_defaults(conn)
        conn.execute("PRAGMA user_version = 1")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.isolation_level = ""


def _registration_year(created_at) -> int | None:
    text = str(created_at or "")[:4]
    return int(text) if text.isdigit() else None


def _rebuild_students(conn, version: int) -> None:
    """Rebuild the students table with the current schema (SQLite can't
    change a CHECK constraint in place), giving every student whose ID is not
    in the current "YYYY-NNNN" format a new one, using the year they were
    registered. Record ids (and so enrollments and logins) stay the same.

    Follows SQLite's documented table-rebuild steps: create the new table,
    copy rows, drop the old table, rename the new one into place."""
    has_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] > 0
    if has_students:
        _backup_database(conn, f"v{version}")

    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        conn.execute(f"CREATE TABLE students_new({schema.STUDENTS_COLUMNS})")
        new_columns = {row["name"] for row in conn.execute("PRAGMA table_info(students_new)")}
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(students)") if row["name"] in new_columns]
        marks = ", ".join("?" for _ in columns)
        for row in conn.execute("SELECT * FROM students ORDER BY id").fetchall():
            values = dict(row)
            if not is_student_number(values["student_number"]):
                values["student_number"] = generate_student_number(
                    conn, _registration_year(values["created_at"]), table="students_new")
            conn.execute(f"INSERT INTO students_new ({', '.join(columns)}) VALUES ({marks})",
                         [values[c] for c in columns])
        conn.execute("DROP TABLE students")
        conn.execute("ALTER TABLE students_new RENAME TO students")
        for statement in schema.INDEXES:
            conn.execute(statement)
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise RuntimeError(f"Foreign key check failed after rebuilding students: {problems}")
        conn.execute(f"PRAGMA user_version = {version}")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.isolation_level = ""


def _migrate_to_v3(conn) -> None:
    """Subjects keep a single descriptive title; the separate description
    column is removed."""
    if "description" in _columns(conn, "subjects"):
        if conn.execute("SELECT COUNT(*) FROM subjects WHERE description <> ''").fetchone()[0]:
            _backup_database(conn, "v3")
        conn.execute("ALTER TABLE subjects DROP COLUMN description")
    conn.execute("PRAGMA user_version = 3")
    conn.commit()


def _migrate_to_v5(conn) -> None:
    """Students get an optional photo (a file name; the image lives in
    database/uploads/students)."""
    if "photo" not in _columns(conn, "students"):
        conn.execute("ALTER TABLE students ADD COLUMN photo TEXT")
    conn.execute("PRAGMA user_version = 5")
    conn.commit()


def run_migrations() -> None:
    conn = get_connection()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            _migrate_to_v1(conn)
        if version < 2:
            _rebuild_students(conn, 2)   # shortened 7-digit IDs (now straight to YYYY-NNNN)
        if version < 3:
            _migrate_to_v3(conn)
        if version < 4:
            _rebuild_students(conn, 4)   # student IDs become YYYY-NNNN
        if version < 5:
            _migrate_to_v5(conn)
    finally:
        conn.close()
