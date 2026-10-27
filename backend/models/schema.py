"""Table definitions for the whole system.

Tables are listed in dependency order so foreign keys always point to a
table that already exists.
"""
from core.ids import INSTRUCTOR_ID_DIGITS, STUDENT_ID_GLOB

SETTINGS_TABLE = """
    CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
"""

COURSES_TABLE = """
    CREATE TABLE IF NOT EXISTS courses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT ''
    )
"""

# Column list kept separate so a migration can rebuild the table under a
# temporary name (SQLite can't change a CHECK constraint in place).
STUDENTS_COLUMNS = f"""
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_number TEXT NOT NULL UNIQUE CHECK (student_number GLOB '{STUDENT_ID_GLOB}'),
        name TEXT NOT NULL,
        age INTEGER,
        birth_date TEXT NOT NULL,
        sex TEXT NOT NULL DEFAULT '',
        address TEXT NOT NULL,
        contact_number TEXT NOT NULL,
        email TEXT UNIQUE COLLATE NOCASE,
        previous_school TEXT NOT NULL DEFAULT '',
        previous_attainment TEXT NOT NULL DEFAULT '',
        course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
        year_level INTEGER CHECK (year_level BETWEEN 1 AND 6),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        photo TEXT  -- file name in database/uploads/students, or NULL
"""

STUDENTS_TABLE = f"CREATE TABLE IF NOT EXISTS students({STUDENTS_COLUMNS})"

INSTRUCTORS_TABLE = f"""
    CREATE TABLE IF NOT EXISTS instructors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instructor_number TEXT NOT NULL UNIQUE CHECK (length(instructor_number) = {INSTRUCTOR_ID_DIGITS}),
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        contact_number TEXT NOT NULL,
        department TEXT NOT NULL DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
"""

CLASSROOMS_TABLE = """
    CREATE TABLE IF NOT EXISTS classrooms(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT NOT NULL DEFAULT '',
        capacity INTEGER NOT NULL DEFAULT 30 CHECK (capacity > 0),
        is_active INTEGER NOT NULL DEFAULT 1
    )
"""

SUBJECTS_TABLE = """
    CREATE TABLE IF NOT EXISTS subjects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE COLLATE NOCASE,
        title TEXT NOT NULL,  -- the subject's descriptive title
        units INTEGER NOT NULL CHECK (units IN (2, 3)),
        course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE RESTRICT
    )
"""

TIME_SLOTS_TABLE = """
    CREATE TABLE IF NOT EXISTS time_slots(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern TEXT NOT NULL CHECK (pattern IN ('MWF', 'TTH')),
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        is_exception INTEGER NOT NULL DEFAULT 0,
        note TEXT NOT NULL DEFAULT '',
        UNIQUE (pattern, start_time, end_time)
    )
"""

# A section is one scheduled offering of a subject (its own time, room,
# instructor and 30-seat capacity).
SECTIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS sections(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
        section_code TEXT NOT NULL COLLATE NOCASE,
        time_slot_id INTEGER NOT NULL REFERENCES time_slots(id) ON DELETE RESTRICT,
        instructor_id INTEGER REFERENCES instructors(id) ON DELETE RESTRICT,
        classroom_id INTEGER REFERENCES classrooms(id) ON DELETE RESTRICT,
        capacity INTEGER NOT NULL DEFAULT 30 CHECK (capacity BETWEEN 1 AND 30),
        UNIQUE (subject_id, section_code)
    )
"""

ENROLLMENTS_TABLE = """
    CREATE TABLE IF NOT EXISTS enrollments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
        section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
        enrolled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (student_id, section_id)
    )
"""

USERS_TABLE = """
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('student', 'instructor', 'admin', 'college_admin')),
        student_id INTEGER UNIQUE REFERENCES students(id) ON DELETE CASCADE,
        instructor_id INTEGER UNIQUE REFERENCES instructors(id) ON DELETE CASCADE,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
"""

SESSIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS sessions(
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires_at TEXT NOT NULL
    )
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_students_course ON students(course_id)",
    "CREATE INDEX IF NOT EXISTS idx_subjects_course ON subjects(course_id)",
    "CREATE INDEX IF NOT EXISTS idx_sections_instructor ON sections(instructor_id)",
    "CREATE INDEX IF NOT EXISTS idx_sections_classroom ON sections(classroom_id)",
    "CREATE INDEX IF NOT EXISTS idx_enrollments_section ON enrollments(section_id)",
    "CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id)",
]

# Enrolled counts and available slots are always derived from the
# enrollments table, never stored, so they can't drift out of sync.
SECTIONS_VIEW = """
    CREATE VIEW IF NOT EXISTS v_sections AS
    SELECT
        s.id, s.section_code, s.capacity,
        s.subject_id, sub.code AS subject_code, sub.title AS subject_title, sub.units,
        sub.course_id, c.code AS course_code,
        s.time_slot_id, t.pattern, t.start_time, t.end_time,
        s.instructor_id, i.name AS instructor_name, i.instructor_number,
        s.classroom_id, r.room_code,
        (SELECT COUNT(*) FROM enrollments e WHERE e.section_id = s.id) AS enrolled_count,
        s.capacity - (SELECT COUNT(*) FROM enrollments e WHERE e.section_id = s.id) AS available_slots
    FROM sections s
    JOIN subjects sub ON sub.id = s.subject_id
    JOIN courses c ON c.id = sub.course_id
    JOIN time_slots t ON t.id = s.time_slot_id
    LEFT JOIN instructors i ON i.id = s.instructor_id
    LEFT JOIN classrooms r ON r.id = s.classroom_id
"""

TABLES = [
    SETTINGS_TABLE,
    COURSES_TABLE,
    STUDENTS_TABLE,
    INSTRUCTORS_TABLE,
    CLASSROOMS_TABLE,
    SUBJECTS_TABLE,
    TIME_SLOTS_TABLE,
    SECTIONS_TABLE,
    ENROLLMENTS_TABLE,
    USERS_TABLE,
    SESSIONS_TABLE,
]
