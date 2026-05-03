"""
Run Benchmark — Batch process all AACR-Bench PRs through CodeReview Bot.

Usage:
    python run_benchmark.py                      # Process all 200 PRs
    python run_benchmark.py --limit 10           # Process first 10 PRs
    python run_benchmark.py --language Python     # Filter by language
    python run_benchmark.py --provider gemini     # Use Gemini instead of Ollama
"""
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from urllib import request, error
from datetime import datetime

# Resolve paths relative to this script
_BENCHMARK_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _BENCHMARK_DIR.parent

# Add benchmark to sys.path
sys.path.insert(0, str(_BENCHMARK_DIR))

from tqdm import tqdm
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


def save_comments_to_file(comments: list, output_file: str) -> None:
    """Save comments in evaluator-compatible tag format."""
    lines = []
    for comment in comments or []:
        if not isinstance(comment, dict):
            continue
        note = str(comment.get("note", "")).strip()
        if not note:
            continue

        path = str(comment.get("path", "")).strip().replace("\\", "/")
        side_raw = str(comment.get("side", "right")).strip()
        side = side_raw.lower() if side_raw else "right"
        from_line = comment.get("from_line")
        to_line = comment.get("to_line")

        lines.append("<notesplit>")
        lines.append(f"<path>{path}</path>")
        lines.append(f"<side>{side}</side>")
        if from_line is not None:
            lines.append(f"<from>{from_line}</from>")
        if to_line is not None:
            lines.append(f"<to>{to_line}</to>")
        lines.append(f"<note>{note}</note>")
        lines.append("</notesplit>")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def post_chat_review(api_base: str, pr_url: str, timeout: float) -> dict:
    """Call backend chat API and return parsed JSON."""
    url = f"{api_base.rstrip('/')}/chat"
    payload = json.dumps({"message": pr_url}).encode("utf-8")
    req = request.Request(
        url=url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def main():
    parser = argparse.ArgumentParser(description="Run CodeReview Bot on AACR-Bench dataset")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of PRs to process (0 = all)")
    parser.add_argument("--language", type=str, default="", help="Filter by project language (e.g. Python, Java)")
    parser.add_argument("--provider", type=str, default="", help="Deprecated in API mode (kept for compatibility)")
    parser.add_argument("--api-base", type=str, default="http://localhost:8000/api/v1", help="Backend API base URL")
    parser.add_argument("--timeout", type=float, default=180.0, help="Request timeout per PR in seconds")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests in seconds")
    parser.add_argument("--dataset", type=str, default="", help="Path to dataset file")
    parser.add_argument(
        "--run-name",
        type=str,
        default="",
        help="Output subfolder under comments (e.g. llm_v1, agent_v2). Default: timestamped run.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run PRs even if output files already exist.",
    )
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

    if args.provider:
        logger.warning("--provider is ignored in API mode; configure provider in backend settings/env.")
    print(f"🌐 API mode enabled: {args.api_base}")

    # Isolate results per run to avoid cross-version overwrite/skip.
    run_name = args.run_name.strip() or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_name = run_name.replace(" ", "_")
    comments_output_dir = COMMENTS_DIR / run_name
    comments_output_dir.mkdir(parents=True, exist_ok=True)
    print(f"🗂️  Run output: {comments_output_dir}")

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
        output_file = comments_output_dir / f"comments_{pr_id}.txt"

        # Skip if already processed
        if output_file.exists() and not args.force:
            logger.info(f"Skipping {pr_id} — already processed")
            skipped += 1
            continue

        try:
            # Run review via backend API
            result = post_chat_review(args.api_base, pr_url, args.timeout)
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

        except error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"❌ {pr_id}: HTTP {e.code} - {error_body}")
            errors += 1
            results_log.append({
                "pr_url": pr_url,
                "pr_id": pr_id,
                "num_comments": 0,
                "status": "error",
                "error": f"HTTP {e.code}: {error_body}",
            })
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
    print(f"Comments saved to: {comments_output_dir}")

    # Save run log
    log_file = COMMENTS_DIR.parent / f"benchmark_run_log_{run_name}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "run_name": run_name,
                "api_base": args.api_base,
                "dataset_path": dataset_path,
                "limit": args.limit,
                "language": args.language,
                "timeout": args.timeout,
                "delay": args.delay,
                "force": args.force,
                "comments_output_dir": str(comments_output_dir),
                "results": results_log,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Run log saved to: {log_file}")


if __name__ == "__main__":
    main()
