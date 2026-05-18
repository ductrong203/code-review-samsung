# Pipeline cong nghe cua CodeReview Bot

Tai lieu nay mo ta cac cong nghe dang dung trong project theo dung pipeline xu ly Pull Request.

## 1. Tong quan luong chay

Project co 2 luong review:

- **Baseline diff-only review**: React frontend goi truc tiep FastAPI backend. Backend tu fetch diff tu GitHub, parse diff, chay multi-agent review va tra ket qua.
- **Graph-powered review**: Extension service build code graph local truoc, tao graph context cho PR, sau do proxy request sang backend de agent review voi them ngu canh do thi.

Thanh phan chinh:

- `backend/`: FastAPI API, fetch diff, parse diff, multi-agent review, consensus.
- `extension/`: FastAPI service cho graph lifecycle, PR graph, graph context, SSE proxy, extension UI.
- `extension/ui/`: HTML/CSS/JS UI cho graph-powered review va 3D graph viewer.
- `frontend/`: React + Vite baseline UI cho diff-only review.

## 2. Nhan PR URL va parse thong tin PR

Cong nghe:

- Python `re`
- FastAPI request models bang Pydantic

Dung o:

- `backend/app/services/github_service.py`
- `extension/api.py`

Cach dung:

1. UI gui GitHub PR URL, vi du `https://github.com/owner/repo/pull/123`.
2. Backend/extension dung regex de tach:
   - `owner`
   - `repo`
   - `pr_number`
3. Neu URL khong dung format GitHub PR thi tra loi loi validation.

## 3. Fetch PR diff

Cong nghe:

- Python `requests`
- GitHub public PR diff endpoint: `{PR_URL}.diff`
- GitHub REST API cho metadata va changed files

Dung o:

- `backend/app/services/github_service.py`
- `extension/api.py`

Cach dung:

1. Backend tao URL diff bang cach them `.diff` vao PR URL.
2. Goi HTTP GET toi endpoint do bang `requests.Session`.
3. Neu co `GITHUB_TOKEN`, request co header `Authorization`.
4. Ket qua nhan ve la raw unified diff text.
5. Metadata PR duoc fetch tu GitHub REST API:
   - `https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}`
6. Danh sach changed files duoc fetch tu:
   - `https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files`

Ly do dung `.diff` endpoint:

- Don gian, phu hop cho public repo.
- Tra ve unified diff day du de parse hunk, line number va added/removed/context lines.
- Backend khong can clone repo chi de doc diff.

## 4. Parse diff va tao review context

Cong nghe:

- Python dataclass
- Regex parse unified diff
- Custom parser noi bo

Dung o:

- `backend/app/services/diff_parser.py`
- `backend/app/services/context_builder.py`

Cach dung:

1. Raw diff duoc parse thanh cac object:
   - `DiffFile`
   - `DiffHunk`
   - `DiffLine`
2. Parser doc cac marker unified diff:
   - `diff --git a/... b/...`
   - `@@ -old_start,old_count +new_start,new_count @@`
   - dong bat dau bang `+`, `-`, hoac space.
3. Moi dong duoc gan:
   - `ADD`
   - `REMOVE`
   - `CONTEXT`
4. Parser tinh line number ben old side va new side.
5. `format_diff_for_llm()` bien diff thanh text co line number de agent co the noi dung vi tri issue chinh xac.
6. `ContextBuilder` tao `ReviewContext` gom:
   - PR title/description
   - raw diff
   - formatted diff
   - file contexts
   - primary language
   - optional graph context

Luu y hien tai:

- Backend dang theo huong simplified: khong fetch full file content. Agent review chinh dua tren diff + graph context.
- Full-file/repo reasoning neu co se den tu graph context thay vi doc toan bo repo trong backend.

## 5. Register repo va chuan bi source cho graph

Cong nghe:

- FastAPI extension service
- Python `subprocess`
- Git CLI
- JSON registry file

Dung o:

- `extension/api.py`
- `extension/graph_manager/registry.py`

Cach dung:

1. Extension UI goi `/api/register`.
2. Neu user truyen `local_path`, extension dung path do.
3. Neu khong co local path, extension clone repo bang:
   - `git clone --filter=blob:none https://github.com/{owner}/{repo}.git`
4. Repo duoc luu vao registry JSON:
   - mac dinh trong `CRG_GRAPH_BASE/registry.json`
5. Registry luu:
   - owner
   - repo name
   - local path
   - optional repo URL

Muc dich:

- Extension service can mot checkout local de `code-review-graph` parse source code va build graph.
- Trong Docker, repo duoc clone vao volume `/repos` de container co the truy cap.

## 6. Build main code graph

Cong nghe:

- `code-review-graph`
- SQLite-backed graph store thong qua `GraphStore`
- FastAPI endpoint `/api/build-main`

Dung o:

- `extension/graph_manager/lifecycle.py`

Cach dung:

1. Sau khi repo duoc register, extension goi `/api/build-main`.
2. `GraphLifecycleManager.build_main_graph()` mo `GraphStore`.
3. Goi `code_review_graph.incremental.full_build(repo_root, store)`.
4. Thu vien `code-review-graph` parse source code, tao nodes va edges.
5. Ket qua duoc luu vao SQLite DB:
   - `{CRG_GRAPH_BASE}/{owner}/{repo}/main.db`

Main graph dai dien cho baseline graph cua repo, thuong la main/default branch.

## 7. Build PR graph

Cong nghe:

- Git worktree
- Git fetch PR head
- `code-review-graph.incremental.incremental_update`
- SQLite DB copy

Dung o:

- `extension/api.py`
- `extension/graph_manager/lifecycle.py`

Cach dung:

1. Extension can graph rieng cho PR de phan tich code sau thay doi.
2. Neu PR graph chua co, extension:
   - fetch PR head bang `git fetch origin pull/{pr_number}/head:{ref}`
   - tao detached worktree bang `git worktree add --detach`
3. `build_pr_graph()` copy:
   - `main.db` → `pr_{N}.db`
4. Sau do goi:
   - `incremental_update(repo_root, store, changed_files=changed_files)`
5. Chi cac file bi thay doi trong PR duoc update vao graph.
6. PR graph duoc luu tai:
   - `{CRG_GRAPH_BASE}/{owner}/{repo}/pr_{N}.db`

Ly do copy `main.db` roi incremental update:

- Nhanh hon full build moi PR.
- Giu duoc context repo rong, nhung chi update phan thay doi.
- Cho phep query impact tren graph tuong ung voi PR branch.

## 8. Duyet va query graph de tao GraphContext

Cong nghe:

- `code_review_graph.graph.GraphStore`
- `code_review_graph.changes.analyze_changes`
- Graph edges/nodes trong SQLite

Dung o:

- `extension/graph_manager/enricher.py`
- `extension/graph_manager/enricher_new.py`

Cach dung:

1. Extension mo `pr_{N}.db` bang `GraphStore`.
2. Changed files tu diff duoc normalize theo path trong graph.
3. Goi `analyze_changes(store=store, changed_files=...)`.
4. Ket qua duoc rut gon thanh `graph_context` gom:
   - `changed_functions`: function/method thay doi, risk score, callers, test status.
   - `affected_flows`: flow bi anh huong.
   - `test_gaps`: function thay doi nhung khong co test link.
   - `overall_risk`: diem rui ro tong.
   - `review_priorities`: cac node nen uu tien review.
5. Enricher cung query truc tiep edges de tim caller va test coverage:
   - `get_edges_by_target(...)`
   - edge kind nhu `CALLS`, `TESTED_BY`

Muc dich:

- Bien graph lon thanh context nho gon de dua vao prompt.
- Agent khong can doc ca repo nhung van biet function nao co caller, flow, test gap, risk cao.

## 9. Extension streaming pipeline

Cong nghe:

- FastAPI `StreamingResponse`
- Server-Sent Events (SSE)
- Python `requests.post(..., stream=True)` de proxy backend stream
- Browser Fetch API + `ReadableStream`

Dung o:

- `extension/api.py`
- `extension/ui/index.html`

Cach dung:

1. Extension UI goi `/api/review/stream`.
2. Extension stream tung stage:
   - parse PR URL
   - fetch PR diff
   - check/build PR graph
   - extract graph context
   - stream backend review
3. Extension proxy SSE tu backend endpoint:
   - `/api/v1/chat/stream`
4. UI doc stream bang:
   - `response.body.getReader()`
   - `TextDecoder`
   - split block SSE theo `\n\n`
5. UI cap nhat live:
   - progress bar
   - graph stats
   - agent done + so findings
   - final findings

## 10. Xay dung agent va multi-agent review

Cong nghe:

- LangChain
- `langchain_ollama.ChatOllama`
- `langchain_google_genai.ChatGoogleGenerativeAI`
- Custom Python agent classes
- JSON output parsing

Dung o:

- `backend/app/services/llm_service.py`
- `backend/app/agents/agent_base.py`
- `backend/app/agents/orchestrator.py`
- `backend/app/agents/*_agent.py`
- `backend/app/agents/agent_prompts.py`

Cach dung:

1. `llm_service.py` tao LangChain chat model tuy theo config:
   - Ollama: `ChatOllama`
   - Gemini: `ChatGoogleGenerativeAI`
2. Tat ca agent ke thua `ReviewAgent`.
3. Moi agent co system prompt va review prompt rieng.
4. Hien co 4 agent:
   - `DefectAgent`: bug, logic error, crash, edge case.
   - `SecurityAgent`: security vulnerability.
   - `PerformanceAgent`: performance bottleneck, memory, IO.
   - `MaintainabilityAgent`: readability, maintainability, error handling.
5. Agent nhan cung mot `ReviewContext`, gom:
   - formatted diff
   - file diff contexts
   - PR metadata
   - graph context neu co
6. Prompt yeu cau agent tra ve JSON array voi cac field:
   - path
   - line range
   - severity
   - confidence
   - context_level
   - note
   - affected_code
   - suggested_fix
   - fix_note
7. `ReviewAgent` parse output theo thu tu:
   - JSON array
   - XML notesplit fallback
   - markdown/freetext fallback

## 11. Dieu phoi multi-agent

Cong nghe:

- Python classes
- `ThreadPoolExecutor` neu bat parallel mode
- Callback progress/finding/graph cho streaming

Dung o:

- `backend/app/agents/orchestrator.py`

Cach dung:

1. `ReviewOrchestrator` khoi tao 4 specialized agents.
2. Pipeline backend:
   - build context
   - report graph summary
   - chay specialized agents
   - verify/consolidate findings
   - inject code snippets
   - final report
3. Co 2 che do:
   - sequential: chay tung agent mot, de debug on dinh hon.
   - parallel: dung `ThreadPoolExecutor` de chay agent song song.
4. Khi agent xong, backend stream progress:
   - `{Agent name} done - {N} findings`
5. UI dung progress nay de hien thi agent nao da xong va co bao nhieu findings.

## 12. Consensus va consolidated findings

Cong nghe:

- Custom Python consensus engine
- Confidence scoring
- Dedup by file/line overlap

Dung o:

- `backend/app/agents/consensus.py`

Cach dung:

1. Nhan raw findings tu tat ca agents.
2. Gom findings theo file.
3. Detect overlap line range de deduplicate.
4. Neu nhieu agent cung flag vung code, boost confidence.
5. Chon severity cao hon khi merge.
6. Gop note/fix khi can.
7. Filter finding theo confidence threshold.
8. Tinh:
   - risk level
   - blast radius
   - total by category
   - total by severity

## 13. Render code issue va suggested fix

Cong nghe:

- Extension UI: HTML/CSS/vanilla JavaScript
- Baseline frontend: React + Vite

Dung o:

- `extension/ui/index.html`
- `frontend/src/components/ReviewComment.jsx`

Cach dung:

1. Backend tra structured comments.
2. Moi comment co:
   - `note`: mo ta loi va ly do.
   - `affected_code`: code goc bi anh huong.
   - `suggested_fix`: code replacement neu co.
   - `fix_note`: goi y sua bang loi.
   - `code_snippet`: snippet diff co dong loi duoc highlight.
3. UI render:
   - severity/category/path/line.
   - affected code.
   - suggested fix code.
   - fix note bang loi ngay trong panel Suggested fix.
4. Neu `suggested_fix` la prose thay vi code, UI day no sang `Fix note` de tranh render prose trong code block.

## 14. Duyet graph tren UI

Cong nghe:

- Three.js
- Browser Canvas/WebGL
- Fetch API
- Custom layout algorithm trong JS

Dung o:

- `extension/ui/index.html`
- `extension/ui/components/graph-viewer.js`
- `extension/api.py`

Cach dung:

1. Extension UI goi graph API:
   - `/api/graph/{owner}/{repo}`
   - optional `pr_number`
2. Extension API doc graph DB bang `GraphStore`.
3. API tra nodes/edges da rank va paginate.
4. UI dung Three.js de render 3D graph:
   - node la mesh/sphere.
   - edge la line segment.
   - label la canvas texture/sprite.
5. User co the:
   - drag de rotate graph.
   - scroll de zoom.
   - click node de inspect.
6. Khi click node, UI goi API node detail/source snippet de hien source code lien quan.

Muc dich:

- Cho phep inspect repo graph bang truc quan 3D.
- Ho tro xem node/function/file nao co degree cao, lien quan den PR, hoac la test/source node.

## 15. Tom tat pipeline graph-powered review

```text
User paste PR URL
  -> Extension UI POST /api/review/stream
  -> Extension parse owner/repo/pr
  -> Fetch PR diff from GitHub .diff endpoint
  -> Parse unified diff
  -> Ensure repo registered and local checkout exists
  -> Ensure main graph exists
  -> Fetch changed files from GitHub API
  -> Fetch PR head and create temporary git worktree
  -> Copy main.db to pr_N.db
  -> Run code-review-graph incremental_update for changed files
  -> Query pr_N.db with GraphContextEnricher
  -> Produce compact graph_context
  -> Proxy request to backend /api/v1/chat/stream
  -> Backend fetches PR diff again
  -> Backend builds ReviewContext = diff + metadata + graph_context
  -> Run Defect/Security/Performance/Maintainability agents
  -> Consensus dedupe/filter/score
  -> Stream progress and final structured findings
  -> Extension UI renders graph stats, agent status, findings, suggested fix, fix note
```

## 16. Tom tat cong nghe theo chuc nang

| Chuc nang | Cong nghe | Noi dung |
| --- | --- | --- |
| API backend | FastAPI, Pydantic | Chat/review endpoints, schema request/response |
| API extension | FastAPI, Pydantic | Register repo, build graph, review stream, graph APIs |
| Fetch diff | `requests`, GitHub `.diff` endpoint | Lay raw unified diff cua PR |
| Fetch metadata/files | `requests`, GitHub REST API | Lay title/body/changed files |
| Parse diff | Custom Python regex parser | Tao DiffFile/DiffHunk/DiffLine co line number |
| LLM orchestration | LangChain | Tao chain prompt -> model -> string parser |
| LLM providers | Ollama, Gemini | Chay local model hoac Gemini API |
| Multi-agent | Custom ReviewAgent classes | 4 agent chuyen mon theo category |
| Parallel agents | `ThreadPoolExecutor` | Tuy chon chay agents song song |
| Consensus | Custom Python engine | Dedup, merge, confidence boost, risk scoring |
| Graph build | `code-review-graph` | Full build va incremental update |
| Graph storage | SQLite qua `GraphStore` | Luu main.db va pr_N.db |
| Git checkout | Git CLI qua `subprocess` | clone, fetch, worktree PR |
| Graph enrichment | `analyze_changes`, GraphStore edge queries | Tao graph_context nho gon cho prompt |
| Streaming | SSE, FastAPI StreamingResponse | Progress, graph stats, final result |
| Extension UI | HTML/CSS/vanilla JS | Live review UI va findings |
| 3D graph UI | Three.js/WebGL | Render nodes/edges, zoom/rotate/click inspect |
| Baseline UI | React + Vite | Diff-only chat UI |
