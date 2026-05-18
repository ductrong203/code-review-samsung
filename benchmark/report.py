"""
Report — Generate a formatted evaluation report from results.

Usage:
    python report.py                               # Generate report from default results
    python report.py --results path/to/results.json # Specify results file
"""
import json
import argparse
import sys
from pathlib import Path
from collections import defaultdict

# Resolve paths relative to this script
_BENCHMARK_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_BENCHMARK_DIR))

from config import RESULTS_DIR


def load_results(results_path: str) -> dict:
    """Load evaluation results JSON."""
    with open(results_path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_table(headers, rows, col_widths=None):
    """Print a formatted ASCII table."""
    if col_widths is None:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = len(str(h))
            for row in rows:
                max_w = max(max_w, len(str(row[i])) if i < len(row) else 0)
            col_widths.append(max_w + 2)

    # Header
    header_line = "│".join(str(h).center(w) for h, w in zip(headers, col_widths))
    separator = "┼".join("─" * w for w in col_widths)
    print(f"┌{'┬'.join('─' * w for w in col_widths)}┐")
    print(f"│{header_line}│")
    print(f"├{separator}┤")

    # Rows
    for row in rows:
        row_line = "│".join(str(v).center(w) for v, w in zip(row, col_widths))
        print(f"│{row_line}│")

    print(f"└{'┴'.join('─' * w for w in col_widths)}┘")


def generate_report(results: dict, report_path: Path | None = None):
    """Generate and print a comprehensive evaluation report."""
    details = results.get("details", [])

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║           CodeReview Bot — Evaluation Report            ║")
    print("║              AACR-Bench Benchmark Results               ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # ── Overall Metrics ──
    print("┌─────────────────────────────────────────────────────────┐")
    print("│                   Overall Metrics                       │")
    print("└─────────────────────────────────────────────────────────┘")
    print()

    metrics = [
        ["Metric", "Value"],
        ["Files Evaluated", f"{results['evaluated_files']}/{results['total_files']}"],
        ["Generated Comments", str(results["total_generated_comments"])],
        ["Reference Comments", str(results["total_reference_comments"])],
        ["", ""],
        ["Line Precision", f"{results['line_precision']:.2%}"],
        ["Semantic Precision", f"{results['semantic_precision']:.2%}"],
        ["Line Recall", f"{results['line_recall']:.2%}"],
        ["Semantic Recall", f"{results['semantic_recall']:.2%}"],
        ["Noise Rate", f"{results['noise_rate']:.2%}"],
    ]

    for row in metrics:
        if row[0] == "":
            print()
        else:
            print(f"  {row[0]:<30} {row[1]:>15}")

    print()

    # ── Breakdown by Language ──
    if details:
        print("┌─────────────────────────────────────────────────────────┐")
        print("│                Breakdown by Language                     │")
        print("└─────────────────────────────────────────────────────────┘")
        print()

        lang_stats = defaultdict(lambda: {
            "count": 0, "generated": 0, "reference": 0,
            "line_matches": 0, "semantic_matches": 0,
        })

        for item in details:
            # Try to get language from the result
            lang = "Unknown"
            if "filter_config" in item:
                langs = item.get("filter_config", {}).get("project_languages", [])
                if langs:
                    lang = langs[0]

            # Fallback: check pr_metadata in the item
            for key in ["project_main_language", "language"]:
                if key in item:
                    lang = item[key]
                    break

            stats = lang_stats[lang]
            stats["count"] += 1
            stats["generated"] += item.get("total_generated_nums", 0)
            stats["reference"] += item.get("positive_expected_nums", 0)
            stats["line_matches"] += item.get("positive_line_match_nums", 0)
            stats["semantic_matches"] += item.get("positive_match_nums", 0)

        headers = ["Language", "PRs", "Gen", "Ref", "LinePr", "SemPr", "LineRe", "SemRe"]
        rows = []
        for lang, stats in sorted(lang_stats.items()):
            gen = stats["generated"]
            ref = stats["reference"]
            lm = stats["line_matches"]
            sm = stats["semantic_matches"]
            rows.append([
                lang,
                stats["count"],
                gen,
                ref,
                f"{lm/gen:.1%}" if gen > 0 else "N/A",
                f"{sm/gen:.1%}" if gen > 0 else "N/A",
                f"{lm/ref:.1%}" if ref > 0 else "N/A",
                f"{sm/ref:.1%}" if ref > 0 else "N/A",
            ])

        print_table(headers, rows)
        print()

    # ── Per-PR Details (top 10) ──
    if details:
        print("┌─────────────────────────────────────────────────────────┐")
        print("│              Top 10 PR Results (by comments)            │")
        print("└─────────────────────────────────────────────────────────┘")
        print()

        sorted_details = sorted(details, key=lambda x: x.get("total_generated_nums", 0), reverse=True)
        top_10 = sorted_details[:10]

        headers = ["PR", "Gen", "Ref", "LineMat", "SemMat", "Precision"]
        rows = []
        for item in top_10:
            eval_id = item.get("evaluation_id", "?")
            gen = item.get("total_generated_nums", 0)
            ref = item.get("positive_expected_nums", 0)
            lm = item.get("positive_line_match_nums", 0)
            sm = item.get("positive_match_nums", 0)
            prec = f"{item.get('positive_match_rate', 0):.1%}"
            rows.append([eval_id[:25], gen, ref, lm, sm, prec])

        print_table(headers, rows)

    print()
    print("═" * 60)
    print(f"  Report generated from: {results['evaluated_files']} evaluated PRs")
    print("═" * 60)

    # Save markdown report
    report_path = report_path or (RESULTS_DIR / "evaluation_report.md")
    save_markdown_report(results, report_path)
    print(f"\n📄 Markdown report saved to: {report_path}")


def save_markdown_report(results: dict, output_path: Path):
    """Save evaluation report as Markdown."""
    lines = [
        "# CodeReview Bot — AACR-Bench Evaluation Report\n",
        f"## Overall Metrics\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Files Evaluated | {results['evaluated_files']}/{results['total_files']} |",
        f"| Generated Comments | {results['total_generated_comments']} |",
        f"| Reference Comments | {results['total_reference_comments']} |",
        f"| **Line Precision** | **{results['line_precision']:.2%}** |",
        f"| **Semantic Precision** | **{results['semantic_precision']:.2%}** |",
        f"| **Line Recall** | **{results['line_recall']:.2%}** |",
        f"| **Semantic Recall** | **{results['semantic_recall']:.2%}** |",
        f"| **Noise Rate** | **{results['noise_rate']:.2%}** |",
        "",
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Generate evaluation report")
    parser.add_argument(
        "--results", type=str,
        default=str(RESULTS_DIR / "evaluation_results.json"),
        help="Path to evaluation results JSON"
    )
    parser.add_argument(
        "--report",
        type=str,
        default="",
        help="Markdown report output path. Default: evaluation_report.md next to --results",
    )
    args = parser.parse_args()

    if not Path(args.results).exists():
        print(f"❌ Results file not found: {args.results}")
        print(f"   Run evaluation first: python evaluate.py")
        sys.exit(1)

    results = load_results(args.results)
    report_path = Path(args.report) if args.report else Path(args.results).with_name("evaluation_report.md")
    generate_report(results, report_path=report_path)


if __name__ == "__main__":
    main()
