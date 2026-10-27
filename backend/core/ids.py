import re
import secrets
from datetime import date

from fastapi import HTTPException

# Student IDs look like "2026-0101": the registration year, a dash, and a
# random 4-digit number (0000-9999), so each year allows 10,000 students.
STUDENT_ID_REGEX = re.compile(r"\d{4}-\d{4}")
STUDENT_ID_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]"
INSTRUCTOR_ID_DIGITS = 10


def is_student_number(value) -> bool:
    return isinstance(value, str) and STUDENT_ID_REGEX.fullmatch(value) is not None


def generate_student_number(conn, year: int | None = None, table: str = "students") -> str:
    """Return an unused student ID for `year` (default: the current year)."""
    prefix = f"{year or date.today().year}-"
    for _ in range(100):
        candidate = f"{prefix}{secrets.randbelow(10_000):04d}"
        if not conn.execute(f"SELECT 1 FROM {table} WHERE student_number = ?", (candidate,)).fetchone():
            return candidate

    # When a year is nearly full, random guesses can miss the few free numbers.
    used = {row[0] for row in conn.execute(
        f"SELECT student_number FROM {table} WHERE student_number LIKE ?", (prefix + "%",))}
    free = [f"{prefix}{n:04d}" for n in range(10_000) if f"{prefix}{n:04d}" not in used]
    if free:
        return secrets.choice(free)
    raise HTTPException(
        status_code=409,
        detail=f"All 10,000 student IDs for {prefix[:-1]} are already in use.",
    )


def generate_unique_number(conn, table: str, column: str, digits: int) -> str:
    """Return a random number with exactly `digits` digits that is not yet
    used in table.column. The column also has a UNIQUE constraint as a
    last line of defence."""
    lowest = 10 ** (digits - 1)
    for _ in range(100):
        candidate = str(lowest + secrets.randbelow(9 * lowest))
        taken = conn.execute(
            f"SELECT 1 FROM {table} WHERE {column} = ?", (candidate,)
        ).fetchone()
        if not taken:
            return candidate

    # Small ID ranges can get nearly full, so random guessing may miss the
    # few free numbers that are left; look for them directly.
    if digits <= 4:
        used = {row[0] for row in conn.execute(f"SELECT {column} FROM {table}")}
        free = [str(n) for n in range(lowest, lowest * 10) if str(n) not in used]
        if free:
            return secrets.choice(free)
    raise HTTPException(
        status_code=409,
        detail=f"All {9 * lowest} possible {digits}-digit IDs are already in use.",
    )
