from datetime import date
from uuid import uuid4

def make_number(prefix: str, on_date: date | None = None) -> str:
    """Human-readable identifier. Database uniqueness remains the final guard."""
    day = on_date or date.today()
    return f"{prefix}-{day:%Y%m%d}-{uuid4().hex[:10].upper()}"
