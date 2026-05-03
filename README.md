# 🔍 CodeReview Bot

AI-powered code review chatbot — paste a GitHub Pull Request URL and get instant, expert code review comments.

Built with **FastAPI** + **LangChain** + **React**, supporting both local LLMs (via **Ollama**) and cloud LLMs (via **Gemini API**).

## ✨ Features

- 💬 **ChatGPT-like Interface** — Dark theme chat UI for natural interaction
- 🔍 **Automated Code Review** — Paste a PR URL → get structured review comments
- 🏠 **Local LLM Support** — Run with Ollama (llama3.1, deepseek-coder, etc.)
- ☁️ **Cloud LLM Support** — Use Google Gemini API
- 📊 **AACR-Bench Evaluation** — Benchmark against 200 PRs, 10 languages
- 🧩 **Extensible Architecture** — Ready for graph code analysis, RAG, multi-agent review

## 🚀 Quick Start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt

# Edit .env — set your LLM provider (ollama or gemini)
# Default: ollama with llama3.1

python run.py
# → API running at http://localhost:8000
# → Docs at http://localhost:8000/docs
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# → UI running at http://localhost:5173
```

### 3. Use It

1. Open http://localhost:5173
2. Paste a GitHub PR URL (e.g. `https://github.com/facebook/react/pull/28000`)
3. Get AI code review comments!

## 📊 Benchmark (AACR-Bench)

### Run Benchmark
```bash
cd benchmark
pip install -r requirements.txt

# Review all 200 PRs
python run_benchmark.py

# Review first 10 PRs only
python run_benchmark.py --limit 10

# Filter by language
python run_benchmark.py --language Python
```

### Evaluate Results
```bash
# Run evaluation (requires aacr-bench evaluator)
python evaluate.py

# Generate report
python report.py
```

### Metrics
| Metric | Description |
|--------|-------------|
| **Line Precision** | Line matches / Total generated |
| **Semantic Precision** | Valid matches / Total generated |
| **Line Recall** | Line matches / Dataset valid count |
| **Semantic Recall** | Valid matches / Dataset valid count |
| **Noise Rate** | Unmatched / Total generated |

## 🏗️ Architecture

```
codeReviewBot/
├── backend/          # FastAPI + LangChain
│   ├── app/
│   │   ├── api/v1/   # Versioned endpoints
│   │   ├── services/  # Business logic
│   │   ├── prompts/   # LLM prompt templates
│   │   └── schemas/   # Pydantic models
│   └── run.py
├── frontend/         # React + Vite
│   └── src/
│       ├── components/ # UI components
│       ├── hooks/      # Custom hooks
│       └── pages/      # Page layouts
└── benchmark/        # AACR-Bench evaluation
    ├── run_benchmark.py
    ├── evaluate.py
    └── report.py
```

## ⚙️ Configuration

Edit `backend/.env`:

```env
# LLM Provider: "ollama" or "gemini"
LLM_PROVIDER=ollama

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1

# Gemini
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-2.0-flash
```

## 📄 License

MIT
