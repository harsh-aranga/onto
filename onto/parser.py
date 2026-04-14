# onto/parser.py
"""ONTO parser - converts ONTO string to JSON."""

import re
from dataclasses import dataclass
from enum import Enum, auto

from .errors import ONTOParseError

# Constants
INDENT_SPACES = 4
PIPE = "|"
CARET = "^"
BACKTICK = "`"


class LineType(Enum):
    """Types of lines in ONTO format."""

    ENTITY = auto()  # EntityName[N]:
    FIELD = auto()  # key: values
    NESTED = auto()  # key: (no values, has nested fields)
    COMMENT = auto()  # # comment
    BLANK = auto()  # empty line


@dataclass
class ParsedLine:
    """Represents a parsed line with its metadata."""

    line_type: LineType
    line_number: int
    indent_level: int
    raw: str
    # For ENTITY lines
    entity_name: str | None = None
    record_count: int | None = None
    # For FIELD/NESTED lines
    field_name: str | None = None
    raw_values: str | None = None  # None for NESTED, string for FIELD


# Regex patterns
ENTITY_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_\-\.]*)\[(\d+)\]:$")
FIELD_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_\-\.]*):(.*)$")


def get_indent_level(line: str) -> int:
    """
    Calculate indentation level from leading spaces.

    Args:
        line: Raw line string

    Returns:
        Indentation level (spaces // 4)

    Raises:
        ONTOParseError: If indentation is not a multiple of 4
    """
    stripped = line.lstrip(" ")
    leading_spaces = len(line) - len(stripped)

    if leading_spaces % INDENT_SPACES != 0:
        return -1  # Signal invalid indentation (caller handles error with line number)

    return leading_spaces // INDENT_SPACES


def categorize_line(line: str, line_number: int) -> ParsedLine:
    """
    Categorize a single line and extract its components.

    Args:
        line: Raw line string
        line_number: 1-indexed line number for error reporting

    Returns:
        ParsedLine with type and extracted data

    Raises:
        ONTOParseError: If line has invalid syntax
    """
    # Blank line
    if not line or line.isspace():
        return ParsedLine(
            line_type=LineType.BLANK,
            line_number=line_number,
            indent_level=0,
            raw=line,
        )

    # Comment line (can have leading whitespace)
    stripped = line.strip()
    if stripped.startswith("#"):
        return ParsedLine(
            line_type=LineType.COMMENT,
            line_number=line_number,
            indent_level=0,
            raw=line,
        )

    # Get indentation
    indent_level = get_indent_level(line)
    if indent_level < 0:
        raise ONTOParseError(
            f"Invalid indentation (must be multiple of {INDENT_SPACES} spaces)",
            line_number,
        )

    content = line.strip()

    # Entity line (must be at indent level 0)
    if indent_level == 0:
        entity_match = ENTITY_PATTERN.match(content)
        if entity_match:
            return ParsedLine(
                line_type=LineType.ENTITY,
                line_number=line_number,
                indent_level=0,
                raw=line,
                entity_name=entity_match.group(1),
                record_count=int(entity_match.group(2)),
            )

    # Field line (must be indented)
    if indent_level > 0:
        field_match = FIELD_PATTERN.match(content)
        if field_match:
            field_name = field_match.group(1)
            raw_values = field_match.group(2).strip()

            # Determine if FIELD (has values) or NESTED (no values)
            if raw_values:
                return ParsedLine(
                    line_type=LineType.FIELD,
                    line_number=line_number,
                    indent_level=indent_level,
                    raw=line,
                    field_name=field_name,
                    raw_values=raw_values,
                )
            else:
                return ParsedLine(
                    line_type=LineType.NESTED,
                    line_number=line_number,
                    indent_level=indent_level,
                    raw=line,
                    field_name=field_name,
                )

    # If we get here, line doesn't match any valid pattern
    raise ONTOParseError(f"Invalid syntax: '{content}'", line_number)


def split_respecting_backticks(raw: str, delimiter: str, strip_backticks: bool = True) -> list[str]:
    """
    Split a string by delimiter, respecting backtick-escaped sections.

    Character-by-character scan to handle backticks properly.

    Args:
        raw: The raw string to split
        delimiter: The delimiter character (| or ^)
        strip_backticks: If True, remove backticks from result. If False, preserve them.

    Returns:
        List of split values

    Raises:
        ONTOParseError: If there's an unclosed backtick
    """
    result = []
    current = []
    in_backtick = False
    i = 0

    while i < len(raw):
        char = raw[i]

        if char == BACKTICK:
            if in_backtick:
                # Closing backtick
                in_backtick = False
                if not strip_backticks:
                    current.append(char)
            else:
                # Opening backtick
                in_backtick = True
                if not strip_backticks:
                    current.append(char)
        elif char == delimiter and not in_backtick:
            # Split here
            result.append("".join(current))
            current = []
        else:
            current.append(char)

        i += 1

    # Check for unclosed backtick
    if in_backtick:
        raise ONTOParseError("Unclosed backtick", line=0)  # Line set by caller

    # Add final segment
    result.append("".join(current))

    return result


def strip_backticks_from_value(value: str) -> str:
    """
    Remove backticks from a value string.

    Args:
        value: A value that may contain backticks

    Returns:
        The value with backticks removed
    """
    result = []
    in_backtick = False
    for char in value:
        if char == BACKTICK:
            in_backtick = not in_backtick
        else:
            result.append(char)
    return "".join(result)


def parse_values_raw(raw: str, line_number: int) -> list[str | list[str]]:
    """
    Parse a raw value string into records, handling arrays.

    NOTE: This returns values WITH backticks still present.
    Type inference will strip backticks after checking for force-string.

    Splits by | for records, then by ^ for arrays.
    Applies array-of-arrays promotion: if ANY record contains ^,
    all records become arrays (single values become single-element arrays).

    Args:
        raw: The raw value string (e.g., "Alice|Bob|Charlie" or "a^b|c^d")
        line_number: For error reporting

    Returns:
        List of values (with backticks preserved). If any value contains arrays,
        all values are lists. Otherwise, all values are strings.

    Raises:
        ONTOParseError: If syntax is invalid (unclosed backtick, empty array element)
    """
    # Check if ANY caret exists outside backticks BEFORE any splitting
    # This determines if we need array treatment
    has_arrays = False
    in_backtick = False
    for char in raw:
        if char == BACKTICK:
            in_backtick = not in_backtick
        elif char == CARET and not in_backtick:
            has_arrays = True
            break

    try:
        # First split by pipe (records) - PRESERVE backticks
        records = split_respecting_backticks(raw, PIPE, strip_backticks=False)
    except ONTOParseError as e:
        raise ONTOParseError(e.message, line_number)

    if not has_arrays:
        # Simple case: no arrays, return strings with backticks preserved
        return records

    # Array case: split each record by caret
    result = []
    for record in records:
        # Empty record = null at outer level (not empty array)
        if record == "":
            result.append(record)  # Will be converted to null by type inference
            continue

        try:
            # Split by caret, preserving backticks
            elements = split_respecting_backticks(record, CARET, strip_backticks=False)
        except ONTOParseError as e:
            raise ONTOParseError(e.message, line_number)

        # Check for empty array elements (invalid per spec)
        for elem in elements:
            if elem == "":
                raise ONTOParseError("Empty array element is invalid", line_number)

        result.append(elements)

    return result


def is_backtick_wrapped(value: str) -> bool:
    """Check if a value is wrapped in backticks (force string)."""
    return value.startswith(BACKTICK) and value.endswith(BACKTICK) and len(value) >= 2


def infer_single_type(value: str) -> tuple[type, any]:
    """
    Infer type for a single value and return (type, converted_value).

    Args:
        value: Raw value string (may have backticks)

    Returns:
        Tuple of (inferred_type, converted_value)
        Types: int, float, bool, type(None), str
    """
    # Backtick-wrapped = force string
    if is_backtick_wrapped(value):
        return (str, strip_backticks_from_value(value))

    # Empty = null
    if value == "":
        return (type(None), None)

    # Boolean (case-insensitive)
    if value.lower() == "true":
        return (bool, True)
    if value.lower() == "false":
        return (bool, False)

    # Integer
    if re.match(r"^-?\d+$", value):
        return (int, int(value))

    # Float
    if re.match(r"^-?\d+\.\d+$", value):
        return (float, float(value))

    # Default: string
    return (str, value)


def harmonize_types(type_value_pairs: list[tuple[type, any]]) -> list:
    """
    Harmonize types across a list of values.

    If all non-null values share the same type, keep that type.
    If mixed types, convert everything to strings.

    Args:
        type_value_pairs: List of (type, value) tuples

    Returns:
        List of values with harmonized types
    """
    # Collect non-null types
    non_null_types = set()
    for t, v in type_value_pairs:
        if t is not type(None):
            non_null_types.add(t)

    # If only one non-null type (or no types), keep as-is
    if len(non_null_types) <= 1:
        return [v for _, v in type_value_pairs]

    # Mixed types: convert everything to string (except null)
    result = []
    for t, v in type_value_pairs:
        if v is None:
            result.append(None)
        else:
            result.append(str(v))
    return result


def infer_types(values: list[str | list[str]]) -> list:
    """
    Apply type inference to parsed values.

    Handles both flat lists and nested arrays.
    Applies field-wide type harmonization.
    Backtick-wrapped values are forced to string, then field harmonizes normally.

    Args:
        values: List from parse_values_raw (backticks still present)

    Returns:
        List with proper Python types (int, float, bool, None, str, or lists thereof)
    """
    if not values:
        return values

    # Check if we have arrays (list of lists) or flat (list of strings)
    has_nested = any(isinstance(v, list) for v in values)

    if not has_nested:
        # Flat case: infer types for each value
        type_value_pairs = [infer_single_type(v) for v in values]
        return harmonize_types(type_value_pairs)

    # Nested case: values may be strings (null at outer level) or lists
    # First, infer types for all elements across all arrays
    all_type_value_pairs = []
    structure = []  # Track structure: None for null, list of pairs for arrays

    for v in values:
        if isinstance(v, str):
            # Outer-level null (empty string)
            pair = infer_single_type(v)
            structure.append(("null", pair))
        else:
            # Array of elements
            pairs = [infer_single_type(elem) for elem in v]
            structure.append(("array", pairs))
            all_type_value_pairs.extend(pairs)

    # Collect all non-null types across ALL array elements
    non_null_types = set()
    for t, v in all_type_value_pairs:
        if t is not type(None):
            non_null_types.add(t)

    # Determine if we need to stringify
    needs_stringify = len(non_null_types) > 1

    # Rebuild result with harmonized types
    result = []
    for kind, data in structure:
        if kind == "null":
            t, v = data
            if v is None:
                result.append(None)
            elif needs_stringify:
                result.append(str(v) if v is not None else None)
            else:
                result.append(v)
        else:
            # Array
            if needs_stringify:
                arr = [str(v) if v is not None else None for _, v in data]
            else:
                arr = [v for _, v in data]
            result.append(arr)

    return result


# Keep old function name for backward compatibility with tests
def parse_values(raw: str, line_number: int) -> list[str | list[str]]:
    """
    Parse a raw value string into records, handling arrays.
    Strips backticks from values.

    NOTE: This is the old interface that strips backticks.
    For type inference pipeline, use parse_values_raw + infer_types.
    """
    raw_values = parse_values_raw(raw, line_number)

    # Strip backticks from all values
    def strip_recursive(v):
        if isinstance(v, list):
            return [strip_backticks_from_value(elem) for elem in v]
        return strip_backticks_from_value(v)

    return [strip_recursive(v) for v in raw_values]


def parse_lines(onto_str: str) -> list[ParsedLine]:
    """
    Parse all lines in an ONTO string.

    Args:
        onto_str: Complete ONTO document string

    Returns:
        List of ParsedLine objects (excluding BLANK and COMMENT)

    Raises:
        ONTOParseError: If any line has invalid syntax
    """
    lines = onto_str.split("\n")
    parsed = []

    for i, line in enumerate(lines, start=1):
        parsed_line = categorize_line(line, i)
        # Skip blanks and comments
        if parsed_line.line_type not in (LineType.BLANK, LineType.COMMENT):
            parsed.append(parsed_line)

    return parsed


def build_structure(parsed_lines: list[ParsedLine]) -> tuple[str, int, dict]:
    """
    Build a columnar structure from parsed lines.

    Returns a dict where keys are field paths and values are typed value lists.
    Nested fields use dot notation internally during building.

    Args:
        parsed_lines: List of ParsedLine from parse_lines()

    Returns:
        Tuple of (entity_name, record_count, fields_dict)
        fields_dict maps field_name -> list of typed values

    Raises:
        ONTOParseError: If structure is invalid
        ONTOValidationError: If record counts don't match
    """
    from .errors import ONTOValidationError

    if not parsed_lines:
        raise ONTOParseError("Empty ONTO document", line=0)

    # First line must be entity
    first = parsed_lines[0]
    if first.line_type != LineType.ENTITY:
        raise ONTOParseError("Document must start with entity declaration", first.line_number)

    entity_name = first.entity_name
    record_count = first.record_count

    # Build nested structure using indentation stack
    # Stack holds (indent_level, field_path_prefix)
    # field_path_prefix is a list of field names leading to current level

    fields = {}  # flat dict: tuple(path...) -> typed values
    indent_stack = [(0, [])]  # (indent_level, path_prefix)

    for line in parsed_lines[1:]:
        indent = line.indent_level

        # Validate: indent can only increase by 1 level at a time
        if indent > indent_stack[-1][0] + 1:
            raise ONTOParseError(
                f"Invalid indentation: level {indent} after level {indent_stack[-1][0]} "
                f"(can only increase by 1)",
                line.line_number
            )

        # Pop stack until we find parent level
        while indent_stack and indent_stack[-1][0] >= indent:
            indent_stack.pop()

        if not indent_stack:
            # Should not happen with valid indentation
            raise ONTOParseError("Invalid indentation structure", line.line_number)

        parent_path = indent_stack[-1][1]
        current_path = parent_path + [line.field_name]

        if line.line_type == LineType.NESTED:
            # Push onto stack for children
            indent_stack.append((indent, current_path))

        elif line.line_type == LineType.FIELD:
            # Parse and type-infer values
            raw_values = parse_values_raw(line.raw_values, line.line_number)
            typed_values = infer_types(raw_values)

            # Validate record count
            if len(typed_values) != record_count:
                raise ONTOValidationError(
                    f"Field '{'.'.join(current_path)}' has {len(typed_values)} values, "
                    f"expected {record_count}",
                    line.line_number
                )

            # Store with path as key
            fields[tuple(current_path)] = typed_values

    return entity_name, record_count, fields


def columnar_to_records(record_count: int, fields: dict) -> list[dict]:
    """
    Convert columnar field data to list of record dicts.

    Args:
        record_count: Number of records
        fields: Dict mapping tuple(path...) -> list of values

    Returns:
        List of dicts, one per record
    """
    records = [{} for _ in range(record_count)]

    for path, values in fields.items():
        for i, value in enumerate(values):
            # Navigate/create nested structure
            current = records[i]
            for key in path[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            current[path[-1]] = value

    return records


def loads(onto_str: str) -> list[dict]:
    """
    Parse ONTO string to list of dicts.

    Args:
        onto_str: ONTO formatted string

    Returns:
        List of dictionaries representing the records

    Raises:
        ONTOParseError: If ONTO syntax is invalid
        ONTOValidationError: If structure is invalid
    """
    parsed_lines = parse_lines(onto_str)
    entity_name, record_count, fields = build_structure(parsed_lines)
    records = columnar_to_records(record_count, fields)
    return records