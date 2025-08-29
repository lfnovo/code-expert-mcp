"""
Auto-refresh manager for intelligent repository synchronization.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Set, TYPE_CHECKING

import git
from git.repo import Repo

from ..config import AutoRefreshConfig

if TYPE_CHECKING:
    from .manager import RepositoryManager

logger = logging.getLogger(__name__)

# Error handling configuration constants
MAX_CONSECUTIVE_FAILURES = 3  # Skip repo after this many consecutive failures
EXPONENTIAL_BACKOFF_BASE_MINUTES = 30  # Base delay for exponential backoff
MAX_BACKOFF_HOURS = 24  # Maximum delay between retries
FAILURE_RESET_HOURS = 72  # Reset failure count after this many hours of no errors


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
        
        # Error tracking and recovery
        self._error_counts: Dict[str, int] = {}  # Track consecutive failures per repo
        self._last_error_times: Dict[str, datetime] = {}  # Track when errors occurred
        self._skipped_repos: Set[str] = set()  # Repositories temporarily skipped due to consistent failures
        
        # Resource monitoring and statistics
        self._refresh_start_times: Dict[str, float] = {}  # Track refresh start times for duration calculation
        self._refresh_statistics: Dict[str, Any] = {
            "total_refreshes": 0,
            "successful_refreshes": 0,
            "failed_refreshes": 0,
            "average_duration_seconds": 0.0,
            "last_refresh_duration": 0.0,
            "total_duration_seconds": 0.0
        }

    async def start(self) -> None:
        """Initialize and start background refresh scheduling."""
        if not self.config.enabled:
            logger.info("Auto-refresh is disabled in configuration")
            return
            
        logger.info("Starting auto-refresh manager")
        logger.info(f"Configuration: active={self.config.active_repo_interval_hours}h, "
                   f"inactive={self.config.inactive_repo_interval_hours}h, "
                   f"max_concurrent={self.config.max_concurrent_refreshes}")
        
        # Load existing scheduled refreshes from persistent metadata
        await self._load_scheduled_refreshes()
        
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
        
        # Store next refresh time in persistent metadata
        await self.repository_manager.cache.update_next_refresh_time(
            repo_path, 
            next_refresh.isoformat()
        )
        
        is_active = await self._is_repository_active(repo_path)
        activity_status = "active" if is_active else "inactive"
        
        logger.debug(f"Scheduled {activity_status} repository '{repo_path}' for refresh at {next_refresh}")

    async def _calculate_next_refresh_time(self, repo_path: str) -> datetime:
        """
        Calculate the next refresh time based on repository activity.

        Determines if a repository is active (commits within activity_threshold_days)
        and schedules the next refresh accordingly. Active repositories are refreshed
        more frequently than inactive ones.

        Args:
            repo_path: Absolute path to the repository to schedule

        Returns:
            datetime: The next scheduled refresh time. For new repositories, applies
                     startup_delay_seconds. For existing repos, uses either
                     active_repo_interval_hours or inactive_repo_interval_hours
                     based on recent activity.
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

        Checks the last commit date (for Git repos) or most recent file modification
        time (for local directories) against the configured activity threshold.
        Repositories with activity within activity_threshold_days are considered active.

        Args:
            repo_path: Absolute path to the repository to check

        Returns:
            bool: True if the repository has activity within the threshold period,
                 False otherwise. Returns False if unable to determine activity
                 or if the repository has no commits/files.
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
                
                # Handle different repository states
                if repo.head.is_detached:
                    # Detached HEAD state - get commit directly
                    last_commit = repo.head.commit
                    return datetime.fromtimestamp(last_commit.committed_date)
                elif repo.heads:  # Has branches and commits
                    last_commit = repo.head.commit
                    return datetime.fromtimestamp(last_commit.committed_date)
                else:
                    # Empty repository
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
                
                # Skip repositories with consecutive failures
                if self._should_skip_repo(repo_path):
                    logger.debug(f"Repository '{repo_path}' skipped due to consecutive failures")
                    continue
                
                # Perform refresh with concurrency control
                async with self._semaphore:
                    self._active_refreshes.add(repo_path)
                    self._start_refresh_timing(repo_path)
                    
                    try:
                        logger.info(f"Starting auto-refresh for repository: {repo_path}")
                        
                        # Perform the actual refresh
                        await self.repository_manager.refresh_repository(repo_path)
                        
                        logger.info(f"Auto-refresh completed successfully for: {repo_path}")
                        
                        # Record successful refresh and reset error tracking
                        self._record_refresh_success(repo_path)
                        self._end_refresh_timing(repo_path, success=True)
                        
                        # Clear the old next refresh time from metadata
                        await self.repository_manager.cache.update_next_refresh_time(repo_path, None)
                        
                        # Reschedule for next refresh
                        await self.schedule_repository_refresh(repo_path)
                        
                    except Exception as e:
                        # Record failure and determine next action
                        self._record_refresh_failure(repo_path, e)
                        self._end_refresh_timing(repo_path, success=False)
                        
                        # Only reschedule if not skipped due to consecutive failures
                        if not self._should_skip_repo(repo_path):
                            # Use exponential backoff for retry delay
                            backoff_delay = self._calculate_backoff_delay(repo_path)
                            next_refresh = datetime.now() + backoff_delay
                            self._scheduled_repos[repo_path] = next_refresh
                            
                            # Persist the retry schedule
                            await self.repository_manager.cache.update_next_refresh_time(
                                repo_path, 
                                next_refresh.isoformat()
                            )
                        else:
                            # Repository is skipped - clear from schedule and metadata
                            self._scheduled_repos.pop(repo_path, None)
                            await self.repository_manager.cache.update_next_refresh_time(repo_path, None)
                        
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
                
                # Check for repository recovery periodically
                self._check_for_repo_recovery()
                
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

    async def _load_scheduled_refreshes(self) -> None:
        """Load scheduled refreshes from persistent metadata."""
        try:
            # Access metadata directly from cache
            with self.repository_manager.cache._file_lock():
                metadata = self.repository_manager.cache._read_metadata()
                
                loaded_count = 0
                now = datetime.now()
                
                for repo_path, repo_metadata in metadata.items():
                    # Only load completed repositories with next refresh time
                    if (repo_metadata.clone_status and 
                        repo_metadata.clone_status.get("status") == "complete" and
                        repo_metadata.next_refresh_time):
                        try:
                            # Parse the ISO format next refresh time
                            next_refresh = datetime.fromisoformat(repo_metadata.next_refresh_time)
                            
                            # Apply startup delay to prevent immediate mass refresh
                            # if the scheduled time has already passed
                            if next_refresh <= now:
                                next_refresh = now + timedelta(seconds=self.config.startup_delay_seconds)
                                # Update the metadata with staggered time
                                await self.repository_manager.cache.update_next_refresh_time(
                                    repo_path, 
                                    next_refresh.isoformat()
                                )
                            
                            self._scheduled_repos[repo_path] = next_refresh
                            loaded_count += 1
                            
                            is_active = await self._is_repository_active(repo_path)
                            activity_status = "active" if is_active else "inactive"
                            logger.debug(f"Loaded {activity_status} repository schedule: '{repo_path}' -> {next_refresh}")
                            
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid next_refresh_time for '{repo_path}': {e}")
                            # Reschedule with default timing
                            await self.schedule_repository_refresh(repo_path)
                
                logger.info(f"Loaded {loaded_count} scheduled refreshes from persistent metadata")
                
        except Exception as e:
            logger.error(f"Failed to load scheduled refreshes from metadata: {e}")
            # Continue without loaded schedules - they'll be scheduled as repos are accessed

    async def get_status(self) -> Dict[str, Any]:
        """Get the current status of the auto-refresh system."""
        try:
            if not self.config.enabled:
                return {
                    "status": "disabled",
                    "message": "Auto-refresh is disabled in configuration"
                }
            
            # Check if background workers are running
            worker_running = self._worker_task and not self._worker_task.done()
            scheduler_running = self._scheduler_task and not self._scheduler_task.done()
            
            system_status = "running" if (worker_running and scheduler_running) else "stopped"
            if worker_running != scheduler_running:
                system_status = "partial"  # One worker is down
            
            # Get current schedule information
            now = datetime.now()
            scheduled_repos = []
            overdue_count = 0
            
            for repo_path, next_refresh in self._scheduled_repos.items():
                is_overdue = next_refresh <= now
                if is_overdue:
                    overdue_count += 1
                    
                is_active = await self._is_repository_active(repo_path)
                
                scheduled_repos.append({
                    "repository": repo_path,
                    "next_refresh": next_refresh.isoformat(),
                    "is_overdue": is_overdue,
                    "is_active": is_active,
                    "minutes_until_refresh": int((next_refresh - now).total_seconds() / 60) if not is_overdue else 0
                })
            
            # Sort by next refresh time
            scheduled_repos.sort(key=lambda x: x["next_refresh"])
            
            return {
                "status": system_status,
                "enabled": self.config.enabled,
                "configuration": {
                    "active_repo_interval_hours": self.config.active_repo_interval_hours,
                    "inactive_repo_interval_hours": self.config.inactive_repo_interval_hours,
                    "startup_delay_seconds": self.config.startup_delay_seconds,
                    "max_concurrent_refreshes": self.config.max_concurrent_refreshes,
                    "activity_threshold_days": self.config.activity_threshold_days
                },
                "statistics": {
                    "scheduled_repositories": len(self._scheduled_repos),
                    "active_refreshes": len(self._active_refreshes),
                    "overdue_refreshes": overdue_count,
                    "skipped_repositories": len(self._skipped_repos),
                    "repositories_with_errors": len(self._error_counts)
                },
                "active_refreshes": list(self._active_refreshes),
                "scheduled_repositories": scheduled_repos[:10],  # Limit to first 10 for readability
                "skipped_repositories": list(self._skipped_repos)[:5],  # Show first 5 skipped repos
                "error_tracking": {
                    repo_path: {
                        "consecutive_failures": count,
                        "last_error_time": self._last_error_times.get(repo_path, "").isoformat() if self._last_error_times.get(repo_path) else ""
                    }
                    for repo_path, count in list(self._error_counts.items())[:5]  # Show first 5 error repos
                },
                "worker_status": {
                    "refresh_worker": "running" if worker_running else "stopped",
                    "scheduler": "running" if scheduler_running else "stopped"
                },
                "resource_usage": self._get_resource_usage_stats()
            }
            
        except Exception as e:
            logger.error(f"Error getting auto-refresh status: {e}")
            return {
                "status": "error",
                "error": str(e),
                "enabled": self.config.enabled if hasattr(self, 'config') else False
            }

    def _should_skip_repo(self, repo_path: str) -> bool:
        """Check if a repository should be skipped due to consecutive failures."""
        if repo_path in self._skipped_repos:
            return True
            
        error_count = self._error_counts.get(repo_path, 0)
        if error_count >= MAX_CONSECUTIVE_FAILURES:
            self._skipped_repos.add(repo_path)
            logger.warning(f"Repository '{repo_path}' skipped after {error_count} consecutive failures")
            return True
            
        return False

    def _calculate_backoff_delay(self, repo_path: str) -> timedelta:
        """Calculate exponential backoff delay based on error count."""
        error_count = self._error_counts.get(repo_path, 0)
        if error_count == 0:
            return timedelta(hours=self.config.active_repo_interval_hours)
            
        # Exponential backoff: base_minutes * (2 ^ (error_count - 1))
        backoff_minutes = EXPONENTIAL_BACKOFF_BASE_MINUTES * (2 ** (error_count - 1))
        backoff_hours = min(backoff_minutes / 60, MAX_BACKOFF_HOURS)
        
        logger.debug(f"Repository '{repo_path}' backoff delay: {backoff_hours:.2f} hours (error count: {error_count})")
        return timedelta(hours=backoff_hours)

    def _record_refresh_success(self, repo_path: str) -> None:
        """Record successful refresh and reset error tracking."""
        if repo_path in self._error_counts:
            del self._error_counts[repo_path]
            logger.debug(f"Reset error count for '{repo_path}' after successful refresh")
            
        if repo_path in self._last_error_times:
            del self._last_error_times[repo_path]
            
        if repo_path in self._skipped_repos:
            self._skipped_repos.remove(repo_path)
            logger.info(f"Repository '{repo_path}' re-enabled after successful refresh")

    def _record_refresh_failure(self, repo_path: str, error: Exception) -> None:
        """Record refresh failure and update error tracking."""
        now = datetime.now()
        
        # Check if we should reset error count due to time passed
        last_error_time = self._last_error_times.get(repo_path)
        if (last_error_time and 
            now - last_error_time > timedelta(hours=FAILURE_RESET_HOURS)):
            logger.info(f"Resetting error count for '{repo_path}' after {FAILURE_RESET_HOURS} hours")
            self._error_counts[repo_path] = 0
        
        # Increment error count
        self._error_counts[repo_path] = self._error_counts.get(repo_path, 0) + 1
        self._last_error_times[repo_path] = now
        
        error_count = self._error_counts[repo_path]
        logger.error(f"Auto-refresh failed for '{repo_path}' (failure #{error_count}): {error}")
        
        if error_count >= MAX_CONSECUTIVE_FAILURES:
            self._skipped_repos.add(repo_path)
            logger.error(f"Repository '{repo_path}' disabled after {error_count} consecutive failures")

    def _check_for_repo_recovery(self) -> None:
        """Check if any skipped repositories can be re-enabled."""
        now = datetime.now()
        recovered_repos = []
        
        for repo_path in list(self._skipped_repos):
            last_error_time = self._last_error_times.get(repo_path)
            if (last_error_time and 
                now - last_error_time > timedelta(hours=FAILURE_RESET_HOURS)):
                self._skipped_repos.remove(repo_path)
                self._error_counts.pop(repo_path, None)
                self._last_error_times.pop(repo_path, None)
                recovered_repos.append(repo_path)
        
        if recovered_repos:
            logger.info(f"Re-enabled {len(recovered_repos)} repositories after error recovery period")
            for repo_path in recovered_repos:
                logger.debug(f"Re-enabled repository: {repo_path}")

    def _start_refresh_timing(self, repo_path: str) -> None:
        """Start timing a repository refresh operation."""
        self._refresh_start_times[repo_path] = time.time()

    def _end_refresh_timing(self, repo_path: str, success: bool) -> None:
        """End timing a repository refresh operation and update statistics."""
        start_time = self._refresh_start_times.pop(repo_path, None)
        if start_time is None:
            return
        
        duration = time.time() - start_time
        
        # Update statistics
        self._refresh_statistics["total_refreshes"] += 1
        self._refresh_statistics["last_refresh_duration"] = duration
        self._refresh_statistics["total_duration_seconds"] += duration
        
        if success:
            self._refresh_statistics["successful_refreshes"] += 1
        else:
            self._refresh_statistics["failed_refreshes"] += 1
        
        # Calculate running average
        total_count = self._refresh_statistics["total_refreshes"]
        if total_count > 0:
            self._refresh_statistics["average_duration_seconds"] = (
                self._refresh_statistics["total_duration_seconds"] / total_count
            )
        
        logger.debug(f"Repository refresh timing - '{repo_path}': {duration:.2f}s (success: {success})")

    def _check_resource_limits(self) -> bool:
        """Check if resource limits allow for more concurrent operations."""
        active_count = len(self._active_refreshes)
        max_concurrent = self.config.max_concurrent_refreshes
        
        if active_count >= max_concurrent:
            logger.debug(f"Resource limit reached: {active_count}/{max_concurrent} concurrent refreshes")
            return False
        
        return True

    def _get_resource_usage_stats(self) -> Dict[str, Any]:
        """Get current resource usage statistics."""
        return {
            "concurrent_refreshes": {
                "active": len(self._active_refreshes),
                "max_allowed": self.config.max_concurrent_refreshes,
                "utilization_percent": (len(self._active_refreshes) / self.config.max_concurrent_refreshes) * 100
            },
            "performance_metrics": self._refresh_statistics.copy(),
            "queue_status": {
                "scheduled_repositories": len(self._scheduled_repos),
                "repositories_in_progress": len(self._active_refreshes),
                "repositories_with_errors": len(self._error_counts),
                "skipped_repositories": len(self._skipped_repos)
            }
        }