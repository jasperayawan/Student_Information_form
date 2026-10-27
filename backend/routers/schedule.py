"""Class scheduling: valid time slots and class sections (subject offerings)."""
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException

from core.db_helpers import count, fetch_all, fetch_one_or_404, insert_row, update_row
from core.scheduling import (check_slot_in_hours, section_conflicts, slot_problems,
                             student_conflicts)
from core.security import require
from core.settings import get_settings
from database import get_db
from schemas.schedule import SectionCreate, SectionUpdate, TimeSlotCreate

router = APIRouter(tags=["Class Scheduling"])


# ---------- Time slots ----------

@router.get("/time-slots")
def get_time_slots(user=Depends(require("sections.view")), conn=Depends(get_db)) -> dict[str, Any]:
    slots = fetch_all(
        conn,
        """SELECT t.*, (SELECT COUNT(*) FROM sections s WHERE s.time_slot_id = t.id) AS section_count
           FROM time_slots t ORDER BY t.pattern, t.start_time""",
    )
    return {"success": True, "data": slots}


@router.post("/time-slots", status_code=201)
def create_time_slot(slot: TimeSlotCreate, user=Depends(require("sections.manage")),
                     conn=Depends(get_db)) -> dict[str, Any]:
    problems = slot_problems(get_settings(conn), slot.pattern, slot.start_time, slot.end_time, slot.is_exception)
    if problems:
        raise HTTPException(status_code=422, detail=" ".join(problems))
    if conn.execute(
        "SELECT 1 FROM time_slots WHERE pattern = ? AND start_time = ? AND end_time = ?",
        (slot.pattern, slot.start_time, slot.end_time),
    ).fetchone():
        raise HTTPException(status_code=409, detail="This time slot already exists.")
    new_id = insert_row(conn, "time_slots", slot.model_dump())
    conn.commit()
    return {"success": True, "message": "Time slot added.", "data": {"id": new_id}}


@router.delete("/time-slots/{slot_id}")
def delete_time_slot(slot_id: int, user=Depends(require("sections.manage")),
                     conn=Depends(get_db)) -> dict[str, Any]:
    fetch_one_or_404(conn, "SELECT id FROM time_slots WHERE id = ?", (slot_id,), "Time slot not found.")
    used = count(conn, "SELECT COUNT(*) FROM sections WHERE time_slot_id = ?", (slot_id,))
    if used:
        raise HTTPException(status_code=409,
                            detail=f"Cannot delete: {used} class section(s) use this time slot.")
    conn.execute("DELETE FROM time_slots WHERE id = ?", (slot_id,))
    conn.commit()
    return {"success": True, "message": "Time slot deleted."}


# ---------- Sections ----------

def get_section(conn, section_id: int) -> dict[str, Any]:
    return fetch_one_or_404(conn, "SELECT * FROM v_sections WHERE id = ?", (section_id,), "Class section not found.")


def _validate_section(conn, section, section_id: int | None = None) -> None:
    """Every scheduling rule for creating or changing a section."""
    if not conn.execute("SELECT 1 FROM subjects WHERE id = ?", (section.subject_id,)).fetchone():
        raise HTTPException(status_code=422, detail="The selected subject does not exist.")
    slot = conn.execute("SELECT * FROM time_slots WHERE id = ?", (section.time_slot_id,)).fetchone()
    if slot is None:
        raise HTTPException(status_code=422, detail="The selected time slot does not exist.")

    if conn.execute(
        "SELECT 1 FROM sections WHERE subject_id = ? AND section_code = ? AND id IS NOT ?",
        (section.subject_id, section.section_code, section_id),
    ).fetchone():
        raise HTTPException(status_code=409,
                            detail=f"Section {section.section_code} already exists for this subject.")

    problems = check_slot_in_hours(conn, slot)

    if section.instructor_id is not None:
        instructor = conn.execute("SELECT is_active FROM instructors WHERE id = ?",
                                  (section.instructor_id,)).fetchone()
        if instructor is None:
            raise HTTPException(status_code=422, detail="The selected instructor does not exist.")
        if not instructor["is_active"]:
            problems.append("The selected instructor is inactive and cannot be assigned.")

    if section.classroom_id is not None:
        room = conn.execute("SELECT * FROM classrooms WHERE id = ?", (section.classroom_id,)).fetchone()
        if room is None:
            raise HTTPException(status_code=422, detail="The selected classroom does not exist.")
        if not room["is_active"]:
            problems.append(f"Room {room['room_code']} is marked unavailable.")
        if section.capacity > room["capacity"]:
            problems.append(f"Room {room['room_code']} only seats {room['capacity']} students.")

    problems += section_conflicts(conn, slot=slot, instructor_id=section.instructor_id,
                                  classroom_id=section.classroom_id, exclude_section_id=section_id)

    if section_id is not None:
        enrolled = conn.execute("SELECT student_id FROM enrollments WHERE section_id = ?", (section_id,)).fetchall()
        if section.capacity < len(enrolled):
            problems.append(f"Capacity cannot be lower than the {len(enrolled)} students already enrolled.")
        # Moving an existing section must not create clashes for its students.
        for row in enrolled:
            clashes = student_conflicts(conn, row["student_id"], slot, exclude_section_id=section_id)
            if clashes:
                name = conn.execute("SELECT name FROM students WHERE id = ?", (row["student_id"],)).fetchone()[0]
                problems.append(f"Enrolled student {name}: {clashes[0]}")

    if problems:
        raise HTTPException(status_code=409, detail=" ".join(problems))


@router.get("/sections")
def get_sections(
    course_id: int | None = None,
    subject_id: int | None = None,
    instructor_id: int | None = None,
    classroom_id: int | None = None,
    pattern: Literal["MWF", "TTH"] | None = None,
    user=Depends(require("sections.view")),
    conn=Depends(get_db),
) -> dict[str, Any]:
    filters = {"course_id": course_id, "subject_id": subject_id, "instructor_id": instructor_id,
               "classroom_id": classroom_id, "pattern": pattern}
    conditions = [f"{column} = ?" for column, value in filters.items() if value is not None]
    params = tuple(value for value in filters.values() if value is not None)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    sections = fetch_all(
        conn, "SELECT * FROM v_sections" + where + " ORDER BY course_code, subject_code, pattern, start_time",
        params,
    )
    return {"success": True, "data": sections}


@router.get("/sections/{section_id}")
def get_section_detail(section_id: int, user=Depends(require("sections.view")),
                       conn=Depends(get_db)) -> dict[str, Any]:
    return {"success": True, "data": get_section(conn, section_id)}


@router.get("/sections/{section_id}/roster")
def get_section_roster(section_id: int, user=Depends(require("sections.view")),
                       conn=Depends(get_db)) -> dict[str, Any]:
    section = get_section(conn, section_id)
    teaches_it = user["instructor_id"] is not None and user["instructor_id"] == section["instructor_id"]
    if "enrollments.view" not in user["permissions"] and not teaches_it:
        raise HTTPException(status_code=403, detail="You can only view rosters of classes you teach.")
    section["students"] = fetch_all(
        conn,
        """SELECT e.id AS enrollment_id, st.id, st.student_number, st.name, st.email, e.enrolled_at
           FROM enrollments e JOIN students st ON st.id = e.student_id
           WHERE e.section_id = ? ORDER BY st.name""",
        (section_id,),
    )
    return {"success": True, "data": section}


@router.post("/sections", status_code=201)
def create_section(section: SectionCreate, user=Depends(require("sections.manage")),
                   conn=Depends(get_db)) -> dict[str, Any]:
    _validate_section(conn, section)
    new_id = insert_row(conn, "sections", section.model_dump())
    conn.commit()
    return {"success": True, "message": "Class section scheduled.", "data": get_section(conn, new_id)}


@router.put("/sections/{section_id}")
def update_section(section_id: int, section: SectionUpdate, user=Depends(require("sections.manage")),
                   conn=Depends(get_db)) -> dict[str, Any]:
    existing = get_section(conn, section_id)
    if section.subject_id != existing["subject_id"] and existing["enrolled_count"]:
        raise HTTPException(status_code=409,
                            detail="Students are enrolled in this section, so its subject cannot be changed.")
    _validate_section(conn, section, section_id)
    update_row(conn, "sections", section_id, section.model_dump())
    conn.commit()
    return {"success": True, "message": "Class section updated.", "data": get_section(conn, section_id)}


@router.delete("/sections/{section_id}")
def delete_section(section_id: int, user=Depends(require("sections.manage")),
                   conn=Depends(get_db)) -> dict[str, Any]:
    section = get_section(conn, section_id)
    if section["enrolled_count"]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: {section['enrolled_count']} student(s) are enrolled. Drop them first.",
        )
    conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
    conn.commit()
    return {"success": True, "message": "Class section deleted."}
