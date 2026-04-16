# benchmarks/formatters.py
"""Format converters for ONTO benchmarks."""

import json
import csv
import io
import yaml
import onto


def to_json(data: list[dict]) -> str:
    """Convert data to JSON string."""
    return json.dumps(data, indent=2)


def to_yaml(data: list[dict]) -> str:
    """Convert data to YAML string."""
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def to_csv(data: list[dict]) -> str:
    """
    Convert data to CSV string.

    Flattens nested dicts using dot notation (e.g., location.lat).
    Arrays are joined with semicolons.
    """
    if not data:
        return ""

    # Flatten all records to get all possible columns
    def flatten(record: dict, prefix: str = "") -> dict:
        flat = {}
        for key, value in record.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flat.update(flatten(value, full_key))
            elif isinstance(value, list):
                flat[full_key] = ";".join(str(v) for v in value)
            else:
                flat[full_key] = value
        return flat

    flat_records = [flatten(r) for r in data]

    # Get all unique columns in order
    columns = []
    for record in flat_records:
        for key in record.keys():
            if key not in columns:
                columns.append(key)

    # Write CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(flat_records)
    return output.getvalue()


def to_onto(data: list[dict], entity_name: str = "Entity") -> str:
    """Convert data to ONTO string."""
    return onto.dumps(data, entity_name)


if __name__ == "__main__":
    # Quick test with sample data
    from generators import generate_iot_telemetry

    data = generate_iot_telemetry(3)

    print("=== JSON ===")
    print(to_json(data)[:500])
    print("\n=== YAML ===")
    print(to_yaml(data)[:500])
    print("\n=== CSV ===")
    print(to_csv(data)[:500])
    print("\n=== ONTO ===")
    print(to_onto(data, "Telemetry"))