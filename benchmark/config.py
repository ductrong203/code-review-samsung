"""
Benchmark Configuration — Paths and settings for AACR-Bench evaluation.
"""
import os
from pathlib import Path

# Paths
BENCHMARK_DIR = Path(__file__).parent
PROJECT_ROOT = BENCHMARK_DIR.parent
AACR_BENCH_PATH = Path(os.getenv("AACR_BENCH_PATH", str(PROJECT_ROOT.parent / "aacr-bench")))

# Use local dataset in benchmark folder
DATASET_PATH = BENCHMARK_DIR / "dataset" / "positive_samples.json"
OUTPUT_DIR = BENCHMARK_DIR / "output"
COMMENTS_DIR = OUTPUT_DIR / "comments" / "agent"
RESULTS_DIR = OUTPUT_DIR / "results" / "agent"

# Ensure output directories exist
COMMENTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
