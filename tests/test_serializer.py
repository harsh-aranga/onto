# tests/test_serializer.py
"""Tests for ONTO serializer."""

import pytest

from onto.errors import ONTOError


class TestSerializerStructureAnalysis:
    """Tests for serializer structure analysis (Phase 2, Piece 1)."""

    # Field path extraction
    def test_get_field_paths_flat(self):
        from onto.serializer import get_field_paths
        record = {"name": "Alice", "age": 30}
        paths = get_field_paths(record)
        assert set(paths) == {("name",), ("age",)}

    def test_get_field_paths_nested(self):
        from onto.serializer import get_field_paths
        record = {"name": "Alice", "address": {"city": "LA", "zip": 90001}}
        paths = get_field_paths(record)
        assert set(paths) == {("name",), ("address", "city"), ("address", "zip")}

    def test_get_field_paths_deep_nested(self):
        from onto.serializer import get_field_paths
        record = {
            "name": "Alice",
            "address": {
                "city": "LA",
                "state": {"long": "California", "short": "CA"}
            }
        }
        paths = get_field_paths(record)
        assert set(paths) == {
            ("name",),
            ("address", "city"),
            ("address", "state", "long"),
            ("address", "state", "short"),
        }

    # Validation
    def test_validate_records_success(self):
        from onto.serializer import validate_records
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        count, paths = validate_records(data)
        assert count == 2
        assert set(paths) == {("name",), ("age",)}

    def test_validate_records_empty_raises(self):
        from onto.serializer import validate_records
        with pytest.raises(ONTOError) as exc_info:
            validate_records([])
        assert "empty" in str(exc_info.value).lower()

    def test_validate_records_dict_not_list_raises(self):
        from onto.serializer import validate_records
        with pytest.raises(ONTOError) as exc_info:
            validate_records({})  # Dict, not list
        assert "list" in str(exc_info.value).lower()

    def test_validate_records_inconsistent_raises(self):
        from onto.serializer import validate_records
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob"},  # Missing age
        ]
        with pytest.raises(ONTOError) as exc_info:
            validate_records(data)
        assert "inconsistent" in str(exc_info.value).lower()

    def test_validate_records_extra_field_raises(self):
        from onto.serializer import validate_records
        data = [
            {"name": "Alice"},
            {"name": "Bob", "extra": "field"},
        ]
        with pytest.raises(ONTOError) as exc_info:
            validate_records(data)
        assert "extra" in str(exc_info.value).lower()

    # Value collection
    def test_collect_columnar_values(self):
        from onto.serializer import collect_columnar_values
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        paths = [("name",), ("age",)]
        columnar = collect_columnar_values(data, paths)
        assert columnar[("name",)] == ["Alice", "Bob"]
        assert columnar[("age",)] == [30, 25]

    def test_collect_columnar_values_nested(self):
        from onto.serializer import collect_columnar_values
        data = [
            {"name": "Alice", "address": {"city": "LA"}},
            {"name": "Bob", "address": {"city": "NYC"}},
        ]
        paths = [("name",), ("address", "city")]
        columnar = collect_columnar_values(data, paths)
        assert columnar[("name",)] == ["Alice", "Bob"]
        assert columnar[("address", "city")] == ["LA", "NYC"]

    # Full analysis
    def test_analyze_structure(self):
        from onto.serializer import analyze_structure
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35},
        ]
        count, paths, columnar = analyze_structure(data)
        assert count == 3
        assert set(paths) == {("name",), ("age",)}
        assert columnar[("name",)] == ["Alice", "Bob", "Charlie"]
        assert columnar[("age",)] == [30, 25, 35]


class TestValueSerialization:
    """Tests for value serialization (Phase 2, Piece 2)."""

    # Scalar serialization
    def test_serialize_scalar_string(self):
        from onto.serializer import serialize_scalar
        assert serialize_scalar("hello") == "hello"
        assert serialize_scalar("hello world") == "hello world"

    def test_serialize_scalar_integer(self):
        from onto.serializer import serialize_scalar
        assert serialize_scalar(42) == "42"
        assert serialize_scalar(-17) == "-17"
        assert serialize_scalar(0) == "0"

    def test_serialize_scalar_float(self):
        from onto.serializer import serialize_scalar
        assert serialize_scalar(3.14) == "3.14"
        assert serialize_scalar(-0.5) == "-0.5"

    def test_serialize_scalar_boolean(self):
        from onto.serializer import serialize_scalar
        assert serialize_scalar(True) == "true"
        assert serialize_scalar(False) == "false"

    def test_serialize_scalar_null(self):
        from onto.serializer import serialize_scalar
        assert serialize_scalar(None) == ""

    def test_serialize_scalar_empty_string(self):
        from onto.serializer import serialize_scalar
        # Empty string needs backticks to distinguish from null
        assert serialize_scalar("") == "``"

    def test_serialize_scalar_with_pipe(self):
        from onto.serializer import serialize_scalar
        assert serialize_scalar("c|c++") == "`c|c++`"

    def test_serialize_scalar_with_caret(self):
        from onto.serializer import serialize_scalar
        assert serialize_scalar("a^b") == "`a^b`"

    def test_serialize_scalar_with_both(self):
        from onto.serializer import serialize_scalar
        assert serialize_scalar("a|b^c") == "`a|b^c`"

    # Array serialization
    def test_serialize_value_array(self):
        from onto.serializer import serialize_value
        assert serialize_value(["python", "ai", "ml"]) == "python^ai^ml"

    def test_serialize_value_array_with_escape(self):
        from onto.serializer import serialize_value
        assert serialize_value(["c|c++", "python"]) == "`c|c++`^python"

    def test_serialize_value_array_single_element(self):
        from onto.serializer import serialize_value
        assert serialize_value(["single"]) == "single"

    def test_serialize_value_scalar(self):
        from onto.serializer import serialize_value
        assert serialize_value("hello") == "hello"
        assert serialize_value(42) == "42"

    # Field values serialization
    def test_serialize_field_values_strings(self):
        from onto.serializer import serialize_field_values
        assert serialize_field_values(["Alice", "Bob", "Charlie"]) == "Alice|Bob|Charlie"

    def test_serialize_field_values_integers(self):
        from onto.serializer import serialize_field_values
        assert serialize_field_values([30, 25, 35]) == "30|25|35"

    def test_serialize_field_values_with_null(self):
        from onto.serializer import serialize_field_values
        assert serialize_field_values(["LA", None, "Dallas"]) == "LA||Dallas"

    def test_serialize_field_values_with_empty_string(self):
        from onto.serializer import serialize_field_values
        assert serialize_field_values(["LA", "", "Dallas"]) == "LA|``|Dallas"

    def test_serialize_field_values_arrays(self):
        from onto.serializer import serialize_field_values
        values = [["python", "ai"], ["java", "web"], ["rust", "systems"]]
        assert serialize_field_values(values) == "python^ai|java^web|rust^systems"

    def test_serialize_field_values_booleans(self):
        from onto.serializer import serialize_field_values
        assert serialize_field_values([True, False, True]) == "true|false|true"

    def test_serialize_field_values_mixed_with_escape(self):
        from onto.serializer import serialize_field_values
        values = ["c|c++", "python", "java"]
        assert serialize_field_values(values) == "`c|c++`|python|java"

    # Error cases
    def test_serialize_scalar_backtick_raises(self):
        from onto.serializer import serialize_scalar
        with pytest.raises(ONTOError) as exc_info:
            serialize_scalar("hello ` world")
        assert "backtick" in str(exc_info.value).lower()

    def test_serialize_value_array_with_none_raises(self):
        from onto.serializer import serialize_value
        with pytest.raises(ONTOError) as exc_info:
            serialize_value([None, "python", "ai"])
        assert "none" in str(exc_info.value).lower()

    def test_serialize_value_array_with_none_middle_raises(self):
        from onto.serializer import serialize_value
        with pytest.raises(ONTOError) as exc_info:
            serialize_value(["python", None, "ai"])
        assert "none" in str(exc_info.value).lower()

    # Type preservation tests
    def test_serialize_scalar_string_looks_like_int(self):
        from onto.serializer import serialize_scalar
        # String "123" must be backtick-wrapped to preserve type
        assert serialize_scalar("123") == "`123`"
        assert serialize_scalar("001") == "`001`"
        assert serialize_scalar("-5") == "`-5`"

    def test_serialize_scalar_string_looks_like_float(self):
        from onto.serializer import serialize_scalar
        assert serialize_scalar("19.99") == "`19.99`"
        assert serialize_scalar("-3.14") == "`-3.14`"

    def test_serialize_scalar_string_looks_like_bool(self):
        from onto.serializer import serialize_scalar
        assert serialize_scalar("true") == "`true`"
        assert serialize_scalar("false") == "`false`"
        assert serialize_scalar("TRUE") == "`TRUE`"
        assert serialize_scalar("False") == "`False`"

    def test_serialize_scalar_normal_string_no_backticks(self):
        from onto.serializer import serialize_scalar
        # Normal strings should NOT get backticks
        assert serialize_scalar("hello") == "hello"
        assert serialize_scalar("Alice") == "Alice"
        assert serialize_scalar("not-a-number") == "not-a-number"

    # Nested array rejection tests
    def test_serialize_value_nested_array_raises(self):
        from onto.serializer import serialize_value
        with pytest.raises(ONTOError) as exc_info:
            serialize_value([[1, 2], [3, 4]])
        assert "nested" in str(exc_info.value).lower()

    def test_serialize_value_dict_in_array_raises(self):
        from onto.serializer import serialize_value
        with pytest.raises(ONTOError) as exc_info:
            serialize_value([{"a": 1}, {"b": 2}])
        assert "dict" in str(exc_info.value).lower()

    # Unsupported type rejection tests
    def test_serialize_scalar_unsupported_type_raises(self):
        from onto.serializer import serialize_scalar
        from datetime import datetime
        with pytest.raises(ONTOError) as exc_info:
            serialize_scalar(datetime.now())
        assert "unsupported" in str(exc_info.value).lower()

    def test_serialize_scalar_tuple_raises(self):
        from onto.serializer import serialize_scalar
        with pytest.raises(ONTOError) as exc_info:
            serialize_scalar((1, 2, 3))
        assert "unsupported" in str(exc_info.value).lower()


class TestIndentationAndOutput:
    """Tests for indentation handling and ONTO output (Phase 2, Piece 3)."""

    def test_dumps_simple_flat(self):
        from onto.serializer import dumps
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        result = dumps(data, "User")
        expected = """User[2]:
    name: Alice|Bob
    age: 30|25"""
        assert result == expected

    def test_dumps_single_record(self):
        from onto.serializer import dumps
        data = [{"name": "Alice", "active": True}]
        result = dumps(data, "User")
        expected = """User[1]:
    name: Alice
    active: true"""
        assert result == expected

    def test_dumps_nested_one_level(self):
        from onto.serializer import dumps
        data = [
            {"name": "Alice", "address": {"city": "LA", "zip": 90001}},
            {"name": "Bob", "address": {"city": "NYC", "zip": 10001}},
        ]
        result = dumps(data, "User")
        expected = """User[2]:
    name: Alice|Bob
    address:
        city: LA|NYC
        zip: 90001|10001"""
        assert result == expected

    def test_dumps_nested_two_levels(self):
        from onto.serializer import dumps
        data = [
            {"name": "Alice", "address": {"city": "LA", "state": {"long": "California", "short": "CA"}}},
            {"name": "Bob", "address": {"city": "NYC", "state": {"long": "New York", "short": "NY"}}},
        ]
        result = dumps(data, "User")
        # Check key parts
        assert "User[2]:" in result
        assert "    name: Alice|Bob" in result
        assert "    address:" in result
        assert "        city: LA|NYC" in result
        assert "        state:" in result
        assert "            long: California|New York" in result
        assert "            short: CA|NY" in result

    def test_dumps_with_arrays(self):
        from onto.serializer import dumps
        data = [
            {"name": "Alice", "tags": ["python", "ai"]},
            {"name": "Bob", "tags": ["java", "web"]},
        ]
        result = dumps(data, "User")
        expected = """User[2]:
    name: Alice|Bob
    tags: python^ai|java^web"""
        assert result == expected

    def test_dumps_with_null(self):
        from onto.serializer import dumps
        data = [
            {"name": "Alice", "city": "LA"},
            {"name": "Bob", "city": None},
            {"name": "Charlie", "city": "Dallas"},
        ]
        result = dumps(data, "User")
        expected = """User[3]:
    name: Alice|Bob|Charlie
    city: LA||Dallas"""
        assert result == expected

    def test_dumps_with_empty_string(self):
        from onto.serializer import dumps
        data = [
            {"name": "Alice", "city": "LA"},
            {"name": "Bob", "city": ""},
            {"name": "Charlie", "city": "Dallas"},
        ]
        result = dumps(data, "User")
        expected = """User[3]:
    name: Alice|Bob|Charlie
    city: LA|``|Dallas"""
        assert result == expected

    def test_dumps_with_escaping(self):
        from onto.serializer import dumps
        data = [
            {"lang": "c|c++"},
            {"lang": "python"},
        ]
        result = dumps(data, "Lang")
        expected = """Lang[2]:
    lang: `c|c++`|python"""
        assert result == expected

    def test_dumps_default_entity_name(self):
        from onto.serializer import dumps
        data = [{"a": 1}]
        result = dumps(data)
        assert result.startswith("Entity[1]:")

    def test_dumps_preserves_field_order(self):
        from onto.serializer import dumps
        data = [{"z": 1, "a": 2, "m": 3}]
        result = dumps(data, "Test")
        lines = result.split("\n")
        # Fields should appear in insertion order (z, a, m)
        assert "z:" in lines[1]
        assert "a:" in lines[2]
        assert "m:" in lines[3]