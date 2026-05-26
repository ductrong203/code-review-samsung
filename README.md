# CodeReview Bot

AI code review chatbot for GitHub Pull Requests. The project has two review
flows:

- Baseline review: React frontend calls the FastAPI backend directly and reviews
  the PR diff.
- Graph-powered review: the extension service builds a local code graph, enriches
  the PR context, then proxies the request to the backend.

The current Docker deploy runs all three services: backend, extension, and
frontend.

## Features

- Multi-agent review pipeline for defects, security, performance, and
  maintainability.
- LLM provider support for Ollama, Gemini, and OpenAI-compatible gateways.
- GitHub PR diff and metadata fetching.
- Optional graph context from `code-review-graph`.
- Persistent graph cache for local or server deployments.
- Benchmark scripts for AACR-style evaluation.

## Project Layout

```text
codeReviewBot/
  backend/      FastAPI API and multi-agent review pipeline
  extension/    Graph manager, graph-powered review proxy, and graph UI
  frontend/     React baseline chat UI
  benchmark/    Dataset, benchmark runner, and evaluation scripts
```

## Services

| Service | Default URL | Purpose |
| --- | --- | --- |
| Backend | `http://localhost:8000` | Main review API at `/api/v1/chat` |
| Extension | `http://localhost:8100` | Graph management UI/API |
| Frontend | `http://localhost:5173` local, `http://localhost` Docker | Baseline React UI |

Use the extension UI on port `8100` when you want graph-powered review. Use the
frontend when you want the baseline diff-only review.

## Configuration

Create `backend/.env` from `backend/.env.example`:

```env
LLM_PROVIDER=ollama

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1

# Gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# OpenAI-compatible endpoint (9Router, vLLM, OpenRouter, etc.)
OPENAI_COMPATIBLE_BASE_URL=http://host.docker.internal:20128/v1
OPENAI_COMPATIBLE_API_KEY=your_9router_api_key_here
OPENAI_COMPATIBLE_MODEL=your_9router_model_name
OPENAI_COMPATIBLE_TIMEOUT_SECONDS=120
OPENAI_COMPATIBLE_ENABLE_THINKING=false

# Optional, useful for private repos and GitHub rate limits
GITHUB_TOKEN=
```

Choose one provider by changing `LLM_PROVIDER` to `ollama`, `gemini`, or
`openai_compatible`. The OpenAI-compatible option uses `/chat/completions`, so
it works with 9Router, vLLM, OpenRouter, and similar gateways.

For Docker, root `.env.example` contains extension/runtime settings:

```env
GITHUB_TOKEN=
POLL_INTERVAL=120
CRG_CLEANUP_AFTER_REVIEW=true
CRG_KEEP_PR_GRAPH=false
CRG_KEEP_FAILED_PR_GRAPH=false
CRG_REPOS_BASE=/repos
CRG_MAX_CACHE_SIZE_GB=10
CRG_MAX_PR_GRAPH_AGE_HOURS=24
```

## Docker Deploy

From the repository root:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
docker compose up -d --build
```

URLs:

- Backend docs: `http://localhost:8000/docs`
- Extension graph UI: `http://localhost:8100`
- Baseline frontend: `http://localhost`

### Docker Graph Storage

Do not register workstation paths such as
`E:\My_Project\samsung\gemini-cli` inside Docker. Containers can only access
paths mounted on the Docker host.

In the current compose setup:

- Graph DBs and `registry.json` persist in Docker volume `graph-data`, mounted
  at `/data/graphs` inside the extension container.
- Source repositories are cloned into host directory `./repos`, mounted as
  `/repos` inside the extension container.

To register `google-gemini/gemini-cli` in the extension UI:

```text
Owner: google-gemini
Repo Name: gemini-cli
Git URL or Server Path: https://github.com/google-gemini/gemini-cli
```

You can leave `Git URL or Server Path` empty for public GitHub repositories. The
extension will clone:

```text
https://github.com/{owner}/{repo}.git
```

into:

```text
/repos/{owner}/{repo}
```

On the Docker host this appears under:

```text
./repos/{owner}/{repo}
```

## Local Development

### Backend

```bash
cd backend
pip install -r requirements.txt
python run.py
```

Backend runs at `http://localhost:8000`.

### Frontend Baseline UI

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` and calls `/api/v1/chat`.

### Extension Graph UI

```bash
cd extension
pip install -r requirements.txt
python main.py --host 127.0.0.1 --port 8100
```

Extension runs at `http://localhost:8100`.

When running the extension directly on Windows, set explicit local storage paths
before starting it:

```powershell
$env:CRG_GRAPH_BASE="E:\My_Project\samsung\codeReviewBot\.crg_graphs"
$env:CRG_REPOS_BASE="E:\My_Project\samsung\codeReviewBot\repos"
python extension\main.py --host 127.0.0.1 --port 8100
```

With these settings:

- Graph DBs are stored in `.crg_graphs`.
- Cloned source repos are stored in `repos`.

## Extension API

Common endpoints:

```text
POST   /api/register
POST   /api/build-main
POST   /api/build-pr
POST   /api/review
GET    /api/repos
GET    /api/graph-status/{owner}/{name}
DELETE /api/repos/{owner}/{name}
```

Example register request:

```json
{
  "owner": "google-gemini",
  "name": "gemini-cli",
  "repo_url": "https://github.com/google-gemini/gemini-cli"
}
```

If `repo_url` and `local_path` are both omitted, the extension clones from the
default public GitHub URL for the owner/repo pair.

## Benchmark

```bash
cd benchmark
pip install -r requirements.txt

# Review all samples
python run_benchmark.py

# Review first 10 samples
python run_benchmark.py --limit 10

# Filter by language
python run_benchmark.py --language Python
```

Evaluate and generate a report:

```bash
python evaluate.py
python report.py
```

Outputs are written under `benchmark/output/`.

## Notes

- Public GitHub PRs can be reviewed without a token, but `GITHUB_TOKEN` is
  recommended to avoid low unauthenticated rate limits.
- If Ollama runs on the Docker host, use
  `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `backend/.env`.
- The extension removes temporary PR graph artifacts by default after review,
  while keeping the main repo graph cache.

## License

MIT
