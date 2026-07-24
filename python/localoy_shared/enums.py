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
    "CuisineType",
]


class EventType(str, Enum):
    """EventType."""

    INDOOR = "indoor"
    OUTDOOR = "outdoor"
    HYBRID = "hybrid"
    OTHER = "other"
    TESTING_ANOTHER_ONE = "testing another one"


class EventStatus(str, Enum):
    """EventStatus."""

    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


class CuisineType(str, Enum):
    """Cuisine categories a dining partner can tag."""

    AFGHAN = "AFGHAN"
    BBQ = "BBQ"
    CHINESE = "CHINESE"
    INDIAN = "INDIAN"
    KOREAN = "KOREAN"
    MEXICAN = "MEXICAN"
    PAKISTANI = "PAKISTANI"
    TURKISH = "TURKISH"
    AMERICAN = "AMERICAN"
    BAKERY = "BAKERY"
    CONTINENTAL = "CONTINENTAL"
    ITALIAN = "ITALIAN"
    LEBANESE = "LEBANESE"
    MIDDLE_EASTERN = "MIDDLE_EASTERN"
    SEAFOOD = "SEAFOOD"
    VEGETARIAN = "VEGETARIAN"
    ARABIAN = "ARABIAN"
    BANGLADESHI = "BANGLADESHI"
    DESSERTS = "DESSERTS"
    JAPANESE = "JAPANESE"
    MEDITERRANEAN = "MEDITERRANEAN"
    NEPALESE = "NEPALESE"
    THAI = "THAI"
