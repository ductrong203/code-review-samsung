"""
Run Benchmark — Batch process all AACR-Bench PRs through CodeReview Bot.

Usage:
    python run_benchmark.py                      # Process all 200 PRs
    python run_benchmark.py --limit 10           # Process first 10 PRs
    python run_benchmark.py --language Python     # Filter by language
    python run_benchmark.py --provider gemini     # Use Gemini instead of Ollama
"""
import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path

# Resolve paths relative to this script
_BENCHMARK_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _BENCHMARK_DIR.parent

# Add backend and benchmark to sys.path
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))
sys.path.insert(0, str(_BENCHMARK_DIR))

from tqdm import tqdm
from app.core.config import Settings
from app.services.review_service import ReviewService, save_comments_to_file
from config import DATASET_PATH, COMMENTS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_dataset(dataset_path: str) -> list:
    """Load AACR-Bench positive samples dataset."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_pr_id(pr_url: str) -> str:
    """Extract repo_name_pr_number from PR URL for filename."""
    parts = pr_url.rstrip("/").split("/")
    if len(parts) >= 2:
        repo = parts[-3]
        pr_number = parts[-1]
        return f"{repo}_{pr_number}"
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Run CodeReview Bot on AACR-Bench dataset")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of PRs to process (0 = all)")
    parser.add_argument("--language", type=str, default="", help="Filter by project language (e.g. Python, Java)")
    parser.add_argument("--provider", type=str, default="", help="Override LLM provider (ollama/gemini)")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests in seconds")
    parser.add_argument("--dataset", type=str, default="", help="Path to dataset file")
    args = parser.parse_args()

    # Load dataset
    dataset_path = args.dataset or str(DATASET_PATH)
    if not Path(dataset_path).exists():
        print(f"❌ Dataset not found: {dataset_path}")
        print(f"   Expected at: {DATASET_PATH}")
        print(f"   Set AACR_BENCH_PATH env variable or use --dataset flag")
        sys.exit(1)

    dataset = load_dataset(dataset_path)
    print(f"📊 Loaded {len(dataset)} PRs from dataset")

    # Filter by language
    if args.language:
        dataset = [
            item for item in dataset
            if item.get("project_main_language", "").lower() == args.language.lower()
        ]
        print(f"🔍 Filtered to {len(dataset)} PRs for language: {args.language}")

    # Limit
    if args.limit > 0:
        dataset = dataset[:args.limit]
        print(f"📋 Processing first {args.limit} PRs")

    # Override provider if specified
    env_overrides = {}
    if args.provider:
        env_overrides["LLM_PROVIDER"] = args.provider

    # Initialize review service
    settings = Settings(**env_overrides) if env_overrides else Settings()
    print(f"🤖 Using LLM provider: {settings.LLM_PROVIDER}")
    print(f"   Model: {settings.OLLAMA_MODEL if settings.LLM_PROVIDER == 'ollama' else settings.GEMINI_MODEL}")

    service = ReviewService(settings)

    # Process each PR
    results_log = []
    skipped = 0
    errors = 0

    for item in tqdm(dataset, desc="Reviewing PRs"):
        pr_url = item.get("githubPrUrl", "")
        if not pr_url:
            skipped += 1
            continue

        pr_id = get_pr_id(pr_url)
        output_file = COMMENTS_DIR / f"comments_{pr_id}.txt"

        # Skip if already processed
        if output_file.exists():
            logger.info(f"Skipping {pr_id} — already processed")
            skipped += 1
            continue

        try:
            # Run review
            result = service.review_pr(pr_url)
            comments = result.get("comments", [])

            # Save comments in AACR-Bench format
            save_comments_to_file(comments, str(output_file))

            results_log.append({
                "pr_url": pr_url,
                "pr_id": pr_id,
                "num_comments": len(comments),
                "status": "success",
            })

            logger.info(f"✅ {pr_id}: {len(comments)} comments")

        except Exception as e:
            logger.error(f"❌ {pr_id}: {e}")
            errors += 1
            results_log.append({
                "pr_url": pr_url,
                "pr_id": pr_id,
                "num_comments": 0,
                "status": "error",
                "error": str(e),
            })

        # Delay to avoid rate limiting
        time.sleep(args.delay)

    # Summary
    print(f"\n{'='*60}")
    print(f"Benchmark Run Complete")
    print(f"{'='*60}")
    print(f"Total PRs: {len(dataset)}")
    print(f"Processed: {len(results_log) - errors}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")
    print(f"Comments saved to: {COMMENTS_DIR}")

    # Save run log
    log_file = COMMENTS_DIR.parent / "benchmark_run_log.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(results_log, f, ensure_ascii=False, indent=2)
    print(f"Run log saved to: {log_file}")


if __name__ == "__main__":
    main()
