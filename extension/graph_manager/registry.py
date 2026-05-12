"""
Graph Manager — Registry for tracking registered repositories.

Stores repo registration data (owner, name, local_path) in a JSON file.
"""
import json
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_PATH = (
    Path(os.environ.get("CRG_GRAPH_BASE", Path.home() / ".crg_graphs"))
    / "registry.json"
)


class RepoRegistry:
    """Manages the list of registered repositories."""

    def __init__(self, registry_path: Path = DEFAULT_REGISTRY_PATH):
        self.registry_path = registry_path
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._repos: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        """Load registry from disk."""
        if self.registry_path.exists():
            try:
                data = json.loads(self.registry_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load registry: {e}")
        return []

    def _save(self) -> None:
        """Persist registry to disk."""
        self.registry_path.write_text(
            json.dumps(self._repos, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def register(self, owner: str, name: str, local_path: str) -> Dict[str, Any]:
        """
        Register a repo for graph tracking.

        Args:
            owner: GitHub owner (e.g. 'facebook')
            name: Repo name (e.g. 'react')
            local_path: Absolute path to the locally cloned repo

        Returns:
            The registered repo entry
        """
        key = f"{owner}/{name}"

        # Check if already registered
        for repo in self._repos:
            if f"{repo['owner']}/{repo['name']}" == key:
                # Update local_path if changed
                repo["local_path"] = local_path
                self._save()
                logger.info(f"Updated repo: {key} -> {local_path}")
                return repo

        entry = {
            "owner": owner,
            "name": name,
            "local_path": local_path,
        }
        self._repos.append(entry)
        self._save()
        logger.info(f"Registered repo: {key} -> {local_path}")
        return entry

    def unregister(self, owner: str, name: str) -> bool:
        """Remove a repo from the registry. Returns True if found and removed."""
        key = f"{owner}/{name}"
        before = len(self._repos)
        self._repos = [
            r for r in self._repos
            if f"{r['owner']}/{r['name']}" != key
        ]
        if len(self._repos) < before:
            self._save()
            logger.info(f"Unregistered repo: {key}")
            return True
        return False

    def get(self, owner: str, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific repo entry."""
        key = f"{owner}/{name}"
        for repo in self._repos:
            if f"{repo['owner']}/{repo['name']}" == key:
                return repo
        return None

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all registered repos."""
        return list(self._repos)
