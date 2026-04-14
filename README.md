# ONTO: Object Notation for Token Optimization

A columnar, token-efficient data notation designed for LLM workflows. Reduces token overhead by 60-70% compared to JSON while preserving human readability.

## Installation

```bash
pip install onto
```

## Quick Start

```python
import onto

# ONTO to JSON
onto_str = """
User[3]:
    name: Alice|Bob|Charlie
    age: 30|25|35
"""
data = onto.loads(onto_str)
# [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}, {"name": "Charlie", "age": 35}]

# JSON to ONTO
onto_str = onto.dumps(data, entity_name="User")
```

## License

MIT