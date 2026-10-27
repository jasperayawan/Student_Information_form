from pydantic import BaseModel, ConfigDict

PHONE_PATTERN = r"^\+?\d{7,15}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class CleanModel(BaseModel):
    """Base model that trims surrounding whitespace from every string and
    rejects unknown fields so typos don't get silently ignored."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def to_text(value):
    # Older clients sent contact numbers as JSON numbers.
    return str(value) if isinstance(value, int) else value
