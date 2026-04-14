# onto/errors.py
"""Custom exceptions for ONTO parsing."""


class ONTOError(Exception):
    """Base exception for ONTO parsing errors."""

    pass


class ONTOParseError(ONTOError):
    """Raised when ONTO input is malformed."""

    def __init__(self, message: str, line: int, position: int | None = None):
        self.message = message
        self.line = line
        self.position = position
        location = f"line {line}" + (f", position {position}" if position else "")
        super().__init__(f"{message} at {location}")


class ONTOValidationError(ONTOError):
    """Raised when ONTO structure is invalid (e.g., mismatched record counts)."""

    def __init__(self, message: str, line: int | None = None):
        self.message = message
        self.line = line
        location = f" at line {line}" if line else ""
        super().__init__(f"{message}{location}")