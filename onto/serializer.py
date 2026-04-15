# onto/serializer.py
"""ONTO serializer - converts JSON to ONTO string."""

from .errors import ONTOError


def get_field_paths(record: dict, prefix: tuple = ()) -> list[tuple]:
    """
    Extract all field paths from a record, flattening nested dicts.

    Uses depth-first traversal to ensure paths are ordered correctly
    for ONTO output generation (parent paths before children, siblings grouped).

    Args:
        record: A single record dict
        prefix: Current path prefix (for recursion)

    Returns:
        List of tuples representing field paths in DFS order
        e.g., {"a": 1, "b": {"c": 2}} -> [("a",), ("b", "c")]
    """
    paths = []
    for key, value in record.items():
        current_path = prefix + (key,)
        if isinstance(value, dict):
            # Recurse into nested dict
            paths.extend(get_field_paths(value, current_path))
        else:
            # Leaf field
            paths.append(current_path)
    return paths


def validate_records(data: list[dict]) -> tuple[int, list[tuple]]:
    """
    Validate that all records have consistent structure.

    Args:
        data: List of record dicts

    Returns:
        Tuple of (record_count, field_paths)

    Raises:
        ONTOError: If data is empty or records have inconsistent structure
    """
    if not isinstance(data, list):
        raise ONTOError("Data must be a list of dicts")

    if not data:
        raise ONTOError("Cannot serialize empty list")

    if not all(isinstance(r, dict) for r in data):
        raise ONTOError("All records must be dicts")

    record_count = len(data)

    # Get field paths from first record
    field_paths = get_field_paths(data[0])
    field_paths_set = set(field_paths)

    # Validate all records have same structure
    for i, record in enumerate(data[1:], start=2):
        record_paths = get_field_paths(record)
        record_paths_set = set(record_paths)

        if record_paths_set != field_paths_set:
            missing = field_paths_set - record_paths_set
            extra = record_paths_set - field_paths_set

            msg_parts = [f"Record {i} has inconsistent structure"]
            if missing:
                msg_parts.append(f"missing: {['.'.join(p) for p in missing]}")
            if extra:
                msg_parts.append(f"extra: {['.'.join(p) for p in extra]}")

            raise ONTOError(". ".join(msg_parts))

    return record_count, field_paths


def get_value_at_path(record: dict, path: tuple):
    """
    Get value from record at given path.

    Args:
        record: A record dict
        path: Tuple path like ("address", "city")

    Returns:
        Value at that path
    """
    current = record
    for key in path:
        current = current[key]
    return current


def collect_columnar_values(data: list[dict], field_paths: list[tuple]) -> dict:
    """
    Collect values for each field path across all records (columnar format).

    Args:
        data: List of record dicts
        field_paths: List of field path tuples

    Returns:
        Dict mapping path -> list of values (one per record)
    """
    columnar = {}
    for path in field_paths:
        values = [get_value_at_path(record, path) for record in data]
        columnar[path] = values
    return columnar


def analyze_structure(data: list[dict]) -> tuple[int, list[tuple], dict]:
    """
    Analyze data structure for serialization.

    Args:
        data: List of record dicts

    Returns:
        Tuple of (record_count, field_paths, columnar_values)

    Raises:
        ONTOError: If data is invalid
    """
    record_count, field_paths = validate_records(data)
    columnar = collect_columnar_values(data, field_paths)
    return record_count, field_paths, columnar


# --- Piece 2: Value serialization ---

PIPE = "|"
CARET = "^"
BACKTICK = "`"

# Allowed scalar types for serialization
ALLOWED_SCALAR_TYPES = (type(None), bool, int, float, str)


def needs_escaping(value: str) -> bool:
    """Check if a string value needs backtick escaping for special characters."""
    return PIPE in value or CARET in value


def looks_like_int(value: str) -> bool:
    """Check if string looks like an integer (would be parsed as int)."""
    if not value:
        return False
    # Match: optional minus, then digits
    if value[0] == '-':
        return value[1:].isdigit() if len(value) > 1 else False
    return value.isdigit()


def looks_like_float(value: str) -> bool:
    """Check if string looks like a float (would be parsed as float)."""
    if not value:
        return False
    # Match: optional minus, digits, dot, digits
    import re
    return bool(re.match(r'^-?\d+\.\d+$', value))


def looks_like_bool(value: str) -> bool:
    """Check if string looks like a boolean (would be parsed as bool)."""
    return value.lower() in ('true', 'false')


def needs_type_preservation(value: str) -> bool:
    """
    Check if a string value needs backticks to preserve its type.

    Without backticks, the parser would interpret these as non-string types.
    """
    return looks_like_int(value) or looks_like_float(value) or looks_like_bool(value)


def serialize_scalar(value) -> str:
    """
    Serialize a single scalar value to ONTO string representation.

    Args:
        value: Python value (str, int, float, bool, None)

    Returns:
        String representation for ONTO

    Raises:
        ONTOError: If value is unsupported type or contains backticks
    """
    # Check for unsupported types first
    if not isinstance(value, ALLOWED_SCALAR_TYPES):
        raise ONTOError(
            f"Unsupported type '{type(value).__name__}' in data. "
            f"ONTO V1 supports only: None, bool, int, float, str"
        )

    if value is None:
        return ""  # Empty = null

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (int, float)):
        return str(value)

    # String
    value_str = str(value)

    # Backticks are reserved and cannot appear in values in V1
    if BACKTICK in value_str:
        raise ONTOError("Backticks in values are not supported in ONTO V1")

    # Empty string needs backticks to distinguish from null
    if value_str == "":
        return f"{BACKTICK}{BACKTICK}"

    # Backtick-wrap if would be misinterpreted as another type
    if needs_type_preservation(value_str):
        return f"{BACKTICK}{value_str}{BACKTICK}"

    # Escape if contains special characters
    if needs_escaping(value_str):
        return f"{BACKTICK}{value_str}{BACKTICK}"

    return value_str


def serialize_value(value) -> str:
    """
    Serialize a value (scalar or array) to ONTO string representation.

    Args:
        value: Python value (scalar or list of scalars)

    Returns:
        String representation for ONTO

    Raises:
        ONTOError: If array contains None, nested arrays, or unsupported types
    """
    if isinstance(value, list):
        # Check for invalid array contents
        for i, elem in enumerate(value):
            if elem is None:
                raise ONTOError("None inside arrays is not supported in ONTO V1")
            if isinstance(elem, list):
                raise ONTOError(
                    "Nested arrays (list of lists) are not supported in ONTO V1. "
                    "Only one level of arrays is allowed."
                )
            if isinstance(elem, dict):
                raise ONTOError(
                    "Dicts inside arrays are not supported in ONTO V1"
                )

        # Array: join elements with ^
        elements = [serialize_scalar(elem) for elem in value]
        return CARET.join(elements)

    return serialize_scalar(value)


def serialize_field_values(values: list) -> str:
    """
    Serialize a list of values (one per record) to ONTO field line.

    Args:
        values: List of values across all records for one field

    Returns:
        Pipe-delimited string of serialized values
    """
    return PIPE.join(serialize_value(v) for v in values)


# --- Piece 3: Indentation handling ---

INDENT = "    "  # 4 spaces


def get_all_prefixes(field_paths: list[tuple]) -> set[tuple]:
    """
    Get all unique prefixes (nested object paths) from field paths.

    Args:
        field_paths: List of field path tuples

    Returns:
        Set of prefix tuples that represent nested objects
    """
    prefixes = set()
    for path in field_paths:
        # Add all prefixes except empty and the full path itself
        for i in range(1, len(path)):
            prefixes.add(path[:i])
    return prefixes


def build_onto_lines(
        entity_name: str,
        record_count: int,
        field_paths: list[tuple],
        columnar: dict
) -> list[str]:
    """
    Build the lines of ONTO output.

    INVARIANT: field_paths MUST be in DFS order (as returned by get_field_paths).
    This ensures nested object declarations are emitted before their children,
    and sibling fields under the same parent are grouped together.

    Args:
        entity_name: Name for entity declaration
        record_count: Number of records
        field_paths: List of field path tuples (in DFS order)
        columnar: Dict mapping path -> list of values

    Returns:
        List of ONTO lines
    """
    lines = []

    # Entity declaration
    lines.append(f"{entity_name}[{record_count}]:")

    # Get all nested object prefixes
    nested_prefixes = get_all_prefixes(field_paths)

    # Track which nested prefixes we've already emitted
    emitted_prefixes = set()

    for path in field_paths:
        # Emit any nested object declarations needed before this field
        for i in range(1, len(path)):
            prefix = path[:i]
            if prefix in nested_prefixes and prefix not in emitted_prefixes:
                # Emit nested object declaration
                indent_level = len(prefix)
                indent = INDENT * indent_level
                field_name = prefix[-1]
                lines.append(f"{indent}{field_name}:")
                emitted_prefixes.add(prefix)

        # Emit the field itself
        indent_level = len(path)
        indent = INDENT * indent_level
        field_name = path[-1]
        values_str = serialize_field_values(columnar[path])
        lines.append(f"{indent}{field_name}: {values_str}")

    return lines


def dumps(data: list[dict], entity_name: str = "Entity") -> str:
    """
    Serialize list of dicts to ONTO string.

    Args:
        data: List of record dicts
        entity_name: Name for entity declaration

    Returns:
        ONTO formatted string

    Raises:
        ONTOError: If data cannot be serialized
    """
    record_count, field_paths, columnar = analyze_structure(data)
    lines = build_onto_lines(entity_name, record_count, field_paths, columnar)
    return "\n".join(lines)