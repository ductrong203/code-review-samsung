"""
PRPoller — Background poller that auto-builds PR graphs.

Polls GitHub API for open PRs on registered repos, auto-builds PR graphs
when new PRs are detected, and promotes/cleans up when PRs are merged/closed.
"""
import logging
import subprocess
import threading
import time
from typing import Dict, Set, Optional

import requests

from graph_manager.lifecycle import GraphLifecycleManager
from graph_manager.registry import RepoRegistry

logger = logging.getLogger(__name__)


class PRPoller:
    """Poll GitHub API, auto-build PR graphs when new PRs detected."""

    def __init__(
        self,
        registry: RepoRegistry,
        lifecycle: GraphLifecycleManager,
        github_token: str = "",
        interval_seconds: int = 120,
    ):
        self.registry = registry
        self.lifecycle = lifecycle
        self.token = github_token
        self.interval = interval_seconds
        self.known_prs: Dict[str, Set[int]] = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            h["Authorization"] = f"token {self.token}"
        return h

    def start(self):
        """Start polling in a background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Poller already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(f"PRPoller started (interval={self.interval}s)")

    def stop(self):
        """Stop the poller."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("PRPoller stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                repos = self.registry.list_all()
                for repo in repos:
                    if self._stop_event.is_set():
                        break
                    self._check_repo(repo)
            except Exception as e:
                logger.error(f"Poll cycle error: {e}")
            self._stop_event.wait(self.interval)

    def _check_repo(self, repo: dict):
        owner, name = repo["owner"], repo["name"]
        key = f"{owner}/{name}"

        prs = self._fetch_open_prs(owner, name)
        known = self.known_prs.setdefault(key, set())
        open_nums = {p["number"] for p in prs}

        # Build graphs for new PRs
        for pr in prs:
            pr_num = pr["number"]
            base_branch = (pr.get("base") or {}).get("ref") or "main"
            if pr_num not in known and not self.lifecycle.pr_graph_ready(owner, name, pr_num):
                known.add(pr_num)
                try:
                    changed = self._fetch_pr_files(owner, name, pr_num)
                    if changed:
                        from pathlib import Path
                        repo_root = Path(repo["local_path"])
                        if not self.lifecycle.branch_graph_ready(owner, name, base_branch):
                            if self._current_git_branch(repo_root) != base_branch:
                                logger.warning(
                                    "Skipping auto-build for %s#%s: checkout is not on base branch %s",
                                    key,
                                    pr_num,
                                    base_branch,
                                )
                                continue
                            self.lifecycle.build_branch_graph(
                                owner, name, base_branch, repo_root,
                            )
                        self.lifecycle.build_pr_graph(
                            owner, name, repo_root,
                            pr_num, changed, base_branch=base_branch,
                        )
                        logger.info(f"Auto-built PR graph: {key}#{pr_num}")
                except Exception as e:
                    logger.error(f"Auto-build failed for {key}#{pr_num}: {e}")
            else:
                known.add(pr_num)

        # Handle closed/merged PRs
        closed = known - open_nums
        for pr_num in closed:
            state = self._get_pr_state(owner, name, pr_num)
            if state == "merged":
                base_branch = self._get_pr_base_branch(owner, name, pr_num)
                self.lifecycle.promote_pr_to_branch(
                    owner, name, pr_num, base_branch,
                )
                logger.info(f"Promoted merged PR: {key}#{pr_num}")
            else:
                self.lifecycle.cleanup_pr(owner, name, pr_num)
                logger.info(f"Cleaned up closed PR: {key}#{pr_num}")
            known.discard(pr_num)

    def _fetch_open_prs(self, owner: str, repo: str) -> list:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls?state=open&per_page=30",
                headers=self._headers, timeout=15,
            )
            return r.json() if r.ok else []
        except Exception:
            return []

    def _fetch_pr_files(self, owner: str, repo: str, pr_num: int) -> list:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}/files",
                headers=self._headers, timeout=15,
            )
            if r.ok:
                return [f["filename"] for f in r.json() if f.get("status") != "removed"]
        except Exception:
            pass
        return []

    def _get_pr_state(self, owner: str, repo: str, pr_num: int) -> str:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}",
                headers=self._headers, timeout=15,
            )
            if r.ok:
                data = r.json()
                return "merged" if data.get("merged") else data.get("state", "closed")
        except Exception:
            pass
        return "closed"

    def _get_pr_base_branch(self, owner: str, repo: str, pr_num: int) -> str:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}",
                headers=self._headers, timeout=15,
            )
            if r.ok:
                return ((r.json().get("base") or {}).get("ref")) or "main"
        except Exception:
            pass
        return "main"

    def _current_git_branch(self, repo_root) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(repo_root),
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            branch = result.stdout.strip()
            return None if branch == "HEAD" else branch
        except Exception:
            return None
