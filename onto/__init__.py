# onto/__init__.py
"""ONTO: Object Notation for Token Optimization."""

from .errors import ONTOError, ONTOParseError, ONTOValidationError
from .parser import loads

__all__ = ["loads", "dumps", "ONTOError", "ONTOParseError", "ONTOValidationError"]


def dumps(data: list[dict], entity_name: str = "Entity") -> str:
    """
    Serialize JSON (list of dicts) to ONTO string.

    Args:
        data: List of dictionaries to serialize
        entity_name: Name for the entity declaration

    Returns:
        ONTO formatted string

    Raises:
        ONTOError: If data cannot be serialized to ONTO
    """
    # TODO: Implement in Phase 2
    raise NotImplementedError("dumps() not yet implemented")