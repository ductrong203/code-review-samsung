"""
Graph Manager — Lifecycle management for graph databases.

Handles building, copying, promoting, and cleaning up graph databases:
- main.db: Full graph of the main/master branch
- pr_{N}.db: Copy of main.db + incremental update with PR changes

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
        ~/.crg_graphs/{owner}/{repo}/main.db      — full graph of default branch
        ~/.crg_graphs/{owner}/{repo}/pr_{N}.db     — PR-specific graph
    """

    BASE = Path(os.environ.get("CRG_GRAPH_BASE", Path.home() / ".crg_graphs"))

    def build_main_graph(self, owner: str, repo: str, repo_root: Path) -> dict:
        """
        Build the main graph from scratch (full AST parse of the entire repo).

        This is called once when a repo is first registered, and again if
        the main branch is significantly updated.

        Args:
            owner: GitHub owner
            repo: Repository name
            repo_root: Local path to the cloned repository

        Returns:
            Build statistics from code-review-graph
        """
        from code_review_graph.incremental import full_build
        from code_review_graph.graph import GraphStore

        db_path = self._db(owner, repo, "main.db")
        logger.info(f"Building main graph: {owner}/{repo} -> {db_path}")

        store = GraphStore(str(db_path))
        try:
            stats = full_build(repo_root, store)
            logger.info(
                f"Main graph built: {stats.get('total_nodes', 0)} nodes, "
                f"{stats.get('total_edges', 0)} edges"
            )
            return stats
        finally:
            store.close()

    def build_pr_graph(
        self, owner: str, repo: str, repo_root: Path,
        pr_number: int, changed_files: list[str]
    ) -> dict:
        """
        Build a PR-specific graph by copying main.db and incrementally updating.

        Steps:
        1. Copy main.db -> pr_{N}.db
        2. Run incremental_update with the PR's changed files

        Args:
            owner: GitHub owner
            repo: Repository name
            repo_root: Local path to the repo (checked out to PR branch)
            pr_number: PR number
            changed_files: List of file paths changed in the PR

        Returns:
            Update statistics from code-review-graph
        """
        from code_review_graph.incremental import incremental_update
        from code_review_graph.graph import GraphStore

        main_db = self._db(owner, repo, "main.db")
        pr_db = self._db(owner, repo, f"pr_{pr_number}.db")

        if not main_db.exists():
            raise FileNotFoundError(
                f"Main graph not found: {main_db}. "
                f"Run build_main_graph first."
            )

        # Copy main.db as the base for this PR
        logger.info(f"Copying main.db -> pr_{pr_number}.db")
        shutil.copy2(str(main_db), str(pr_db))

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

    def promote_pr_to_main(self, owner: str, repo: str, pr_number: int) -> None:
        """
        Replace main.db with the merged PR's graph.

        Called when a PR is merged — the PR graph becomes the new baseline.
        """
        pr_db = self._db(owner, repo, f"pr_{pr_number}.db")
        main_db = self._db(owner, repo, "main.db")

        if pr_db.exists():
            # Remove old main.db WAL/SHM sidecars if any
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = main_db.parent / f"{main_db.name}{suffix}"
                if sidecar.exists():
                    sidecar.unlink()

            shutil.move(str(pr_db), str(main_db))
            logger.info(f"Promoted pr_{pr_number}.db -> main.db")

            # Cleanup PR sidecars
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = pr_db.parent / f"pr_{pr_number}.db{suffix}"
                if sidecar.exists():
                    sidecar.unlink()
        else:
            logger.warning(f"PR graph not found for promotion: {pr_db}")

    def cleanup_pr(self, owner: str, repo: str, pr_number: int) -> None:
        """
        Remove only the PR graph database and SQLite sidecars.

        main.db is intentionally preserved as the repo-level cache.
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

        This deletes main.db, pr_*.db, SQLite sidecars, and temporary PR
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
        """Check if the main graph database exists."""
        return self._db(owner, repo, "main.db").exists()

    def get_pr_db_path(self, owner: str, repo: str, pr_number: int) -> Optional[Path]:
        """Get the path to a PR graph database, or None if it doesn't exist."""
        db = self._db(owner, repo, f"pr_{pr_number}.db")
        return db if db.exists() else None

    def get_main_db_path(self, owner: str, repo: str) -> Optional[Path]:
        """Get the path to the main graph database, or None if it doesn't exist."""
        db = self._db(owner, repo, "main.db")
        return db if db.exists() else None

    def _db(self, owner: str, repo: str, filename: str) -> Path:
        """Get the path to a graph database file, creating parent dirs."""
        d = self.BASE / owner / repo
        d.mkdir(parents=True, exist_ok=True)
        return d / filename
