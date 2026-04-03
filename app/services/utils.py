from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.inspection import inspect


def model_to_dict(obj: object) -> dict:
    mapper = inspect(obj).mapper
    out: dict = {}
    for col in mapper.column_attrs:
        key = col.key
        val = getattr(obj, key)
        if isinstance(val, (UUID,)):
            out[key] = str(val)
        elif isinstance(val, (datetime, date)):
            out[key] = val.isoformat()
        else:
            out[key] = val
    return out

