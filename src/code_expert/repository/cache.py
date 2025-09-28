"""
Repository caching functionality.
"""

import json
import logging
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set

import filelock

logger = logging.getLogger(__name__)


@dataclass
class RepositoryMetadata:
    """Metadata for a cached repository"""

    path: str
    url: Optional[str]
    last_access: str  # Changed from float to str for ISO format
    branch: Optional[str] = None  # Track the requested branch for cloning
    cache_strategy: Optional[str] = None  # Track which cache strategy was used
    clone_status: Dict[str, Any] = None
    repo_map_status: Optional[Dict[str, Any]] = None
    critical_files_analysis: Optional[Dict[str, Any]] = None  # Cache for critical files analysis
    next_refresh_time: Optional[str] = None  # ISO format timestamp for auto-refresh scheduling

    def __post_init__(self):
        # Only set default if clone_status is explicitly None (not just empty dict)
        if self.clone_status is None:
            self.clone_status = {
                "status": "not_started",
                "started_at": None,
                "completed_at": None,
                "error": None,
            }


class RepositoryCache:
    def __init__(
        self, cache_dir: Path, max_cached_repos: int = 50, cleanup_interval: int = 86400
    ):
        # cache_dir is now expected to be a Path object from RepositoryManager
        self.cache_dir = cache_dir
        self.max_cached_repos = max_cached_repos
        self.cleanup_interval = cleanup_interval
        self.metadata_file = self.cache_dir / "metadata.json"
        # Define the primary lock file path. FileLock will append its own suffix or use this.
        # Let's use a distinct name for the lock file that FileLock will manage.
        self.actual_lock_file_path = str(self.cache_dir / "cache.fslock")

        # Create cache directory and lock file if they don't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # No need to manually touch self.lock_file for FileLock library itself,
        # but the original code had self.lock_file = self.cache_dir / "cache.lock"
        # and touched it. If other parts of the code use self.lock_file directly (they shouldn't for locking),
        # this might need review. For now, we assume _file_lock is the sole mechanism.
        # The old self.lock_file was just for fcntl to operate on an open file descriptor.
        # FileLock manages its own lock file based on the path string.

    @contextmanager
    def _file_lock(self):
        """File-based lock to handle concurrent operations using the FileLock library."""
        # timeout=0 means it will try to acquire the lock once and fail immediately if it can't.
        # A very small positive timeout (e.g., 0.05 for 50ms) allows for extremely brief contention.
        lock = filelock.FileLock(self.actual_lock_file_path, timeout=0.05)
        try:
            with lock: # This attempts to acquire the lock within the timeout
                yield
        except filelock.Timeout:
            # If we can't get the lock, mirror the original behavior: yield anyway.
            # This implies that operations under this lock can tolerate proceeding
            # without the lock if it cannot be acquired immediately.
            logger.warning(
                f"Could not acquire file lock on {self.actual_lock_file_path} within timeout. "
                "Proceeding without lock, as per original fallback behavior."
            )
            yield

    def _get_actual_repos(self) -> Set[str]:
        """Get set of actual repository paths on disk"""
        repos = set()
        # Walk through the cache directory structure
        for host_dir in self.cache_dir.iterdir():
            if not host_dir.is_dir() or host_dir.name in {".git", "__pycache__", "metadata.json", "cache.fslock"}:
                continue

            if host_dir.name == "github":
                # For GitHub repos, use org/repo structure
                for org_dir in host_dir.iterdir():
                    if not org_dir.is_dir():
                        continue
                    for repo_dir in org_dir.iterdir():
                        if repo_dir.is_dir():
                            repos.add(str(repo_dir.resolve()))
                            
            elif host_dir.name == "azure":
                # For Azure DevOps repos, use org/project/repo structure
                for org_dir in host_dir.iterdir():
                    if not org_dir.is_dir():
                        continue
                    for project_dir in org_dir.iterdir():
                        if not project_dir.is_dir():
                            continue
                        for repo_dir in project_dir.iterdir():
                            if repo_dir.is_dir():
                                repos.add(str(repo_dir.resolve()))
                                
            elif host_dir.name == "local":
                # For local repos, only add the immediate subdirectories
                for repo_dir in host_dir.iterdir():
                    if repo_dir.is_dir():
                        repos.add(str(repo_dir.resolve()))
            else:
                # Generic handling for other providers (future-proof)
                # Recursively find all leaf directories (repos)
                def find_repo_dirs(path, depth=0, max_depth=3):
                    if depth > max_depth:
                        return
                    for item in path.iterdir():
                        if item.is_dir():
                            # Check if this looks like a repo (has .git or is a leaf)
                            has_git = (item / ".git").exists()
                            has_subdirs = any(p.is_dir() for p in item.iterdir() if p.name not in {".git", "__pycache__"})
                            
                            if has_git or not has_subdirs:
                                repos.add(str(item.resolve()))
                            else:
                                find_repo_dirs(item, depth + 1, max_depth)
                
                find_repo_dirs(host_dir)

        return repos

    def _write_metadata(self, metadata: Dict[str, RepositoryMetadata]):
        """Write metadata to file in atomic operation"""
        data = {
            path: {
                "url": meta.url,
                "last_access": meta.last_access,
                "branch": meta.branch,
                "cache_strategy": meta.cache_strategy,
                "clone_status": meta.clone_status,
                "repo_map_status": meta.repo_map_status,
                "critical_files_analysis": meta.critical_files_analysis,
            }
            for path, meta in metadata.items()
        }

        with open(self.metadata_file, "w") as f:
            json.dump(data, f, indent=2)

    def _read_metadata(self) -> Dict[str, RepositoryMetadata]:
        """Read metadata from file"""
        metadata = {}
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r") as f:
                    data = json.load(f)

                for path, info in data.items():
                    metadata[path] = RepositoryMetadata(
                        path=path,
                        url=info.get("url"),
                        last_access=info.get("last_access", ""),
                        branch=info.get("branch"),
                        cache_strategy=info.get("cache_strategy"),
                        clone_status=info.get("clone_status"),
                        repo_map_status=info.get("repo_map_status"),
                        critical_files_analysis=info.get("critical_files_analysis"),
                    )
            except json.JSONDecodeError:
                logger.warning(f"Error decoding JSON from metadata file {self.metadata_file}. Starting with empty metadata.")
        return metadata

    def _sync_metadata(self) -> Dict[str, RepositoryMetadata]:
        """Synchronize metadata with disk state"""
        metadata = self._read_metadata()
        actual_repos = self._get_actual_repos()

        # Remove metadata for missing repos
        for path in list(metadata.keys()):
            if path not in actual_repos:
                del metadata[path]

        # Add missing repos to metadata
        for path in actual_repos:
            if path not in metadata:
                metadata[path] = RepositoryMetadata(
                    path=path, url=None, last_access=datetime.now().isoformat()
                )

        self._write_metadata(metadata)
        return metadata

    async def prepare_for_clone(self, target_path: str) -> bool:
        """
        Prepare cache for a new repository clone.
        Returns True if clone can proceed, False if not.
        """
        with self._file_lock():
            metadata = self._sync_metadata()

            # If target already exists in metadata, treat as success
            # (This just means we have metadata for it, not that clone is complete)
            if target_path in metadata:
                return True

            # If we're at limit, cleanup oldest
            if len(metadata) >= self.max_cached_repos:
                sorted_repos = sorted(
                    metadata.items(),
                    key=lambda x: datetime.fromisoformat(x[1].last_access),
                )

                # Remove oldest repo
                oldest_path, _ = sorted_repos[0]
                try:
                    repo_path = Path(oldest_path)
                    if repo_path.exists():
                        shutil.rmtree(repo_path)
                    del metadata[oldest_path]
                    self._write_metadata(metadata)
                except Exception as e:
                    logger.error(f"Failed to remove old repo {oldest_path}: {e}")
                    return False

            return True

    async def add_repo(self, path: str, url: Optional[str] = None, branch: Optional[str] = None, cache_strategy: Optional[str] = None):
        """Register a new repository after successful clone"""
        with self._file_lock():
            metadata = self._read_metadata()  # Use _read_metadata to preserve existing data
            if path in metadata:
                # Update existing metadata, preserving clone_status and other fields
                metadata[path].url = url
                metadata[path].branch = branch
                metadata[path].cache_strategy = cache_strategy
                metadata[path].last_access = datetime.now().isoformat()
            else:
                # Create new metadata only if it doesn't exist
                metadata[path] = RepositoryMetadata(
                    path=path,
                    url=url,
                    branch=branch,
                    cache_strategy=cache_strategy,
                    last_access=datetime.now().isoformat(),
                    repo_map_status=None,
                )
            self._write_metadata(metadata)

    async def update_access(self, path: str):
        """Update access time for a repository"""
        with self._file_lock():
            metadata = self._sync_metadata()
            if path in metadata:
                metadata[path].last_access = datetime.now().isoformat()
                self._write_metadata(metadata)

    async def remove_repo(self, path: str):
        """Remove a repository from cache"""
        with self._file_lock():
            metadata = self._sync_metadata()
            if path in metadata:
                try:
                    repo_path = Path(path)
                    if repo_path.exists():
                        shutil.rmtree(repo_path)
                    del metadata[path]
                    self._write_metadata(metadata)
                except Exception as e:
                    logger.error(f"Failed to remove repo {path}: {e}")
                    raise

    async def cleanup_old_repos(self):
        """Remove old cached repositories if over limit."""
        with self._file_lock():
            metadata = self._sync_metadata()

            if len(metadata) <= self.max_cached_repos:
                return

            # Sort by last access time
            sorted_repos = sorted(
                metadata.items(), key=lambda x: datetime.fromisoformat(x[1].last_access)
            )

            # Remove oldest until under limit
            while len(metadata) > self.max_cached_repos:
                oldest_path, _ = sorted_repos.pop(0)
                try:
                    repo_path = Path(oldest_path)
                    if repo_path.exists():
                        shutil.rmtree(repo_path)
                    del metadata[oldest_path]
                except Exception as e:
                    logger.error(f"Error removing repository {oldest_path}: {e}")

            self._write_metadata(metadata)

    async def update_clone_status(self, path: str, status: Dict[str, Any]):
        """Update clone status while preserving repo map status"""
        logger.debug(f"update_clone_status called for path: {path}, status: {status}")
        with self._file_lock():
            metadata = self._read_metadata()
            if path not in metadata:
                logger.debug(f"Creating new metadata entry for path: {path}")
                metadata[path] = RepositoryMetadata(
                    path=path, url=None, last_access=datetime.now().isoformat()
                )
            logger.debug(f"Setting clone_status to: {status}")
            metadata[path].clone_status = status
            self._write_metadata(metadata)
            logger.debug(f"Metadata written successfully for path: {path}")

    async def update_repo_map_status(self, path: str, status: Dict[str, Any]):
        """Update repo map status while preserving clone status"""
        with self._file_lock():
            metadata = self._read_metadata()
            if path not in metadata:
                metadata[path] = RepositoryMetadata(
                    path=path, url=None, last_access=datetime.now().isoformat()
                )
            metadata[path].repo_map_status = status
            self._write_metadata(metadata)

    async def update_critical_files_analysis(self, path: str, analysis: Dict[str, Any]):
        """Update critical files analysis cache"""
        with self._file_lock():
            metadata = self._read_metadata()
            if path not in metadata:
                metadata[path] = RepositoryMetadata(
                    path=path, url=None, last_access=datetime.now().isoformat()
                )
            metadata[path].critical_files_analysis = analysis
            self._write_metadata(metadata)

    async def update_next_refresh_time(self, path: str, next_refresh_time: Optional[str]):
        """Update next refresh time for auto-refresh scheduling"""
        with self._file_lock():
            metadata = self._read_metadata()
            if path not in metadata:
                metadata[path] = RepositoryMetadata(
                    path=path, url=None, last_access=datetime.now().isoformat()
                )
            metadata[path].next_refresh_time = next_refresh_time
            self._write_metadata(metadata)

    async def get_repository_status(self, path: str) -> Dict[str, Any]:
        """Get combined status information for a repository"""
        with self._file_lock():
            metadata = self._read_metadata()
            if path not in metadata:
                return {"status": "error", "error": "Repository not found in cache"}

            repo_metadata = metadata[path]
            status = {
                "clone_status": repo_metadata.clone_status,
                "repo_map_status": repo_metadata.repo_map_status,
                "requested_branch": repo_metadata.branch,
            }
            
            # Try to get the current active branch from the git repository
            try:
                from git import Repo
                repo = Repo(path)
                if repo.head.is_detached:
                    status["current_branch"] = f"detached at {repo.head.commit.hexsha[:8]}"
                else:
                    status["current_branch"] = repo.active_branch.name
            except Exception as e:
                # If we can't get git info, it might not be a git repo or might have issues
                status["current_branch"] = None
                status["branch_error"] = str(e)
            
            return status
