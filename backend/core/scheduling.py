"""Scheduling rules shared by sections, time slots, enrollments and reports."""
from typing import Any

from core.settings import get_settings

PATTERN_DAYS = {"MWF": ("Mon", "Wed", "Fri"), "TTH": ("Tue", "Thu")}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

MAX_SECTION_CAPACITY = 30
MIN_SUBJECTS_PER_COURSE = 10
MIN_OFFERINGS_PER_DAY = 4
REQUIRED_COURSE_COUNT = 4


def to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def format_time(hhmm: str) -> str:
    hours, minutes = (int(part) for part in hhmm.split(":"))
    suffix = "AM" if hours < 12 else "PM"
    return f"{hours % 12 or 12}:{minutes:02d} {suffix}"


def describe_slot(slot: dict[str, Any]) -> str:
    return f"{slot['pattern']} {format_time(slot['start_time'])}-{format_time(slot['end_time'])}"


def slots_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two slots clash when they share a weekday and their times intersect."""
    shared_days = set(PATTERN_DAYS[a["pattern"]]) & set(PATTERN_DAYS[b["pattern"]])
    return (
        bool(shared_days)
        and to_minutes(a["start_time"]) < to_minutes(b["end_time"])
        and to_minutes(b["start_time"]) < to_minutes(a["end_time"])
    )


def expected_duration(settings: dict[str, Any], pattern: str) -> int:
    if pattern == "MWF":
        return settings["mwf_duration_minutes"]
    return settings["tth_duration_minutes"]


def slot_problems(settings: dict[str, Any], pattern: str, start: str, end: str,
                  is_exception: bool) -> list[str]:
    problems = []
    duration = to_minutes(end) - to_minutes(start)
    if duration <= 0:
        problems.append("End time must be later than start time.")
    elif not is_exception and duration != expected_duration(settings, pattern):
        problems.append(
            f"{pattern} classes must last {expected_duration(settings, pattern)} minutes "
            f"(this slot is {duration}). Mark the slot as an approved exception to allow a different length."
        )
    opens, closes = settings["room_open_time"], settings["room_close_time"]
    if to_minutes(start) < to_minutes(opens) or to_minutes(end) > to_minutes(closes):
        problems.append(
            f"Classes must fall within room operating hours "
            f"({format_time(opens)}-{format_time(closes)})."
        )
    return problems


def check_slot_in_hours(conn, slot: dict[str, Any]) -> list[str]:
    """Re-check a stored slot against the current operating hours.
    (Duration was validated when the slot was created.)"""
    return slot_problems(get_settings(conn), slot["pattern"], slot["start_time"],
                         slot["end_time"], is_exception=True)


def section_conflicts(conn, *, slot: dict[str, Any], instructor_id: int | None,
                      classroom_id: int | None, exclude_section_id: int | None = None) -> list[str]:
    """Instructor and classroom double-booking checks."""
    if instructor_id is None and classroom_id is None:
        return []
    others = conn.execute(
        """SELECT * FROM v_sections
           WHERE id IS NOT ? AND (instructor_id = ? OR classroom_id = ?)""",
        (exclude_section_id, instructor_id, classroom_id),
    ).fetchall()
    problems = []
    for other in others:
        if not slots_overlap(slot, other):
            continue
        clash = f"{other['subject_code']} section {other['section_code']} ({describe_slot(other)})"
        if instructor_id is not None and other["instructor_id"] == instructor_id:
            problems.append(f"Instructor {other['instructor_name']} is already teaching {clash}.")
        if classroom_id is not None and other["classroom_id"] == classroom_id:
            problems.append(f"Room {other['room_code']} is already booked for {clash}.")
    return problems


def student_conflicts(conn, student_id: int, slot: dict[str, Any],
                      exclude_section_id: int | None = None) -> list[str]:
    taken = conn.execute(
        """SELECT v.* FROM enrollments e JOIN v_sections v ON v.id = e.section_id
           WHERE e.student_id = ? AND v.id IS NOT ?""",
        (student_id, exclude_section_id),
    ).fetchall()
    return [
        f"Schedule conflict with {other['subject_code']} section {other['section_code']} "
        f"({describe_slot(other)})."
        for other in taken
        if slots_overlap(slot, other)
    ]


def weekly_minutes(slot: dict[str, Any]) -> int:
    duration = to_minutes(slot["end_time"]) - to_minutes(slot["start_time"])
    return duration * len(PATTERN_DAYS[slot["pattern"]])


def offerings_per_day(conn) -> dict[int, dict[str, int]]:
    """For each subject id: how many sections meet on each weekday."""
    counts: dict[int, dict[str, int]] = {}
    for row in conn.execute("SELECT subject_id, pattern FROM v_sections"):
        per_day = counts.setdefault(row["subject_id"], {day: 0 for day in WEEKDAYS})
        for day in PATTERN_DAYS[row["pattern"]]:
            per_day[day] += 1
    return counts
