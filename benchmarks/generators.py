# benchmarks/generators.py
"""Synthetic data generators for ONTO benchmarks."""

import random
from datetime import datetime, timedelta


def generate_iot_telemetry(n: int, seed: int = 42) -> list[dict]:
    """
    Generate IoT telemetry data.

    Fields: device_id, timestamp, temperature, humidity, pressure,
            battery_level, location: {lat, lon}
    """
    random.seed(seed)
    base_time = datetime(2025, 1, 1, 0, 0, 0)

    records = []
    for i in range(n):
        records.append({
            "device_id": f"sensor-{random.randint(1000, 9999)}",
            "timestamp": (base_time + timedelta(minutes=i * 5)).isoformat(),
            "temperature": round(random.uniform(18.0, 32.0), 2),
            "humidity": round(random.uniform(30.0, 80.0), 2),
            "pressure": round(random.uniform(990.0, 1030.0), 2),
            "battery_level": random.randint(10, 100),
            "location": {
                "lat": round(random.uniform(25.0, 48.0), 6),
                "lon": round(random.uniform(-125.0, -70.0), 6),
            },
        })
    return records


def generate_system_metrics(n: int, seed: int = 42, anomaly_rate: float = 0.0) -> dict:
    """
    Generate system metrics data.

    Fields: host, timestamp, cpu_percent, memory_percent,
            disk_io_read, disk_io_write, network_in, network_out

    Args:
        n: Number of records
        seed: Random seed for reproducibility
        anomaly_rate: Fraction of records to inject anomalies (0.0-1.0)

    Returns:
        Dict with 'data', 'anomaly_indices', and 'anomaly_details'
    """
    random.seed(seed)
    base_time = datetime(2025, 1, 1, 0, 0, 0)
    hosts = [f"server-{i:03d}" for i in range(1, 21)]

    records = []
    anomaly_indices = []
    anomaly_details = []

    # Determine which indices will have anomalies
    num_anomalies = int(n * anomaly_rate)
    anomaly_set = set(random.sample(range(n), min(num_anomalies, n))) if num_anomalies > 0 else set()

    for i in range(n):
        record = {
            "host": random.choice(hosts),
            "timestamp": (base_time + timedelta(seconds=i * 30)).isoformat(),
            "cpu_percent": round(random.uniform(5.0, 70.0), 1),
            "memory_percent": round(random.uniform(20.0, 75.0), 1),
            "disk_io_read": random.randint(0, 500000),
            "disk_io_write": random.randint(0, 300000),
            "network_in": random.randint(0, 10000000),
            "network_out": random.randint(0, 5000000),
        }

        # Inject anomaly if this index is selected
        if i in anomaly_set:
            anomaly_type = random.choice(["cpu_spike", "memory_spike", "negative_value", "zero_network"])

            if anomaly_type == "cpu_spike":
                record["cpu_percent"] = round(random.uniform(95.0, 100.0), 1)
                anomaly_details.append({
                    "index": i, "field": "cpu_percent",
                    "value": record["cpu_percent"], "type": "spike"
                })
            elif anomaly_type == "memory_spike":
                record["memory_percent"] = round(random.uniform(95.0, 100.0), 1)
                anomaly_details.append({
                    "index": i, "field": "memory_percent",
                    "value": record["memory_percent"], "type": "spike"
                })
            elif anomaly_type == "negative_value":
                record["disk_io_read"] = -random.randint(1000, 50000)
                anomaly_details.append({
                    "index": i, "field": "disk_io_read",
                    "value": record["disk_io_read"], "type": "negative"
                })
            elif anomaly_type == "zero_network":
                record["network_in"] = 0
                record["network_out"] = 0
                anomaly_details.append({
                    "index": i, "field": "network_in,network_out",
                    "value": "0,0", "type": "zero_activity"
                })

            anomaly_indices.append(i)

        records.append(record)

    return {
        "data": records,
        "anomaly_indices": sorted(anomaly_indices),
        "anomaly_details": anomaly_details,
    }


def generate_log_entries(n: int, seed: int = 42) -> list[dict]:
    """
    Generate structured log entries.

    Fields: timestamp, level, service, message, request_id,
            duration_ms, status_code
    """
    random.seed(seed)
    base_time = datetime(2025, 1, 1, 0, 0, 0)

    levels = ["INFO", "INFO", "INFO", "WARN", "ERROR"]  # Weighted toward INFO
    services = ["auth-service", "api-gateway", "user-service", "order-service", "payment-service"]
    messages = [
        "Request processed successfully",
        "Connection established",
        "Cache hit",
        "Cache miss, fetching from database",
        "Retrying failed request",
        "Rate limit exceeded",
        "Authentication successful",
        "Token refreshed",
        "Database query completed",
        "External API call completed",
    ]

    records = []
    for i in range(n):
        level = random.choice(levels)
        status = 200 if level == "INFO" else (400 if level == "WARN" else 500)

        records.append({
            "timestamp": (base_time + timedelta(milliseconds=i * 100)).isoformat(),
            "level": level,
            "service": random.choice(services),
            "message": random.choice(messages),
            "request_id": f"req-{random.randint(100000, 999999)}",
            "duration_ms": random.randint(1, 2000),
            "status_code": status,
        })
    return records


if __name__ == "__main__":
    # Quick test
    print("IoT Telemetry (3 records):")
    for r in generate_iot_telemetry(3):
        print(f"  {r}")

    print("\nSystem Metrics (5 records, 40% anomalies):")
    result = generate_system_metrics(5, anomaly_rate=0.4)
    for i, r in enumerate(result["data"]):
        marker = " <-- ANOMALY" if i in result["anomaly_indices"] else ""
        print(f"  {r}{marker}")
    print(f"Anomaly details: {result['anomaly_details']}")

    print("\nLog Entries (3 records):")
    for r in generate_log_entries(3):
        print(f"  {r}")