"""
Auto-refresh manager for intelligent repository synchronization.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Set, TYPE_CHECKING

import git
from git.repo import Repo

from ..config import AutoRefreshConfig

if TYPE_CHECKING:
    from .manager import RepositoryManager

logger = logging.getLogger(__name__)


class AutoRefreshManager:
    """
    Manages automatic repository refresh scheduling based on repository activity.
    
    Provides intelligent scheduling that refreshes active repositories more frequently
    than inactive ones to balance freshness with resource usage.
    """

    def __init__(self, config: AutoRefreshConfig, repository_manager: "RepositoryManager"):
        """
        Initialize the auto-refresh manager.

        Args:
            config: Auto-refresh configuration settings
            repository_manager: Repository manager instance to perform refreshes
        """
        self.config = config
        self.repository_manager = repository_manager
        
        # Scheduling infrastructure
        self._refresh_queue: asyncio.Queue[str] = asyncio.Queue()
        self._scheduled_repos: Dict[str, datetime] = {}
        self._active_refreshes: Set[str] = set()
        
        # Concurrency control
        self._semaphore = asyncio.Semaphore(config.max_concurrent_refreshes)
        
        # Background task management
        self._worker_task: Optional[asyncio.Task] = None
        self._scheduler_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Initialize and start background refresh scheduling."""
        if not self.config.enabled:
            logger.info("Auto-refresh is disabled in configuration")
            return
            
        logger.info("Starting auto-refresh manager")
        logger.info(f"Configuration: active={self.config.active_repo_interval_hours}h, "
                   f"inactive={self.config.inactive_repo_interval_hours}h, "
                   f"max_concurrent={self.config.max_concurrent_refreshes}")
        
        # Start background workers
        self._worker_task = asyncio.create_task(self._refresh_worker())
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info("Auto-refresh manager started successfully")

    async def stop(self) -> None:
        """Cleanup and shutdown auto-refresh system."""
        if not self.config.enabled:
            return
            
        logger.info("Stopping auto-refresh manager")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel background tasks
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
                
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Auto-refresh manager stopped")

    async def schedule_repository_refresh(self, repo_path: str) -> None:
        """
        Add a repository to the refresh schedule.

        Args:
            repo_path: Path to the repository to schedule for refresh
        """
        if not self.config.enabled:
            return
            
        next_refresh = await self._calculate_next_refresh_time(repo_path)
        self._scheduled_repos[repo_path] = next_refresh
        
        is_active = await self._is_repository_active(repo_path)
        activity_status = "active" if is_active else "inactive"
        
        logger.debug(f"Scheduled {activity_status} repository '{repo_path}' for refresh at {next_refresh}")

    async def _calculate_next_refresh_time(self, repo_path: str) -> datetime:
        """
        Calculate the next refresh time based on repository activity.

        Args:
            repo_path: Path to the repository

        Returns:
            The next scheduled refresh time
        """
        now = datetime.now()
        
        # Apply startup delay for immediate scheduling
        if repo_path not in self._scheduled_repos:
            return now + timedelta(seconds=self.config.startup_delay_seconds)
        
        # Determine refresh interval based on activity
        is_active = await self._is_repository_active(repo_path)
        interval_hours = (
            self.config.active_repo_interval_hours 
            if is_active 
            else self.config.inactive_repo_interval_hours
        )
        
        return now + timedelta(hours=interval_hours)

    async def _is_repository_active(self, repo_path: str) -> bool:
        """
        Determine if a repository is considered active based on recent commits.

        Args:
            repo_path: Path to the repository

        Returns:
            True if the repository has recent activity, False otherwise
        """
        try:
            last_commit_date = await self._get_last_commit_date(repo_path)
            if last_commit_date is None:
                # No commit data available, consider inactive
                return False
            
            threshold = datetime.now() - timedelta(days=self.config.activity_threshold_days)
            return last_commit_date > threshold
            
        except Exception as e:
            logger.warning(f"Error checking activity for '{repo_path}': {e}")
            return False

    async def _get_last_commit_date(self, repo_path: str) -> Optional[datetime]:
        """
        Get the last commit date for a repository.

        Args:
            repo_path: Path to the repository

        Returns:
            The date of the last commit, or None if unable to determine
        """
        repo_path_obj = Path(repo_path)
        
        # Handle Git repositories
        if (repo_path_obj / ".git").exists():
            try:
                # Use GitPython for git operations
                repo = Repo(repo_path_obj)
                if repo.heads:  # Has commits
                    last_commit = repo.head.commit
                    return datetime.fromtimestamp(last_commit.committed_date)
                else:
                    return None
                    
            except Exception as e:
                logger.debug(f"Failed to get Git commit date for '{repo_path}': {e}")
                # Fall back to subprocess approach
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "git", "log", "-1", "--format=%cd", "--date=iso",
                        cwd=repo_path_obj,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await proc.communicate()
                    
                    if proc.returncode == 0:
                        date_str = stdout.decode().strip()
                        # Parse ISO format: "2023-12-01 10:30:45 +0000"
                        return datetime.fromisoformat(date_str.replace(" +", "+").replace(" -", "-"))
                        
                except Exception as subprocess_error:
                    logger.debug(f"Git subprocess also failed for '{repo_path}': {subprocess_error}")
        
        # Handle local directories - use most recent file modification time
        try:
            if not repo_path_obj.exists() or not repo_path_obj.is_dir():
                return None
                
            latest_time = None
            
            # Walk through directory to find most recent modification
            for file_path in repo_path_obj.rglob("*"):
                if file_path.is_file():
                    try:
                        mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if latest_time is None or mod_time > latest_time:
                            latest_time = mod_time
                    except (OSError, ValueError):
                        continue
                        
            return latest_time
            
        except Exception as e:
            logger.debug(f"Failed to get file modification times for '{repo_path}': {e}")
            return None

    async def _refresh_worker(self) -> None:
        """Background worker that processes repository refresh requests."""
        logger.debug("Auto-refresh worker started")
        
        while not self._shutdown_event.is_set():
            try:
                # Wait for repository refresh request or shutdown
                try:
                    repo_path = await asyncio.wait_for(
                        self._refresh_queue.get(),
                        timeout=1.0  # Check shutdown every second
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Skip if already being refreshed
                if repo_path in self._active_refreshes:
                    logger.debug(f"Repository '{repo_path}' refresh already in progress, skipping")
                    continue
                
                # Perform refresh with concurrency control
                async with self._semaphore:
                    self._active_refreshes.add(repo_path)
                    try:
                        logger.info(f"Starting auto-refresh for repository: {repo_path}")
                        
                        # Perform the actual refresh
                        await self.repository_manager.refresh_repository(repo_path)
                        
                        logger.info(f"Auto-refresh completed successfully for: {repo_path}")
                        
                        # Reschedule for next refresh
                        await self.schedule_repository_refresh(repo_path)
                        
                    except Exception as e:
                        logger.error(f"Auto-refresh failed for '{repo_path}': {e}")
                        
                        # Reschedule with longer delay on error
                        error_delay = max(
                            self.config.active_repo_interval_hours,
                            self.config.inactive_repo_interval_hours
                        ) * 2
                        next_refresh = datetime.now() + timedelta(hours=error_delay)
                        self._scheduled_repos[repo_path] = next_refresh
                        
                    finally:
                        self._active_refreshes.discard(repo_path)
                        
            except Exception as e:
                logger.error(f"Unexpected error in refresh worker: {e}")
                await asyncio.sleep(1)  # Brief pause before continuing
                
        logger.debug("Auto-refresh worker stopped")

    async def _scheduler_loop(self) -> None:
        """Background scheduler that queues repositories for refresh when due."""
        logger.debug("Auto-refresh scheduler started")
        
        while not self._shutdown_event.is_set():
            try:
                now = datetime.now()
                due_repos = []
                
                # Find repositories due for refresh
                for repo_path, next_refresh in list(self._scheduled_repos.items()):
                    if now >= next_refresh and repo_path not in self._active_refreshes:
                        due_repos.append(repo_path)
                
                # Queue due repositories for refresh
                for repo_path in due_repos:
                    try:
                        await self._refresh_queue.put(repo_path)
                        # Remove from schedule - will be rescheduled after refresh
                        del self._scheduled_repos[repo_path]
                    except Exception as e:
                        logger.error(f"Failed to queue repository '{repo_path}' for refresh: {e}")
                
                # Sleep before next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Unexpected error in scheduler loop: {e}")
                await asyncio.sleep(30)
                
        logger.debug("Auto-refresh scheduler stopped")