"""
Evaluate — Run AACR-Bench evaluator on generated comments.

Uses the evaluator_runner from the aacr-bench project directly.

Usage:
    python evaluate.py                           # Evaluate all
    python evaluate.py --language Python          # Filter by language
    python evaluate.py --no-semantic              # Skip semantic matching (faster)
    python evaluate.py --matcher embedding        # Use embedding matcher
"""
import os
import sys
import json
import asyncio
import argparse
import logging
from pathlib import Path

# Resolve paths relative to this script
_BENCHMARK_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_BENCHMARK_DIR))

from tqdm import tqdm
from config import (
    AACR_BENCH_PATH,
    DATASET_PATH,
    COMMENTS_DIR,
    RESULTS_DIR,
)

# evaluator_runner is now local in benchmark/evaluator_runner folder
# No need to add AACR_BENCH_PATH to sys.path anymore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_dataset(path: str) -> list:
    """Load AACR-Bench positive samples."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_reference_by_url(pr_url: str, dataset: list) -> dict:
    """Find reference data by PR URL."""
    for item in dataset:
        if item.get("githubPrUrl") == pr_url:
            return item
    return None


def infer_pr_url_from_filename(filename: str, dataset: list) -> str:
    """
    Infer PR URL from comment filename.
    Expected format: comments_{repo}_{pr_number}.txt
    """
    stem = Path(filename).stem
    if stem.startswith("comments_"):
        parts = stem[9:].rsplit("_", 1)
        if len(parts) == 2:
            repo_name, pr_number = parts
            for item in dataset:
                url = item.get("githubPrUrl", "")
                if repo_name.lower() in url.lower() and f"/pull/{pr_number}" in url:
                    return url

    # Fallback: fuzzy match
    for item in dataset:
        pr_url = item.get("githubPrUrl", "")
        url_parts = pr_url.split("/")
        if len(url_parts) >= 7:
            repo_name = url_parts[-3]
            pr_number = url_parts[-1]
            if repo_name.lower() in stem.lower() and pr_number in stem:
                return pr_url
    return None


async def run_evaluation(args):
    """Run the full evaluation pipeline."""
    # Import evaluator after adding to path
    from evaluator_runner import (
        get_evaluator_ans_from_json,
        load_generated_comments_from_file,
        EvaluatorConfig,
        SemanticMatcherType,
        FilterConfig,
    )

    # Load dataset
    dataset_path = args.dataset or str(DATASET_PATH)
    if not Path(dataset_path).exists():
        print(f"❌ Dataset not found: {dataset_path}")
        sys.exit(1)

    dataset = load_dataset(dataset_path)
    print(f"📊 Loaded {len(dataset)} reference PRs")

    # Find all generated comment files
    comments_dir = Path(args.comments_dir or str(COMMENTS_DIR))
    if not comments_dir.exists():
        print(f"❌ Comments directory not found: {comments_dir}")
        print(f"   Run benchmark first: python run_benchmark.py")
        sys.exit(1)

    comment_files = list(comments_dir.glob("*.txt"))
    if not comment_files:
        print(f"❌ No comment files found in: {comments_dir}")
        sys.exit(1)

    print(f"📁 Found {len(comment_files)} comment files to evaluate")

    # Build evaluator config
    matcher_type = (
        SemanticMatcherType.EMBEDDING
        if args.matcher == "embedding"
        else SemanticMatcherType.LLM
    )

    filter_config = None
    if args.language:
        filter_config = FilterConfig(
            project_languages=[args.language],
        )

    config = EvaluatorConfig(
        line_distance_threshold=args.line_threshold,
        semantic_matcher_type=matcher_type,
        enable_semantic_match=not args.no_semantic,
        filter_config=filter_config,
    )

    print(f"⚙️  Config: line_threshold={args.line_threshold}, "
          f"semantic={'enabled' if not args.no_semantic else 'disabled'}, "
          f"matcher={args.matcher}")

    # Evaluate each file
    results = []
    total_generated = 0
    total_reference = 0
    total_line_matches = 0
    total_semantic_matches = 0

    for file_path in tqdm(comment_files, desc="Evaluating"):
        # Infer PR URL
        pr_url = infer_pr_url_from_filename(file_path.name, dataset)
        if not pr_url:
            logger.warning(f"Skipped {file_path.name}: cannot match PR URL")
            continue

        # Find reference comments
        ref_item = find_reference_by_url(pr_url, dataset)
        if not ref_item:
            logger.warning(f"Skipped {file_path.name}: no reference data")
            continue

        reference_comments = ref_item.get("comments", [])

        # Load generated comments
        try:
            generated_comments = load_generated_comments_from_file(str(file_path))
        except Exception as e:
            logger.warning(f"Skipped {file_path.name}: parse error ({e})")
            continue

        if not generated_comments:
            logger.warning(f"Skipped {file_path.name}: no valid comments")
            continue

        # Run evaluation
        pr_metadata = {
            "category": ref_item.get("category"),
            "project_main_language": ref_item.get("project_main_language"),
        }

        result = await get_evaluator_ans_from_json(
            github_pr_url=pr_url,
            generated_comments=generated_comments,
            good_comments=reference_comments,
            config=config,
            pr_metadata=pr_metadata,
        )

        if result.get("skipped"):
            logger.info(f"Skipped {file_path.name}: {result.get('skip_reason')}")
            continue

        results.append(result)

        # Accumulate stats
        total_generated += result.get("total_generated_nums", 0)
        total_reference += result.get("positive_expected_nums", 0)
        total_line_matches += result.get("positive_line_match_nums", 0)
        total_semantic_matches += result.get("positive_match_nums", 0)

    # Calculate overall metrics
    def safe_div(a, b):
        return round(a / b, 4) if b > 0 else 0.0

    summary = {
        "total_files": len(comment_files),
        "evaluated_files": len(results),
        "total_generated_comments": total_generated,
        "total_reference_comments": total_reference,
        "total_line_matches": total_line_matches,
        "total_semantic_matches": total_semantic_matches,
        # Precision metrics
        "line_precision": safe_div(total_line_matches, total_generated),
        "semantic_precision": safe_div(total_semantic_matches, total_generated),
        # Recall metrics
        "line_recall": safe_div(total_line_matches, total_reference),
        "semantic_recall": safe_div(total_semantic_matches, total_reference),
        # Noise rate
        "noise_rate": safe_div(
            total_generated - total_semantic_matches, total_generated
        ),
        # Per-PR details
        "details": results,
    }

    # Save results
    output_dir = Path(args.output_dir or str(RESULTS_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / args.output_file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"📈 Evaluation Results")
    print(f"{'='*60}")
    print(f"Files Evaluated:           {summary['evaluated_files']}/{summary['total_files']}")
    print(f"Total Generated Comments:  {summary['total_generated_comments']}")
    print(f"Total Reference Comments:  {summary['total_reference_comments']}")
    print(f"")
    print(f"--- Precision (of generated) ---")
    print(f"  Line Precision:          {summary['line_precision']:.2%}")
    print(f"  Semantic Precision:      {summary['semantic_precision']:.2%}")
    print(f"")
    print(f"--- Recall (of reference) ---")
    print(f"  Line Recall:             {summary['line_recall']:.2%}")
    print(f"  Semantic Recall:         {summary['semantic_recall']:.2%}")
    print(f"")
    print(f"--- Quality ---")
    print(f"  Noise Rate:              {summary['noise_rate']:.2%}")
    print(f"")
    print(f"📁 Results saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate CodeReview Bot against AACR-Bench")
    parser.add_argument("--dataset", type=str, default="", help="Path to positive_samples.json")
    parser.add_argument("--comments-dir", type=str, default="", help="Path to generated comments dir")
    parser.add_argument("--language", type=str, default="", help="Filter by language")
    parser.add_argument("--line-threshold", type=int, default=10, help="Line distance threshold (default: 10 for LLM accuracy)")
    parser.add_argument("--matcher", type=str, default="llm", choices=["llm", "embedding"], help="Semantic matcher")
    parser.add_argument("--no-semantic", action="store_true", help="Disable semantic matching")
    parser.add_argument("--output-dir", type=str, default="", help="Directory for evaluation_results.json")
    parser.add_argument("--output-file", type=str, default="evaluation_results.json", help="Evaluation JSON filename")
    args = parser.parse_args()

    asyncio.run(run_evaluation(args))


if __name__ == "__main__":
    main()
