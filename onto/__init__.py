# onto/__init__.py
"""ONTO: Object Notation for Token Optimization."""

from .errors import ONTOError, ONTOParseError, ONTOValidationError
from .parser import loads
from .serializer import dumps

__all__ = ["loads", "dumps", "ONTOError", "ONTOParseError", "ONTOValidationError"]