"""
Data models for Repository Management API requests and responses.

All models use dataclasses with type hints for strict type checking.
"""

from dataclasses import dataclass
from typing import List, Optional


# HTTP Status Code Constants
HTTP_200_OK = 200
HTTP_201_CREATED = 201
HTTP_400_BAD_REQUEST = 400
HTTP_401_UNAUTHORIZED = 401
HTTP_404_NOT_FOUND = 404
HTTP_409_CONFLICT = 409
HTTP_500_INTERNAL_SERVER_ERROR = 500
HTTP_507_INSUFFICIENT_STORAGE = 507


@dataclass
class ErrorResponse:
    """
    Standard error response format for all API errors.

    Attributes:
        status: Always "error" to indicate error response
        error: Human-readable error message
        suggestion: Optional actionable suggestion for resolution
    """

    status: str = "error"
    error: str = ""
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {"status": self.status, "error": self.error}
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


@dataclass
class CloneRequest:
    """
    Request model for POST /api/repos/clone endpoint.

    Attributes:
        url: Repository URL (GitHub, Azure DevOps, or local path)
        branch: Optional branch name (defaults to repository's default branch)
        cache_strategy: "shared" (one cache, switch branches) or "per-branch" (separate caches)
    """

    url: str
    branch: Optional[str] = None
    cache_strategy: str = "shared"

    def validate(self) -> Optional[str]:
        """
        Validate the clone request parameters.

        Returns:
            Error message if validation fails, None if valid.
        """
        # URL validation
        if not self.url or not self.url.strip():
            return "Repository URL is required and cannot be empty"

        # Basic URL format validation
        if not self.url.startswith(("http://", "https://", "git@")):
            return "Repository URL must start with http://, https://, or git@"

        # Cache strategy validation
        if self.cache_strategy not in ("shared", "per-branch"):
            return "cache_strategy must be either 'shared' or 'per-branch'"

        # Branch name validation (security check for path traversal)
        if self.branch:
            if ".." in self.branch or "/" in self.branch or "\\" in self.branch:
                return "Invalid branch name: cannot contain path separators or parent directory references"

        return None


@dataclass
class CloneResponse:
    """
    Response model for POST /api/repos/clone endpoint.

    Attributes:
        status: Clone operation status - "pending", "already_cloned", or "switched_branch"
        message: Human-readable status message
        path: Optional path to the cached repository
        cache_strategy: The cache strategy being used
        current_branch: The current branch of the repository
    """

    status: str
    message: str
    path: Optional[str] = None
    cache_strategy: Optional[str] = None
    current_branch: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {"status": self.status, "message": self.message}
        if self.path:
            result["path"] = self.path
        if self.cache_strategy:
            result["cache_strategy"] = self.cache_strategy
        if self.current_branch:
            result["current_branch"] = self.current_branch
        return result


@dataclass
class CloneStatus:
    """
    Clone operation status information.

    Attributes:
        status: Current clone status (pending, cloning, complete, failed)
        started_at: When clone operation started (ISO 8601 string)
        completed_at: When clone operation completed (ISO 8601 string)
        error: Error message if clone failed
    """

    status: str
    started_at: Optional[str] = None  # ISO 8601 string
    completed_at: Optional[str] = None  # ISO 8601 string
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "started_at": self.started_at,  # Already ISO string
            "completed_at": self.completed_at,  # Already ISO string
            "error": self.error,
        }


@dataclass
class RepoMapStatus:
    """
    Repository map generation status information.

    Attributes:
        status: Current repo map status (pending, building, complete, failed)
        started_at: When repo map generation started (ISO 8601 string)
        completed_at: When repo map generation completed (ISO 8601 string)
        error: Error message if generation failed
    """

    status: str
    started_at: Optional[str] = None  # ISO 8601 string
    completed_at: Optional[str] = None  # ISO 8601 string
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "started_at": self.started_at,  # Already ISO string
            "completed_at": self.completed_at,  # Already ISO string
            "error": self.error,
        }


@dataclass
class Repository:
    """
    Repository metadata for list response.

    Attributes:
        cache_path: Full path to cached repository
        url: Repository URL
        last_access: Last access timestamp
        current_branch: Current branch name
        cache_strategy: Cache strategy used (shared or per-branch)
        clone_status: Clone operation status
        repo_map_status: Repository map generation status
        cache_size_bytes: Cache size in bytes
        cache_size_mb: Cache size in megabytes
    """

    cache_path: str
    url: str
    last_access: str  # ISO 8601 string from repo_manager
    current_branch: str
    cache_strategy: str
    clone_status: CloneStatus
    repo_map_status: RepoMapStatus
    cache_size_bytes: int
    cache_size_mb: float

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cache_path": self.cache_path,
            "url": self.url,
            "last_access": self.last_access,  # Already ISO string
            "current_branch": self.current_branch,
            "cache_strategy": self.cache_strategy,
            "clone_status": self.clone_status.to_dict(),
            "repo_map_status": self.repo_map_status.to_dict(),
            "cache_size_bytes": self.cache_size_bytes,
            "cache_size_mb": self.cache_size_mb,
        }


@dataclass
class ListRepositoriesResponse:
    """
    Response model for GET /api/repos endpoint.

    Attributes:
        status: Response status (success or error)
        total_cached: Number of repositories in cache
        max_cached_repos: Maximum allowed cached repositories
        cache_dir: Cache directory path
        repositories: List of repository metadata
    """

    status: str
    total_cached: int
    max_cached_repos: int
    cache_dir: str
    repositories: List[Repository]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "total_cached": self.total_cached,
            "max_cached_repos": self.max_cached_repos,
            "cache_dir": self.cache_dir,
            "repositories": [repo.to_dict() for repo in self.repositories],
        }


@dataclass
class DeleteResponse:
    """
    Response model for DELETE /api/repos endpoint.

    Attributes:
        status: Response status (success or error)
        message: Human-readable status message
        url: The URL of the deleted repository
        cache_path: Optional path that was removed
    """

    status: str
    message: str
    url: Optional[str] = None
    cache_path: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {"status": self.status, "message": self.message}
        if self.url:
            result["url"] = self.url
        if self.cache_path:
            result["cache_path"] = self.cache_path
        return result
