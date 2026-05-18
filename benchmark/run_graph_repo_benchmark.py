"""
Run graph-context benchmark for one repository at a time.

This is the v3 benchmark path:
1. Use an already registered repo/main graph from the local extension.
2. Review only dataset PRs from that repo through extension /api/review.
3. Append comments into one run directory so all repos can be evaluated later.

Usage:
    python benchmark/run_graph_repo_benchmark.py --repo google-gemini/gemini-cli --run-name graph_v3
    python benchmark/run_graph_repo_benchmark.py --repo google-gemini/gemini-cli --run-name graph_v3 --limit 2
"""
import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib import error, request

_BENCHMARK_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_BENCHMARK_DIR))

from config import COMMENTS_DIR, DATASET_PATH
from run_benchmark import get_pr_id, save_comments_to_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_dataset(dataset_path: str) -> list:
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_repo(value: str) -> tuple[str, str]:
    parts = value.strip().strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("--repo must use owner/name format, e.g. google-gemini/gemini-cli")
    return parts[0], parts[1]


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    parts = pr_url.rstrip("/").split("/")
    if len(parts) < 7 or parts[-2] != "pull":
        raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
    return parts[-4], parts[-3], int(parts[-1])


def api_json(
    method: str,
    url: str,
    payload: dict | None = None,
    timeout: float = 300.0,
) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def filter_dataset(dataset: list, owner: str, repo: str, language: str, limit: int) -> list:
    selected = []
    for item in dataset:
        pr_url = item.get("githubPrUrl", "")
        try:
            item_owner, item_repo, _ = parse_pr_url(pr_url)
        except ValueError:
            continue
        if item_owner.lower() != owner.lower() or item_repo.lower() != repo.lower():
            continue
        if language and item.get("project_main_language", "").lower() != language.lower():
            continue
        selected.append(item)
    return selected[:limit] if limit > 0 else selected


def graph_status(extension_base: str, owner: str, repo: str, timeout: float) -> dict:
    url = f"{extension_base.rstrip('/')}/graph-status/{owner}/{repo}"
    try:
        return api_json("GET", url, timeout=timeout)
    except error.HTTPError as exc:
        if exc.code == 404:
            return {"registered": False, "main_graph_ready": False}
        raise


def review_with_graph(
    extension_base: str,
    backend_url: str,
    pr_url: str,
    timeout: float,
) -> dict:
    payload = {"pr_url": pr_url}
    if backend_url:
        payload["server_url"] = backend_url.rstrip("/")
    return api_json(
        "POST",
        f"{extension_base.rstrip('/')}/review",
        payload=payload,
        timeout=timeout,
    )


def graph_summary(graph_context: dict) -> dict:
    graph_context = graph_context or {}
    return {
        "changed_functions": len(graph_context.get("changed_functions", []) or []),
        "affected_flows": len(graph_context.get("affected_flows", []) or []),
        "test_gaps": len(graph_context.get("test_gaps", []) or []),
        "review_priorities": len(graph_context.get("review_priorities", []) or []),
        "related_context": len(graph_context.get("related_context", []) or []),
        "overall_risk": graph_context.get("overall_risk", 0.0),
        "error": graph_context.get("_error"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run graph-context benchmark for one repo")
    parser.add_argument("--repo", required=True, help="GitHub repo in owner/name format")
    parser.add_argument("--dataset", default="", help="Path to positive_samples.json")
    parser.add_argument("--run-name", default="graph_v3", help="Shared output folder under comments/")
    parser.add_argument("--extension-base", default="http://localhost:8100/api", help="Extension API base URL")
    parser.add_argument("--backend-url", default="", help="Optional backend URL override for extension review")
    parser.add_argument("--language", default="", help="Optional language filter")
    parser.add_argument("--limit", type=int, default=0, help="Limit PRs for this repo")
    parser.add_argument("--timeout", type=float, default=900.0, help="HTTP timeout for graph/review calls")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between PR reviews")
    parser.add_argument("--force", action="store_true", help="Re-run PRs with existing comment files")
    parser.add_argument(
        "--skip-graph-status-check",
        action="store_true",
        help="Skip checking that the repo is registered and main graph is ready",
    )
    args = parser.parse_args()

    owner, repo = parse_repo(args.repo)
    dataset_path = args.dataset or str(DATASET_PATH)
    dataset = load_dataset(dataset_path)
    selected = filter_dataset(dataset, owner, repo, args.language, args.limit)
    if not selected:
        print(f"No dataset PRs found for {owner}/{repo}")
        return

    run_name = args.run_name.strip().replace(" ", "_") or "graph_v3"
    comments_output_dir = COMMENTS_DIR.parent / run_name
    comments_output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = COMMENTS_DIR.parent.parent / "logs" / run_name
    logs_dir.mkdir(parents=True, exist_ok=True)

    print(f"Repo: {owner}/{repo}")
    print(f"PRs selected: {len(selected)}")
    print(f"Comments output: {comments_output_dir}")

    run_log = {
        "run_name": run_name,
        "repo": f"{owner}/{repo}",
        "dataset_path": dataset_path,
        "extension_base": args.extension_base,
        "backend_url": args.backend_url,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "comments_output_dir": str(comments_output_dir),
        "results": [],
    }

    if not args.skip_graph_status_check:
        try:
            status = graph_status(args.extension_base, owner, repo, args.timeout)
            run_log["initial_graph_status"] = status
            if not status.get("registered"):
                raise RuntimeError(
                    f"{owner}/{repo} is not registered in the local extension. "
                    "Register it and build the graph from the UI first."
                )
            if not status.get("main_graph_ready"):
                raise RuntimeError(
                    f"Main graph is not ready for {owner}/{repo}. "
                    "Build the repo graph from the UI first."
                )
            logger.info(
                "Using local graph for %s/%s at %s",
                owner,
                repo,
                status.get("local_path", ""),
            )
        except Exception as exc:
            run_log["setup_error"] = str(exc)
            log_file = logs_dir / f"repo_{owner}_{repo}.json"
            log_file.write_text(json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8")
            raise

    errors = 0
    skipped = 0
    for item in selected:
        pr_url = item.get("githubPrUrl", "")
        pr_id = get_pr_id(pr_url)
        output_file = comments_output_dir / f"comments_{pr_id}.txt"
        if output_file.exists() and not args.force:
            skipped += 1
            logger.info("Skipping %s - already exists", pr_id)
            run_log["results"].append({
                "pr_url": pr_url,
                "pr_id": pr_id,
                "status": "skipped_existing",
                "output_file": str(output_file),
            })
            continue

        started = time.time()
        try:
            response = review_with_graph(
                args.extension_base,
                args.backend_url,
                pr_url,
                args.timeout,
            )
            review = response.get("review", {}) or {}
            comments = review.get("comments", []) or []
            save_comments_to_file(comments, str(output_file))
            graph_info = graph_summary(response.get("graph_context", {}) or {})
            elapsed = round(time.time() - started, 2)
            run_log["results"].append({
                "pr_url": pr_url,
                "pr_id": pr_id,
                "status": "success",
                "num_comments": len(comments),
                "elapsed_seconds": elapsed,
                "graph": graph_info,
                "output_file": str(output_file),
            })
            logger.info("%s: %s comments, graph=%s", pr_id, len(comments), graph_info)
        except error.HTTPError as exc:
            errors += 1
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("%s: HTTP %s - %s", pr_id, exc.code, body[:500])
            run_log["results"].append({
                "pr_url": pr_url,
                "pr_id": pr_id,
                "status": "error",
                "error": f"HTTP {exc.code}: {body}",
            })
        except Exception as exc:
            errors += 1
            logger.error("%s: %s", pr_id, exc)
            run_log["results"].append({
                "pr_url": pr_url,
                "pr_id": pr_id,
                "status": "error",
                "error": str(exc),
            })

        log_file = logs_dir / f"repo_{owner}_{repo}.json"
        log_file.write_text(json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(args.delay)

    run_log["finished_at"] = datetime.now().isoformat(timespec="seconds")
    run_log["summary"] = {
        "selected": len(selected),
        "success": len([r for r in run_log["results"] if r.get("status") == "success"]),
        "skipped": skipped,
        "errors": errors,
    }
    log_file = logs_dir / f"repo_{owner}_{repo}.json"
    log_file.write_text(json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nGraph repo benchmark complete")
    print(json.dumps(run_log["summary"], indent=2))
    print(f"Repo log: {log_file}")


if __name__ == "__main__":
    main()
