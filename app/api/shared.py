"""Shared utility helpers for API route modules."""
from decimal import Decimal


def _decimal_to_float(val) -> float:
    """Convert Decimal to float for JSON serialization."""
    if isinstance(val, Decimal):
        return float(val)
    return val
