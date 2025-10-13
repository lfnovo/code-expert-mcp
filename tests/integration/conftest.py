"""
Pytest configuration and fixtures for integration tests.

Provides test application setup with mocked repository manager.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from code_expert.api.handlers import handle_clone_repository


@pytest.fixture
def test_app(monkeypatch):
    """
    Create a test Starlette application with API routes.

    Provides a minimal app with clone and list endpoints and mocked repo_manager.
    """
    from code_expert.api.handlers import handle_list_repositories

    # Set API password for tests
    monkeypatch.setenv("REPO_API_PASSWORD", "test-password-123")

    # Create mock repo_manager
    mock_repo_manager = Mock()
    mock_repo_manager.config = Mock()
    mock_repo_manager.config.max_cached_repos = 10
    mock_repo_manager.config.cache_dir = "/tmp/test-cache"

    # Track cloned repositories and in-progress clones
    cloned_repos = {}
    in_progress_clones = set()

    # Mock list_cached_repositories to return cloned repos
    async def mock_list_cached_repositories():
        return {
            "repositories": [
                {"url": url, "path": info["path"], "branch": info["branch"]}
                for url, info in cloned_repos.items()
            ]
        }

    mock_repo_manager.list_cached_repositories = mock_list_cached_repositories

    # Mock clone_repository with stateful behavior
    async def mock_clone_repository(url, branch=None, cache_strategy="shared"):
        # Check for unsupported providers
        if "unsupported-provider.com" in url:
            raise ValueError("Unsupported git provider")

        # Check if already cloned (completed)
        if url in cloned_repos:
            return {
                "status": "already_cloned",
                "path": cloned_repos[url]["path"],
                "current_branch": cloned_repos[url]["branch"],
            }

        # Check if already in progress (for large repos, simulate ongoing clone)
        if url in in_progress_clones:
            return {
                "status": "cloning",
                "path": f"/tmp/test-cache/{url.split('/')[-1]}",
                "current_branch": branch or "main",
            }

        # Start new clone
        path = f"/tmp/test-cache/{url.split('/')[-1]}"
        current_branch = branch or "main"

        # For "large" repos, mark as in-progress but don't complete immediately
        if "large" in url:
            in_progress_clones.add(url)
        else:
            # For normal repos, mark as completed immediately
            cloned_repos[url] = {"path": path, "branch": current_branch}

        return {
            "status": "pending",
            "path": path,
            "current_branch": current_branch,
        }

    mock_repo_manager.clone_repository = mock_clone_repository

    # Create minimal Starlette app
    app = Starlette(
        debug=True,
        routes=[
            Route("/api/repos/clone", handle_clone_repository, methods=["POST"]),
            Route("/api/repos", handle_list_repositories, methods=["GET"]),
        ],
    )

    # Attach mock repo_manager to app state
    app.state.repo_manager = mock_repo_manager

    return app


@pytest.fixture
def api_password():
    """Fixture providing the test API password."""
    return "test-password-123"


@pytest.fixture
def test_app_empty(monkeypatch):
    """
    Create a test app with empty repository cache.

    Useful for testing list endpoint with no repositories.
    """
    from code_expert.api.handlers import handle_clone_repository, handle_list_repositories

    monkeypatch.setenv("REPO_API_PASSWORD", "test-password-123")

    mock_repo_manager = Mock()
    mock_repo_manager.config = Mock()
    mock_repo_manager.config.max_cached_repos = 10
    mock_repo_manager.config.cache_dir = "/tmp/test-cache"

    async def mock_list_cached_repositories():
        return {"repositories": []}

    mock_repo_manager.list_cached_repositories = mock_list_cached_repositories

    app = Starlette(
        debug=True,
        routes=[
            Route("/api/repos/clone", handle_clone_repository, methods=["POST"]),
            Route("/api/repos", handle_list_repositories, methods=["GET"]),
        ],
    )
    app.state.repo_manager = mock_repo_manager
    return app


@pytest.fixture
def test_app_with_repos(monkeypatch):
    """
    Create a test app with pre-populated repository cache.

    Includes multiple repositories for testing list and delete functionality.
    """
    from code_expert.api.handlers import (
        handle_clone_repository,
        handle_list_repositories,
        handle_delete_repository
    )

    monkeypatch.setenv("REPO_API_PASSWORD", "test-password-123")

    mock_repo_manager = Mock()
    mock_repo_manager.config = Mock()
    mock_repo_manager.config.max_cached_repos = 10
    mock_repo_manager.config.cache_dir = "/tmp/test-cache"

    # Track repositories (mutable for delete operations)
    repos_dict = {
        "https://github.com/anthropics/anthropic-sdk-python": {
            "cache_path": "/tmp/test-cache/github/anthropics/anthropic-sdk-python-abc123",
            "url": "https://github.com/anthropics/anthropic-sdk-python",
            "last_access": "2025-10-12T10:30:00",
            "current_branch": "main",
            "cache_strategy": "shared",
            "clone_status": {
                "status": "complete",
                "started_at": "2025-10-12T10:25:00",
                "completed_at": "2025-10-12T10:28:00",
                "error": None
            },
            "repo_map_status": {
                "status": "complete",
                "started_at": "2025-10-12T10:28:00",
                "completed_at": "2025-10-12T10:29:00",
                "error": None
            },
            "cache_size_bytes": 52428800,
            "cache_size_mb": 50.0
        },
        "https://github.com/test/another-repo": {
            "cache_path": "/tmp/test-cache/github/test/another-repo-def456",
            "url": "https://github.com/test/another-repo",
            "last_access": "2025-10-12T11:00:00",
            "current_branch": "develop",
            "cache_strategy": "per-branch",
            "clone_status": {
                "status": "complete",
                "started_at": "2025-10-12T10:55:00",
                "completed_at": "2025-10-12T10:58:00",
                "error": None
            },
            "repo_map_status": {
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "error": None
            },
            "cache_size_bytes": 10485760,
            "cache_size_mb": 10.0
        }
    }

    # Mock list_cached_repositories to return repos from dict
    async def mock_list_cached_repositories():
        return {"repositories": list(repos_dict.values())}

    mock_repo_manager.list_cached_repositories = mock_list_cached_repositories

    # Mock delete_repository
    async def mock_delete_repository(identifier: str):
        """Delete repository by URL or path."""
        # Try to find by URL first
        if identifier in repos_dict:
            url = identifier
            del repos_dict[url]
            return {"status": "success", "url": url}

        # Try to find by path
        for url, repo_data in list(repos_dict.items()):
            if repo_data.get("cache_path") == identifier:
                del repos_dict[url]
                return {"status": "success", "url": url}

        # Not found
        raise ValueError(f"Repository not found: {identifier}")

    mock_repo_manager.delete_repository = mock_delete_repository

    app = Starlette(
        debug=True,
        routes=[
            Route("/api/repos/clone", handle_clone_repository, methods=["POST"]),
            Route("/api/repos", handle_list_repositories, methods=["GET"]),
            Route("/api/repos", handle_delete_repository, methods=["DELETE"]),
        ],
    )
    app.state.repo_manager = mock_repo_manager
    return app
