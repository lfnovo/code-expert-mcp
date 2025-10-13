"""
Integration tests for list repositories endpoint.

Tests the GET /api/repos endpoint with various scenarios.
"""

import pytest
from starlette.testclient import TestClient

from tests.integration.test_api_base import APITestBase


class TestListRepositories(APITestBase):
    """Test list repositories endpoint."""

    def test_list_repositories_returns_200_with_array(self, test_app, api_password):
        """Test GET /api/repos returns 200 with repository array."""
        client = TestClient(test_app)

        response = client.get(
            "/api/repos",
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "repositories" in data
        assert isinstance(data["repositories"], list)
        assert "total_cached" in data
        assert "max_cached_repos" in data
        assert "cache_dir" in data

    def test_list_empty_cache_returns_empty_array(self, test_app_empty, api_password):
        """Test GET /api/repos with empty cache returns empty array."""
        client = TestClient(test_app_empty)

        response = client.get(
            "/api/repos",
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["repositories"] == []
        assert data["total_cached"] == 0

    def test_list_repository_metadata_fields(self, test_app_with_repos, api_password):
        """Test repository metadata includes all required fields."""
        client = TestClient(test_app_with_repos)

        response = client.get(
            "/api/repos",
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["repositories"]) > 0

        repo = data["repositories"][0]
        # Required fields
        assert "cache_path" in repo
        assert "url" in repo
        assert "last_access" in repo
        assert "current_branch" in repo
        assert "cache_strategy" in repo

        # Status objects
        assert "clone_status" in repo
        assert "repo_map_status" in repo

        # Size fields
        assert "cache_size_bytes" in repo
        assert "cache_size_mb" in repo

    def test_list_filter_by_url(self, test_app_with_repos, api_password):
        """Test GET /api/repos with url query parameter."""
        client = TestClient(test_app_with_repos)

        # Filter for specific repository
        response = client.get(
            "/api/repos?url=https://github.com/anthropics/anthropic-sdk-python",
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 200
        data = response.json()
        # Should only return matching repositories
        for repo in data["repositories"]:
            assert "anthropic-sdk-python" in repo["url"]

    def test_list_without_authentication_returns_401(self, test_app):
        """Test GET /api/repos without Authorization header returns 401."""
        client = TestClient(test_app)

        response = client.get("/api/repos")

        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"
        assert "Authorization" in data["error"]

    def test_list_with_invalid_password_returns_401(self, test_app):
        """Test GET /api/repos with invalid password returns 401."""
        client = TestClient(test_app)

        response = client.get(
            "/api/repos",
            headers=self.get_invalid_auth_headers()
        )

        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"
        assert "Invalid API password" in data["error"]
