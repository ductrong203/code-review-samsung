"""
Extension API — Local FastAPI server for graph management and review proxy.

Endpoints:
  POST /api/register       — Register a repo for graph tracking
  POST /api/build-main     — Build the main branch graph
  POST /api/build-pr       — Build a PR-specific graph
  POST /api/review         — Review a PR (build graph context + proxy to server)
  GET  /api/repos          — List registered repos
  GET  /api/graph-status   — Check graph status for a repo/PR
  DELETE /api/repos/{owner}/{name}  — Unregister a repo
  POST /api/poller/start   — Start background PR poller
  POST /api/poller/stop    — Stop background PR poller
  GET  /api/poller/status  — Check poller status
  GET  /                   — Chatbot UI
"""
import logging
import json
import os
import re
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Optional, Any, Dict, List
from dataclasses import asdict, is_dataclass

# Add backend to Python path for imports
_project_root = Path(__file__).parent.parent
_backend_path = _project_root / "backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from graph_manager.registry import RepoRegistry
from graph_manager.lifecycle import GraphLifecycleManager
from graph_manager.enricher_new import GraphContextEnricher
from graph_manager.poller import PRPoller

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Code Review Graph Extension",
    description="Local extension for graph-powered code review",
    version="0.1.0",
)

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ui_assets_path = Path(__file__).parent / "ui"
if ui_assets_path.exists():
    app.mount("/ui", StaticFiles(directory=str(ui_assets_path)), name="ui")

# ─── Singletons ──────────────────────────────────────────────────────────
registry = RepoRegistry()
lifecycle = GraphLifecycleManager()
poller = PRPoller(
    registry=registry,
    lifecycle=lifecycle,
    github_token=os.environ.get("GITHUB_TOKEN", ""),
    interval_seconds=int(os.environ.get("POLL_INTERVAL", "120")),
)

# Server URL (the codeReviewBot backend)
REVIEW_SERVER_URL = os.environ.get("REVIEW_SERVER_URL", "http://localhost:8000")


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


CRG_CLEANUP_AFTER_REVIEW = env_bool("CRG_CLEANUP_AFTER_REVIEW", True)
CRG_KEEP_PR_GRAPH = env_bool("CRG_KEEP_PR_GRAPH", False)
CRG_KEEP_FAILED_PR_GRAPH = env_bool("CRG_KEEP_FAILED_PR_GRAPH", False)


# ─── Request/Response Models ─────────────────────────────────────────────


class RegisterRequest(BaseModel):
    owner: str = Field(..., description="GitHub owner (e.g. 'facebook')")
    name: str = Field(..., description="Repo name (e.g. 'react')")
    local_path: Optional[str] = Field(
        default=None,
        description="Path visible to this extension process/container",
    )
    repo_url: Optional[str] = Field(
        default=None,
        description="Git clone URL. Defaults to https://github.com/{owner}/{name}.git",
    )


class BuildMainRequest(BaseModel):
    owner: str
    name: str


class BuildPRRequest(BaseModel):
    owner: str
    name: str
    pr_number: int
    changed_files: List[str] = Field(
        default_factory=list,
        description="List of file paths changed in the PR",
    )


class ReviewRequest(BaseModel):
    pr_url: str = Field(..., description="GitHub PR URL")
    server_url: Optional[str] = Field(
        default=None,
        description="Override review server URL",
    )


class GraphStatusRequest(BaseModel):
    owner: str
    name: str
    pr_number: Optional[int] = None


# ─── Helpers ─────────────────────────────────────────────────────────────


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Extract (owner, repo, pr_number) from a GitHub PR URL."""
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)",
        pr_url.strip(),
    )
    if not match:
        raise ValueError(f"Invalid PR URL: {pr_url}")
    return match.group(1), match.group(2), int(match.group(3))


def fetch_pr_changed_files(owner: str, repo: str, pr_number: int) -> List[str]:
    """Fetch the list of changed files from a PR via GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    try:
        resp = requests.get(url, timeout=15)
        if resp.ok:
            files = resp.json()
            return [
                f["filename"]
                for f in files
                if f.get("status") != "removed"
            ]
    except Exception as e:
        logger.warning(f"Failed to fetch PR files: {e}")
    return []


def changed_files_from_diff_files(diff_files) -> List[str]:
    """Derive changed file paths from parsed diff data."""
    changed_files: List[str] = []
    seen = set()
    for df in diff_files or []:
        if getattr(df, "is_deleted", False):
            continue
        path = getattr(df, "new_path", None) or getattr(df, "old_path", None)
        if not path or path in seen:
            continue
        seen.add(path)
        changed_files.append(path)
    return changed_files


def _safe_path_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def get_managed_repo_path(owner: str, repo: str) -> Path:
    repos_base = Path(os.environ.get("CRG_REPOS_BASE", "/repos"))
    return repos_base / _safe_path_part(owner) / _safe_path_part(repo)


def _run_git(args: List[str], cwd: Optional[Path] = None, timeout: int = 300) -> None:
    logger.info("git %s", " ".join(args))
    subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def ensure_repo_checkout(owner: str, repo: str, repo_url: Optional[str]) -> Path:
    """
    Ensure a server/container-local checkout exists and return its path.

    In Docker deploys this keeps source repos under the mounted /repos volume so
    graph builds never depend on workstation-only paths such as E:\\...
    """
    checkout = get_managed_repo_path(owner, repo)
    url = repo_url or f"https://github.com/{owner}/{repo}.git"

    if (checkout / ".git").exists():
        _run_git(["fetch", "origin", "--prune"], cwd=checkout)
        return checkout

    if checkout.exists() and any(checkout.iterdir()):
        raise ValueError(
            f"Managed repo path exists but is not a git checkout: {checkout}"
        )

    checkout.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["clone", "--filter=blob:none", url, str(checkout)], timeout=900)
    return checkout


def get_pr_worktree_path(owner: str, repo: str, pr_number: int) -> Path:
    return (
        GraphLifecycleManager.BASE
        / "worktrees"
        / _safe_path_part(owner)
        / _safe_path_part(repo)
        / f"pr_{pr_number}"
    )


def prepare_pr_worktree(
    owner: str,
    repo: str,
    repo_root: Path,
    pr_number: int,
) -> Optional[Path]:
    """
    Fetch a PR head into a temporary detached worktree for graph updates.

    The graph must be updated from the PR's actual source tree. Using the
    registered local checkout as-is breaks old benchmark PRs when files have
    moved or disappeared on current main.
    """
    if not (repo_root / ".git").exists():
        logger.warning("Repo root is not a git checkout: %s", repo_root)
        return None

    worktree_root = get_pr_worktree_path(owner, repo, pr_number)
    ref = f"refs/codereviewbot/pr-{pr_number}"

    try:
        if worktree_root.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_root)],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if worktree_root.exists():
                shutil.rmtree(worktree_root, ignore_errors=True)

        _run_git(
            ["fetch", "origin", f"pull/{pr_number}/head:{ref}", "--force"],
            cwd=repo_root,
            timeout=120,
        )
        _run_git(
            ["worktree", "add", "--detach", str(worktree_root), ref],
            cwd=repo_root,
            timeout=120,
        )
        return worktree_root
    except Exception as e:
        logger.warning(
            "Could not prepare PR worktree for %s/%s#%s: %s",
            owner,
            repo,
            pr_number,
            e,
        )
        return None


def cleanup_pr_worktree(repo_root: Path, worktree_path: Optional[Path]) -> None:
    if not worktree_path:
        return
    if worktree_path.exists():
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception as e:
            logger.debug("Failed to remove PR worktree %s: %s", worktree_path, e)
    if worktree_path.exists():
        shutil.rmtree(worktree_path, ignore_errors=True)


def should_cleanup_review_artifacts(success: bool) -> bool:
    if not CRG_CLEANUP_AFTER_REVIEW:
        return False
    if CRG_KEEP_PR_GRAPH:
        return False
    if not success and CRG_KEEP_FAILED_PR_GRAPH:
        return False
    return True


def cleanup_review_artifacts(
    owner: str,
    repo: str,
    pr_number: int,
    repo_root: Optional[Path],
) -> None:
    lifecycle.cleanup_pr(owner, repo, pr_number)

    worktree_path = get_pr_worktree_path(owner, repo, pr_number)
    if repo_root and (repo_root / ".git").exists():
        cleanup_pr_worktree(repo_root, worktree_path)
    elif worktree_path.exists():
        shutil.rmtree(worktree_path, ignore_errors=True)


def _graph_stats_to_dict(stats: Any) -> Dict[str, Any]:
    if stats is None:
        return {}
    if is_dataclass(stats):
        return asdict(stats)
    if isinstance(stats, dict):
        return stats
    return {
        key: getattr(stats, key)
        for key in (
            "total_nodes",
            "total_edges",
            "nodes_by_kind",
            "edges_by_kind",
            "languages",
            "files_count",
            "last_updated",
        )
        if hasattr(stats, key)
    }


def _compact_graph_path(path: str) -> str:
    normalized = (path or "").replace("\\", "/")
    if not normalized:
        return ""

    parts = [p for p in normalized.split("/") if p]
    if len(parts) <= 3:
        return normalized
    return "/".join(parts[-3:])


def _graph_module_name(path: str) -> str:
    normalized = (path or "").replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    if not parts:
        return "unknown"
    if len(parts) == 1:
        return parts[0]
    if parts[0] in {"src", "app", "packages", "libs", "lib", "tests", "test"} and len(parts) >= 3:
        return "/".join(parts[:3])
    return "/".join(parts[:2])


def _node_to_view(node: Any, degree: int = 0) -> Dict[str, Any]:
    qualified_name = getattr(node, "qualified_name", "") or ""
    name = getattr(node, "name", "") or qualified_name.rsplit("::", 1)[-1]
    file_path = getattr(node, "file_path", "")
    return {
        "id": qualified_name,
        "name": name,
        "kind": getattr(node, "kind", ""),
        "parent_name": getattr(node, "parent_name", None),
        "params": getattr(node, "params", None),
        "return_type": getattr(node, "return_type", None),
        "file": _compact_graph_path(file_path),
        "module": _graph_module_name(file_path),
        "line_start": getattr(node, "line_start", None),
        "line_end": getattr(node, "line_end", None),
        "language": getattr(node, "language", ""),
        "is_test": bool(getattr(node, "is_test", False)),
        "degree": degree,
    }


def _read_node_code(
    node: Any,
    repo_root: Optional[Path] = None,
    max_lines: int = 260,
) -> Dict[str, Any]:
    """Read the source span for a graph node when the backing file is available."""
    file_path = Path(getattr(node, "file_path", "") or "")
    line_start = getattr(node, "line_start", None)
    line_end = getattr(node, "line_end", None)

    candidates = [file_path]
    if repo_root and not file_path.is_absolute():
        candidates.insert(0, repo_root / file_path)

    source_path = next((path for path in candidates if path.exists()), None)

    if not source_path or not line_start or not line_end:
        return {
            "code_snippet": "",
            "snippet_start_line": None,
            "snippet_end_line": None,
            "code_truncated": False,
            "source_path": "",
        }

    try:
        lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {
            "code_snippet": "",
            "snippet_start_line": None,
            "snippet_end_line": None,
            "code_truncated": False,
            "source_path": "",
        }

    start = max(int(line_start), 1)
    end = max(int(line_end), start)
    truncated = False
    if end - start + 1 > max_lines:
        end = start + max_lines - 1
        truncated = True

    selected = lines[start - 1:end]
    return {
        "code_snippet": "\n".join(selected),
        "snippet_start_line": start,
        "snippet_end_line": end,
        "code_truncated": truncated,
        "source_path": str(source_path),
    }


def _edge_to_view(edge: Any) -> Dict[str, Any]:
    return {
        "source": getattr(edge, "source_qualified", ""),
        "target": getattr(edge, "target_qualified", ""),
        "kind": getattr(edge, "kind", ""),
        "line": getattr(edge, "line", None),
        "confidence": getattr(edge, "confidence", 1.0),
    }


def _graph_degree(edges: List[Any]) -> Dict[str, int]:
    degree: Dict[str, int] = {}
    for edge in edges:
        source = getattr(edge, "source_qualified", "")
        target = getattr(edge, "target_qualified", "")
        if source:
            degree[source] = degree.get(source, 0) + 1
        if target:
            degree[target] = degree.get(target, 0) + 1
    return degree


def _rank_graph_nodes(nodes: List[Any], degree: Dict[str, int]) -> List[Any]:
    return sorted(
        nodes,
        key=lambda node: (
            degree.get(getattr(node, "qualified_name", ""), 0),
            0 if getattr(node, "is_test", False) else 1,
            getattr(node, "kind", "") in {"Function", "Class", "Method"},
        ),
        reverse=True,
    )


def _graph_search_text(node: Any) -> str:
    return " ".join(
        str(value or "")
        for value in (
            getattr(node, "name", ""),
            getattr(node, "qualified_name", ""),
            getattr(node, "kind", ""),
            getattr(node, "file_path", ""),
            getattr(node, "parent_name", ""),
            getattr(node, "language", ""),
        )
    ).lower()


def _graph_search_score(node: Any, query: str) -> float:
    q = query.strip().lower()
    if not q:
        return 0.0
    name = str(getattr(node, "name", "") or "").lower()
    qualified = str(getattr(node, "qualified_name", "") or "").lower()
    file_path = str(getattr(node, "file_path", "") or "").replace("\\", "/").lower()
    haystack = _graph_search_text(node)

    if name == q or qualified == q:
        return 1000.0
    if name.startswith(q):
        return 900.0 - len(name) * 0.01
    if file_path.endswith(q) or qualified.endswith(q):
        return 760.0 - len(qualified) * 0.005
    if q in name:
        return 680.0 - name.index(q)
    if q in haystack:
        return 420.0 - haystack.index(q) * 0.01

    qi = 0
    for char in haystack:
        if qi < len(q) and char == q[qi]:
            qi += 1
        if qi == len(q):
            return 160.0 - len(haystack) * 0.001
    return 0.0


def _graph_node_relations(
    store: Any,
    qualified_name: str,
    page_size: int = 200,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return incoming/outgoing relation targets with graph-page offsets."""
    nodes = store.get_all_nodes(exclude_files=True)
    edges = store.get_all_edges()
    degree = _graph_degree(edges)
    ranked_nodes = _rank_graph_nodes(nodes, degree)
    node_by_id = {
        getattr(node, "qualified_name", ""): node
        for node in ranked_nodes
    }
    rank_by_id = {
        getattr(node, "qualified_name", ""): index
        for index, node in enumerate(ranked_nodes)
    }
    bounded_page_size = max(10, min(page_size, 2000))

    def relation_record(node_id: str, edge: Any) -> Optional[Dict[str, Any]]:
        node = node_by_id.get(node_id)
        if not node:
            return None
        rank = rank_by_id.get(node_id, 0)
        return {
            "node": _node_to_view(node, degree.get(node_id, 0)),
            "page_offset": (rank // bounded_page_size) * bounded_page_size,
            "edge_kind": getattr(edge, "kind", ""),
            "line": getattr(edge, "line", None),
        }

    incoming: List[Dict[str, Any]] = []
    outgoing: List[Dict[str, Any]] = []
    seen_incoming = set()
    seen_outgoing = set()

    for edge in store.get_edges_by_target(qualified_name):
        source = getattr(edge, "source_qualified", "")
        if not source or source in seen_incoming:
            continue
        seen_incoming.add(source)
        record = relation_record(source, edge)
        if record:
            incoming.append(record)

    for edge in store.get_edges_by_source(qualified_name):
        target = getattr(edge, "target_qualified", "")
        if not target or target in seen_outgoing:
            continue
        seen_outgoing.add(target)
        record = relation_record(target, edge)
        if record:
            outgoing.append(record)

    incoming.sort(key=lambda item: item["node"].get("degree", 0), reverse=True)
    outgoing.sort(key=lambda item: item["node"].get("degree", 0), reverse=True)
    return {"incoming": incoming, "outgoing": outgoing}


def build_graph_view(
    owner: str,
    repo: str,
    db_path: Path,
    limit: int = 80,
    offset: int = 0,
    edge_limit: int = 20000,
) -> Dict[str, Any]:
    """
    Return a small high-signal graph slice for browser visualization.

    Large repositories can contain thousands of nodes, so the endpoint ranks
    nodes by call/dependency degree and returns only the visible subgraph.
    """
    from code_review_graph.graph import GraphStore

    store = GraphStore(str(db_path))
    try:
        nodes = store.get_all_nodes(exclude_files=True)
        edges = store.get_all_edges()
        stats = _graph_stats_to_dict(store.get_stats())
    finally:
        store.close()

    degree = _graph_degree(edges)
    ranked_nodes = _rank_graph_nodes(nodes, degree)
    all_nodes_requested = limit <= 0
    bounded_offset = 0 if all_nodes_requested else max(0, offset)
    visible_nodes = (
        ranked_nodes
        if all_nodes_requested
        else ranked_nodes[bounded_offset:bounded_offset + limit]
    )
    visible_edge_limit = max(0, edge_limit)
    selected = {getattr(node, "qualified_name", "") for node in visible_nodes}
    visible_edges = [
        edge for edge in edges
        if getattr(edge, "source_qualified", "") in selected
        and getattr(edge, "target_qualified", "") in selected
    ][: visible_edge_limit]

    cluster_counts: Dict[str, int] = {}
    for node in visible_nodes:
        cluster = _compact_graph_path(getattr(node, "file_path", ""))
        cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1

    return {
        "repo": f"{owner}/{repo}",
        "owner": owner,
        "name": repo,
        "db_path": str(db_path),
        "stats": stats,
        "all_nodes_requested": all_nodes_requested,
        "total_node_count": len(ranked_nodes),
        "total_edge_count": len(edges),
        "offset": bounded_offset,
        "limit": limit,
        "has_previous": not all_nodes_requested and bounded_offset > 0,
        "has_next": (
            not all_nodes_requested
            and bounded_offset + len(visible_nodes) < len(ranked_nodes)
        ),
        "previous_offset": max(0, bounded_offset - limit) if not all_nodes_requested else None,
        "next_offset": (
            bounded_offset + limit
            if not all_nodes_requested
            and bounded_offset + len(visible_nodes) < len(ranked_nodes)
            else None
        ),
        "visible_node_count": len(visible_nodes),
        "visible_edge_count": len(visible_edges),
        "clusters": [
            {"name": name, "count": count}
            for name, count in sorted(cluster_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        "nodes": [
            _node_to_view(node, degree.get(getattr(node, "qualified_name", ""), 0))
            for node in visible_nodes
        ],
        "edges": [_edge_to_view(edge) for edge in visible_edges],
    }


def get_graph_db_or_404(owner: str, name: str, pr_number: Optional[int] = None) -> Path:
    """Resolve a main or PR graph DB path, raising an HTTP 404 when absent."""
    if pr_number is not None:
        db_path = lifecycle.get_pr_db_path(owner, name, pr_number)
        if not db_path:
            raise HTTPException(
                status_code=404,
                detail=f"PR graph not built for {owner}/{name}#{pr_number}.",
            )
        return db_path

    db_path = lifecycle.get_main_db_path(owner, name)
    if not db_path:
        raise HTTPException(
            status_code=404,
            detail=f"Main graph not built for {owner}/{name}.",
        )
    return db_path


# ─── Endpoints ───────────────────────────────────────────────────────────


@app.post("/api/register", tags=["repos"])
async def register_repo(request: RegisterRequest):
    """Register a repository for graph tracking."""
    try:
        if request.local_path:
            local = Path(request.local_path)
            if not local.exists():
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Local path does not exist from the extension container: "
                        f"{request.local_path}. In Docker, either mount that repo "
                        "under /repos or register by repo_url so the server clones it."
                    ),
                )
        else:
            local = ensure_repo_checkout(
                request.owner, request.name, request.repo_url,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Repo checkout failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

    entry = registry.register(
        request.owner,
        request.name,
        str(local),
        repo_url=request.repo_url,
    )
    return {
        "status": "registered",
        "repo": entry,
        "message": f"Repo {request.owner}/{request.name} registered. "
                   f"Run /api/build-main to build the main graph.",
    }


@app.post("/api/build-main", tags=["graph"])
async def build_main_graph(request: BuildMainRequest):
    """Build the main branch graph for a registered repo."""
    repo = registry.get(request.owner, request.name)
    if not repo:
        raise HTTPException(
            status_code=404,
            detail=f"Repo {request.owner}/{request.name} not registered. "
                   f"Call /api/register first.",
        )

    repo_root = Path(repo["local_path"])
    if not repo_root.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Repo local path not found: {repo['local_path']}",
        )

    try:
        stats = lifecycle.build_main_graph(
            request.owner, request.name, repo_root,
        )
        return {
            "status": "built",
            "stats": stats,
            "message": f"Main graph built for {request.owner}/{request.name}",
        }
    except Exception as e:
        logger.error(f"Build main graph failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/build-pr", tags=["graph"])
async def build_pr_graph(request: BuildPRRequest):
    """Build a PR-specific graph (copy main + incremental update)."""
    repo = registry.get(request.owner, request.name)
    if not repo:
        raise HTTPException(
            status_code=404,
            detail=f"Repo {request.owner}/{request.name} not registered.",
        )

    if not lifecycle.main_graph_ready(request.owner, request.name):
        raise HTTPException(
            status_code=400,
            detail="Main graph not built yet. Call /api/build-main first.",
        )

    repo_root = Path(repo["local_path"])

    # Use provided changed_files or fetch from GitHub API
    changed_files = request.changed_files
    if not changed_files:
        changed_files = fetch_pr_changed_files(
            request.owner, request.name, request.pr_number,
        )
        if not changed_files:
            try:
                from app.services.github_service import GitHubService
                from app.services.diff_parser import parse_diff

                pr_url = (
                    f"https://github.com/{request.owner}/"
                    f"{request.name}/pull/{request.pr_number}"
                )
                raw_diff = GitHubService().fetch_pr_diff(pr_url)
                changed_files = changed_files_from_diff_files(parse_diff(raw_diff))
                if changed_files:
                    logger.warning(
                        "GitHub PR files API returned no files for %s/%s#%s; "
                        "using %s file(s) parsed from diff",
                        request.owner,
                        request.name,
                        request.pr_number,
                        len(changed_files),
                    )
            except Exception as e:
                logger.warning(
                    "Could not derive changed files from PR diff for %s/%s#%s: %s",
                    request.owner,
                    request.name,
                    request.pr_number,
                    e,
                )
        if not changed_files:
            raise HTTPException(
                status_code=400,
                detail="No changed files found. Provide changed_files "
                       "or ensure the PR exists.",
            )

    pr_worktree = prepare_pr_worktree(
        request.owner,
        request.name,
        repo_root,
        request.pr_number,
    )
    graph_repo_root = pr_worktree or repo_root

    try:
        stats = lifecycle.build_pr_graph(
            request.owner, request.name, graph_repo_root,
            request.pr_number, changed_files,
        )
        return {
            "status": "built",
            "pr_number": request.pr_number,
            "stats": stats,
            "message": f"PR #{request.pr_number} graph built",
        }
    except Exception as e:
        logger.error(f"Build PR graph failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_pr_worktree(repo_root, pr_worktree)


@app.post("/api/review", tags=["review"])
async def review_pr(request: ReviewRequest):
    """
    SIMPLIFIED review flow:
    1. Parse PR URL -> owner/repo/pr_number
    2. Fetch PR diff from GitHub
    3. Build/verify PR graph exists
    4. Extract functions from diff hunks (not file matching)
    5. Query graph for impact of those functions
    6. Send { pr_url, graph_context } to review server
    7. Return review result
    
    NO file context needed - only diff + graph impact analysis.
    """
    try:
        owner, repo, pr_number = parse_pr_url(request.pr_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"Reviewing PR: {owner}/{repo}#{pr_number}")
    review_success = False
    repo_root_for_cleanup: Optional[Path] = None

    try:
        # Step 1: Fetch PR diff
        try:
            from app.services.github_service import GitHubService
            gh = GitHubService()
            raw_diff = gh.fetch_pr_diff(request.pr_url)
            from app.services.diff_parser import parse_diff
            diff_files = parse_diff(raw_diff)
            logger.info(f"Parsed {len(diff_files)} files from diff")
        except Exception as e:
            logger.error(f"Failed to fetch diff: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Could not fetch PR diff: {str(e)}",
            )

        reg = registry.get(owner, repo)
        if reg:
            repo_root_for_cleanup = Path(reg["local_path"])

        # Step 2: Build/verify PR graph
        if not lifecycle.pr_graph_ready(owner, repo, pr_number):
            if lifecycle.main_graph_ready(owner, repo) and reg:
                changed_files = fetch_pr_changed_files(owner, repo, pr_number)
                if not changed_files:
                    changed_files = changed_files_from_diff_files(diff_files)
                    if changed_files:
                        logger.warning(
                            "GitHub PR files API returned no files for %s/%s#%s; "
                            "using %s file(s) parsed from diff",
                            owner,
                            repo,
                            pr_number,
                            len(changed_files),
                        )
                if changed_files:
                    try:
                        logger.info(f"Auto-building PR graph for {owner}/{repo}#{pr_number}")
                        repo_root = Path(reg["local_path"])
                        pr_worktree = prepare_pr_worktree(
                            owner, repo, repo_root, pr_number,
                        )
                        try:
                            lifecycle.build_pr_graph(
                                owner, repo, pr_worktree or repo_root,
                                pr_number, changed_files,
                            )
                        finally:
                            cleanup_pr_worktree(repo_root, pr_worktree)
                    except Exception as e:
                        logger.warning(f"Auto-build PR graph failed: {e}")

            if not lifecycle.pr_graph_ready(owner, repo, pr_number):
                raise HTTPException(
                    status_code=400,
                    detail=f"Graph not ready for PR #{pr_number}. "
                           f"Build it via /api/build-pr or ensure repo is registered.",
                )

        # Step 3: Extract functions from diff and query graph
        pr_db = lifecycle.get_pr_db_path(owner, repo, pr_number)

        try:
            with GraphContextEnricher(str(pr_db)) as enricher:
                graph_context = enricher.get_context_from_diff(diff_files)

            if not graph_context.get("changed_functions"):
                changed_files = [
                    df.new_path or df.old_path
                    for df in diff_files
                    if not getattr(df, "is_deleted", False)
                ]
                if reg and changed_files:
                    logger.warning(
                        "Graph context is empty for %s/%s#%s; rebuilding PR graph "
                        "from PR worktree and retrying enrichment",
                        owner,
                        repo,
                        pr_number,
                    )
                    repo_root = Path(reg["local_path"])
                    pr_worktree = prepare_pr_worktree(owner, repo, repo_root, pr_number)
                    try:
                        lifecycle.build_pr_graph(
                            owner,
                            repo,
                            pr_worktree or repo_root,
                            pr_number,
                            changed_files,
                        )
                    finally:
                        cleanup_pr_worktree(repo_root, pr_worktree)

                    pr_db = lifecycle.get_pr_db_path(owner, repo, pr_number)
                    with GraphContextEnricher(str(pr_db)) as enricher:
                        graph_context = enricher.get_context_from_diff(diff_files)

            logger.info(
                f"Built graph context: "
                f"{len(graph_context.get('changed_functions', []))} functions"
            )
        except Exception as e:
            logger.error(f"Failed to enrich graph context: {e}", exc_info=True)
            graph_context = {
                "changed_functions": [],
                "affected_flows": [],
                "test_gaps": [],
                "overall_risk": 0.0,
                "review_priorities": [],
                "_error": str(e),
            }

        # Step 4: Send to review server
        server_url = request.server_url or REVIEW_SERVER_URL
        payload = {
            "message": request.pr_url,
            "graph_context": graph_context,
            # Note: raw_diff is NOT sent - backend will fetch it
            # This keeps payload size small
        }

        try:
            logger.info(f"Sending review request to {server_url}")
            resp = requests.post(
                f"{server_url}/api/v1/chat",
                json=payload,
                timeout=300,  # 5 min timeout for review
            )

            if resp.ok:
                review_data = resp.json()
                review_success = "_error" not in graph_context
                return {
                    "status": "reviewed",
                    "graph_context": graph_context,
                    "review": review_data,
                }

            logger.error(f"Review server error: {resp.status_code}")
            return {
                "status": "error",
                "graph_context": graph_context,
                "error": f"Review server returned {resp.status_code}: {resp.text[:500]}",
            }

        except requests.exceptions.ConnectionError:
            raise HTTPException(
                status_code=502,
                detail=f"Cannot connect to review server at {server_url}. "
                       f"Is the backend running?",
            )
        except Exception as e:
            logger.error(f"Review request failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    finally:
        if should_cleanup_review_artifacts(review_success):
            cleanup_review_artifacts(
                owner,
                repo,
                pr_number,
                repo_root_for_cleanup,
            )
        else:
            logger.info(
                "Keeping PR graph artifacts for %s/%s#%s "
                "(success=%s, cleanup_after_review=%s, keep_pr_graph=%s, "
                "keep_failed_pr_graph=%s)",
                owner,
                repo,
                pr_number,
                review_success,
                CRG_CLEANUP_AFTER_REVIEW,
                CRG_KEEP_PR_GRAPH,
                CRG_KEEP_FAILED_PR_GRAPH,
            )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/review/stream", tags=["review"])
async def review_pr_stream(request: ReviewRequest):
    """Graph-powered review with SSE proxy to backend streaming endpoint."""
    def generate():
        review_success = False
        repo_root_for_cleanup: Optional[Path] = None
        owner = repo = ""
        pr_number = 0

        try:
            yield _sse("progress", {"stage": "Parsing PR URL...", "progress": 0.03})
            owner, repo, pr_number = parse_pr_url(request.pr_url)
            reg = registry.get(owner, repo)
            if reg:
                repo_root_for_cleanup = Path(reg["local_path"])

            yield _sse("progress", {"stage": "Fetching PR diff...", "progress": 0.08})
            from app.services.github_service import GitHubService
            from app.services.diff_parser import parse_diff
            gh = GitHubService()
            raw_diff = gh.fetch_pr_diff(request.pr_url)
            diff_files = parse_diff(raw_diff)

            yield _sse("progress", {"stage": "Checking PR graph...", "progress": 0.16})
            if not lifecycle.pr_graph_ready(owner, repo, pr_number):
                if lifecycle.main_graph_ready(owner, repo) and reg:
                    changed_files = fetch_pr_changed_files(owner, repo, pr_number)
                    repo_root = Path(reg["local_path"])
                    pr_worktree = prepare_pr_worktree(owner, repo, repo_root, pr_number)
                    try:
                        yield _sse("progress", {"stage": "Building PR graph...", "progress": 0.24})
                        lifecycle.build_pr_graph(
                            owner,
                            repo,
                            pr_worktree or repo_root,
                            pr_number,
                            changed_files,
                        )
                    finally:
                        cleanup_pr_worktree(repo_root, pr_worktree)

            if not lifecycle.pr_graph_ready(owner, repo, pr_number):
                raise RuntimeError(
                    f"Graph not ready for PR #{pr_number}. Build it via /api/build-pr first."
                )

            yield _sse("progress", {"stage": "Extracting graph context...", "progress": 0.32})
            pr_db = lifecycle.get_pr_db_path(owner, repo, pr_number)
            with GraphContextEnricher(str(pr_db)) as enricher:
                graph_context = enricher.get_context_from_diff(diff_files)

            graph_summary = {
                "changed_functions": len(graph_context.get("changed_functions", []) or []),
                "affected_flows": len(graph_context.get("affected_flows", []) or []),
                "test_gaps": len(graph_context.get("test_gaps", []) or []),
                "review_priorities": len(graph_context.get("review_priorities", []) or []),
                "related_context": len(graph_context.get("related_context", []) or []),
                "overall_risk": graph_context.get("overall_risk", 0.0),
            }
            yield _sse("graph", graph_summary)

            server_url = request.server_url or REVIEW_SERVER_URL
            payload = {"message": request.pr_url, "graph_context": graph_context}
            yield _sse("progress", {"stage": "Streaming backend review...", "progress": 0.4})
            with requests.post(
                f"{server_url}/api/v1/chat/stream",
                json=payload,
                timeout=300,
                stream=True,
            ) as resp:
                if not resp.ok:
                    raise RuntimeError(
                        f"Review server returned {resp.status_code}: {resp.text[:500]}"
                    )
                for line in resp.iter_lines(decode_unicode=True):
                    if line is None:
                        continue
                    yield line + "\n"
            review_success = True
        except Exception as e:
            logger.error(f"Streaming review failed: {e}", exc_info=True)
            yield _sse("error", {"error": str(e)})
        finally:
            if owner and repo and pr_number:
                if should_cleanup_review_artifacts(review_success):
                    cleanup_review_artifacts(
                        owner,
                        repo,
                        pr_number,
                        repo_root_for_cleanup,
                    )
            yield _sse("done", {"ok": review_success})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/repos", tags=["repos"])
async def list_repos():
    """List all registered repos with graph status."""
    repos = registry.list_all()
    result = []
    for repo in repos:
        owner, name = repo["owner"], repo["name"]
        result.append({
            **repo,
            "main_graph_ready": lifecycle.main_graph_ready(owner, name),
        })
    return {"repos": result}


@app.get("/api/graph-status/{owner}/{name}", tags=["graph"])
async def graph_status(owner: str, name: str, pr_number: Optional[int] = None):
    """Check graph status for a repo (and optionally a specific PR)."""
    repo = registry.get(owner, name)
    if not repo:
        raise HTTPException(
            status_code=404,
            detail=f"Repo {owner}/{name} not registered.",
        )

    status = {
        "repo": f"{owner}/{name}",
        "registered": True,
        "local_path": repo["local_path"],
        "main_graph_ready": lifecycle.main_graph_ready(owner, name),
    }

    if pr_number is not None:
        status["pr_number"] = pr_number
        status["pr_graph_ready"] = lifecycle.pr_graph_ready(owner, name, pr_number)

    return status


@app.get("/api/graph/{owner}/{name}", tags=["graph"])
async def graph_view(
    owner: str,
    name: str,
    pr_number: Optional[int] = None,
    limit: int = 80,
    offset: int = 0,
    edge_limit: int = 20000,
):
    """Return a compact node/edge view of a built main or PR graph."""
    repo = registry.get(owner, name)
    if not repo:
        raise HTTPException(
            status_code=404,
            detail=f"Repo {owner}/{name} not registered.",
        )

    bounded_limit = 0 if limit <= 0 else max(10, min(limit, 2000))
    bounded_offset = max(0, offset)
    bounded_edge_limit = max(0, min(edge_limit, 100000))
    db_path = get_graph_db_or_404(owner, name, pr_number)

    try:
        return build_graph_view(
            owner=owner,
            repo=name,
            db_path=db_path,
            limit=bounded_limit,
            offset=bounded_offset,
            edge_limit=bounded_edge_limit,
        )
    except Exception as e:
        logger.error("Failed to load graph view for %s/%s: %s", owner, name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/{owner}/{name}/search", tags=["graph"])
async def graph_search(
    owner: str,
    name: str,
    q: str,
    pr_number: Optional[int] = None,
    limit: int = 20,
    page_size: int = 100,
):
    """Search the full graph DB and return matches with the page offset containing each node."""
    repo = registry.get(owner, name)
    if not repo:
        raise HTTPException(
            status_code=404,
            detail=f"Repo {owner}/{name} not registered.",
        )

    query = (q or "").strip()
    if not query:
        return {"query": "", "matches": [], "total_node_count": 0}

    bounded_limit = max(1, min(limit, 50))
    bounded_page_size = max(10, min(page_size, 2000))
    db_path = get_graph_db_or_404(owner, name, pr_number)

    from code_review_graph.graph import GraphStore

    store = GraphStore(str(db_path))
    try:
        nodes = store.get_all_nodes(exclude_files=True)
        edges = store.get_all_edges()
    finally:
        store.close()

    degree = _graph_degree(edges)
    ranked_nodes = _rank_graph_nodes(nodes, degree)
    rank_by_id = {
        getattr(node, "qualified_name", ""): index
        for index, node in enumerate(ranked_nodes)
    }

    scored = []
    for node in ranked_nodes:
        score = _graph_search_score(node, query)
        if score > 0:
            scored.append((score, node))

    scored.sort(
        key=lambda item: (
            item[0],
            degree.get(getattr(item[1], "qualified_name", ""), 0),
        ),
        reverse=True,
    )

    matches = []
    for score, node in scored[:bounded_limit]:
        node_id = getattr(node, "qualified_name", "")
        rank = rank_by_id.get(node_id, 0)
        page_offset = (rank // bounded_page_size) * bounded_page_size
        matches.append({
            "node": _node_to_view(node, degree.get(node_id, 0)),
            "rank": rank,
            "page_offset": page_offset,
            "score": round(score, 3),
        })

    return {
        "query": query,
        "matches": matches,
        "total_node_count": len(ranked_nodes),
    }


@app.get("/api/graph/{owner}/{name}/node", tags=["graph"])
async def graph_node_detail(
    owner: str,
    name: str,
    qualified_name: str,
    pr_number: Optional[int] = None,
    page_size: int = 200,
):
    """Return node metadata plus the source span for the selected code node."""
    repo = registry.get(owner, name)
    if not repo:
        raise HTTPException(
            status_code=404,
            detail=f"Repo {owner}/{name} not registered.",
        )

    db_path = get_graph_db_or_404(owner, name, pr_number)

    from code_review_graph.graph import GraphStore

    store = GraphStore(str(db_path))
    try:
        node = store.get_node(qualified_name)
        relations = _graph_node_relations(store, qualified_name, page_size)
    finally:
        store.close()

    if not node:
        raise HTTPException(
            status_code=404,
            detail=f"Node not found: {qualified_name}",
        )

    return {
        "node": _node_to_view(node),
        "relations": relations,
        **_read_node_code(node, Path(repo["local_path"])),
    }


@app.delete("/api/repos/{owner}/{name}", tags=["repos"])
async def unregister_repo(owner: str, name: str):
    """Unregister a repository and remove its local graph artifacts."""
    repo_entry = registry.get(owner, name)
    if not repo_entry:
        raise HTTPException(
            status_code=404,
            detail=f"Repo {owner}/{name} not found in registry.",
        )

    repo_root = Path(repo_entry["local_path"])
    worktree_base = get_pr_worktree_path(owner, name, 0).parent
    if (repo_root / ".git").exists() and worktree_base.exists():
        for worktree_path in worktree_base.glob("pr_*"):
            cleanup_pr_worktree(repo_root, worktree_path)

    cleanup = lifecycle.cleanup_repo(owner, name)
    removed = registry.unregister(owner, name)
    if removed:
        return {
            "status": "unregistered",
            "repo": f"{owner}/{name}",
            "cleanup": cleanup,
            "message": (
                f"Repo {owner}/{name} unregistered and local graph artifacts "
                "removed. Source checkout was not deleted."
            ),
        }
    raise HTTPException(status_code=500, detail=f"Failed to unregister {owner}/{name}")

# ─── Webhook Endpoints (GitHub Integration) ────────────────────────────


class GitHubWebhookEvent(BaseModel):
    """GitHub webhook event payload."""
    action: str
    pull_request: Optional[Dict[str, Any]] = None
    repository: Optional[Dict[str, Any]] = None


@app.post("/api/webhook/github", tags=["webhook"])
async def github_webhook(event: GitHubWebhookEvent):
    """
    Handle GitHub webhook events.
    
    Currently handles:
    - pull_request.closed (merged or closed)
    
    When PR is merged:
    - Promote PR graph to main
    - Cleanup PR graph
    - Next PR will use updated baseline
    """
    logger.info(f"GitHub webhook: {event.action}")
    
    if not event.pull_request or not event.repository:
        return {"status": "ignored", "reason": "Missing payload"}
    
    owner = event.repository.get("owner", {}).get("login", "")
    repo = event.repository.get("name", "")
    pr_number = event.pull_request.get("number", 0)
    is_merged = event.pull_request.get("merged", False)
    
    if not owner or not repo or not pr_number:
        return {"status": "ignored", "reason": "Invalid payload"}
    
    # Only handle merged PRs
    if event.action == "closed" and is_merged:
        logger.info(f"PR merged: {owner}/{repo}#{pr_number}")
        
        if not registry.get(owner, repo):
            logger.warning(f"Repo not registered: {owner}/{repo}")
            return {"status": "ignored", "reason": "Repo not registered"}
        
        try:
            # Promote PR graph to main
            lifecycle.promote_pr_to_main(owner, repo, pr_number)
            logger.info(f"Promoted PR#{pr_number} graph to main")
            
            return {
                "status": "processed",
                "action": "promoted",
                "repo": f"{owner}/{repo}",
                "pr_number": pr_number,
            }
        except Exception as e:
            logger.error(f"Failed to promote PR graph: {e}", exc_info=True)
            return {
                "status": "error",
                "reason": str(e),
            }
    
    return {"status": "ignored", "reason": "Event not handled"}

# ─── Poller Endpoints (S6) ──────────────────────────────────────────────


class PollerStartRequest(BaseModel):
    github_token: Optional[str] = None
    interval_seconds: Optional[int] = None


@app.post("/api/poller/start", tags=["poller"])
async def start_poller(request: PollerStartRequest = None):
    """Start the background PR poller."""
    if request and request.github_token:
        poller.token = request.github_token
    if request and request.interval_seconds:
        poller.interval = request.interval_seconds
    poller.start()
    return {"status": "started", "interval": poller.interval}


@app.post("/api/poller/stop", tags=["poller"])
async def stop_poller():
    """Stop the background PR poller."""
    poller.stop()
    return {"status": "stopped"}


@app.get("/api/poller/status", tags=["poller"])
async def poller_status():
    """Get poller status."""
    return {
        "running": poller.is_running,
        "interval": poller.interval,
        "known_prs": {k: list(v) for k, v in poller.known_prs.items()},
    }


# ─── Chatbot UI (S5) ────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse, tags=["ui"])
async def chatbot_ui():
    """Serve the chatbot UI."""
    ui_path = Path(__file__).parent / "ui" / "index.html"
    if ui_path.exists():
        content = ui_path.read_text(encoding="utf-8")
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        return HTMLResponse(content=content, headers=headers)
    return HTMLResponse("<h1>UI not found</h1><p>Create extension/ui/index.html</p>")
