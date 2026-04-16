# benchmarks/benchmark_accuracy.py
"""Accuracy benchmark for ONTO vs JSON vs YAML vs TOON using cloud LLMs.

Tests cold (no system prompt) vs warm (with ONTO explanation) accuracy.
No timing measurements - focus purely on correctness.
"""

import argparse
import json
import os
import re
import time
import yaml
from datetime import datetime
from pathlib import Path

import tiktoken
from dotenv import load_dotenv

from generators import generate_iot_telemetry, generate_system_metrics
import onto

# Try to import toon-py
try:
    from toon_py import encode as toon_encode

    TOON_AVAILABLE = True
except ImportError:
    TOON_AVAILABLE = False
    print("WARNING: toon-py not installed. Run: pip install toon-py")

load_dotenv()

# --- Constants ---

DATASETS = {
    "iot_telemetry": ("Telemetry", generate_iot_telemetry, "temperature"),
    "system_metrics": ("Metrics", generate_system_metrics, "cpu_percent"),
}

# Test scenarios: (format, mode)
# JSON, YAML, TOON = cold only (LLMs know them or no good spec to teach)
# ONTO = cold and warm
TEST_SCENARIOS = [
    ("json", "cold"),
    ("yaml", "cold"),
    ("toon", "cold"),
    ("onto", "cold"),
    ("onto", "warm"),
]

# --- System Prompts ---

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

# --- Task Prompts ---

TASK_PROMPT = """Analyze this data containing {n} records.

{data}

Answer these questions. Return ONLY a JSON object with keys "q1", "q2", "q3", "q4". No other text.

1. {q1}
2. {q2}
3. {q3}
4. {q4}"""


# --- Question Generation ---

def generate_questions_iot(data: list[dict]) -> dict:
    """Generate questions and ground truth for IoT telemetry data."""
    # Pick a record at 1/3 position for lookup
    target_record = data[len(data) // 3]
    target_id = target_record["device_id"]

    # Count devices with battery below 30%
    low_battery_count = sum(1 for r in data if r["battery_level"] < 30)

    # Unique device IDs
    device_ids = sorted(set(r["device_id"] for r in data))

    # Max temperature
    max_temp = max(r["temperature"] for r in data)

    return {
        "questions": {
            "q1": f'What is the temperature for device "{target_id}"?',
            "q2": 'How many devices have battery_level below 30?',
            "q3": 'List all unique device_id values as a JSON array.',
            "q4": 'What is the highest temperature?',
        },
        "answers": {
            "q1": target_record["temperature"],
            "q2": low_battery_count,
            "q3": device_ids,
            "q4": max_temp,
        }
    }


def generate_questions_metrics(data: list[dict]) -> dict:
    """Generate questions and ground truth for system metrics data."""
    # Pick a record at 1/3 position for lookup
    target_record = data[len(data) // 3]
    target_host = target_record["host"]

    # Count high CPU hosts (above 50% - realistic threshold given 5-70% range)
    high_cpu_count = sum(1 for r in data if r["cpu_percent"] > 50)

    # Unique hosts
    hosts = sorted(set(r["host"] for r in data))

    # Max memory percent
    max_memory = max(r["memory_percent"] for r in data)

    return {
        "questions": {
            "q1": f'What is the cpu_percent for host "{target_host}"?',
            "q2": 'How many records have cpu_percent above 50?',
            "q3": 'List all unique host names as a JSON array.',
            "q4": 'What is the highest memory_percent?',
        },
        "answers": {
            "q1": target_record["cpu_percent"],
            "q2": high_cpu_count,
            "q3": hosts,
            "q4": max_memory,
        }
    }


def generate_questions(data: list[dict], dataset_name: str) -> dict:
    """Generate questions based on dataset type."""
    if dataset_name == "iot_telemetry":
        return generate_questions_iot(data)
    elif dataset_name == "system_metrics":
        return generate_questions_metrics(data)
    else:
        raise ValueError(f"Unknown dataset: {dataset_name}")


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


# --- LLM Clients ---

def call_openai(model: str, prompt: str, system_prompt: str = None) -> str:
    """Call OpenAI API, return response text."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
    )

    return response.choices[0].message.content.strip()


def call_anthropic(model: str, prompt: str, system_prompt: str = None) -> str:
    """Call Anthropic API, return response text."""
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    kwargs = {
        "model": model,
        "max_tokens": 256,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    response = client.messages.create(**kwargs)

    return response.content[0].text.strip()


def call_llm(provider: str, model: str, prompt: str, system_prompt: str = None) -> str:
    """Dispatch to appropriate provider."""
    if provider == "openai":
        return call_openai(model, prompt, system_prompt)
    elif provider == "anthropic":
        return call_anthropic(model, prompt, system_prompt)
    else:
        raise ValueError(f"Unknown provider: {provider}")


# --- Scoring ---

def parse_response(response: str) -> dict | None:
    """Parse JSON response from LLM."""
    # Try to extract JSON from response
    response = response.strip()

    # Remove markdown code blocks if present
    if response.startswith("```"):
        lines = response.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.startswith("```")]
        response = "\n".join(lines)

    try:
        return json.loads(response)
    except json.JSONDecodeError:
        # Try to find JSON object in response
        match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None


def score_answer(parsed, expected, question_type: str) -> bool:
    """Score a single answer against expected value."""
    if parsed is None:
        return False

    if question_type == "number":
        # Allow 1% tolerance for numeric answers
        try:
            parsed_num = float(parsed)
            expected_num = float(expected)
            if expected_num == 0:
                return abs(parsed_num) < 0.01
            return abs(parsed_num - expected_num) / abs(expected_num) < 0.01
        except (ValueError, TypeError):
            return False

    elif question_type == "integer":
        # Exact integer match
        try:
            return int(parsed) == int(expected)
        except (ValueError, TypeError):
            return False

    elif question_type == "list":
        # Set comparison (order doesn't matter)
        try:
            if isinstance(parsed, str):
                # Try to parse as JSON array
                parsed = json.loads(parsed)
            parsed_set = set(str(x).lower().strip() for x in parsed)
            expected_set = set(str(x).lower().strip() for x in expected)
            return parsed_set == expected_set
        except (json.JSONDecodeError, TypeError):
            return False

    return False


def score_response(response: str, answers: dict) -> dict:
    """Score full response against expected answers."""
    parsed = parse_response(response)

    if parsed is None:
        return {
            "correct": 0,
            "total": 4,
            "details": {
                "q1": {"correct": False, "error": "parse_failed"},
                "q2": {"correct": False, "error": "parse_failed"},
                "q3": {"correct": False, "error": "parse_failed"},
                "q4": {"correct": False, "error": "parse_failed"},
            },
            "parsed": None,
            "expected": answers,
        }

    # Question types: q1=number, q2=integer, q3=list, q4=number
    question_types = {"q1": "number", "q2": "integer", "q3": "list", "q4": "number"}

    details = {}
    correct_count = 0

    for q_key in ["q1", "q2", "q3", "q4"]:
        parsed_val = parsed.get(q_key)
        expected_val = answers[q_key]
        q_type = question_types[q_key]

        is_correct = score_answer(parsed_val, expected_val, q_type)
        if is_correct:
            correct_count += 1

        details[q_key] = {
            "correct": is_correct,
            "parsed": parsed_val,
            "expected": expected_val,
        }

    return {
        "correct": correct_count,
        "total": 4,
        "accuracy": correct_count / 4,
        "details": details,
        "parsed": parsed,
        "expected": answers,
    }


# --- Benchmark ---

def run_single(
        provider: str,
        model: str,
        fmt: str,
        dataset_name: str,
        data: list[dict],
        entity_name: str,
        questions_data: dict,
        mode: str,  # "cold" or "warm"
) -> dict:
    """Run a single accuracy test."""
    n = len(data)

    # Format data
    data_str = format_data(data, fmt, entity_name)
    input_tokens = count_tokens(data_str)

    # Build prompt with questions
    questions = questions_data["questions"]
    prompt = TASK_PROMPT.format(
        n=n,
        data=data_str,
        q1=questions["q1"],
        q2=questions["q2"],
        q3=questions["q3"],
        q4=questions["q4"],
    )

    # Determine system prompt
    system_prompt = None
    if mode == "warm" and fmt == "onto":
        system_prompt = ONTO_SYSTEM_PROMPT

    # Call LLM
    try:
        response = call_llm(provider, model, prompt, system_prompt)
        error = None
    except Exception as e:
        response = ""
        error = str(e)

    # Score
    score = score_response(response, questions_data["answers"])

    return {
        "format": fmt,
        "dataset": dataset_name,
        "mode": mode,
        "input_tokens": input_tokens,
        "response": response,
        "score": score,
        "error": error,
    }


def run_benchmark(
        provider: str,
        model: str,
        records: int,
        runs: int,
        output_dir: Path,
        delay: float = 1.0,
) -> dict:
    """Run full accuracy benchmark."""

    # Filter out TOON if not available
    scenarios = TEST_SCENARIOS
    if not TOON_AVAILABLE:
        scenarios = [(fmt, mode) for fmt, mode in scenarios if fmt != "toon"]

    results = {
        "provider": provider,
        "model": model,
        "scenarios": [(fmt, mode) for fmt, mode in scenarios],
        "records": records,
        "runs": runs,
        "timestamp": datetime.now().isoformat(),
        "runs_data": [],
    }

    datasets_to_test = ["iot_telemetry", "system_metrics"]

    for run_num in range(runs):
        seed = 1000 + run_num
        print(f"\n--- Run {run_num + 1}/{runs} (seed={seed}) ---")

        run_results = {"run_num": run_num, "seed": seed, "scenarios": []}

        for dataset_name in datasets_to_test:
            entity_name, generator = DATASETS[dataset_name][:2]

            # Generate data once per dataset per run
            if dataset_name == "system_metrics":
                gen_result = generator(records, seed=seed, anomaly_rate=0)
                data = gen_result["data"]
            else:
                data = generator(records, seed=seed)

            # Generate questions from this data
            questions_data = generate_questions(data, dataset_name)

            for fmt, test_mode in scenarios:
                label = f"{dataset_name}/{fmt}/{test_mode}"
                print(f"  {label}...", end=" ", flush=True)

                result = run_single(
                    provider=provider,
                    model=model,
                    fmt=fmt,
                    dataset_name=dataset_name,
                    data=data,
                    entity_name=entity_name,
                    questions_data=questions_data,
                    mode=test_mode,
                )
                result["seed"] = seed
                run_results["scenarios"].append(result)

                if result["error"]:
                    print(f"ERROR: {result['error']}")
                else:
                    score = result["score"]
                    print(f"{score['correct']}/4 correct")

                # Rate limit delay
                time.sleep(delay)

        results["runs_data"].append(run_results)

    return results


# --- Analysis ---

def compute_summary(results: dict) -> dict:
    """Compute accuracy summary."""
    summary = {"by_scenario": {}, "by_question": {}, "comparisons": {}}

    # Aggregate by scenario
    scenario_data = {}
    question_data = {}  # Track per-question accuracy

    for run in results["runs_data"]:
        for scenario in run["scenarios"]:
            key = f"{scenario['dataset']}/{scenario['format']}/{scenario['mode']}"
            if key not in scenario_data:
                scenario_data[key] = {"correct": 0, "total": 0, "q_correct": [0, 0, 0, 0]}

            score = scenario["score"]
            scenario_data[key]["correct"] += score.get("correct", 0)
            scenario_data[key]["total"] += score.get("total", 4)

            # Track per-question
            details = score.get("details", {})
            for i, q_key in enumerate(["q1", "q2", "q3", "q4"]):
                if details.get(q_key, {}).get("correct"):
                    scenario_data[key]["q_correct"][i] += 1

    # Compute accuracy per scenario
    for key, data in scenario_data.items():
        accuracy = data["correct"] / data["total"] if data["total"] > 0 else 0
        runs = data["total"] // 4  # 4 questions per run
        summary["by_scenario"][key] = {
            "questions_correct": data["correct"],
            "questions_total": data["total"],
            "accuracy": round(accuracy, 3),
            "runs": runs,
            "q1_accuracy": data["q_correct"][0] / runs if runs > 0 else 0,
            "q2_accuracy": data["q_correct"][1] / runs if runs > 0 else 0,
            "q3_accuracy": data["q_correct"][2] / runs if runs > 0 else 0,
            "q4_accuracy": data["q_correct"][3] / runs if runs > 0 else 0,
        }

    # Compare all formats for each dataset
    for dataset in ["iot_telemetry", "system_metrics"]:
        comparison = {}

        # All cold formats
        for fmt in ["json", "yaml", "toon", "onto"]:
            key = f"{dataset}/{fmt}/cold"
            if key in summary["by_scenario"]:
                comparison[f"{fmt}_cold"] = summary["by_scenario"][key]["accuracy"]

        # ONTO warm
        warm_key = f"{dataset}/onto/warm"
        if warm_key in summary["by_scenario"]:
            comparison["onto_warm"] = summary["by_scenario"][warm_key]["accuracy"]

        # Delta: ONTO warm vs cold
        if "onto_cold" in comparison and "onto_warm" in comparison:
            comparison["onto_warm_vs_cold"] = round(
                comparison["onto_warm"] - comparison["onto_cold"], 3
            )

        if comparison:
            summary["comparisons"][dataset] = comparison

    return summary


def print_summary(results: dict, summary: dict):
    """Print summary to console."""
    print("\n" + "=" * 60)
    print("ACCURACY BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Provider: {results['provider']} | Model: {results['model']}")
    print(f"Records: {results['records']} | Runs: {results['runs']}")
    print(f"Tasks: Q1=lookup, Q2=count, Q3=list, Q4=max")

    print("\n--- Accuracy by Scenario (% of questions correct) ---")
    print("| Dataset | Format | Mode | Accuracy | Q1 | Q2 | Q3 | Q4 |")
    print("|---------|--------|------|----------|----|----|----|----|")
    for key, stats in sorted(summary["by_scenario"].items()):
        parts = key.split("/")
        dataset, fmt, mode = parts[0], parts[1], parts[2]
        pct = f"{stats['accuracy'] * 100:.0f}%"
        q1 = f"{stats['q1_accuracy'] * 100:.0f}%"
        q2 = f"{stats['q2_accuracy'] * 100:.0f}%"
        q3 = f"{stats['q3_accuracy'] * 100:.0f}%"
        q4 = f"{stats['q4_accuracy'] * 100:.0f}%"
        print(f"| {dataset} | {fmt} | {mode} | {pct} | {q1} | {q2} | {q3} | {q4} |")

    print("\n--- Format Comparison ---")
    print("| Dataset | JSON | YAML | TOON | ONTO cold | ONTO warm | Δ warm-cold |")
    print("|---------|------|------|------|-----------|-----------|-------------|")
    for dataset, comp in sorted(summary["comparisons"].items()):
        json_cold = f"{comp.get('json_cold', 0) * 100:.0f}%" if "json_cold" in comp else "—"
        yaml_cold = f"{comp.get('yaml_cold', 0) * 100:.0f}%" if "yaml_cold" in comp else "—"
        toon_cold = f"{comp.get('toon_cold', 0) * 100:.0f}%" if "toon_cold" in comp else "—"
        onto_cold = f"{comp.get('onto_cold', 0) * 100:.0f}%" if "onto_cold" in comp else "—"
        onto_warm = f"{comp.get('onto_warm', 0) * 100:.0f}%" if "onto_warm" in comp else "—"
        delta = f"+{comp['onto_warm_vs_cold'] * 100:.0f}%" if "onto_warm_vs_cold" in comp and comp[
            'onto_warm_vs_cold'] >= 0 else f"{comp.get('onto_warm_vs_cold', 0) * 100:.0f}%" if "onto_warm_vs_cold" in comp else "—"
        print(f"| {dataset} | {json_cold} | {yaml_cold} | {toon_cold} | {onto_cold} | {onto_warm} | {delta} |")


def save_results(results: dict, summary: dict, output_dir: Path) -> Path:
    """Save results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"results_accuracy_{timestamp}.json"

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
    parser = argparse.ArgumentParser(description="ONTO Accuracy Benchmark")
    parser.add_argument("--provider", choices=["openai", "anthropic"], required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--records", type=int, default=50)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between API calls (seconds)")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "results")

    args = parser.parse_args()

    # Validate API key
    if args.provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set")
        return
    if args.provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set")
        return

    if not TOON_AVAILABLE:
        print("Warning: toon-py not installed, skipping TOON format")

    print(f"Starting accuracy benchmark...")
    print(f"Provider: {args.provider} | Model: {args.model}")
    print(f"Records: {args.records} | Runs: {args.runs}")
    print(f"Scenarios: JSON, YAML, TOON, ONTO(cold), ONTO(warm)")

    results = run_benchmark(
        provider=args.provider,
        model=args.model,
        records=args.records,
        runs=args.runs,
        output_dir=args.output_dir,
        delay=args.delay,
    )

    summary = compute_summary(results)
    print_summary(results, summary)
    save_results(results, summary, args.output_dir)


if __name__ == "__main__":
    main()