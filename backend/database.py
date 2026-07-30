from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DB_FOLDER = BASE_DIR / "database"

DB_FOLDER.mkdir(exist_ok=True)

DATABASE = DB_FOLDER / "students.db"


def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn
