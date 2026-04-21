# ONTO — Object Notation for Token Optimization

A columnar, human-readable data format that reduces LLM token consumption by 46-51% compared to JSON.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![arXiv](https://img.shields.io/badge/arXiv-2604.17512-b31b1b.svg)](https://arxiv.org/abs/2604.17512)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.19650416-blue.svg)](https://doi.org/10.5281/zenodo.19650416)

## Why ONTO?

Every time you send structured data to an LLM, JSON repeats field names for every record. For 1000 sensor readings, you're paying for `"temperature":` a thousand times. That's not data — that's overhead.

ONTO declares field names once and aligns values in columns. Same data, half the tokens.

## Results

**Token Reduction vs JSON** (tiktoken cl100k_base, 1000 records):

| Dataset | JSON Tokens | ONTO Tokens | Reduction |
|---------|-------------|-------------|-----------|
| IoT Telemetry (nested) | 79,774 | 42,813 | **46.3%** |
| System Metrics (flat) | 78,710 | 38,752 | **50.8%** |
| Log Entries (mixed) | 65,482 | 34,513 | **47.3%** |

**Latency Improvement** (Qwen 2.5 7B, 1000 records, 20 runs):

| Dataset | TTFT Reduction | Total Time Reduction |
|---------|----------------|----------------------|
| IoT Telemetry | 7.4% | 10.5% |
| System Metrics | 5.5% | 9.3% |

**Comprehension Parity**: No degradation in LLM accuracy on lookup, counting, extraction, and aggregation tasks when using ONTO with a format explanation prompt (tested on GPT-5.4-mini, 20 runs).

## Quick Example

**JSON (79,774 tokens for 1000 records):**
```json
[
  {"device_id": "sensor-001", "temperature": 23.5, "humidity": 45.2, "location": {"lat": 37.77, "lon": -122.41}},
  {"device_id": "sensor-002", "temperature": 24.1, "humidity": 43.8, "location": {"lat": 37.78, "lon": -122.42}},
  {"device_id": "sensor-003", "temperature": 22.9, "humidity": 46.1, "location": {"lat": 37.79, "lon": -122.43}}
]
```

**ONTO (42,813 tokens for 1000 records):**
```
Telemetry[3]:
    device_id: sensor-001|sensor-002|sensor-003
    temperature: 23.5|24.1|22.9
    humidity: 45.2|43.8|46.1
    location:
        lat: 37.77|37.78|37.79
        lon: -122.41|-122.42|-122.43
```

Same data. 46% fewer tokens.

## Installation

```bash
git clone https://github.com/harsh-aranga/onto.git
cd onto
pip install -e .
```

## Usage

```python
import onto

# Parse ONTO string to Python objects
data = onto.loads("""
Sensors[2]:
    device_id: sensor-001|sensor-002
    temperature: 23.5|24.1
""")
# Returns: [{"device_id": "sensor-001", "temperature": 23.5}, {"device_id": "sensor-002", "temperature": 24.1}]

# Serialize Python objects to ONTO
onto_string = onto.dumps(data, entity_name="Sensors")
```

## Format Specification

### Core Syntax

| Element | Syntax | Example |
|---------|--------|---------|
| Record separator | `\|` | `value1\|value2\|value3` |
| Array elements | `^` | `tag1^tag2\|tag3^tag4` |
| Nesting | 4-space indent | See example above |
| Force string | Backticks | `` `123` `` → "123" |
| Null | Empty value | `\|\|` → null |
| Empty string | Backticked empty | ``` `` ``` → "" |

### Type Inference

- Integers: `42` → 42
- Floats: `3.14` → 3.14
- Booleans: `true` / `false` → True / False
- Strings: Everything else, or backtick-wrapped

### Identifiers

- May contain: letters, digits, underscores, hyphens, dots
- Must start with letter
- Examples: `device_id`, `cpu.usage`, `network-in`

## Datasets Tested

| Dataset | Structure | Fields | Use Case |
|---------|-----------|--------|----------|
| IoT Telemetry | Nested | device_id, temperature, humidity, location.lat, location.lon | Sensor data ingestion |
| System Metrics | Flat | host, cpu_percent, memory_percent, disk_io, network | Infrastructure monitoring |
| Log Entries | Mixed | timestamp, level, service, message, metadata | Log analysis |

All benchmarks use synthetic data with realistic distributions. See `benchmarks/generators.py` for details.

## When to Use ONTO

### ✅ Use ONTO for:
- LLM input optimization on operational data
- Reducing context window consumption
- Batch processing of structured records
- Anomaly detection, summarization, root cause analysis

### ❌ Don't use ONTO for:
- API request/response formats
- Database storage
- Configuration files
- Small datasets (< 50 records)
- Streaming data (v1 limitation)

ONTO is an **input optimization layer**, not a replacement for JSON in your infrastructure.

## Benchmarks

Run benchmarks locally:

```bash
# Token counting (deterministic)
python benchmarks/benchmark_tokens.py --records 1000

# Speed (requires Ollama + Qwen)
python benchmarks/benchmark_speed.py --model qwen2.5:7b-instruct-q4_K_M --records 1000 --runs 20

# Accuracy (requires OpenAI API key)
python benchmarks/benchmark_accuracy.py --provider openai --model gpt-5.4-mini --records 50 --runs 20
```

Full benchmark results available in `benchmarks/results/`.

## Future Work

- **Tool Definition Serialization**: Compress function schemas for tool-use prompts
- **Compact Mode**: Dot notation for deeply nested structures
- **Streaming Parser**: Process ONTO data incrementally
- **Multi-language Support**: JavaScript/TypeScript implementation

## Citation

If you use ONTO in your research, please cite the paper:

```bibtex
@article{deekeswar2026onto-paper,
  author       = {Deekeswar, Harshavardhanan},
  title        = {{ONTO: A Token-Efficient Columnar Notation for
                   LLM Input Optimization}},
  journal      = {arXiv preprint arXiv:2604.17512},
  year         = {2026},
  url          = {https://arxiv.org/abs/2604.17512}
}
```

If you use the software implementation, please cite the release:

```bibtex
@software{deekeswar2026onto-software,
  author       = {Deekeswar, Harshavardhanan},
  title        = {{ONTO: A Token-Efficient Columnar Notation for
                   LLM Input Optimization}},
  year         = 2026,
  publisher    = {Zenodo},
  version      = {v1.0.2},
  doi          = {10.5281/zenodo.19650416},
  url          = {https://doi.org/10.5281/zenodo.19650416}
}
```

The accompanying research paper is forthcoming on arXiv. BibTeX will be updated upon publication.

## License

MIT License. See [LICENSE](LICENSE) for details.

## Author

**Harshavardhanan Deekeswar**
[ORCID: 0009-0000-0319-083X](https://orcid.org/0009-0000-0319-083X) · [GitHub](https://github.com/harsh-aranga) · [Email](mailto:harsh@pragmaticbyharsh.com)

---

*ONTO is a research prototype demonstrating token-efficient serialization for LLM workflows. For production use, evaluate against your specific data patterns and model requirements.*