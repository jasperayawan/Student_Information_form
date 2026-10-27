from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from core.db_helpers import count, fetch_all
from core.scheduling import (MIN_OFFERINGS_PER_DAY, MIN_SUBJECTS_PER_COURSE, REQUIRED_COURSE_COUNT,
                             WEEKDAYS, offerings_per_day, to_minutes, weekly_minutes)
from core.security import require
from core.settings import get_settings, save_settings
from database import get_db
from schemas.schedule import SettingsUpdate

router = APIRouter(tags=["Dashboard and Reports"])


def admin_statistics(conn) -> dict[str, Any]:
    """Every number is counted from the live tables."""
    seats = conn.execute(
        "SELECT COALESCE(SUM(capacity), 0), COALESCE(SUM(available_slots), 0) FROM v_sections"
    ).fetchone()
    return {
        "students": count(conn, "SELECT COUNT(*) FROM students"),
        "instructors": count(conn, "SELECT COUNT(*) FROM instructors"),
        "courses": count(conn, "SELECT COUNT(*) FROM courses"),
        "subjects": count(conn, "SELECT COUNT(*) FROM subjects"),
        "classrooms": count(conn, "SELECT COUNT(*) FROM classrooms"),
        "active_classrooms": count(conn, "SELECT COUNT(*) FROM classrooms WHERE is_active = 1"),
        "sections": count(conn, "SELECT COUNT(*) FROM sections"),
        "enrollments": count(conn, "SELECT COUNT(*) FROM enrollments"),
        "total_seats": seats[0],
        "available_slots": seats[1],
        "enrolled_students": count(conn, "SELECT COUNT(DISTINCT student_id) FROM enrollments"),
        "active_instructors": count(conn, "SELECT COUNT(*) FROM instructors WHERE is_active = 1"),
        "teaching_instructors": count(conn, "SELECT COUNT(DISTINCT instructor_id) FROM sections "
                                            "WHERE instructor_id IS NOT NULL"),
        "scheduled_subjects": count(conn, "SELECT COUNT(DISTINCT subject_id) FROM sections"),
        "rooms_in_use": count(conn, "SELECT COUNT(DISTINCT classroom_id) FROM sections "
                                    "WHERE classroom_id IS NOT NULL"),
        "time_slots": count(conn, "SELECT COUNT(*) FROM time_slots"),
    }


def compliance_report(conn) -> dict[str, Any]:
    courses = fetch_all(
        conn,
        """SELECT c.id, c.code, c.name, COUNT(s.id) AS subject_count
           FROM courses c LEFT JOIN subjects s ON s.course_id = c.id
           GROUP BY c.id ORDER BY c.id""",
    )
    for course in courses:
        course["meets_minimum"] = course["subject_count"] >= MIN_SUBJECTS_PER_COURSE

    per_day = offerings_per_day(conn)
    subjects = fetch_all(conn, "SELECT s.id, s.code, s.title, c.code AS course_code FROM subjects s "
                               "JOIN courses c ON c.id = s.course_id ORDER BY c.code, s.code")
    short = []
    for subject in subjects:
        days = per_day.get(subject["id"], {day: 0 for day in WEEKDAYS})
        meeting = [n for n in days.values() if n > 0]
        if not meeting or min(meeting) < MIN_OFFERINGS_PER_DAY:
            short.append({**subject, "offerings_per_day": days})
    return {
        "required_course_count": REQUIRED_COURSE_COUNT,
        "course_count_ok": len(courses) == REQUIRED_COURSE_COUNT,
        "min_subjects_per_course": MIN_SUBJECTS_PER_COURSE,
        "min_offerings_per_day": MIN_OFFERINGS_PER_DAY,
        "courses": courses,
        "subjects_below_offering_minimum": short,
    }


def room_utilization(conn) -> list[dict[str, Any]]:
    settings = get_settings(conn)
    weekly_open = (to_minutes(settings["room_close_time"]) - to_minutes(settings["room_open_time"])) * len(WEEKDAYS)
    rooms = fetch_all(conn, "SELECT id, room_code, is_active FROM classrooms ORDER BY room_code")
    sections = fetch_all(conn, "SELECT classroom_id, pattern, start_time, end_time FROM v_sections "
                               "WHERE classroom_id IS NOT NULL")
    for room in rooms:
        used = sum(weekly_minutes(s) for s in sections if s["classroom_id"] == room["id"])
        room["sections"] = sum(1 for s in sections if s["classroom_id"] == room["id"])
        room["booked_hours"] = round(used / 60, 1)
        room["open_hours"] = round(weekly_open / 60, 1)
        room["utilization_percent"] = round(100 * used / weekly_open, 1) if weekly_open else 0
    return rooms


@router.get("/dashboard")
def dashboard(user=Depends(require("dashboard.view")), conn=Depends(get_db)) -> dict[str, Any]:
    data: dict[str, Any] = {"role": user["role"]}
    if "reports.view" in user["permissions"]:
        data["stats"] = admin_statistics(conn)
        data["compliance"] = compliance_report(conn)
    if user["role"] == "instructor" and user["instructor_id"]:
        sections = fetch_all(conn, "SELECT * FROM v_sections WHERE instructor_id = ? ORDER BY pattern, start_time",
                             (user["instructor_id"],))
        data["teaching"] = {
            "sections": sections,
            "students": sum(s["enrolled_count"] for s in sections),
        }
    if user["role"] == "student" and user["student_id"]:
        classes = fetch_all(
            conn,
            """SELECT v.* FROM enrollments e JOIN v_sections v ON v.id = e.section_id
               WHERE e.student_id = ? ORDER BY v.pattern, v.start_time""",
            (user["student_id"],),
        )
        data["studies"] = {"classes": classes, "units": sum(c["units"] for c in classes)}
    return {"success": True, "data": data}


@router.get("/reports/room-utilization")
def room_utilization_report(user=Depends(require("reports.view")), conn=Depends(get_db)) -> dict[str, Any]:
    return {"success": True, "data": room_utilization(conn)}


@router.get("/reports/compliance")
def compliance(user=Depends(require("reports.view")), conn=Depends(get_db)) -> dict[str, Any]:
    return {"success": True, "data": compliance_report(conn)}


@router.get("/settings")
def read_settings(user=Depends(require("settings.view")), conn=Depends(get_db)) -> dict[str, Any]:
    return {"success": True, "data": get_settings(conn)}


@router.put("/settings")
def update_settings(body: SettingsUpdate, user=Depends(require("settings.manage")),
                    conn=Depends(get_db)) -> dict[str, Any]:
    if to_minutes(body.room_close_time) <= to_minutes(body.room_open_time):
        raise HTTPException(status_code=422, detail="Closing time must be later than opening time.")
    outside = fetch_all(
        conn,
        """SELECT DISTINCT t.pattern, t.start_time, t.end_time FROM time_slots t
           JOIN sections s ON s.time_slot_id = t.id
           WHERE t.start_time < ? OR t.end_time > ?""",
        (body.room_open_time, body.room_close_time),
    )
    if outside:
        listed = ", ".join(f"{s['pattern']} {s['start_time']}-{s['end_time']}" for s in outside)
        raise HTTPException(
            status_code=409,
            detail=f"Scheduled classes would fall outside the new hours ({listed}). Move them first.",
        )
    save_settings(conn, body.model_dump())
    conn.commit()
    return {"success": True, "message": "Settings saved.", "data": get_settings(conn)}
