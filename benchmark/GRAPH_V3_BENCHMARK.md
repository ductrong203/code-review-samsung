# Graph Context Benchmark V3

This guide describes how to evaluate the current graph-context review pipeline
repo by repo, then compare the final metrics with v1/v2.

## Why Repo By Repo

Version 3 depends on a repo-level main graph. Building graphs for the full
AACR-Bench dataset can be expensive, so the intended workflow is:

1. Pick one repository from the dataset.
2. Register that repo and build its graph in the extension UI.
3. Run benchmark PRs for that repo through graph-powered review.
4. Repeat for other repos.
5. Evaluate all generated comments together with the same metrics as v1/v2.

## Prerequisites

Start backend and extension first.

```powershell
docker compose up -d --build backend extension
```

Default URLs:

```text
Backend:   http://localhost:8000
Extension: http://localhost:8100
```

The extension API is used because it builds/extracts graph context and forwards
the review request to the backend.

Register the repo and build the main graph in the extension UI before running
the benchmark script. The script intentionally does not register repos or build
main graphs; it only uses the graph already stored by the local extension for
the `owner/repo` name you pass.

## Run One Repo

Run graph-context benchmark for one repository:

```powershell
python benchmark\run_graph_repo_benchmark.py `
  --repo google-gemini/gemini-cli `
  --run-name graph_v3 `
  --extension-base http://localhost:8100/api `
  --backend-url http://localhost:8000
```

Quick smoke test with only two PRs:

```powershell
python benchmark\run_graph_repo_benchmark.py `
  --repo google-gemini/gemini-cli `
  --run-name graph_v3 `
  --limit 2
```

The script will:

1. Check `GET /api/graph-status/{owner}/{repo}` on the local extension.
2. Fail early if that repo is not registered or its main graph is not ready.
3. Run only dataset PRs matching that repo.
4. Call extension `/api/review`, which uses the graph stored under that repo name.
5. Save generated comments in evaluator-compatible `<notesplit>` format.

## Useful Options

```text
--repo owner/name              Required GitHub repository.
--run-name graph_v3            Shared output folder for all v3 repo runs.
--limit N                      Run only first N matching PRs.
--force                        Re-run PRs even if comment files exist.
--skip-graph-status-check      Skip registered/main-graph-ready preflight.
--timeout SECONDS              Timeout for graph/review HTTP calls.
--language LANGUAGE            Optional language filter.
```

The repo name must match the repo registered in the extension UI. For example,
`--repo google-gemini/gemini-cli` uses the local graph stored for
`google-gemini/gemini-cli`.

## Outputs

Generated comments:

```text
benchmark/output/comments/graph_v3/
```

Per-repo run logs:

```text
benchmark/output/logs/graph_v3/
```

Each comment file uses the same format as v1/v2:

```text
comments_{repo}_{pr_number}.txt
```

## Evaluate All V3 Results

After running one or more repos, evaluate the shared comments folder:

```powershell
python benchmark\evaluate.py `
  --comments-dir benchmark\output\comments\graph_v3 `
  --output-dir benchmark\output\results\graph_v3
```

This computes the same metrics used by earlier versions:

```text
line_precision
semantic_precision
line_recall
semantic_recall
noise_rate
```

Generate a Markdown report:

```powershell
python benchmark\report.py `
  --results benchmark\output\results\graph_v3\evaluation_results.json
```

## Evaluate Repo By Repo Then Aggregate

If you prefer to evaluate each repo separately, write each repo result to its
own output folder:

```powershell
python benchmark\evaluate.py `
  --comments-dir benchmark\output\comments\graph_v3 `
  --output-dir benchmark\output\results\graph_v3\repos\gemini-cli
```

After all repo-level evaluations are done, aggregate them:

```powershell
python benchmark\aggregate_evaluations.py `
  --inputs "benchmark/output/results/graph_v3/repos/*/evaluation_results.json" `
  --output benchmark/output/results/graph_v3/evaluation_results.json
```

Then generate the final report:

```powershell
python benchmark\report.py `
  --results benchmark\output\results\graph_v3\evaluation_results.json
```

## Compare With V1/V2

Use the final v3 file:

```text
benchmark/output/results/graph_v3/evaluation_results.json
```

Compare it with previous result files, for example:

```text
benchmark/output/results/evaluation_results.json
benchmark/output/results/agent/evaluation_results.json
```

---------The metric names are intentionally unchanged so the comparison is direct.
Chạy benchmark và lưu output sang folder riêng

Ví dụ đặt tên run là graph_v3_qwen36:

python benchmark\run_graph_repo_benchmark.py ` 
--repo google-gemini/gemini-cli`
--run-name graph_v3_qwen36
Output sẽ nằm ở:

benchmark/output/comments/graph_v3_qwen36/
benchmark/output/logs/graph_v3_qwen36/ 3. Evaluate riêng cho Qwen

python benchmark\evaluate.py `  --comments-dir benchmark\output\comments\graph_v3_qwen36`
--output-dir benchmark\output\results\graph_v3_qwen36
Report:

python benchmark\report.py `
--results benchmark\output\results\graph_v3_qwen36\evaluation_results.json
