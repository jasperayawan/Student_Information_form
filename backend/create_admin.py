"""Create (or reset) an administrator login.

Usage (from the backend folder):
    python create_admin.py <username>
You will be asked for the password; it is never stored in plain text.
"""
import getpass
import sys

from core.security import hash_password
from database import get_connection
from models.init_tables import initialize_tables


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python create_admin.py <username>")
        sys.exit(1)
    username = sys.argv[1].strip()
    password = getpass.getpass("Password (min 8 characters): ")
    if len(password) < 8 or password != getpass.getpass("Repeat password: "):
        print("Passwords must match and be at least 8 characters.")
        sys.exit(1)

    initialize_tables()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')
               ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash,
                   role = 'admin', student_id = NULL, instructor_id = NULL, is_active = 1""",
            (username, hash_password(password)),
        )
        conn.commit()
    finally:
        conn.close()
    print(f"Administrator '{username}' is ready. Log in at http://127.0.0.1:8000/app/")


if __name__ == "__main__":
    main()
