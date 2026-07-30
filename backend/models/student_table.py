from database import get_connection


def create_student_table() -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age TEXT NOT NULL,
            course TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            address TEXT NOT NULL,
            contact_number INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()
