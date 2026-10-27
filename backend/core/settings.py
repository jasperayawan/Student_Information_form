from typing import Any

# Default room operating window is 8 hours. The start time is a placeholder
# chosen so the example evening classes (7:10 PM / 7:30 PM) fit; the real
# hours must be confirmed by the school and set in the Settings page.
DEFAULT_SETTINGS = {
    "room_open_time": "13:00",
    "room_close_time": "21:00",
    "mwf_duration_minutes": "60",
    "tth_duration_minutes": "90",
    "student_enrollment_enabled": "1",
}


def get_settings(conn) -> dict[str, Any]:
    values = dict(DEFAULT_SETTINGS)
    for row in conn.execute("SELECT key, value FROM settings"):
        values[row["key"]] = row["value"]
    return {
        "room_open_time": values["room_open_time"],
        "room_close_time": values["room_close_time"],
        "mwf_duration_minutes": int(values["mwf_duration_minutes"]),
        "tth_duration_minutes": int(values["tth_duration_minutes"]),
        "student_enrollment_enabled": values["student_enrollment_enabled"] == "1",
    }


def save_settings(conn, data: dict[str, Any]) -> None:
    for key, value in data.items():
        if isinstance(value, bool):
            value = "1" if value else "0"
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value))
        )
