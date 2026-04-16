# benchmarks/benchmark_tokens.py
"""Token counting benchmark for ONTO vs TOON vs JSON vs YAML."""

import argparse
import json
import tiktoken
from datetime import datetime
from pathlib import Path

from generators import generate_iot_telemetry, generate_system_metrics, generate_log_entries
from formatters import to_json, to_yaml, to_onto

# Try to import toon-py
try:
    from toon_py import encode as toon_encode

    TOON_AVAILABLE = True
except ImportError:
    TOON_AVAILABLE = False

# Dataset registry
DATASETS = {
    "iot_telemetry": ("Telemetry", generate_iot_telemetry),
    "system_metrics": ("Metrics", generate_system_metrics),
    "log_entries": ("LogEntry", generate_log_entries),
}


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens using tiktoken."""
    try:
        enc = tiktoken.get_encoding(encoding_name)
        return len(enc.encode(text))
    except Exception:
        # Fallback: rough approximation (for testing in restricted networks)
        # Real runs should use tiktoken properly
        return len(text) // 4  # ~4 chars per token approximation


def run_benchmark(dataset_name: str, records: int) -> dict:
    """
    Run benchmark for a single dataset and record count.

    Returns dict with token counts and compression ratios.
    """
    entity_name, generator = DATASETS[dataset_name]

    # Generate data (handle both old list format and new dict format)
    result = generator(records)
    if isinstance(result, dict) and "data" in result:
        data = result["data"]
    else:
        data = result

    # Format to strings (JSON minified for fair comparison)
    json_str = json.dumps(data)  # No indent = minified
    yaml_str = to_yaml(data)
    onto_str = to_onto(data, entity_name)
    toon_str = toon_encode(data) if TOON_AVAILABLE else ""

    # Count tokens
    json_tokens = count_tokens(json_str)
    yaml_tokens = count_tokens(yaml_str)
    onto_tokens = count_tokens(onto_str)
    toon_tokens = count_tokens(toon_str) if TOON_AVAILABLE else 0

    # Calculate reductions vs JSON baseline
    yaml_reduction = (1 - yaml_tokens / json_tokens) * 100
    onto_reduction = (1 - onto_tokens / json_tokens) * 100
    toon_reduction = (1 - toon_tokens / json_tokens) * 100 if TOON_AVAILABLE else 0
    onto_vs_toon = (1 - onto_tokens / toon_tokens) * 100 if TOON_AVAILABLE and toon_tokens > 0 else 0

    return {
        "dataset": dataset_name,
        "records": records,
        "timestamp": datetime.now().isoformat(),
        "formats": {
            "json": {"tokens": json_tokens, "chars": len(json_str)},
            "yaml": {"tokens": yaml_tokens, "chars": len(yaml_str)},
            "toon": {"tokens": toon_tokens, "chars": len(toon_str)},
            "onto": {"tokens": onto_tokens, "chars": len(onto_str)},
        },
        "reduction_vs_json": {
            "yaml": f"{yaml_reduction:.1f}%",
            "toon": f"{toon_reduction:.1f}%",
            "onto": f"{onto_reduction:.1f}%",
        },
        "onto_vs_toon": f"{onto_vs_toon:.1f}%",
        "strings": {
            "json": json_str,
            "yaml": yaml_str,
            "toon": toon_str,
            "onto": onto_str,
        }
    }


def save_results(result: dict, output_dir: Path):
    """Save benchmark results and format files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset = result["dataset"]
    records = result["records"]
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # Save format files
    base_name = f"{dataset}_{records}"
    (output_dir / f"{base_name}.json").write_text(result["strings"]["json"])
    (output_dir / f"{base_name}.yaml").write_text(result["strings"]["yaml"])
    (output_dir / f"{base_name}.onto").write_text(result["strings"]["onto"])
    if result["strings"]["toon"]:
        (output_dir / f"{base_name}.toon").write_text(result["strings"]["toon"])

    # Save results JSON (without the large strings)
    results_data = {k: v for k, v in result.items() if k != "strings"}
    results_file = output_dir / f"results_{dataset}_{timestamp}_{records}_records.json"
    results_file.write_text(json.dumps(results_data, indent=2))

    return results_file


def print_table(results: list[dict]):
    """Print markdown table of results."""
    print("\n## Token Count Benchmark Results\n")

    if TOON_AVAILABLE:
        print("| Dataset | Records | JSON | YAML | TOON | ONTO | TOON vs JSON | ONTO vs JSON | **ONTO vs TOON** |")
        print("|---------|---------|------|------|------|------|--------------|--------------|------------------|")

        for r in results:
            print(f"| {r['dataset']} | {r['records']} | "
                  f"{r['formats']['json']['tokens']:,} | "
                  f"{r['formats']['yaml']['tokens']:,} | "
                  f"{r['formats']['toon']['tokens']:,} | "
                  f"{r['formats']['onto']['tokens']:,} | "
                  f"{r['reduction_vs_json']['toon']} | "
                  f"{r['reduction_vs_json']['onto']} | "
                  f"**{r['onto_vs_toon']}** |")

        # Summary
        onto_reductions = [float(r['reduction_vs_json']['onto'].rstrip('%')) for r in results]
        toon_reductions = [float(r['reduction_vs_json']['toon'].rstrip('%')) for r in results]
        onto_vs_toon = [float(r['onto_vs_toon'].rstrip('%')) for r in results]

        print(f"\n**Averages:**")
        print(f"- TOON vs JSON: {sum(toon_reductions) / len(toon_reductions):.1f}%")
        print(f"- ONTO vs JSON: {sum(onto_reductions) / len(onto_reductions):.1f}%")
        print(f"- **ONTO vs TOON: {sum(onto_vs_toon) / len(onto_vs_toon):.1f}%**")
    else:
        print("| Dataset | Records | JSON | YAML | ONTO | YAML vs JSON | ONTO vs JSON |")
        print("|---------|---------|------|------|------|--------------|--------------|")

        for r in results:
            print(f"| {r['dataset']} | {r['records']} | "
                  f"{r['formats']['json']['tokens']:,} | "
                  f"{r['formats']['yaml']['tokens']:,} | "
                  f"{r['formats']['onto']['tokens']:,} | "
                  f"{r['reduction_vs_json']['yaml']} | "
                  f"{r['reduction_vs_json']['onto']} |")

        onto_reductions = [float(r['reduction_vs_json']['onto'].rstrip('%')) for r in results]
        print(f"\n**Average ONTO vs JSON: {sum(onto_reductions) / len(onto_reductions):.1f}%**")
        print("\n_Note: Install toon-py for TOON comparison: pip install toon-py_")


def main():
    parser = argparse.ArgumentParser(description="ONTO Token Benchmark")
    parser.add_argument(
        "--dataset",
        choices=list(DATASETS.keys()) + ["all"],
        default="all",
        help="Dataset to benchmark (default: all)"
    )
    parser.add_argument(
        "--records",
        type=str,
        default="100,500,1000",
        help="Comma-separated record counts (default: 100,500,1000)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "results",
        help="Output directory for results"
    )

    args = parser.parse_args()

    # Parse record counts
    record_counts = [int(x.strip()) for x in args.records.split(",")]

    # Determine datasets to run
    if args.dataset == "all":
        datasets = list(DATASETS.keys())
    else:
        datasets = [args.dataset]

    # Run benchmarks
    all_results = []
    for dataset in datasets:
        for records in record_counts:
            print(f"Running: {dataset} with {records} records...")
            result = run_benchmark(dataset, records)
            results_file = save_results(result, args.output_dir)
            print(f"  Saved: {results_file.name}")
            all_results.append(result)

    # Print summary table
    print_table(all_results)


if __name__ == "__main__":
    main()