# AUTO-GENERATED FROM enums.json — DO NOT EDIT
# Regenerate with `python generate.py` from the repo root.

"""Canonical Localoy enums.

Each enum subclasses ``str`` so pydantic/FastAPI serialize members to their
raw string value with no custom encoder.
"""

from enum import Enum

__all__ = [
    "EventType",
    "EventStatus",
]


class EventType(str, Enum):
    """EventType."""

    INDOOR = "indoor"
    OUTDOOR = "outdoor"


class EventStatus(str, Enum):
    """EventStatus."""

    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"
