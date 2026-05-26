"""
Graph Manager — Lifecycle management for graph databases.

Handles building, copying, promoting, and cleaning up graph databases:
- branch_{name}.db: Full graph of a target/base branch
- pr_{N}.db: Copy of branch_{name}.db + incremental update with PR changes

Uses the real `code_review_graph` library API:
- full_build(repo_root, store) for initial full build
- incremental_update(repo_root, store, changed_files=...) for PR updates
"""
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GraphLifecycleManager:
    """
    Manages the lifecycle of graph databases for repos and PRs.

    Database layout:
        ~/.crg_graphs/{owner}/{repo}/branch_{name}.db - full graph of a branch
        ~/.crg_graphs/{owner}/{repo}/pr_{N}.db - PR-specific graph
    """

    BASE = Path(os.environ.get("CRG_GRAPH_BASE", Path.home() / ".crg_graphs"))

    def build_branch_graph(
        self,
        owner: str,
        repo: str,
        branch: str,
        repo_root: Path,
    ) -> dict:
        """
        Build a target/base branch graph from scratch.

        PR graphs are copied from this branch baseline before the PR's changed
        files are applied, so review context matches the branch the PR targets.

        Args:
            owner: GitHub owner
            repo: Repository name
            branch: Target/base branch name
            repo_root: Local path to the cloned repository

        Returns:
            Build statistics from code-review-graph
        """
        from code_review_graph.incremental import full_build
        from code_review_graph.graph import GraphStore

        db_path = self._db(owner, repo, self._branch_db_name(branch))
        logger.info(f"Building branch graph: {owner}/{repo}@{branch} -> {db_path}")

        store = GraphStore(str(db_path))
        try:
            stats = full_build(repo_root, store)
            logger.info(
                f"Branch graph built: {stats.get('total_nodes', 0)} nodes, "
                f"{stats.get('total_edges', 0)} edges"
            )
            return stats
        finally:
            store.close()

    def build_main_graph(self, owner: str, repo: str, repo_root: Path) -> dict:
        """Backward-compatible wrapper for callers that still build main."""
        return self.build_branch_graph(owner, repo, "main", repo_root)

    def build_pr_graph(
        self, owner: str, repo: str, repo_root: Path,
        pr_number: int, changed_files: list[str], base_branch: str = "main"
    ) -> dict:
        """
        Build a PR-specific graph by copying the target branch DB and updating.

        Steps:
        1. Copy branch_{base_branch}.db -> pr_{N}.db
        2. Run incremental_update with the PR's changed files

        Args:
            owner: GitHub owner
            repo: Repository name
            repo_root: Local path to the repo (checked out to PR branch)
            pr_number: PR number
            changed_files: List of file paths changed in the PR
            base_branch: PR target/base branch name

        Returns:
            Update statistics from code-review-graph
        """
        from code_review_graph.incremental import incremental_update
        from code_review_graph.graph import GraphStore

        base_db = self._db(owner, repo, self._branch_db_name(base_branch))
        if not base_db.exists() and base_branch == "main":
            legacy_main_db = self._db(owner, repo, "main.db")
            if legacy_main_db.exists():
                base_db = legacy_main_db
        pr_db = self._db(owner, repo, f"pr_{pr_number}.db")

        if not base_db.exists():
            raise FileNotFoundError(
                f"Branch graph not found: {base_db}. "
                f"Run build_branch_graph for '{base_branch}' first."
            )

        # Copy target branch graph as the base for this PR.
        logger.info(f"Copying {base_db.name} -> pr_{pr_number}.db")
        shutil.copy2(str(base_db), str(pr_db))

        # Incrementally update with PR changes
        store = GraphStore(str(pr_db))
        try:
            stats = incremental_update(
                repo_root, store,
                changed_files=changed_files,
            )
            logger.info(
                f"PR graph built: pr_{pr_number}.db — "
                f"{stats.get('files_updated', 0)} files updated"
            )
            return stats
        finally:
            store.close()

    def promote_pr_to_branch(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        base_branch: str = "main",
    ) -> None:
        """
        Replace the target branch DB with the merged PR's graph.

        Called when a PR is merged — the PR graph becomes the new baseline.
        """
        pr_db = self._db(owner, repo, f"pr_{pr_number}.db")
        branch_db = self._db(owner, repo, self._branch_db_name(base_branch))

        if pr_db.exists():
            # Remove old branch DB WAL/SHM sidecars if any
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = branch_db.parent / f"{branch_db.name}{suffix}"
                if sidecar.exists():
                    sidecar.unlink()

            shutil.move(str(pr_db), str(branch_db))
            logger.info(f"Promoted pr_{pr_number}.db -> {branch_db.name}")

            # Cleanup PR sidecars
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = pr_db.parent / f"pr_{pr_number}.db{suffix}"
                if sidecar.exists():
                    sidecar.unlink()
        else:
            logger.warning(f"PR graph not found for promotion: {pr_db}")

    def promote_pr_to_main(self, owner: str, repo: str, pr_number: int) -> None:
        """Backward-compatible wrapper for older callers."""
        self.promote_pr_to_branch(owner, repo, pr_number, "main")

    def cleanup_pr(self, owner: str, repo: str, pr_number: int) -> None:
        """
        Remove only the PR graph database and SQLite sidecars.

        Branch graph DBs are intentionally preserved as repo-level caches.
        """
        db = self._db(owner, repo, f"pr_{pr_number}.db")
        removed = False
        for path in (
            db,
            db.parent / f"{db.name}-wal",
            db.parent / f"{db.name}-shm",
            db.parent / f"{db.name}-journal",
        ):
            if path.exists():
                path.unlink()
                removed = True

        if removed:
            logger.info(f"Cleaned up pr_{pr_number}.db")

    def cleanup_repo(self, owner: str, repo: str) -> dict:
        """
        Remove all local graph artifacts for a registered repo.

        This deletes branch_*.db, pr_*.db, SQLite sidecars, and temporary PR
        worktree folders under CRG_GRAPH_BASE. It does not delete the cloned
        source repository path registered by the user.
        """
        repo_dir = self.BASE / owner / repo
        worktree_dir = self.BASE / "worktrees" / owner / repo
        removed = {
            "graph_dir": str(repo_dir),
            "worktree_dir": str(worktree_dir),
            "removed_graph_dir": False,
            "removed_worktree_dir": False,
        }

        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)
            removed["removed_graph_dir"] = True

        if worktree_dir.exists():
            shutil.rmtree(worktree_dir, ignore_errors=True)
            removed["removed_worktree_dir"] = True

        logger.info(
            "Cleaned local graph artifacts for %s/%s: graph_dir=%s worktree_dir=%s",
            owner,
            repo,
            removed["removed_graph_dir"],
            removed["removed_worktree_dir"],
        )
        return removed

    def pr_graph_ready(self, owner: str, repo: str, pr_number: int) -> bool:
        """Check if a PR graph database exists and is ready for querying."""
        return self._db(owner, repo, f"pr_{pr_number}.db").exists()

    def main_graph_ready(self, owner: str, repo: str) -> bool:
        """Check if the backward-compatible main branch graph exists."""
        return self.branch_graph_ready(owner, repo, "main")

    def branch_graph_ready(self, owner: str, repo: str, branch: str) -> bool:
        """Check if a target/base branch graph database exists."""
        if self._db(owner, repo, self._branch_db_name(branch)).exists():
            return True
        return branch == "main" and self._db(owner, repo, "main.db").exists()

    def get_pr_db_path(self, owner: str, repo: str, pr_number: int) -> Optional[Path]:
        """Get the path to a PR graph database, or None if it doesn't exist."""
        db = self._db(owner, repo, f"pr_{pr_number}.db")
        return db if db.exists() else None

    def get_main_db_path(self, owner: str, repo: str) -> Optional[Path]:
        """Get the path to the main branch graph database, or None."""
        return self.get_branch_db_path(owner, repo, "main")

    def get_branch_db_path(
        self,
        owner: str,
        repo: str,
        branch: str,
    ) -> Optional[Path]:
        """Get the path to a branch graph database, or None if absent."""
        db = self._db(owner, repo, self._branch_db_name(branch))
        if not db.exists() and branch == "main":
            legacy_db = self._db(owner, repo, "main.db")
            if legacy_db.exists():
                return legacy_db
        return db if db.exists() else None

    def _branch_db_name(self, branch: str) -> str:
        safe = "".join(
            c if c.isalnum() or c in {"-", "_", "."} else "_"
            for c in (branch or "main")
        ).strip("._")
        return f"branch_{safe or 'main'}.db"

    def _db(self, owner: str, repo: str, filename: str) -> Path:
        """Get the path to a graph database file, creating parent dirs."""
        d = self.BASE / owner / repo
        d.mkdir(parents=True, exist_ok=True)
        return d / filename
