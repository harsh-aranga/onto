# tests/test_parser.py
"""Tests for ONTO parser."""

import pytest

from onto.parser import (
    LineType,
    ParsedLine,
    categorize_line,
    get_indent_level,
    parse_lines,
)
from onto.errors import ONTOParseError, ONTOValidationError


class TestIndentation:
    """Tests for indentation level calculation."""

    def test_no_indent(self):
        assert get_indent_level("User[3]:") == 0

    def test_one_level_indent(self):
        assert get_indent_level("    name: Alice") == 1

    def test_two_level_indent(self):
        assert get_indent_level("        city: LA") == 2

    def test_three_level_indent(self):
        assert get_indent_level("            short: CA") == 3

    def test_invalid_indent_returns_negative(self):
        # 2 spaces is not valid (must be multiple of 4)
        assert get_indent_level("  name: Alice") == -1

    def test_empty_line(self):
        assert get_indent_level("") == 0


class TestLineCategorization:
    """Tests for categorizing individual lines."""

    # Entity lines
    def test_entity_line_simple(self):
        result = categorize_line("User[3]:", 1)
        assert result.line_type == LineType.ENTITY
        assert result.entity_name == "User"
        assert result.record_count == 3
        assert result.indent_level == 0

    def test_entity_line_with_numbers_in_name(self):
        result = categorize_line("Device01[100]:", 1)
        assert result.line_type == LineType.ENTITY
        assert result.entity_name == "Device01"
        assert result.record_count == 100

    def test_entity_line_with_underscore(self):
        result = categorize_line("user_data[5]:", 1)
        assert result.line_type == LineType.ENTITY
        assert result.entity_name == "user_data"

    def test_entity_line_with_hyphen(self):
        result = categorize_line("device-info[10]:", 1)
        assert result.line_type == LineType.ENTITY
        assert result.entity_name == "device-info"

    def test_entity_line_with_dot(self):
        result = categorize_line("cpu.usage[50]:", 1)
        assert result.line_type == LineType.ENTITY
        assert result.entity_name == "cpu.usage"

    # Field lines with values
    def test_field_line_simple(self):
        result = categorize_line("    name: Alice|Bob|Charlie", 1)
        assert result.line_type == LineType.FIELD
        assert result.field_name == "name"
        assert result.raw_values == "Alice|Bob|Charlie"
        assert result.indent_level == 1

    def test_field_line_with_spaces_in_values(self):
        result = categorize_line("    city: Los Angeles|New York|Dallas", 1)
        assert result.line_type == LineType.FIELD
        assert result.raw_values == "Los Angeles|New York|Dallas"

    # Nested field lines (no values)
    def test_nested_field_line(self):
        result = categorize_line("    address:", 1)
        assert result.line_type == LineType.NESTED
        assert result.field_name == "address"
        assert result.raw_values is None
        assert result.indent_level == 1

    def test_nested_field_deeper(self):
        result = categorize_line("        state:", 2)
        assert result.line_type == LineType.NESTED
        assert result.field_name == "state"
        assert result.indent_level == 2

    # Comment lines
    def test_comment_line(self):
        result = categorize_line("# This is a comment", 1)
        assert result.line_type == LineType.COMMENT

    def test_comment_line_with_leading_space(self):
        result = categorize_line("    # Indented comment", 1)
        assert result.line_type == LineType.COMMENT

    # Blank lines
    def test_blank_line_empty(self):
        result = categorize_line("", 1)
        assert result.line_type == LineType.BLANK

    def test_blank_line_whitespace(self):
        result = categorize_line("   ", 1)
        assert result.line_type == LineType.BLANK

    # Error cases
    def test_invalid_indentation_raises_error(self):
        with pytest.raises(ONTOParseError) as exc_info:
            categorize_line("  name: Alice", 5)  # 2 spaces invalid
        assert "indentation" in str(exc_info.value).lower()
        assert exc_info.value.line == 5

    def test_entity_at_wrong_indent_raises_error(self):
        # Entity declaration indented is invalid syntax
        with pytest.raises(ONTOParseError) as exc_info:
            categorize_line("    User[3]:", 3)
        assert exc_info.value.line == 3


class TestParseLines:
    """Tests for parsing complete ONTO documents into lines."""

    def test_simple_document(self):
        onto = """User[3]:
    name: Alice|Bob|Charlie
    age: 30|25|35"""

        result = parse_lines(onto)

        assert len(result) == 3
        assert result[0].line_type == LineType.ENTITY
        assert result[0].entity_name == "User"
        assert result[1].line_type == LineType.FIELD
        assert result[1].field_name == "name"
        assert result[2].line_type == LineType.FIELD
        assert result[2].field_name == "age"

    def test_document_with_comments_and_blanks(self):
        onto = """# User data
User[2]:
    name: Alice|Bob

    # Ages follow
    age: 30|25"""

        result = parse_lines(onto)

        # Comments and blanks should be filtered out
        assert len(result) == 3
        assert result[0].line_type == LineType.ENTITY
        assert result[1].field_name == "name"
        assert result[2].field_name == "age"

    def test_nested_document(self):
        onto = """User[2]:
    name: Alice|Bob
    address:
        city: LA|NYC
        state:
            long: California|New York
            short: CA|NY"""

        result = parse_lines(onto)

        assert len(result) == 7
        assert result[0].line_type == LineType.ENTITY
        assert result[1].line_type == LineType.FIELD  # name
        assert result[2].line_type == LineType.NESTED  # address
        assert result[2].indent_level == 1
        assert result[3].line_type == LineType.FIELD  # city
        assert result[3].indent_level == 2
        assert result[4].line_type == LineType.NESTED  # state
        assert result[4].indent_level == 2
        assert result[5].indent_level == 3  # long
        assert result[6].indent_level == 3  # short

    def test_line_numbers_preserved(self):
        onto = """# Comment on line 1
User[2]:
    name: Alice|Bob"""

        result = parse_lines(onto)

        # Line 1 is comment (filtered), line 2 is entity, line 3 is field
        assert result[0].line_number == 2
        assert result[1].line_number == 3


class TestValueParsing:
    """Tests for parsing values (Piece 2)."""

    # Simple pipe splitting
    def test_simple_pipe_split(self):
        from onto.parser import parse_values
        result = parse_values("Alice|Bob|Charlie", 1)
        assert result == ["Alice", "Bob", "Charlie"]

    def test_single_value(self):
        from onto.parser import parse_values
        result = parse_values("Alice", 1)
        assert result == ["Alice"]

    def test_values_with_spaces(self):
        from onto.parser import parse_values
        result = parse_values("Los Angeles|New York|Dallas", 1)
        assert result == ["Los Angeles", "New York", "Dallas"]

    def test_values_with_commas(self):
        from onto.parser import parse_values
        # Commas don't need escaping per spec
        result = parse_values("no1, 1st street|no2, 2nd street", 1)
        assert result == ["no1, 1st street", "no2, 2nd street"]

    # Backtick escaping
    def test_backtick_escapes_pipe(self):
        from onto.parser import parse_values
        result = parse_values("`c|c++`|python|java", 1)
        assert result == ["c|c++", "python", "java"]

    def test_backtick_at_middle(self):
        from onto.parser import parse_values
        result = parse_values("python|`c|c++`|java", 1)
        assert result == ["python", "c|c++", "java"]

    def test_unclosed_backtick_raises_error(self):
        from onto.parser import parse_values
        with pytest.raises(ONTOParseError) as exc_info:
            parse_values("`unclosed|value", 5)
        assert "backtick" in str(exc_info.value).lower()
        assert exc_info.value.line == 5

    # Array parsing (caret)
    def test_simple_array(self):
        from onto.parser import parse_values
        result = parse_values("python^ai^ml|java^web|rust^systems", 1)
        assert result == [
            ["python", "ai", "ml"],
            ["java", "web"],
            ["rust", "systems"],
        ]

    def test_array_with_backtick_escape(self):
        from onto.parser import parse_values
        # Element contains pipe
        result = parse_values("`c|c++`^python|java^kotlin", 1)
        assert result == [
            ["c|c++", "python"],
            ["java", "kotlin"],
        ]

    def test_array_with_caret_in_backtick(self):
        from onto.parser import parse_values
        # Element contains caret
        result = parse_values("`a^b`^c|d^e", 1)
        assert result == [
            ["a^b", "c"],
            ["d", "e"],
        ]

    # Array-of-arrays promotion
    def test_array_promotion_mixed(self):
        from onto.parser import parse_values
        # "single" has no caret, but because others have ^, it becomes ["single"]
        result = parse_values("python^ai|single|rust^systems", 1)
        assert result == [
            ["python", "ai"],
            ["single"],
            ["rust", "systems"],
        ]

    # Null handling (empty between pipes)
    def test_empty_is_null_no_arrays(self):
        from onto.parser import parse_values
        result = parse_values("LA||Dallas", 1)
        assert result == ["LA", "", "Dallas"]  # Empty string = null (type inference handles)

    def test_null_in_array_context(self):
        from onto.parser import parse_values
        # Empty at outer level = null, not empty array
        result = parse_values("python^ai||rust^systems", 1)
        assert result == [
            ["python", "ai"],
            "",  # null at outer level
            ["rust", "systems"],
        ]

    # Error: empty array element
    def test_empty_array_element_raises_error(self):
        from onto.parser import parse_values
        # ^python means first element is empty - invalid
        with pytest.raises(ONTOParseError) as exc_info:
            parse_values("^python|java", 3)
        assert "empty array element" in str(exc_info.value).lower()
        assert exc_info.value.line == 3

    def test_trailing_caret_raises_error(self):
        from onto.parser import parse_values
        # python^ means second element is empty - invalid
        with pytest.raises(ONTOParseError) as exc_info:
            parse_values("python^|java", 4)
        assert "empty array element" in str(exc_info.value).lower()

    def test_double_caret_raises_error(self):
        from onto.parser import parse_values
        # python^^ai means middle element is empty - invalid
        with pytest.raises(ONTOParseError) as exc_info:
            parse_values("python^^ai|java", 2)
        assert "empty array element" in str(exc_info.value).lower()


class TestTypeInference:
    """Tests for type inference (Piece 3)."""

    # Single value type inference
    def test_infer_integer(self):
        from onto.parser import infer_single_type
        assert infer_single_type("42") == (int, 42)
        assert infer_single_type("-17") == (int, -17)
        assert infer_single_type("0") == (int, 0)

    def test_infer_float(self):
        from onto.parser import infer_single_type
        assert infer_single_type("3.14") == (float, 3.14)
        assert infer_single_type("-0.5") == (float, -0.5)
        assert infer_single_type("100.00") == (float, 100.0)

    def test_infer_boolean(self):
        from onto.parser import infer_single_type
        assert infer_single_type("true") == (bool, True)
        assert infer_single_type("false") == (bool, False)
        assert infer_single_type("TRUE") == (bool, True)
        assert infer_single_type("False") == (bool, False)

    def test_infer_null(self):
        from onto.parser import infer_single_type
        assert infer_single_type("") == (type(None), None)

    def test_infer_string(self):
        from onto.parser import infer_single_type
        assert infer_single_type("hello") == (str, "hello")
        assert infer_single_type("hello world") == (str, "hello world")

    def test_backtick_forces_string(self):
        from onto.parser import infer_single_type
        # Backtick-wrapped integers become strings
        assert infer_single_type("`123`") == (str, "123")
        assert infer_single_type("`true`") == (str, "true")

    # Full type inference with harmonization
    def test_infer_types_integers(self):
        from onto.parser import infer_types, parse_values_raw
        raw = parse_values_raw("30|25|40", 1)
        result = infer_types(raw)
        assert result == [30, 25, 40]

    def test_infer_types_floats(self):
        from onto.parser import infer_types, parse_values_raw
        raw = parse_values_raw("19.99|24.50|9.99", 1)
        result = infer_types(raw)
        assert result == [19.99, 24.50, 9.99]

    def test_infer_types_booleans(self):
        from onto.parser import infer_types, parse_values_raw
        raw = parse_values_raw("true|false|TRUE", 1)
        result = infer_types(raw)
        assert result == [True, False, True]

    def test_infer_types_mixed_becomes_strings(self):
        from onto.parser import infer_types, parse_values_raw
        # Mixed int and string -> all strings
        raw = parse_values_raw("100|N/A|85", 1)
        result = infer_types(raw)
        assert result == ["100", "N/A", "85"]

    def test_infer_types_mixed_int_float_upcasts(self):
        from onto.parser import infer_types, parse_values_raw
        # Mixed int and float -> upcast to float (not strings)
        raw = parse_values_raw("-10|-3.14|5", 1)
        result = infer_types(raw)
        assert result == [-10.0, -3.14, 5.0]
        assert all(isinstance(v, float) for v in result)

    def test_infer_types_nested_array_int_float_upcasts(self):
        from onto.parser import infer_types, parse_values_raw
        # Mixed int and float in nested arrays -> upcast to float (not strings)
        raw = parse_values_raw("1^2.5|3^4", 1)
        result = infer_types(raw)
        assert result == [[1.0, 2.5], [3.0, 4.0]]
        assert all(isinstance(v, float) for v in result[0])
        assert all(isinstance(v, float) for v in result[1])

    def test_infer_types_with_null(self):
        from onto.parser import infer_types, parse_values_raw
        raw = parse_values_raw("LA||Dallas", 1)
        result = infer_types(raw)
        assert result == ["LA", None, "Dallas"]

    def test_infer_types_integers_with_null(self):
        from onto.parser import infer_types, parse_values_raw
        # Null doesn't break type harmony
        raw = parse_values_raw("10||30", 1)
        result = infer_types(raw)
        assert result == [10, None, 30]

    def test_infer_types_backtick_forces_string_field_wide(self):
        from onto.parser import infer_types, parse_values_raw
        # One backtick-wrapped value forces string, others infer normally
        # Then field harmonization kicks in (mixed types -> all strings)
        # But non-backticked values lose their original form when stringified
        raw = parse_values_raw("`001`|002|003", 1)
        result = infer_types(raw)
        # 001 is string (backtick), 002/003 are int, mixed -> all strings
        # But 002 becomes "2" not "002" because it was inferred as int first
        assert result == ["001", "2", "3"]

    # Array type inference
    def test_infer_types_array_integers(self):
        from onto.parser import infer_types, parse_values_raw
        raw = parse_values_raw("1^2^3|4^5|6^7^8^9", 1)
        result = infer_types(raw)
        assert result == [[1, 2, 3], [4, 5], [6, 7, 8, 9]]

    def test_infer_types_array_mixed_becomes_strings(self):
        from onto.parser import infer_types, parse_values_raw
        # scores: 1^2|3^x -> all strings across the whole field
        raw = parse_values_raw("1^2|3^x", 1)
        result = infer_types(raw)
        assert result == [["1", "2"], ["3", "x"]]

    def test_infer_types_array_with_null_outer(self):
        from onto.parser import infer_types, parse_values_raw
        # Null at outer level in array context
        raw = parse_values_raw("python^ai||rust^systems", 1)
        result = infer_types(raw)
        assert result == [["python", "ai"], None, ["rust", "systems"]]

    def test_infer_types_array_promotion_with_inference(self):
        from onto.parser import infer_types, parse_values_raw
        # Mixed: some have ^, some don't -> promotion + type inference
        raw = parse_values_raw("1^2|3|4^5", 1)
        result = infer_types(raw)
        assert result == [[1, 2], [3], [4, 5]]

    def test_infer_types_empty_string_vs_null(self):
        from onto.parser import infer_types, parse_values_raw
        # Backtick empty = empty string, not null
        raw = parse_values_raw("LA|``|Dallas", 1)
        result = infer_types(raw)
        assert result == ["LA", "", "Dallas"]


class TestStructureBuilding:
    """Tests for structure building (Piece 4)."""

    # Basic structure
    def test_simple_flat_structure(self):
        from onto.parser import loads
        onto = """User[3]:
    name: Alice|Bob|Charlie
    age: 30|25|35"""
        result = loads(onto)
        assert result == [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35},
        ]

    def test_single_record(self):
        from onto.parser import loads
        onto = """User[1]:
    name: Alice
    active: true"""
        result = loads(onto)
        assert result == [{"name": "Alice", "active": True}]

    # Nested structure
    def test_nested_one_level(self):
        from onto.parser import loads
        onto = """User[2]:
    name: Alice|Bob
    address:
        city: LA|NYC
        zip: 90001|10001"""
        result = loads(onto)
        assert result == [
            {"name": "Alice", "address": {"city": "LA", "zip": 90001}},
            {"name": "Bob", "address": {"city": "NYC", "zip": 10001}},
        ]

    def test_nested_two_levels(self):
        from onto.parser import loads
        onto = """User[2]:
    name: Alice|Bob
    address:
        city: LA|NYC
        state:
            long: California|New York
            short: CA|NY"""
        result = loads(onto)
        assert result == [
            {"name": "Alice", "address": {"city": "LA", "state": {"long": "California", "short": "CA"}}},
            {"name": "Bob", "address": {"city": "NYC", "state": {"long": "New York", "short": "NY"}}},
        ]

    def test_multiple_nested_siblings(self):
        from onto.parser import loads
        onto = """User[2]:
    name: Alice|Bob
    home:
        city: LA|NYC
    work:
        city: SF|Boston"""
        result = loads(onto)
        assert result == [
            {"name": "Alice", "home": {"city": "LA"}, "work": {"city": "SF"}},
            {"name": "Bob", "home": {"city": "NYC"}, "work": {"city": "Boston"}},
        ]

    # With arrays
    def test_with_arrays(self):
        from onto.parser import loads
        onto = """User[2]:
    name: Alice|Bob
    tags: python^ai|java^web"""
        result = loads(onto)
        assert result == [
            {"name": "Alice", "tags": ["python", "ai"]},
            {"name": "Bob", "tags": ["java", "web"]},
        ]

    # With nulls
    def test_with_nulls(self):
        from onto.parser import loads
        onto = """User[3]:
    name: Alice|Bob|Charlie
    city: LA||Dallas"""
        result = loads(onto)
        assert result == [
            {"name": "Alice", "city": "LA"},
            {"name": "Bob", "city": None},
            {"name": "Charlie", "city": "Dallas"},
        ]

    # With comments
    def test_with_comments(self):
        from onto.parser import loads
        onto = """# User data
User[2]:
    # Names
    name: Alice|Bob
    # Ages in years
    age: 30|25"""
        result = loads(onto)
        assert result == [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]

    # Type inference integration
    def test_type_inference_integration(self):
        from onto.parser import loads
        onto = """Data[3]:
    count: 10|20|30
    ratio: 0.5|1.5|2.5
    active: true|false|true
    label: a|b|c"""
        result = loads(onto)
        assert result == [
            {"count": 10, "ratio": 0.5, "active": True, "label": "a"},
            {"count": 20, "ratio": 1.5, "active": False, "label": "b"},
            {"count": 30, "ratio": 2.5, "active": True, "label": "c"},
        ]

    # Error cases
    def test_error_mismatched_record_count(self):
        from onto.parser import loads
        onto = """User[3]:
    name: Alice|Bob|Charlie
    age: 30|25"""
        with pytest.raises(ONTOValidationError) as exc_info:
            loads(onto)
        assert "2 values" in str(exc_info.value)
        assert "expected 3" in str(exc_info.value)

    def test_error_nested_mismatched_count(self):
        from onto.parser import loads
        onto = """User[3]:
    name: Alice|Bob|Charlie
    address:
        city: LA|NYC"""
        with pytest.raises(ONTOValidationError) as exc_info:
            loads(onto)
        assert "address.city" in str(exc_info.value)

    def test_error_empty_document(self):
        from onto.parser import loads
        with pytest.raises(ONTOParseError):
            loads("")

    def test_error_no_entity(self):
        from onto.parser import loads
        onto = """    name: Alice|Bob"""
        with pytest.raises(ONTOParseError) as exc_info:
            loads(onto)
        assert "entity" in str(exc_info.value).lower()

    def test_error_indent_jump(self):
        from onto.parser import loads
        # Level 2 directly under entity (level 0) - skips level 1
        onto = """User[2]:
        city: LA|NYC"""
        with pytest.raises(ONTOParseError) as exc_info:
            loads(onto)
        assert "indentation" in str(exc_info.value).lower()

    def test_error_multiple_entities(self):
        from onto.parser import loads
        onto = """User[2]:
    name: Alice|Bob
Order[3]:
    id: 1|2|3"""
        with pytest.raises(ONTOParseError) as exc_info:
            loads(onto)
        assert "multiple" in str(exc_info.value).lower()

    def test_error_empty_nested_declaration(self):
        from onto.parser import loads
        onto = """User[1]:
    address:"""
        with pytest.raises(ONTOParseError) as exc_info:
            loads(onto)
        assert "empty" in str(exc_info.value).lower()

    def test_error_empty_nested_followed_by_sibling(self):
        from onto.parser import loads
        # address: has no children, then name appears at same level
        onto = """User[1]:
    address:
    name: Alice"""
        with pytest.raises(ONTOParseError) as exc_info:
            loads(onto)
        assert "empty" in str(exc_info.value).lower()