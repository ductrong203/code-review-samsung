"""
Aggregate multiple evaluation_results.json files into one comparable summary.

Use this when graph v3 is evaluated repo-by-repo:
    python benchmark/aggregate_evaluations.py \
      --inputs benchmark/output/results/graph_v3/repos/*/evaluation_results.json \
      --output benchmark/output/results/graph_v3/evaluation_results.json
"""
import argparse
import glob
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_div(a: int, b: int) -> float:
    return round(a / b, 4) if b > 0 else 0.0


def aggregate(paths: list[Path]) -> dict:
    details = []
    total_files = 0
    total_generated = 0
    total_reference = 0
    total_line_matches = 0
    total_semantic_matches = 0

    for path in paths:
        result = load_json(path)
        total_files += result.get("total_files", 0)
        total_generated += result.get("total_generated_comments", 0)
        total_reference += result.get("total_reference_comments", 0)
        total_line_matches += result.get("total_line_matches", 0)
        total_semantic_matches += result.get("total_semantic_matches", 0)
        details.extend(result.get("details", []) or [])

    return {
        "total_files": total_files,
        "evaluated_files": len(details),
        "total_generated_comments": total_generated,
        "total_reference_comments": total_reference,
        "total_line_matches": total_line_matches,
        "total_semantic_matches": total_semantic_matches,
        "line_precision": safe_div(total_line_matches, total_generated),
        "semantic_precision": safe_div(total_semantic_matches, total_generated),
        "line_recall": safe_div(total_line_matches, total_reference),
        "semantic_recall": safe_div(total_semantic_matches, total_reference),
        "noise_rate": safe_div(total_generated - total_semantic_matches, total_generated),
        "source_result_files": [str(path) for path in paths],
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate benchmark evaluation JSON files")
    parser.add_argument("--inputs", nargs="+", required=True, help="Files or glob patterns")
    parser.add_argument("--output", required=True, help="Output evaluation_results.json path")
    args = parser.parse_args()

    paths = []
    for pattern in args.inputs:
        matches = [Path(p) for p in glob.glob(pattern)]
        if matches:
            paths.extend(matches)
        else:
            paths.append(Path(pattern))
    paths = sorted({p.resolve() for p in paths if p.exists()})
    if not paths:
        raise SystemExit("No input evaluation result files found")

    summary = aggregate(paths)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Aggregated {len(paths)} result files")
    print(f"Files evaluated: {summary['evaluated_files']}/{summary['total_files']}")
    print(f"Semantic precision: {summary['semantic_precision']:.2%}")
    print(f"Semantic recall: {summary['semantic_recall']:.2%}")
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
