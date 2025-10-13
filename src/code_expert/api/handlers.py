"""
API endpoint handlers for Repository Management interface.

All handlers are async and use Starlette request/response objects.
"""

import json
import logging
import shutil
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from code_expert.api.auth import require_api_password
from code_expert.api.models import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_507_INSUFFICIENT_STORAGE,
    CloneRequest,
    CloneResponse,
    CloneStatus,
    DeleteResponse,
    ErrorResponse,
    ListRepositoriesResponse,
    RepoMapStatus,
    Repository,
)

logger = logging.getLogger(__name__)


@require_api_password
async def handle_clone_repository(request: Request) -> JSONResponse:
    """
    Handle POST /api/repos/clone endpoint.

    Request body:
        {
            "url": "https://github.com/user/repo",
            "branch": "main",  // optional
            "cache_strategy": "shared"  // optional, defaults to "shared"
        }

    Returns:
        201 Created: Clone started (status: "pending")
        200 OK: Already cloned (status: "already_cloned" or "switched_branch")
        400 Bad Request: Invalid request parameters
        401 Unauthorized: Invalid or missing API password
        409 Conflict: Clone already in progress
        500 Internal Server Error: Server error
        507 Insufficient Storage: Cache full
    """
    try:
        # Parse request body
        try:
            body = await request.json()
        except json.JSONDecodeError:
            error = ErrorResponse(
                error="Invalid JSON in request body",
                suggestion="Ensure request body is valid JSON",
            )
            return JSONResponse(error.to_dict(), status_code=HTTP_400_BAD_REQUEST)

        # Create and validate CloneRequest
        clone_req = CloneRequest(
            url=body.get("url", ""),
            branch=body.get("branch"),
            cache_strategy=body.get("cache_strategy", "shared"),
        )

        validation_error = clone_req.validate()
        if validation_error:
            error = ErrorResponse(error=validation_error)
            return JSONResponse(error.to_dict(), status_code=HTTP_400_BAD_REQUEST)

        # Get repo_manager from app state
        repo_manager = request.app.state.repo_manager
        if not repo_manager:
            error = ErrorResponse(
                error="Repository manager not available",
                suggestion="Server configuration error - contact administrator",
            )
            return JSONResponse(
                error.to_dict(), status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Check cache capacity and disk space
        try:
            cached_repos = await repo_manager.list_repositories()
            max_cached = repo_manager.config.repository.max_cached_repos

            # Check if already cloned first
            is_cloned = False
            for repo_info in cached_repos:
                if repo_info.get("url") == clone_req.url:
                    is_cloned = True
                    break

            # If not cloned, check cache fullness
            if not is_cloned and len(cached_repos) >= max_cached:
                error = ErrorResponse(
                    error=f"Repository cache is full ({len(cached_repos)}/{max_cached} repositories cached)",
                    suggestion="Delete unused repositories using DELETE /api/repos before cloning new ones",
                )
                return JSONResponse(
                    error.to_dict(), status_code=HTTP_507_INSUFFICIENT_STORAGE
                )

            # Check available disk space (require at least 1GB free)
            if not is_cloned:
                cache_dir = Path(repo_manager.config.repository.cache_dir)
                try:
                    stat = shutil.disk_usage(cache_dir)
                    # Require at least 1GB (1073741824 bytes) free space
                    min_free_space = 1073741824
                    if stat.free < min_free_space:
                        error = ErrorResponse(
                            error=f"Insufficient disk space: {stat.free / (1024**3):.2f} GB available, minimum 1 GB required",
                            suggestion="Free up disk space or delete unused repositories using DELETE /api/repos",
                        )
                        return JSONResponse(
                            error.to_dict(), status_code=HTTP_507_INSUFFICIENT_STORAGE
                        )
                except Exception as disk_err:
                    logger.warning(f"Could not check disk space: {disk_err}")
                    # Continue with clone attempt even if disk check fails

        except Exception as e:
            logger.error(f"Error checking cache status: {e}", exc_info=True)
            # Continue with clone attempt even if cache check fails

        # Attempt to clone repository
        try:
            result = await repo_manager.clone_repository(
                url=clone_req.url,
                branch=clone_req.branch,
                cache_strategy=clone_req.cache_strategy,
            )

            # Map result status to response
            status = result.get("status", "pending")

            if status == "already_cloned":
                response = CloneResponse(
                    status="already_cloned",
                    message=f"Repository already cloned at {result.get('path')}",
                    path=result.get("path"),
                    cache_strategy=clone_req.cache_strategy,
                    current_branch=result.get("current_branch"),
                )
                return JSONResponse(response.to_dict(), status_code=HTTP_200_OK)

            elif status == "switched_branch":
                response = CloneResponse(
                    status="switched_branch",
                    message=f"Switched to branch {result.get('current_branch')}",
                    path=result.get("path"),
                    cache_strategy=clone_req.cache_strategy,
                    current_branch=result.get("current_branch"),
                )
                return JSONResponse(response.to_dict(), status_code=HTTP_200_OK)

            elif status == "cloning":
                # Clone operation in progress from previous request
                error = ErrorResponse(
                    error="Clone operation already in progress for this repository",
                    suggestion="Wait for the current clone operation to complete",
                )
                return JSONResponse(error.to_dict(), status_code=HTTP_409_CONFLICT)

            else:
                # Default: pending status
                response = CloneResponse(
                    status="pending",
                    message=f"Clone operation started for {clone_req.url}",
                    path=result.get("path"),
                    cache_strategy=clone_req.cache_strategy,
                    current_branch=result.get("current_branch"),
                )
                return JSONResponse(response.to_dict(), status_code=HTTP_201_CREATED)

        except ValueError as e:
            # Invalid URL or unsupported provider
            error = ErrorResponse(
                error=str(e),
                suggestion="Ensure URL is a valid GitHub or Azure DevOps repository URL",
            )
            return JSONResponse(error.to_dict(), status_code=HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error cloning repository: {e}", exc_info=True)
            error = ErrorResponse(
                error=f"Failed to clone repository: {str(e)}",
                suggestion="Check server logs for details",
            )
            return JSONResponse(
                error.to_dict(), status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )

    except Exception as e:
        logger.error(f"Unexpected error in clone handler: {e}", exc_info=True)
        error = ErrorResponse(
            error="Internal server error",
            suggestion="Contact administrator if problem persists",
        )
        return JSONResponse(error.to_dict(), status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@require_api_password
async def handle_list_repositories(request: Request) -> JSONResponse:
    """
    Handle GET /api/repos endpoint.

    Query parameters:
        url (optional): Filter repositories by URL (partial match)
        status (optional): Filter repositories by clone status

    Returns:
        200 OK: List of repositories with metadata
        401 Unauthorized: Invalid or missing API password
        500 Internal Server Error: Server error
    """
    try:
        # Get repo_manager from app state
        repo_manager = request.app.state.repo_manager
        if not repo_manager:
            error = ErrorResponse(
                error="Repository manager not available",
                suggestion="Server configuration error - contact administrator",
            )
            return JSONResponse(
                error.to_dict(), status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Parse query parameters
        url_filter = request.query_params.get("url")
        status_filter = request.query_params.get("status")

        try:
            # Get list of cached repositories
            repos_data_response = await repo_manager.list_cached_repositories()
            repos_data = repos_data_response.get("repositories", [])

            # Apply filters if provided
            if url_filter:
                repos_data = [
                    repo for repo in repos_data if url_filter in repo.get("url", "")
                ]

            if status_filter:
                repos_data = [
                    repo
                    for repo in repos_data
                    if repo.get("clone_status", {}).get("status") == status_filter
                ]

            # Convert to Repository models
            repositories = []
            for repo_data in repos_data:
                # Parse clone status (handle None)
                clone_status_data = repo_data.get("clone_status") or {}
                clone_status = CloneStatus(
                    status=clone_status_data.get("status", "unknown"),
                    started_at=clone_status_data.get("started_at"),
                    completed_at=clone_status_data.get("completed_at"),
                    error=clone_status_data.get("error"),
                )

                # Parse repo map status (handle None)
                repo_map_status_data = repo_data.get("repo_map_status") or {}
                repo_map_status = RepoMapStatus(
                    status=repo_map_status_data.get("status", "unknown"),
                    started_at=repo_map_status_data.get("started_at"),
                    completed_at=repo_map_status_data.get("completed_at"),
                    error=repo_map_status_data.get("error"),
                )

                # Create Repository model
                # Note: last_access is already an ISO string from repo_manager
                last_access_str = repo_data.get("last_access", "")

                repo = Repository(
                    cache_path=repo_data.get("cache_path", ""),
                    url=repo_data.get("url", ""),
                    last_access=last_access_str,  # Already a string
                    current_branch=repo_data.get("current_branch", ""),
                    cache_strategy=repo_data.get("cache_strategy", "shared"),
                    clone_status=clone_status,
                    repo_map_status=repo_map_status,
                    cache_size_bytes=repo_data.get("cache_size_bytes", 0),
                    cache_size_mb=repo_data.get("cache_size_mb", 0.0),
                )
                repositories.append(repo)

            # Create response
            response = ListRepositoriesResponse(
                status="success",
                total_cached=len(repositories),
                max_cached_repos=repo_manager.config.max_cached_repos,
                cache_dir=repo_manager.config.cache_dir or "/cache",
                repositories=repositories,
            )

            return JSONResponse(response.to_dict(), status_code=HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error listing repositories: {e}", exc_info=True)
            error = ErrorResponse(
                error=f"Failed to list repositories: {str(e)}",
                suggestion="Check server logs for details",
            )
            return JSONResponse(
                error.to_dict(), status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )

    except Exception as e:
        logger.error(f"Unexpected error in list handler: {e}", exc_info=True)
        error = ErrorResponse(
            error="Internal server error",
            suggestion="Contact administrator if problem persists",
        )
        return JSONResponse(error.to_dict(), status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@require_api_password
async def handle_delete_repository(request: Request) -> JSONResponse:
    """
    Handle DELETE /api/repos endpoint.

    Query parameters:
        url (required): Repository URL to delete
        OR
        path (required): Cache path to delete

    Note: Exactly one of url or path must be provided.

    Returns:
        200 OK: Repository deleted successfully
        400 Bad Request: Invalid request parameters (missing identifier, both provided, or invalid format)
        401 Unauthorized: Invalid or missing API password
        404 Not Found: Repository not found
        500 Internal Server Error: Server error
    """
    try:
        # Get repo_manager from app state
        repo_manager = request.app.state.repo_manager
        if not repo_manager:
            error = ErrorResponse(
                error="Repository manager not available",
                suggestion="Server configuration error - contact administrator",
            )
            return JSONResponse(
                error.to_dict(), status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Parse query parameters
        url_param = request.query_params.get("url")
        path_param = request.query_params.get("path")

        # Validation: exactly one identifier required
        if not url_param and not path_param:
            error = ErrorResponse(
                error="Repository identifier required",
                suggestion="Provide either 'url' or 'path' query parameter",
            )
            return JSONResponse(error.to_dict(), status_code=HTTP_400_BAD_REQUEST)

        if url_param and path_param:
            error = ErrorResponse(
                error="Cannot specify both 'url' and 'path' parameters",
                suggestion="Provide only one identifier: either 'url' or 'path'",
            )
            return JSONResponse(error.to_dict(), status_code=HTTP_400_BAD_REQUEST)

        # Determine identifier to use
        identifier = url_param or path_param

        # Validate URL format if URL provided
        if url_param:
            if not url_param.startswith(("http://", "https://", "git@")):
                error = ErrorResponse(
                    error=f"Invalid URL format: {url_param}",
                    suggestion="URL must start with http://, https://, or git@",
                )
                return JSONResponse(error.to_dict(), status_code=HTTP_400_BAD_REQUEST)

        # Attempt to delete repository
        try:
            result = await repo_manager.delete_repository(identifier)

            response = DeleteResponse(
                status="success",
                message=f"Successfully deleted repository: {identifier}",
                url=result.get("url"),
                cache_path=result.get("cache_path"),
            )
            return JSONResponse(response.to_dict(), status_code=HTTP_200_OK)

        except ValueError as e:
            # Repository not found
            error = ErrorResponse(
                error=f"Repository not found: {str(e)}",
                suggestion="Verify the repository URL or path is correct",
            )
            return JSONResponse(error.to_dict(), status_code=HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error(f"Error deleting repository: {e}", exc_info=True)
            error = ErrorResponse(
                error=f"Failed to delete repository: {str(e)}",
                suggestion="Check server logs for details",
            )
            return JSONResponse(
                error.to_dict(), status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )

    except Exception as e:
        logger.error(f"Unexpected error in delete handler: {e}", exc_info=True)
        error = ErrorResponse(
            error="Internal server error",
            suggestion="Contact administrator if problem persists",
        )
        return JSONResponse(error.to_dict(), status_code=HTTP_500_INTERNAL_SERVER_ERROR)
