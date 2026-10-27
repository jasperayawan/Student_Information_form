from pathlib import Path
import os
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DB_FOLDER = BASE_DIR / "database"

DB_FOLDER.mkdir(exist_ok=True)

# STUDENT_DB_PATH lets the test-suite run against a throwaway database file.
DATABASE = Path(os.environ.get("STUDENT_DB_PATH", DB_FOLDER / "students.db"))


def get_connection():
    conn = sqlite3.connect(DATABASE, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """FastAPI dependency: one connection per request.

    Endpoints call conn.commit() themselves; anything not committed is
    rolled back when the connection closes.
    """
    conn = get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
