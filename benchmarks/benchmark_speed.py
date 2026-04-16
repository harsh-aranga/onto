# benchmarks/benchmark_speed.py
"""Speed benchmark for ONTO vs TOON vs JSON using local Ollama inference.

Measures TTFT and total time only. No accuracy scoring.
"""

import argparse
import json
import time
import yaml
from datetime import datetime
from pathlib import Path

import tiktoken

from generators import generate_iot_telemetry, generate_system_metrics
import onto

# Try to import toon-py
try:
    from toon_py import encode as toon_encode

    TOON_AVAILABLE = True
except ImportError:
    TOON_AVAILABLE = False
    print("WARNING: toon-py not installed. Run: pip install toon-py")

# --- Constants ---

DATASETS = {
    "iot_telemetry": ("Telemetry", generate_iot_telemetry),
    "system_metrics": ("Metrics", generate_system_metrics),
}

FORMATS = ["json", "yaml", "toon", "onto"]

# Simple prompt - just ask for a summary, don't need complex reasoning
PROMPT_TEMPLATE = """Analyze this data containing {n} records.

{data}

Summarize the data in one sentence."""

# ONTO format explanation
ONTO_SYSTEM_PROMPT = """You are analyzing data in ONTO format - a columnar notation for structured data.

ONTO format rules:
- First line declares the entity name and field names: `entity: field1, field2, field3`
- Following lines contain pipe-separated values: `value1|value2|value3`
- Each line is one record, fields match the header order
- Nested objects use indentation (4 spaces) with their own field declarations
- Arrays use ^ separator: `val1^val2^val3`
- Empty value || means null

Example:
```
sensors: id, temp, status
  location: lat, lon
s1|23.5|active
    40.7|-74.0
s2|19.2|idle
    34.0|-118.2
```
This represents 2 sensor records, each with a nested location object."""


# --- Token Counting ---

def count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base)."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


# --- Data Formatting ---

def format_data(data: list[dict], fmt: str, entity_name: str) -> str:
    """Format data to specified format string."""
    if fmt == "json":
        return json.dumps(data, separators=(",", ":"))
    elif fmt == "yaml":
        return yaml.dump(data, default_flow_style=False)
    elif fmt == "toon":
        if not TOON_AVAILABLE:
            raise RuntimeError("toon-py not installed")
        return toon_encode(data)
    elif fmt == "onto":
        return onto.dumps(data, entity_name)
    else:
        raise ValueError(f"Unknown format: {fmt}")


# --- Ollama Client ---

def call_ollama(model: str, prompt: str, system_prompt: str = None) -> dict:
    """Call Ollama API with streaming, measure TTFT and total time."""
    from openai import OpenAI

    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    start_time = time.perf_counter()
    ttft = None
    full_response = ""

    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
    )

    for chunk in stream:
        if chunk.choices[0].delta.content:
            if ttft is None:
                ttft = time.perf_counter() - start_time
            full_response += chunk.choices[0].delta.content

    total_time = time.perf_counter() - start_time

    return {
        "ttft": ttft,
        "total_time": total_time,
        "output_chars": len(full_response),
    }


# --- Benchmark ---

def run_single(
        model: str,
        fmt: str,
        dataset_name: str,
        data: list[dict],
        entity_name: str,
        use_system_prompt: bool = False,
) -> dict:
    """Run a single speed test."""
    n = len(data)

    # Format data
    data_str = format_data(data, fmt, entity_name)
    input_tokens = count_tokens(data_str)

    # Build prompt
    prompt = PROMPT_TEMPLATE.format(n=n, data=data_str)
    prompt_tokens = count_tokens(prompt)

    # Determine system prompt (only for ONTO)
    system_prompt = ONTO_SYSTEM_PROMPT if (use_system_prompt and fmt == "onto") else None

    # Call LLM
    try:
        result = call_ollama(model, prompt, system_prompt)
        error = None
    except Exception as e:
        result = {"ttft": None, "total_time": None, "output_chars": 0}
        error = str(e)

    return {
        "format": fmt,
        "dataset": dataset_name,
        "ttft": result["ttft"],
        "total_time": result["total_time"],
        "input_tokens": input_tokens,
        "prompt_tokens": prompt_tokens,
        "output_chars": result["output_chars"],
        "error": error,
    }


def run_benchmark(
        model: str,
        records: int,
        runs: int,
        output_dir: Path,
) -> dict:
    """Run full speed benchmark."""

    results = {
        "model": model,
        "records": records,
        "runs": runs,
        "timestamp": datetime.now().isoformat(),
        "runs_data": [],
    }

    # Test scenarios: (format, mode, use_system_prompt)
    scenarios_to_test = [
        ("json", "cold", False),
        ("yaml", "cold", False),
        ("onto", "cold", False),
        ("onto", "warm", True),
    ]
    if TOON_AVAILABLE:
        scenarios_to_test.insert(2, ("toon", "cold", False))  # json, yaml, toon, onto_cold, onto_warm

    datasets_to_test = ["iot_telemetry", "system_metrics"]

    for run_num in range(runs):
        seed = 1000 + run_num
        print(f"\n--- Run {run_num + 1}/{runs} (seed={seed}) ---")

        run_results = {"run_num": run_num, "seed": seed, "scenarios": []}

        for dataset_name in datasets_to_test:
            entity_name, generator = DATASETS[dataset_name]

            # Generate data once per dataset per run
            if dataset_name == "system_metrics":
                gen_result = generator(records, seed=seed, anomaly_rate=0)
                data = gen_result["data"]
            else:
                data = generator(records, seed=seed)

            for fmt, mode, use_sys_prompt in scenarios_to_test:
                label = f"{dataset_name}/{fmt}/{mode}"
                print(f"  {label}...", end=" ", flush=True)

                result = run_single(
                    model=model,
                    fmt=fmt,
                    dataset_name=dataset_name,
                    data=data,
                    entity_name=entity_name,
                    use_system_prompt=use_sys_prompt,
                )
                result["seed"] = seed
                result["mode"] = mode
                run_results["scenarios"].append(result)

                if result["error"]:
                    print(f"ERROR: {result['error']}")
                else:
                    print(
                        f"TTFT={result['ttft']:.3f}s, Total={result['total_time']:.3f}s, Tokens={result['input_tokens']}")

        results["runs_data"].append(run_results)

    return results


# --- Analysis ---

def compute_summary(results: dict) -> dict:
    """Compute summary statistics."""
    summary = {"by_scenario": {}, "paired_deltas": {}}

    # Aggregate by scenario
    scenario_data = {}
    for run in results["runs_data"]:
        for scenario in run["scenarios"]:
            mode = scenario.get("mode", "cold")
            key = f"{scenario['dataset']}/{scenario['format']}/{mode}"
            if key not in scenario_data:
                scenario_data[key] = {"ttft": [], "total": [], "tokens": []}
            if scenario["ttft"] is not None:
                scenario_data[key]["ttft"].append(scenario["ttft"])
                scenario_data[key]["total"].append(scenario["total_time"])
                scenario_data[key]["tokens"].append(scenario["input_tokens"])

    # Compute averages
    for key, data in scenario_data.items():
        if data["ttft"]:
            summary["by_scenario"][key] = {
                "n": len(data["ttft"]),
                "avg_ttft": sum(data["ttft"]) / len(data["ttft"]),
                "min_ttft": min(data["ttft"]),
                "max_ttft": max(data["ttft"]),
                "avg_total": sum(data["total"]) / len(data["total"]),
                "avg_tokens": sum(data["tokens"]) / len(data["tokens"]),
            }

    # Compute paired deltas vs JSON
    for dataset in ["iot_telemetry", "system_metrics"]:
        json_key = f"{dataset}/json/cold"
        if json_key not in summary["by_scenario"]:
            continue
        json_stats = summary["by_scenario"][json_key]

        for fmt_mode in ["yaml/cold", "toon/cold", "onto/cold", "onto/warm"]:
            fmt_key = f"{dataset}/{fmt_mode}"
            if fmt_key not in summary["by_scenario"]:
                continue
            fmt_stats = summary["by_scenario"][fmt_key]

            delta_key = f"{dataset}/{fmt_mode}_vs_json"
            summary["paired_deltas"][delta_key] = {
                "ttft_reduction_pct": (1 - fmt_stats["avg_ttft"] / json_stats["avg_ttft"]) * 100,
                "total_reduction_pct": (1 - fmt_stats["avg_total"] / json_stats["avg_total"]) * 100,
                "token_reduction_pct": (1 - fmt_stats["avg_tokens"] / json_stats["avg_tokens"]) * 100,
            }

    return summary


def print_summary(results: dict, summary: dict):
    """Print summary to console."""
    print("\n" + "=" * 60)
    print("SPEED BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Model: {results['model']}")
    print(f"Records: {results['records']} | Runs: {results['runs']}")

    print("\n--- Average Times by Scenario ---")
    print("| Dataset | Format | Mode | TTFT (s) | Total (s) | Tokens |")
    print("|---------|--------|------|----------|-----------|--------|")
    for key, stats in sorted(summary["by_scenario"].items()):
        parts = key.split("/")
        dataset, fmt, mode = parts[0], parts[1], parts[2]
        print(
            f"| {dataset} | {fmt} | {mode} | {stats['avg_ttft']:.3f} | {stats['avg_total']:.3f} | {stats['avg_tokens']:.0f} |")

    print("\n--- Reduction vs JSON ---")
    print("| Dataset | Format/Mode | TTFT Δ | Total Δ | Token Δ |")
    print("|---------|-------------|--------|---------|---------|")
    for key, delta in sorted(summary["paired_deltas"].items()):
        parts = key.split("/")
        dataset = parts[0]
        fmt_mode = "/".join(parts[1:]).replace("_vs_json", "")
        print(
            f"| {dataset} | {fmt_mode} | {delta['ttft_reduction_pct']:.1f}% | {delta['total_reduction_pct']:.1f}% | {delta['token_reduction_pct']:.1f}% |")


def save_results(results: dict, summary: dict, output_dir: Path) -> Path:
    """Save results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"results_speed_{timestamp}.json"

    output = {
        "results": results,
        "summary": summary,
    }

    filepath = output_dir / filename
    filepath.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nResults saved to: {filepath}")

    return filepath


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="ONTO Speed Benchmark (Ollama)")
    parser.add_argument("--model", type=str, default="qwen2.5:7b-instruct-q4_K_M")
    parser.add_argument("--records", type=int, default=100)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "results")

    args = parser.parse_args()

    if not TOON_AVAILABLE:
        print("Warning: toon-py not installed, skipping TOON format")

    print(f"Starting speed benchmark...")
    print(f"Model: {args.model}")
    print(f"Records: {args.records} | Runs: {args.runs}")
    print(f"Scenarios: JSON, YAML, TOON, ONTO(cold), ONTO(warm)")

    results = run_benchmark(
        model=args.model,
        records=args.records,
        runs=args.runs,
        output_dir=args.output_dir,
    )

    summary = compute_summary(results)
    print_summary(results, summary)
    save_results(results, summary, args.output_dir)


if __name__ == "__main__":
    main()