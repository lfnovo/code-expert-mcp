"""
Repository management and operations.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union, Literal

import git
import pathspec
from git.repo import Repo

from ..config import RepositoryConfig
from .cache import RepositoryCache, RepositoryMetadata
from .path_utils import get_cache_path, is_git_url
from .providers.registry import get_default_registry

logger = logging.getLogger(__name__)

# Import auto-refresh components - handle gracefully if not available
try:
    from .auto_refresh import AutoRefreshManager
    from ..config import AutoRefreshConfig
    AUTO_REFRESH_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Auto-refresh functionality not available: {e}")
    AUTO_REFRESH_AVAILABLE = False
    AutoRefreshManager = None
    AutoRefreshConfig = None


class Repository:
    def __init__(
        self,
        repo_id: str,
        root_path: Path,
        repo_type: str,
        is_git: bool,
        url: Optional[str] = None,
        branch: Optional[str] = None,
        manager: Optional["RepositoryManager"] = None,
    ):
        self.id = repo_id
        self.root_path = Path(root_path)
        self.repo_type = repo_type
        self.is_git = is_git
        self.url = url
        self.branch = branch
        self._git_repo: Optional[Repo] = None
        self._manager = manager

        if self.is_git and self.root_path.exists():
            self._git_repo = Repo(self.root_path)

    def is_ignored(self, path: Union[str, Path]) -> bool:
        """Check if a path should be ignored based on .gitignore patterns.

        Args:
            path: Path to check, either as string or Path object

        Returns:
            True if path matches any gitignore pattern, False otherwise
        """
        gitignore_path = self.root_path / ".gitignore"
        if not gitignore_path.exists():
            return False

        with open(gitignore_path, "r") as f:
            patterns = f.read().splitlines()

        spec = pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern, patterns
        )

        if isinstance(path, str):
            path = Path(path)

        rel_path = str(path.relative_to(self.root_path) if path.is_absolute() else path)
        return spec.match_file(rel_path)

    async def get_resource(self, resource_path: str) -> Dict[str, Any]:
        """Get contents of a file or directory listing."""
        path = self.root_path / resource_path

        if not path.exists():
            raise FileNotFoundError(f"Resource not found: {resource_path}")

        if path.is_file():
            return {
                "type": "file",
                "path": str(resource_path),
                "content": path.read_text(),
            }
        else:
            return {
                "type": "directory",
                "path": str(resource_path),
                "contents": [
                    str(p.relative_to(self.root_path)) for p in path.iterdir()
                ],
            }

    async def refresh(self) -> Dict[str, Any]:
        """Update repository with latest changes."""
        if self._manager:
            await self._manager.cache.update_access(str(self.root_path))

        if not self.is_git or not self._git_repo:
            return {"status": "not_git_repo"}

        try:
            origin = self._git_repo.remotes.origin
            origin.pull()
            return {"status": "success", "commit": str(self._git_repo.head.commit)}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class RepositoryManager:
    def __init__(self, config: RepositoryConfig, server_config = None):
        self.config = config
        self.server_config = server_config  # Store full server config for auto-refresh access
        # Use the new method from RepositoryConfig to get the cache directory path
        self.cache_dir = config.get_cache_dir_path()
        # The mkdir is now handled by get_cache_dir_path(), but keeping it here is also fine / doesn't harm.
        # self.cache_dir.mkdir(parents=True, exist_ok=True) # This line can be removed if get_cache_dir_path always ensures existence
        self.repositories: Dict[str, Repository] = {}
        self.cache = RepositoryCache(self.cache_dir, config.max_cached_repos)
        
        # Initialize auto-refresh manager if available and enabled
        self.auto_refresh_manager: Optional[AutoRefreshManager] = None
        if (AUTO_REFRESH_AVAILABLE and 
            server_config and 
            hasattr(server_config, 'auto_refresh') and 
            server_config.auto_refresh and 
            server_config.auto_refresh.enabled):
            try:
                self.auto_refresh_manager = AutoRefreshManager(
                    server_config.auto_refresh, 
                    self
                )
                logger.info("Auto-refresh manager initialized")
            except Exception as e:
                logger.error(f"Failed to initialize auto-refresh manager: {e}")
                self.auto_refresh_manager = None
        else:
            if not AUTO_REFRESH_AVAILABLE:
                logger.debug("Auto-refresh not available due to import error")
            elif not server_config:
                logger.debug("Auto-refresh not initialized - no server config provided")
            elif not hasattr(server_config, 'auto_refresh') or not server_config.auto_refresh:
                logger.debug("Auto-refresh not initialized - no auto_refresh config")
            elif not server_config.auto_refresh.enabled:
                logger.debug("Auto-refresh disabled in configuration")
            else:
                logger.debug("Auto-refresh not initialized for unknown reason")

    def _cleanup_if_needed(self):
        """Remove least recently accessed repositories if over limit."""
        if len(self.repositories) <= self.config.max_cached_repos:
            return

        # Sort repositories by last access time
        sorted_repos = sorted(
            self.repositories.items(), key=lambda x: x[1].last_accessed
        )

        # Remove oldest repositories until under limit
        while len(self.repositories) > self.config.max_cached_repos:
            repo_id, repo = sorted_repos.pop(0)
            try:
                if repo.root_path.exists():
                    shutil.rmtree(repo.root_path)
                del self.repositories[repo_id]
            except Exception as e:
                logger.error(f"Error cleaning up repository {repo_id}: {e}")

    async def get_repository(self, path: str) -> Repository:
        """Get or create a Repository instance for the given path."""
        is_git = is_git_url(path)
        cache_path = get_cache_path(self.cache_dir, path)
        str_path = str(cache_path.resolve())

        # If it's a Git URL and not cached, start async clone
        if is_git and not cache_path.exists():
            try:
                # Ensure we can add another repo before starting clone
                if not await self.cache.prepare_for_clone(str_path):
                    raise Exception("Failed to prepare cache for clone")

                # Start clone in background
                asyncio.create_task(self._do_clone(path, str_path))

                # Create temporary repository instance
                repository = Repository(
                    repo_id=str_path,
                    root_path=cache_path,
                    repo_type="git",
                    is_git=True,
                    url=path,
                    manager=self,
                )
                self.repositories[str_path] = repository

                # Initialize metadata with cloning status for Git repositories
                with self.cache._file_lock():
                    metadata_dict = self.cache._read_metadata()
                    if str_path not in metadata_dict:
                        metadata_dict[str_path] = RepositoryMetadata(
                            path=str_path,
                            url=path,
                            last_access=datetime.now().isoformat(),
                            clone_status={
                                "status": "cloning",
                                "started_at": datetime.now().isoformat(),
                                "completed_at": None,
                                "error": None,
                            }
                        )
                    self.cache._write_metadata(metadata_dict)

                return repository

            except Exception as e:
                raise Exception(f"Failed to start repository clone: {e}")

        # For local paths that aren't in cache, start async copy
        if not is_git and not cache_path.exists():
            original_path = Path(path).resolve()
            if not original_path.exists():
                raise FileNotFoundError(f"Repository not found: {path}")

            try:
                # Ensure we can add another repo before starting copy
                if not await self.cache.prepare_for_clone(str_path):
                    raise Exception("Failed to prepare cache for clone")

                # Start copy in background
                asyncio.create_task(
                    self._do_clone(str(original_path), str_path, is_local=True)
                )

                # Create temporary repository instance
                repository = Repository(
                    repo_id=str_path,
                    root_path=cache_path,
                    repo_type="local",
                    is_git=False,
                    url=path,
                    manager=self,
                )
                self.repositories[str_path] = repository

                # Initialize metadata with copying status for local paths
                with self.cache._file_lock():
                    metadata_dict = self.cache._read_metadata()
                    if str_path not in metadata_dict:
                        metadata_dict[str_path] = RepositoryMetadata(
                            path=str_path,
                            url=path,
                            last_access=datetime.now().isoformat(),
                            clone_status={
                                "status": "copying",
                                "started_at": datetime.now().isoformat(),
                                "completed_at": None,
                                "error": None,
                            }
                        )
                    self.cache._write_metadata(metadata_dict)

                return repository

            except Exception as e:
                raise Exception(f"Failed to start repository copy: {e}")

        # Update access time
        await self.cache.update_access(str(cache_path.resolve()))

        # Check if it's a Git repository
        is_git_repo = False
        url = None
        try:
            repo = Repo(cache_path)
            is_git_repo = True
            if len(repo.remotes) > 0:
                url = repo.remotes.origin.url
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            pass

        # Create or update repository instance
        repo_id = str(cache_path.resolve())  # Use absolute path as ID
        if repo_id in self.repositories:
            return self.repositories[repo_id]

        # Create new repository instance
        repository = Repository(
            repo_id=repo_id,
            root_path=cache_path.resolve(),  # Ensure absolute path
            repo_type="git" if is_git else "local",
            is_git=is_git_repo,
            url=path if is_git else url,
            manager=self,  # Pass manager reference
        )
        self.repositories[repo_id] = repository

        return repository

    async def _do_clone(
        self,
        url: str,
        str_path: str,
        branch: Optional[str] = None,
        is_local: bool = False,
        cache_strategy: Optional[str] = None,
    ):
        """Internal method to perform the actual clone or copy"""
        # Store original URL for metadata/logs
        original_url = url
        cache_path = Path(str_path)

        try:
            # Update status to cloning/copying (preserving existing started_at if present)
            status_msg = "copying" if is_local else "cloning"
            
            # Get current metadata to preserve existing started_at timestamp
            current_metadata = await self.cache.get_repository_status(str_path)
            started_at = datetime.now().isoformat()
            if (current_metadata and 
                current_metadata.get("clone_status") and 
                current_metadata["clone_status"].get("started_at")):
                started_at = current_metadata["clone_status"]["started_at"]
            
            await self.cache.update_clone_status(
                str_path,
                {"status": status_msg, "started_at": started_at},
            )

            # Create parent directories
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            if is_local:
                # For local directories, use copytree with ignore function to exclude common artifacts
                def ignore_artifacts(dir_path, files):
                    """Ignore common build artifacts, dependencies, and temporary files."""
                    ignore_patterns = {
                        # Version control
                        '.git',
                        '.svn',
                        '.hg',
                        
                        # Python
                        '__pycache__',
                        '.pytest_cache',
                        '.tox',
                        '.venv',
                        'venv',
                        '.env',
                        'env',
                        '.virtualenv',
                        'virtualenv',
                        '.pyenv',
                        '*.pyc',
                        '*.pyo',
                        '*.pyd',
                        '.Python',
                        'pip-log.txt',
                        'pip-delete-this-directory.txt',
                        '.mypy_cache',
                        '.ruff_cache',
                        '.coverage',
                        'htmlcov',
                        '.hypothesis',
                        
                        # JavaScript/Node
                        'node_modules',
                        'bower_components',
                        '.npm',
                        '.yarn',
                        '.pnp',
                        '.pnp.js',
                        
                        # Angular specific
                        '.angular',
                        '*.tsbuildinfo',
                        
                        # Build outputs
                        'dist',
                        'build',
                        'out',
                        'target',
                        'bin',
                        'obj',
                        '*.egg-info',
                        
                        # .NET Core / C# specific
                        'Debug',
                        'Release',
                        'x64',
                        'x86',
                        'ARM',
                        'ARM64',
                        'packages',
                        'TestResults',
                        '.vs',
                        '*.user',
                        '*.userosscache',
                        '*.sln.docstates',
                        '.nuget',
                        'project.lock.json',
                        'project.fragment.lock.json',
                        'artifacts/',
                        'PublishProfiles',
                        '*.publishproj',
                        '*.nupkg',
                        '*.snupkg',
                        
                        # IDE and editor files
                        '.idea',
                        '.vscode',
                        '*.swp',
                        '*.swo',
                        '*~',
                        '.DS_Store',
                        'Thumbs.db',
                        
                        # Logs and databases
                        '*.log',
                        '*.sqlite',
                        '*.db',
                        
                        # Package manager locks and caches
                        '.bundle',
                        'vendor/bundle',
                        '.sass-cache',
                        '.parcel-cache',
                        
                        # Web development
                        '.next',
                        '.nuxt',
                        '.vuepress',
                        '.docusaurus',
                        '.serverless',
                        '.webpack',
                        '.turbo',
                        
                        # Other common artifacts
                        '.cache',
                        'cache',
                        'tmp',
                        'temp',
                        '.tmp',
                        '.temp',
                        'coverage',
                        '.nyc_output',
                    }
                    
                    ignored = []
                    for file in files:
                        # Check if file/folder matches any ignore pattern
                        if file in ignore_patterns:
                            ignored.append(file)
                        # Also check for pattern matching (e.g., *.pyc)
                        elif any(file.endswith(pattern.replace('*', '')) for pattern in ignore_patterns if '*' in pattern):
                            ignored.append(file)
                    
                    if ignored:
                        logger.debug(f"Ignoring in {os.path.basename(dir_path)}: {', '.join(ignored)}")
                    
                    return ignored

                await asyncio.to_thread(
                    shutil.copytree,
                    url,
                    cache_path,
                    dirs_exist_ok=True,
                    ignore=ignore_artifacts,
                    symlinks=False,  # Copy the files symlinks point to, not the symlinks themselves
                    ignore_dangling_symlinks=True,  # Skip broken symlinks instead of failing
                )
            else:
                # For Git repos, modify URL only for clone operation
                clone_url = url  # Default to original
                if not is_local:
                    # Use provider-based authentication
                    try:
                        provider_registry = get_default_registry()
                        provider = provider_registry.get_provider(url)
                        if provider:
                            token = os.environ.get(provider.get_env_var_name())
                            # Always use get_authenticated_url to normalize URLs
                            # (e.g., convert Azure DevOps short format to full format)
                            clone_url = provider.get_authenticated_url(url, token)
                            if token:
                                logger.debug(
                                    f"Using authenticated URL for clone with {provider.get_provider_name()}: {url} (token hidden)"
                                )
                            else:
                                logger.debug(
                                    f"No token found for {provider.get_provider_name()} in {provider.get_env_var_name()}"
                                )
                        else:
                            logger.debug(f"No provider found for URL: {url}")
                    except Exception as e:
                        logger.warning(f"Failed to get provider authentication for {url}: {e}")
                        # Fall back to original URL

                # Use clone_url for git operation only
                await asyncio.to_thread(
                    Repo.clone_from, clone_url, cache_path, branch=branch
                )
                
                # Verify the repository is on the correct branch after cloning
                if not is_local and branch:
                    try:
                        repo = Repo(cache_path)
                        if not repo.head.is_detached and repo.active_branch.name != branch:
                            # If not on the requested branch, check it out
                            logger.debug(f"Repository cloned to {repo.active_branch.name}, checking out {branch}")
                            repo.git.checkout(branch)
                            logger.debug(f"Successfully checked out branch: {branch}")
                    except Exception as e:
                        logger.warning(f"Could not verify/checkout branch {branch}: {e}")

            # Update success status
            logger.info(f"Updating clone status to complete for: {str_path}")
            await self.cache.update_clone_status(
                str_path,
                {"status": "complete", "completed_at": datetime.now().isoformat()},
            )
            logger.info(f"Clone status updated successfully for: {str_path}")

            # Determine the actual current branch after cloning
            actual_branch = branch  # Default to requested branch
            if not is_local:
                try:
                    repo = Repo(cache_path)
                    if not repo.head.is_detached:
                        actual_branch = repo.active_branch.name
                        logger.debug(f"Repository cloned to branch: {actual_branch}")
                    else:
                        logger.debug("Repository is in detached HEAD state")
                except Exception as e:
                    logger.warning(f"Could not determine current branch: {e}")

            # Register the repo with original URL and actual branch information
            await self.cache.add_repo(str_path, original_url, actual_branch, cache_strategy)

            # Import here to avoid circular dependency
            try:
                from ..context.builder import RepoMapBuilder
            except ImportError:
                # Fallback to mock if aider is not available
                from ..context.mock_builder import RepoMapBuilder

            # Start RepoMap build now that clone/copy is complete
            repo_map_builder = RepoMapBuilder(self.cache)
            await repo_map_builder.start_build(str_path)
            
            # Start critical files analysis in background
            try:
                from ..analysis.complexity import CodeComplexityAnalyzer
                analyzer = CodeComplexityAnalyzer(self, repo_map_builder)
                asyncio.create_task(analyzer.analyze_and_cache_critical_files(str_path))
                logger.debug(f"Started background critical files analysis for {str_path}")
            except Exception as e:
                logger.warning(f"Could not start critical files analysis: {str(e)}")
            
            # Schedule repository for auto-refresh if auto-refresh manager is available
            if self.auto_refresh_manager:
                try:
                    await self.auto_refresh_manager.schedule_repository_refresh(str_path)
                    logger.debug(f"Scheduled repository for auto-refresh: {str_path}")
                except Exception as e:
                    logger.warning(f"Failed to schedule repository for auto-refresh: {e}")

        except Exception as e:
            logger.error(
                f"{'Copy' if is_local else 'Clone'} failed for {original_url}: {str(e)}"
            )
            # Update failure status
            await self.cache.update_clone_status(
                str_path,
                {
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now().isoformat(),
                },
            )

            # Cleanup failed clone/copy directory
            if cache_path.exists():
                shutil.rmtree(cache_path)
            if str_path in self.repositories:
                del self.repositories[str_path]
            raise

    async def _cleanup_repos_for_clone(self):
        """Clean up repositories if we've reached the max limit to make room for a new clone."""
        # Get actual repositories on disk
        actual_repos = await asyncio.to_thread(
            lambda: list(self.cache._get_actual_repos())
        )

        if len(actual_repos) < self.config.max_cached_repos:
            # We're under the limit, no cleanup needed
            return

        # We need to remove at least one repository to make room
        logger.info(
            f"Repository limit reached ({len(actual_repos)}/{self.config.max_cached_repos}), cleaning up oldest repositories"
        )

        # Get last access times from metadata
        with self.cache._file_lock():
            metadata = self.cache._read_metadata()

        # Sort repos by access time
        repo_with_times = []
        for repo_path in actual_repos:
            if repo_path in metadata:
                access_time = datetime.fromisoformat(metadata[repo_path].last_access)
            else:
                access_time = datetime.min
            repo_with_times.append((repo_path, access_time))

        # Sort by access time (oldest first)
        sorted_repos = sorted(repo_with_times, key=lambda x: x[1])

        # Remove oldest repositories until under limit
        to_remove = (
            len(actual_repos) - self.config.max_cached_repos + 1
        )  # +1 to make room for new repo
        for i in range(min(to_remove, len(sorted_repos))):
            repo_path, _ = sorted_repos[i]
            try:
                logger.info(f"Removing old repository: {repo_path}")
                repo_path_obj = Path(repo_path)
                if repo_path_obj.exists():
                    await asyncio.to_thread(shutil.rmtree, repo_path_obj)

                # Remove from in-memory dict if present
                if repo_path in self.repositories:
                    del self.repositories[repo_path]

                # Remove from metadata
                with self.cache._file_lock():
                    curr_metadata = self.cache._read_metadata()
                    if repo_path in curr_metadata:
                        del curr_metadata[repo_path]
                    self.cache._write_metadata(curr_metadata)

            except Exception as e:
                logger.error(
                    f"Error removing repository {repo_path}: {e}", exc_info=True
                )

    async def clone_repository(
        self, 
        url: str, 
        branch: Optional[str] = None,
        cache_strategy: Literal["shared", "per-branch"] = "shared"
    ) -> Dict[str, Any]:
        """Clone a repository with configurable cache strategy.
        
        Args:
            url: Repository URL
            branch: Target branch to clone
            cache_strategy: 
                - "shared": One cache entry per repo, switch branches in place (default)
                - "per-branch": Separate cache entries for each branch
        """
        logger.info(f"Starting clone of repository: {url}")

        # Get cache path based on strategy
        cache_path = get_cache_path(
            self.cache_dir, 
            url, 
            branch if cache_strategy == "per-branch" else None,
            per_branch=(cache_strategy == "per-branch")
        )
        str_path = str(cache_path.resolve())
        logger.debug(f"Cache path for repository ({cache_strategy} strategy): {str_path}")

        # Check if repository is already cloned or being cloned
        repo_status = await self.cache.get_repository_status(str_path)
        if repo_status and "clone_status" in repo_status:
            clone_status = repo_status["clone_status"]
            
            # Handle failed clones - clean up and retry
            if clone_status and clone_status.get("status") == "failed":
                logger.info(f"Previous clone failed, cleaning up and retrying: {str_path}")
                await self.cache.remove_repo(str_path)
                if cache_path.exists():
                    shutil.rmtree(cache_path)
                # Fall through to fresh clone attempt
            elif clone_status and clone_status.get("status") == "complete":
                # Check if we need to switch branches (only for shared strategy)
                stored_branch = repo_status.get("requested_branch")
                current_branch = repo_status.get("current_branch")
                
                if branch and stored_branch != branch and cache_strategy == "shared":
                    # Switch to the requested branch
                    try:
                        repo = Repo(cache_path)
                        
                        # Try to checkout the requested branch
                        try:
                            repo.git.checkout(branch)
                            logger.debug(f"Successfully switched from {current_branch} to {branch}")
                            
                            # Update metadata with new branch
                            await self.cache.add_repo(str_path, url, branch, cache_strategy)
                            
                            return {
                                "status": "switched_branch",
                                "path": str_path,
                                "message": f"Switched from {stored_branch} to {branch}",
                                "previous_branch": stored_branch,
                                "current_branch": branch
                            }
                        except Exception as checkout_error:
                            return {
                                "status": "error",
                                "error": f"Failed to switch to branch {branch}: {str(checkout_error)}"
                            }
                    except Exception as e:
                        return {
                            "status": "error", 
                            "error": f"Failed to access repository for branch switching: {str(e)}"
                        }
                else:
                    # For per-branch strategy or same branch, return already cloned
                    return {
                        "status": "already_cloned",
                        "path": str_path, 
                        "message": "Repository already cloned and ready",
                        "current_branch": stored_branch,
                        "cache_strategy": cache_strategy
                    }
            elif clone_status and clone_status.get("status") in ["pending", "cloning", "copying"]:
                return {
                    "status": "clone_in_progress",
                    "path": str_path,
                    "message": "Repository clone already in progress",
                    "cache_strategy": cache_strategy
                }

        # Before cloning, check if we need to clean up any repositories
        # to make room for the new one
        await self._cleanup_repos_for_clone()

        # First, ensure we can add another repo
        logger.debug("Preparing cache for clone...")
        if not await self.cache.prepare_for_clone(str_path):
            logger.error("Failed to prepare cache for clone")
            return {"status": "error", "error": "Failed to prepare cache for clone"}

        # Create initial metadata entry immediately to prevent race condition
        # where analysis tools check for repository before _do_clone creates metadata
        await self.cache.update_clone_status(
            str_path,
            {
                "status": "pending",
                "started_at": datetime.now().isoformat(),
                "message": "Clone starting"
            }
        )

        try:
            # Start clone in background
            asyncio.create_task(self._do_clone(url, str_path, branch, False, cache_strategy))

            return {
                "status": "pending",
                "path": str_path,
                "message": "Clone started in background",
                "cache_strategy": cache_strategy
            }

        except Exception as e:
            logger.error(f"Error initiating clone: {str(e)}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def refresh_repository(
        self, 
        path: str, 
        branch: Optional[str] = None, 
        cache_strategy: Literal["shared", "per-branch"] = "shared"
    ) -> Dict[str, Any]:
        """Refresh a repository with latest changes and optionally switch branches.
        
        Args:
            path: Repository path or URL
            branch: Optional branch to switch to during refresh
            cache_strategy: Cache strategy to use (must match original clone strategy)
        """
        try:
            # Get cache path based on strategy (should match original clone)
            cache_path = get_cache_path(
                self.cache_dir, 
                path, 
                branch if cache_strategy == "per-branch" else None,
                per_branch=(cache_strategy == "per-branch")
            )
            str_path = str(cache_path.resolve())

            # Check repository exists in cache
            with self.cache._file_lock():
                metadata = self.cache._read_metadata()
                if str_path not in metadata:
                    return {"status": "error", "error": "Repository not found in cache"}

                # Verify both statuses are complete
                repo_metadata = metadata[str_path]
                if (
                    not repo_metadata.clone_status
                    or repo_metadata.clone_status["status"] != "complete"
                    or not repo_metadata.repo_map_status
                    or repo_metadata.repo_map_status["status"] != "complete"
                ):
                    return {
                        "status": "error",
                        "error": "Cannot refresh repository - clone or repo map build is in progress",
                    }

            # Start refresh in background
            asyncio.create_task(self._do_refresh(path, str_path, branch, cache_strategy))

            return {
                "status": "pending",
                "path": str_path,
                "message": "Refresh started in background",
                "cache_strategy": cache_strategy
            }

        except Exception as e:
            logger.error(f"Error initiating refresh: {str(e)}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def list_repository_branches(self, repo_url: str) -> Dict[str, Any]:
        """List all cached versions of a repository across different branches.
        
        Args:
            repo_url: Repository URL to search for
            
        Returns:
            Dictionary containing information about each cached branch including paths and metadata.
        """
        try:
            cached_branches = []
            
            with self.cache._file_lock():
                metadata = self.cache._read_metadata()
                
                for cache_path, repo_metadata in metadata.items():
                    # Check if this cache entry is for the requested repo URL
                    if repo_metadata.url == repo_url:
                        # Get current branch info
                        try:
                            repo = Repo(cache_path)
                            if repo.head.is_detached:
                                current_branch = f"detached at {repo.head.commit.hexsha[:8]}"
                            else:
                                current_branch = repo.active_branch.name
                        except Exception:
                            current_branch = "unknown"
                        
                        # Get cache strategy from metadata (preferred) or fall back to detection
                        cache_strategy = repo_metadata.cache_strategy or "shared"
                        
                        cached_branches.append({
                            "requested_branch": repo_metadata.branch,
                            "current_branch": current_branch,
                            "cache_path": cache_path,
                            "cache_strategy": cache_strategy,
                            "last_access": repo_metadata.last_access,
                            "clone_status": repo_metadata.clone_status,
                            "repo_map_status": repo_metadata.repo_map_status
                        })
            
            return {
                "status": "success",
                "repo_url": repo_url,
                "cached_branches": cached_branches,
                "total_cached": len(cached_branches)
            }
            
        except Exception as e:
            logger.error(f"Error listing repository branches: {str(e)}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def _do_refresh(self, original_path: str, cache_path: str, branch: Optional[str] = None, cache_strategy: Optional[str] = None):
        """Internal method to perform the actual refresh"""
        try:
            # Update status to refreshing
            await self.cache.update_clone_status(
                cache_path,  # Fixed: use string path directly, no str() needed
                {"status": "refreshing", "started_at": datetime.now().isoformat()},
            )

            # Remove repo map status and critical files analysis cache entirely
            await self.cache.update_repo_map_status(
                cache_path, None
            )  # Ensure path is string
            await self.cache.update_critical_files_analysis(
                cache_path, None
            )  # Clear critical files cache on refresh

            is_git = is_git_url(original_path)
            if is_git:
                # For Git repos, do git pull
                repo = Repo(cache_path)
                await asyncio.to_thread(repo.remotes.origin.pull)
                if branch:
                    try:
                        if not repo.head.is_detached and repo.active_branch.name != branch:
                            logger.debug(f"Repository pulled to {repo.active_branch.name}, checking out {branch}")
                            repo.git.checkout(branch)
                            logger.debug(f"Successfully checked out branch: {branch}")
                    except Exception as e:
                        logger.warning(f"Could not verify/checkout branch {branch} during refresh: {e}")
            else:
                # For local dirs:
                original_path = Path(original_path).resolve()
                cache_path_obj = Path(cache_path)  # Rename to avoid confusion

                # First remove everything in the cache directory
                # No special handling for .git needed since we're copying a local dir
                if cache_path_obj.exists():
                    shutil.rmtree(cache_path_obj)

                # Do a fresh copy, still excluding .git in case source has one
                def ignore_git(dir, files):
                    return [".git"] if ".git" in files else []

                await asyncio.to_thread(
                    shutil.copytree,
                    original_path,
                    cache_path_obj,
                    dirs_exist_ok=False,  # Changed since we just removed the directory
                    ignore=ignore_git,
                )

            # Update success status
            await self.cache.update_clone_status(
                cache_path,  # Fixed: use string path directly, no str() needed
                {"status": "complete", "completed_at": datetime.now().isoformat()},
            )

            # Update branch information if a branch was specified
            if branch and is_git:
                await self.cache.add_repo(cache_path, original_path, branch, cache_strategy)

            # Start repo map build
            try:
                from ..context.builder import RepoMapBuilder
            except ImportError:
                # Fallback to mock if aider is not available
                from ..context.mock_builder import RepoMapBuilder

            repo_map_builder = RepoMapBuilder(self.cache)
            await repo_map_builder.start_build(str(cache_path))  # Ensure path is string
            
            # Start critical files analysis after refresh
            try:
                from ..analysis.complexity import CodeComplexityAnalyzer
                analyzer = CodeComplexityAnalyzer(self, repo_map_builder)
                asyncio.create_task(analyzer.analyze_and_cache_critical_files(cache_path))
                logger.debug(f"Started background critical files analysis after refresh for {cache_path}")
            except Exception as e:
                logger.warning(f"Could not start critical files analysis after refresh: {str(e)}")
            
            # Schedule repository for auto-refresh if auto-refresh manager is available
            if self.auto_refresh_manager:
                try:
                    await self.auto_refresh_manager.schedule_repository_refresh(cache_path)
                    logger.debug(f"Scheduled repository for auto-refresh after refresh: {cache_path}")
                except Exception as e:
                    logger.warning(f"Failed to schedule repository for auto-refresh after refresh: {e}")

        except Exception as e:
            logger.error(f"Refresh failed for {original_path}: {str(e)}")
            # Update failure status
            await self.cache.update_clone_status(
                cache_path,  # Fixed: use string path directly, no str() needed
                {
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now().isoformat(),
                },
            )
            raise

    async def list_cached_repositories(self) -> Dict[str, Any]:
        """List all cached repositories with their metadata.
        
        Returns:
            Dictionary containing list of all cached repositories with full metadata
        """
        try:
            cached_repos = []
            
            with self.cache._file_lock():
                metadata = self.cache._read_metadata()
                
                for cache_path, repo_metadata in metadata.items():
                    # Include all metadata fields from RepositoryMetadata
                    repo_info = {
                        "cache_path": cache_path,
                        "url": repo_metadata.url,
                        "last_access": repo_metadata.last_access,
                        "branch": repo_metadata.branch,
                        "cache_strategy": repo_metadata.cache_strategy,
                        "clone_status": repo_metadata.clone_status,
                        "repo_map_status": repo_metadata.repo_map_status,
                    }
                    
                    # Add current Git branch if it's a Git repository
                    try:
                        repo_path = Path(cache_path)
                        if repo_path.exists() and (repo_path / ".git").exists():
                            repo = Repo(cache_path)
                            if repo.head.is_detached:
                                repo_info["current_branch"] = f"detached at {repo.head.commit.hexsha[:8]}"
                            else:
                                repo_info["current_branch"] = repo.active_branch.name
                        else:
                            repo_info["current_branch"] = None
                    except Exception:
                        repo_info["current_branch"] = "unknown"
                    
                    # Calculate cache size
                    try:
                        repo_path = Path(cache_path)
                        if repo_path.exists():
                            size = sum(f.stat().st_size for f in repo_path.rglob('*') if f.is_file())
                            repo_info["cache_size_bytes"] = size
                            repo_info["cache_size_mb"] = round(size / (1024 * 1024), 2)
                        else:
                            repo_info["cache_size_bytes"] = 0
                            repo_info["cache_size_mb"] = 0
                    except Exception:
                        repo_info["cache_size_bytes"] = None
                        repo_info["cache_size_mb"] = None
                    
                    cached_repos.append(repo_info)
            
            # Sort by last access time (most recent first)
            cached_repos.sort(key=lambda x: x.get("last_access", ""), reverse=True)
            
            return {
                "status": "success",
                "total_cached": len(cached_repos),
                "max_cached_repos": self.cache.max_cached_repos,
                "cache_dir": str(self.cache_dir),
                "repositories": cached_repos
            }
            
        except Exception as e:
            logger.error(f"Error listing cached repositories: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }

    async def delete_repository(self, repo_identifier: str) -> Dict[str, Any]:
        """Delete a repository from cache by identifier.
        
        This method supports two identification strategies:
        1. Direct cache path: If repo_identifier is an existing directory path, 
           it will be treated as a direct cache path and deleted immediately.
        2. Repository URL: If repo_identifier appears to be a URL, this method will 
           find all cached entries for that repository and delete them all.
           
        Args:
            repo_identifier: Either:
                - Repository URL (finds all cache entries for that repo)
                - Direct cache path (deletes specific cache entry)
                
        Returns:
            Dict with status and details:
                - {"status": "success", "deleted_paths": [...], "message": "..."}
                - {"status": "error", "error": "error message"}
        """
        # Input validation
        if not repo_identifier or not isinstance(repo_identifier, str) or not repo_identifier.strip():
            logger.warning("Empty or invalid repository identifier provided")
            return {"status": "error", "error": "Repository identifier cannot be empty"}
        
        # Sanitize input
        repo_identifier = repo_identifier.strip()
        logger.info(f"Deleting repository with identifier: {repo_identifier}")
        
        try:
            # Strategy 1: Check if it's a direct cache path
            repo_path = Path(repo_identifier)
            if repo_path.exists() and repo_path.is_dir():
                # Additional validation: ensure this is actually a repository cache directory
                # Check if it's within the cache directory and contains repository markers
                try:
                    cache_dir = self.cache_dir
                    if not repo_path.is_relative_to(cache_dir):
                        logger.warning(f"Path {repo_identifier} is not within cache directory")
                        return {"status": "error", "error": "Invalid cache path: not within repository cache directory"}
                    
                    # Check for repository markers (either .git directory or metadata suggests it's a repo)
                    has_git = (repo_path / ".git").exists()
                    # Also accept if the path matches our cache structure patterns
                    is_cache_path = any(parent.name in ['github', 'git', 'local', 'azure'] for parent in repo_path.parents)
                    
                    if not (has_git or is_cache_path):
                        logger.warning(f"Path {repo_identifier} does not appear to be a repository cache")
                        return {"status": "error", "error": "Invalid cache path: directory does not appear to be a repository cache"}
                        
                except (OSError, ValueError) as e:
                    logger.warning(f"Failed to validate cache path {repo_identifier}: {e}")
                    return {"status": "error", "error": f"Invalid cache path: {str(e)}"}
                
                logger.debug(f"Treating {repo_identifier} as direct cache path")
                await self.cache.remove_repo(repo_identifier)
                
                # Thread-safe cleanup of in-memory reference
                try:
                    if repo_identifier in self.repositories:
                        del self.repositories[repo_identifier]
                        logger.debug(f"Removed in-memory reference for {repo_identifier}")
                except KeyError:
                    # Race condition - reference was already removed, which is fine
                    logger.debug(f"In-memory reference for {repo_identifier} was already removed")
                
                return {
                    "status": "success", 
                    "deleted_paths": [repo_identifier],
                    "message": f"Successfully deleted repository cache at {repo_identifier}"
                }
            
            # Strategy 2: Treat as repository URL - find all cache entries
            logger.debug(f"Treating {repo_identifier} as repository URL")
            branches_result = await self.list_repository_branches(repo_identifier)
            
            if branches_result["status"] == "success" and branches_result["cached_branches"]:
                deleted_paths = []
                failed_paths = []
                
                for branch_info in branches_result["cached_branches"]:
                    cache_path = branch_info["cache_path"]
                    try:
                        await self.cache.remove_repo(cache_path)
                        deleted_paths.append(cache_path)
                        logger.info(f"Successfully deleted cache entry: {cache_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete cache entry {cache_path}: {e}")
                        failed_paths.append(cache_path)
                        continue
                
                # Thread-safe cleanup of in-memory references for deleted paths
                for deleted_path in deleted_paths:
                    try:
                        if deleted_path in self.repositories:
                            del self.repositories[deleted_path]
                            logger.debug(f"Removed in-memory reference for {deleted_path}")
                    except KeyError:
                        # Race condition - reference was already removed, which is fine
                        logger.debug(f"In-memory reference for {deleted_path} was already removed")
                
                if deleted_paths:
                    message = f"Successfully deleted {len(deleted_paths)} cache entries for repository: {repo_identifier}"
                    if failed_paths:
                        message += f" ({len(failed_paths)} entries failed to delete)"
                    
                    return {
                        "status": "success",
                        "deleted_paths": deleted_paths,
                        "message": message
                    }
                else:
                    return {
                        "status": "error",
                        "error": f"Failed to delete all cache entries for repository: {repo_identifier}"
                    }
            else:
                # No cached branches found or error occurred
                if branches_result["status"] != "success":
                    error_msg = branches_result.get("error", "Unknown error occurred while querying repository cache")
                    return {"status": "error", "error": f"Failed to query repository cache: {error_msg}"}
                else:
                    return {"status": "error", "error": f"No cached entries found for repository: {repo_identifier}"}
                
        except Exception as e:
            logger.error(f"Error deleting repository {repo_identifier}: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def cleanup(self):
        """Cleanup all repositories on server shutdown."""
        # Stop auto-refresh first
        await self.stop_auto_refresh()
        
        for repo_id, repo in list(self.repositories.items()):
            try:
                if repo.root_path.exists():
                    shutil.rmtree(repo.root_path)
                del self.repositories[repo_id]
            except Exception as e:
                logger.error(f"Error cleaning up repository {repo_id}: {e}")
    
    async def start_auto_refresh(self) -> None:
        """Start the auto-refresh system if available."""
        if self.auto_refresh_manager:
            try:
                await self.auto_refresh_manager.start()
                logger.info("Auto-refresh system started")
            except Exception as e:
                logger.error(f"Failed to start auto-refresh system: {e}")
        else:
            logger.debug("Auto-refresh manager not available - cannot start auto-refresh")
    
    async def stop_auto_refresh(self) -> None:
        """Stop the auto-refresh system if running."""
        if self.auto_refresh_manager:
            try:
                await self.auto_refresh_manager.stop()
                logger.info("Auto-refresh system stopped")
            except Exception as e:
                logger.error(f"Failed to stop auto-refresh system: {e}")
        else:
            logger.debug("Auto-refresh manager not available - nothing to stop")
    
    async def get_auto_refresh_status(self) -> Dict[str, Any]:
        """Get the status of the auto-refresh system."""
        if self.auto_refresh_manager:
            try:
                return await self.auto_refresh_manager.get_status()
            except Exception as e:
                logger.error(f"Failed to get auto-refresh status: {e}")
                return {"status": "error", "error": str(e)}
        else:
            return {
                "status": "disabled",
                "message": "Auto-refresh manager not available or disabled"
            }
