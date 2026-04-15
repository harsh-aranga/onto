# tests/test_integration.py
"""Integration tests for ONTO public API."""

import pytest


class TestPublicAPI:
    """Integration tests using public API (Piece 5)."""

    def test_import_loads(self):
        import onto
        assert hasattr(onto, "loads")
        assert callable(onto.loads)

    def test_import_dumps(self):
        import onto
        assert hasattr(onto, "dumps")
        assert callable(onto.dumps)
        # dumps is now implemented
        result = onto.dumps([{"a": 1}])
        assert "Entity[1]:" in result

    def test_import_exceptions(self):
        import onto
        assert hasattr(onto, "ONTOError")
        assert hasattr(onto, "ONTOParseError")
        assert hasattr(onto, "ONTOValidationError")

    def test_loads_via_public_api(self):
        import onto
        result = onto.loads("""User[2]:
    name: Alice|Bob
    age: 30|25""")
        assert result == [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]

    def test_full_spec_example(self):
        """Test the example from the spec."""
        import onto
        onto_str = """User[3]:
    name: Alice|Bob|Charlie
    age: 30|25|35
    city: LA|NYC|Dallas"""
        result = onto.loads(onto_str)
        assert len(result) == 3
        assert result[0] == {"name": "Alice", "age": 30, "city": "LA"}
        assert result[1] == {"name": "Bob", "age": 25, "city": "NYC"}
        assert result[2] == {"name": "Charlie", "age": 35, "city": "Dallas"}

    def test_deep_nesting_example(self):
        """Test the deep nesting example from spec."""
        import onto
        onto_str = """User[3]:
    name: Alice|Bob|Charlie
    age: 30|25|35
    address:
        street: 1st Ave|2nd Ave|3rd Ave
        city: LA|NYC|Dallas
        state:
            longform: California|New York|Texas
            shortform: CA|NY|TX"""
        result = onto.loads(onto_str)
        assert len(result) == 3
        assert result[0]["address"]["state"]["shortform"] == "CA"
        assert result[1]["address"]["city"] == "NYC"
        assert result[2]["name"] == "Charlie"

    def test_arrays_example(self):
        """Test array syntax from spec."""
        import onto
        onto_str = """User[3]:
    name: Alice|Bob|Charlie
    tags: python^ai^ml|javascript^web|rust^systems"""
        result = onto.loads(onto_str)
        assert result[0]["tags"] == ["python", "ai", "ml"]
        assert result[1]["tags"] == ["javascript", "web"]
        assert result[2]["tags"] == ["rust", "systems"]

    def test_null_handling(self):
        """Test null vs empty string."""
        import onto
        onto_str = """Data[3]:
    a: value||another
    b: value|``|another"""
        result = onto.loads(onto_str)
        assert result[0]["a"] == "value"
        assert result[1]["a"] is None
        assert result[1]["b"] == ""
        assert result[2]["a"] == "another"

    def test_type_inference_comprehensive(self):
        """Test all type inference cases."""
        import onto
        onto_str = """Data[4]:
    int_val: 1|2|3|4
    float_val: 1.5|2.5|3.5|4.5
    bool_val: true|false|TRUE|False
    str_val: a|b|c|d
    mixed_val: 1|two|3|four"""
        result = onto.loads(onto_str)
        # Integers
        assert all(isinstance(r["int_val"], int) for r in result)
        # Floats
        assert all(isinstance(r["float_val"], float) for r in result)
        # Booleans
        assert result[0]["bool_val"] is True
        assert result[1]["bool_val"] is False
        # Strings
        assert all(isinstance(r["str_val"], str) for r in result)
        # Mixed -> all strings
        assert all(isinstance(r["mixed_val"], str) for r in result)
        assert result[0]["mixed_val"] == "1"

    def test_backtick_escaping(self):
        """Test backtick escaping for special characters."""
        import onto
        onto_str = """Lang[2]:
    name: `c|c++`|python
    tags: `a^b`^c|d^e"""
        result = onto.loads(onto_str)
        assert result[0]["name"] == "c|c++"
        assert result[0]["tags"] == ["a^b", "c"]
        assert result[1]["tags"] == ["d", "e"]

    def test_error_raises_parse_error(self):
        """Test that parse errors are properly raised."""
        import onto
        with pytest.raises(onto.ONTOParseError):
            onto.loads("invalid onto")

    def test_error_raises_validation_error(self):
        """Test that validation errors are properly raised."""
        import onto
        with pytest.raises(onto.ONTOValidationError):
            onto.loads("""User[3]:
    name: Alice|Bob""")  # Only 2 values for 3 records


class TestRoundTrip:
    """Round-trip tests: JSON -> ONTO -> JSON."""

    def test_roundtrip_simple_flat(self):
        import onto
        original = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        onto_str = onto.dumps(original, "User")
        result = onto.loads(onto_str)
        assert result == original

    def test_roundtrip_nested(self):
        import onto
        original = [
            {"name": "Alice", "address": {"city": "LA", "zip": 90001}},
            {"name": "Bob", "address": {"city": "NYC", "zip": 10001}},
        ]
        onto_str = onto.dumps(original, "User")
        result = onto.loads(onto_str)
        assert result == original

    def test_roundtrip_deep_nested(self):
        import onto
        original = [
            {"name": "Alice", "address": {"city": "LA", "state": {"long": "California", "short": "CA"}}},
            {"name": "Bob", "address": {"city": "NYC", "state": {"long": "New York", "short": "NY"}}},
        ]
        onto_str = onto.dumps(original, "User")
        result = onto.loads(onto_str)
        assert result == original

    def test_roundtrip_with_arrays(self):
        import onto
        original = [
            {"name": "Alice", "tags": ["python", "ai", "ml"]},
            {"name": "Bob", "tags": ["java", "web"]},
        ]
        onto_str = onto.dumps(original, "User")
        result = onto.loads(onto_str)
        assert result == original

    def test_roundtrip_with_null(self):
        import onto
        original = [
            {"name": "Alice", "city": "LA"},
            {"name": "Bob", "city": None},
            {"name": "Charlie", "city": "Dallas"},
        ]
        onto_str = onto.dumps(original, "User")
        result = onto.loads(onto_str)
        assert result == original

    def test_roundtrip_with_empty_string(self):
        import onto
        original = [
            {"name": "Alice", "note": "hello"},
            {"name": "Bob", "note": ""},
            {"name": "Charlie", "note": "world"},
        ]
        onto_str = onto.dumps(original, "User")
        result = onto.loads(onto_str)
        assert result == original

    def test_roundtrip_with_booleans(self):
        import onto
        original = [
            {"name": "Alice", "active": True},
            {"name": "Bob", "active": False},
        ]
        onto_str = onto.dumps(original, "User")
        result = onto.loads(onto_str)
        assert result == original

    def test_roundtrip_with_floats(self):
        import onto
        original = [
            {"item": "A", "price": 19.99},
            {"item": "B", "price": 24.50},
        ]
        onto_str = onto.dumps(original, "Product")
        result = onto.loads(onto_str)
        assert result == original

    def test_roundtrip_with_escaping(self):
        import onto
        original = [
            {"lang": "c|c++", "desc": "systems"},
            {"lang": "python", "desc": "scripting"},
        ]
        onto_str = onto.dumps(original, "Lang")
        result = onto.loads(onto_str)
        assert result == original

    def test_roundtrip_complex(self):
        """Test a complex structure with multiple features."""
        import onto
        original = [
            {
                "id": 1,
                "name": "Alice",
                "active": True,
                "score": 95.5,
                "tags": ["python", "ai"],
                "address": {
                    "city": "LA",
                    "state": {"long": "California", "short": "CA"}
                }
            },
            {
                "id": 2,
                "name": "Bob",
                "active": False,
                "score": 87.0,
                "tags": ["java", "web"],
                "address": {
                    "city": "NYC",
                    "state": {"long": "New York", "short": "NY"}
                }
            },
        ]
        onto_str = onto.dumps(original, "User")
        result = onto.loads(onto_str)
        assert result == original

    def test_roundtrip_string_type_preservation(self):
        """Test that strings that look like other types are preserved."""
        import onto
        original = [
            {"id": "001", "flag": "true", "price": "19.99"},
            {"id": "002", "flag": "false", "price": "24.50"},
        ]
        onto_str = onto.dumps(original, "Data")
        result = onto.loads(onto_str)
        # Must remain strings, not converted to int/bool/float
        assert result == original
        assert isinstance(result[0]["id"], str)
        assert isinstance(result[0]["flag"], str)
        assert isinstance(result[0]["price"], str)