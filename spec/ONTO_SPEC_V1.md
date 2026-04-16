# ONTO: Object Notation for Token Optimization

**Version:** 1.0 (Draft)  
**Author:** Harshavardhanan Aranga  
**Status:** Specification for review

---

## Overview

ONTO is a columnar, token-efficient data notation designed for LLM workflows. It can reduce token overhead by 60-70% compared to JSON in structured datasets with repeated keys (based on representative benchmarks), while preserving human readability and hierarchical structure.

### Design Philosophy

- **Schema-once, data-many:** Declare field names once, list values with pipe delimiters
- **YAML-like indentation:** Visual hierarchy through indentation, not braces
- **Columnar compression:** Values stored per-field, not per-record
- **LLM-optimized:** Indentation-based structure prevents models from getting lost in deeply nested braces

### Primary Use Case

ONTO optimizes token usage for scenarios where LLMs analyze large-scale structured input data:

- Anomaly detection on logs
- Root cause analysis across metrics
- Summarizing telemetry patterns
- Policy/configuration suggestions
- Decision support systems

**Important:** ONTO is an **input compression** format. LLMs consume large structured data (ONTO saves tokens here) and produce small reasoning outputs (natural language, not ONTO).

### When to Use ONTO

✅ LLM prompts with structured data (100+ records)  
✅ High token cost scenarios (millions of tokens/day)  
✅ Operational data fed to LLMs for analysis  
✅ Context-window constrained tasks

### When NOT to Use ONTO

❌ APIs (use JSON — it's the standard)  
❌ Config files (use YAML — it's readable)  
❌ Databases (use Parquet/Arrow)  
❌ Small datasets (<100 records)  
❌ Binary efficiency needs (use Protobuf)

---

## Syntax Specification

### Basic Structure

```
EntityName[record_count]:
    field1: value1|value2|value3
    field2: value1|value2|value3
```

- **Entity declaration:** `EntityName[N]:` where N is the number of records
- **Fields:** Indented under entity, one field per line
- **Values:** Pipe-delimited (`|`), one value per record
- **Indentation:** 4 spaces (consistent throughout)

### Example

**JSON (273 tokens):**
```json
{
  "users": [
    {"name": "Alice", "age": 30, "city": "LA"},
    {"name": "Bob", "age": 25, "city": "NYC"},
    {"name": "Charlie", "age": 35, "city": "Dallas"}
  ]
}
```

**ONTO (89 tokens):**
```
User[3]:
    name: Alice|Bob|Charlie
    age: 30|25|35
    city: LA|NYC|Dallas
```

---

## Nesting

Nested objects use indentation:

```
User[3]:
    name: Alice|Bob|Charlie
    age: 30|25|35
    address:
        street: 1st Ave|2nd Ave|3rd Ave
        city: LA|NYC|Dallas
        state:
            longform: California|New York|Texas
            shortform: CA|NY|TX
```

Equivalent JSON:
```json
{
  "users": [
    {
      "name": "Alice",
      "age": 30,
      "address": {
        "street": "1st Ave",
        "city": "LA",
        "state": {"longform": "California", "shortform": "CA"}
      }
    },
    ...
  ]
}
```

---

## Arrays

Arrays within values use `^` as separator. Nested arrays are **one level deep** in V1; deeper nesting (e.g., `a^b^c` as nested-within-nested) is not supported.

```
User[3]:
    name: Alice|Bob|Charlie
    tags: python^ai^ml|javascript^web|rust^systems
```

Parses to:
```json
[
  {"name": "Alice", "tags": ["python", "ai", "ml"]},
  {"name": "Bob", "tags": ["javascript", "web"]},
  {"name": "Charlie", "tags": ["rust", "systems"]}
]
```

### Array-of-Arrays Promotion

If **any value in a field contains `^`**, the entire field is interpreted as an **array of arrays**. Values without `^` become single-element arrays.

```
tags: python^ai|single|rust^systems
```

Parses to:
```json
[
  ["python", "ai"],
  ["single"],
  ["rust", "systems"]
]
```

**Rationale:** Preserves structural consistency and avoids mixed scalar/array types in the same field.

### Empty Nested Arrays

Empty nested arrays (e.g., `^` with no elements, or `^|` patterns) are **invalid syntax**. Each array element must contain at least one character or be explicitly marked as null at the outer level.

```
# Invalid — empty array element
tags: ^python|rust^systems      # Error: Empty array element

# Valid — null at outer level
tags: |python^ai|rust^systems   # First record is null, not empty array
```

### Escaping in Arrays

Use backticks when array elements contain `|` or `^`:

```
# Element contains pipe
languages: `c|c++`^python|java^kotlin

# Element contains caret
topics: `encryption^rsa`^security|networking^tcp
```

---

## Special Characters and Escaping

### Separators

| Character | Purpose |
|-----------|---------|
| `|` | Record separator (between values) |
| `^` | Array element separator |
| `` ` `` | Escape wrapper for special characters |

### When Backticks Are Required

Backticks are **only** needed when a value contains:
- Pipe (`|`)
- Caret (`^`)

Commas, spaces, and other characters do **not** require escaping:

```
# No backticks needed — commas are just text
address: no1, 1st street, LA|no2, 2nd street, NYC

# Backticks needed — value contains pipe
languages: `c|c++`^python|java^kotlin
```

### Backtick Handling

Backticks are **reserved characters** in ONTO.

**Rules:**
- Backticks (`` ` ``) are used exclusively for grouping/escaping values
- Values MUST NOT contain unescaped backticks
- Escaping backticks within values is **not supported in V1**

**Rationale:** Backticks are extremely rare in structured operational data (telemetry, logs, metrics). Supporting escape-within-escape adds complexity with negligible real-world benefit. Keeping backticks reserved ensures simpler parsing and stronger determinism.

**Implication:** ONTO is optimized for structured data, not arbitrary text blobs.

---

## Type Inference

Parsers automatically infer types:

| Pattern | Inferred Type |
|---------|---------------|
| `^-?\d+$` | Integer |
| `^-?\d+\.\d+$` | Float |
| `true` / `false` (case-insensitive) | Boolean |
| Empty (between pipes) | Null |
| Everything else | String |

### Rules

1. **Backticks force string:** `` `123` `` → `"123"` (string, not integer)
2. **Mixed types → all strings:** If a field has `100|N/A|85`, entire field becomes `["100", "N/A", "85"]`
3. **Recursive inference:** Type inference applies recursively to elements within nested arrays
4. **Array promotion precedence:** Array-of-arrays promotion takes precedence over type inference. Parser checks for `^` first, then infers types on individual elements.

### Examples

```
# Type inference
age: 30|25|40              → [30, 25, 40] (integers)
price: 19.99|24.50|9.99    → [19.99, 24.50, 9.99] (floats)
active: true|false|true    → [true, false, true] (booleans)
score: 100|N/A|85          → ["100", "N/A", "85"] (mixed → strings)

# Forced string
id: `001`|`002`|`003`      → ["001", "002", "003"] (strings, not integers)
```

---

## Null and Empty String Handling

| Syntax | Result |
|--------|--------|
| Empty between pipes (`\|\|`) | `null` |
| Backticked empty (`` ` ` ``) | `""` (empty string) |

### Examples

```
city: LA||Dallas           → ["LA", null, "Dallas"]
city: LA|``|Dallas         → ["LA", "", "Dallas"]
```

### Null in Nested Arrays

Empty values represent `null` at the **outer array level**, regardless of nesting:

```
tags: python^ai||rust^systems
```

Parses to:
```json
[
  ["python", "ai"],
  null,
  ["rust", "systems"]
]
```

---

## Comments

Lines starting with `#` are comments and ignored by parsers:

```
# Device telemetry data - Q4 2025
# Format: device_id, timestamp, reading
Device[100]:
    id: d001|d002|d003|...
    # Temperatures in Celsius
    temp: 23.5|24.1|22.8|...
```

### Comment Semantics

- Comments are **informational only**
- Comments have **no structural or semantic binding** to data
- Comments may describe the field or block that follows, but have no programmatic effect
- Parsers MUST ignore comment lines entirely

---

## Error Handling

### Strict Mode (Default)

Parsers MUST operate in strict mode by default:

- Malformed input MUST result in an error
- Errors MUST include location details (line number, position)
- No partial parsing — fail fast on invalid syntax

### Lenient Mode (Optional)

Parsers MAY provide a lenient mode for debugging:

- Best-effort parsing with warnings
- Collect all errors rather than fail on first
- Not recommended for production use

### Record Count Consistency

All fields under the same entity MUST have the same number of values. This rule applies **recursively at all nesting levels**.

**Invalid — top level mismatch:**
```
User[3]:
    name: Alice|Bob|Charlie
    age: 30|25                   # Error: Expected 3 values, found 2
```

**Invalid — nested level mismatch:**
```
User[3]:
    name: Alice|Bob|Charlie
    address:
        city: LA|NYC|Dallas
        zip: 123|456             # Error: Expected 3 values, found 2
```

### Error Examples

```
# Error: Mismatched record count
User[3]:
    name: Alice|Bob          # Error: Expected 3 values, found 2

# Error: Invalid indentation
User[2]:
    name: Alice|Bob
  age: 30|25                 # Error: Inconsistent indentation

# Error: Unclosed backtick
tags: `python|ai             # Error: Unclosed backtick at line 1
```

---

## Grammar (EBNF)

> **Note:** The EBNF grammar provided is **illustrative**, not authoritative. The reference implementation defines exact parsing behavior. Real-world formats often exceed grammar expressiveness.

```ebnf
document      = { comment | entity } ;
comment       = "#" , { any_char } , newline ;
entity        = identifier , "[" , count , "]" , ":" , newline , fields ;
count         = digit , { digit } ;
fields        = { field } ;
field         = indent , identifier , ":" , values , newline
              | indent , identifier , ":" , newline , nested_fields ;
nested_fields = { nested_field } ;
nested_field  = indent , indent , identifier , ":" , values , newline
              | indent , indent , identifier , ":" , newline , deeper_fields ;
values        = value , { "|" , value } ;
value         = escaped_value | array_value | simple_value ;
escaped_value = "`" , { any_char_except_backtick } , "`" ;
array_value   = array_elem , { "^" , array_elem } ;
array_elem    = escaped_value | simple_array_elem ;
simple_value  = { any_char_except_pipe_newline } ;
simple_array_elem = { any_char_except_pipe_caret_newline } ;
indent        = "    " ;  (* 4 spaces *)
identifier    = letter , { letter | digit | "_" | "-" | "." } ;  (* allows device-id, cpu.usage *)
```

---

## API Reference (Python)

### Installation

```bash
pip install onto-python
```

### Basic Usage

```python
import onto

# JSON to ONTO
json_data = [
    {"name": "Alice", "age": 30},
    {"name": "Bob", "age": 25}
]
onto_str = onto.dumps(json_data, entity_name="User")
print(onto_str)
# User[2]:
#     name: Alice|Bob
#     age: 30|25

# ONTO to JSON
onto_str = """
User[2]:
    name: Alice|Bob
    age: 30|25
"""
json_data = onto.loads(onto_str)
print(json_data)
# [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
```

### Error Handling

```python
import onto

try:
    data = onto.loads(malformed_onto_string)
except onto.ParseError as e:
    print(f"Error at line {e.line}: {e.message}")
```

---

## Comparison with Other Formats

| Format | Token Count (1000 records) | Human Readable | Nested Support | LLM Optimized |
|--------|---------------------------|----------------|----------------|---------------|
| JSON | 100% (baseline) | ✅ | ✅ | ❌ (brace matching) |
| YAML | ~90% | ✅ | ✅ | ⚠️ (better than JSON) |
| CSV | ~40% | ⚠️ (flat only) | ❌ | ⚠️ (no hierarchy) |
| ONTO | ~35% | ✅ | ✅ | ✅ (indentation-based) |

---

## Known Limitations (V1)

1. **No schema validation:** Parser assumes well-formed input
2. **No streaming:** Entire input must fit in memory
3. **Homogeneous records:** All records in an entity must have same fields
4. **No mixed nesting:** Cannot mix array and object nesting arbitrarily
5. **4-space indentation only:** Tabs or other spacing not supported
6. **No backtick escaping:** Backticks cannot appear in values
7. **No multi-line values:** Each field must be on a single line

---

## Future Work (V2 Considerations)

- Schema definitions for validation
- Streaming parser for large datasets
- Support for heterogeneous record structures
- Configurable indentation
- Binary encoding option for storage (not for LLM use)
- Multi-line value continuation for large datasets
- Backtick escaping within values

---

## License

MIT License

---

## References

- [GitHub Repository](https://github.com/pragmaticbyharsh/onto)
- [ArXiv Paper](https://arxiv.org/abs/xxxx.xxxxx) (pending)
