"""
Integration tests for delete repository endpoint.

Tests the DELETE /api/repos endpoint with various scenarios.
"""

import pytest
from starlette.testclient import TestClient

from tests.integration.test_api_base import APITestBase


class TestDeleteRepository(APITestBase):
    """Test delete repository endpoint."""

    def test_delete_repository_by_url_returns_200(self, test_app_with_repos, api_password):
        """Test DELETE /api/repos with url parameter returns 200."""
        client = TestClient(test_app_with_repos)

        response = client.delete(
            "/api/repos?url=https://github.com/anthropics/anthropic-sdk-python",
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "deleted" in data["message"].lower()
        assert data["url"] == "https://github.com/anthropics/anthropic-sdk-python"

    def test_delete_repository_by_path_returns_200(self, test_app_with_repos, api_password):
        """Test DELETE /api/repos with path parameter returns 200."""
        client = TestClient(test_app_with_repos)

        response = client.delete(
            "/api/repos?path=/tmp/test-cache/github/anthropics/anthropic-sdk-python-abc123",
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "deleted" in data["message"].lower()

    def test_delete_nonexistent_repository_returns_404(self, test_app_with_repos, api_password):
        """Test DELETE /api/repos with nonexistent repository returns 404."""
        client = TestClient(test_app_with_repos)

        response = client.delete(
            "/api/repos?url=https://github.com/nonexistent/repo",
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert "not found" in data["error"].lower()

    def test_delete_without_identifier_returns_400(self, test_app_with_repos, api_password):
        """Test DELETE /api/repos without url or path parameter returns 400."""
        client = TestClient(test_app_with_repos)

        response = client.delete(
            "/api/repos",
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "required" in data["error"].lower()

    def test_delete_with_both_identifiers_returns_400(self, test_app_with_repos, api_password):
        """Test DELETE /api/repos with both url and path returns 400."""
        client = TestClient(test_app_with_repos)

        response = client.delete(
            "/api/repos?url=https://github.com/test/repo&path=/tmp/test-cache/repo",
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "only one" in data["error"].lower() or "both" in data["error"].lower()

    def test_delete_without_authentication_returns_401(self, test_app_with_repos):
        """Test DELETE /api/repos without Authorization header returns 401."""
        client = TestClient(test_app_with_repos)

        response = client.delete("/api/repos?url=https://github.com/test/repo")

        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"
        assert "Authorization" in data["error"]

    def test_delete_with_invalid_password_returns_401(self, test_app_with_repos):
        """Test DELETE /api/repos with invalid password returns 401."""
        client = TestClient(test_app_with_repos)

        response = client.delete(
            "/api/repos?url=https://github.com/test/repo",
            headers=self.get_invalid_auth_headers()
        )

        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"
        assert "Invalid API password" in data["error"]

    def test_delete_with_invalid_url_format_returns_400(self, test_app_with_repos, api_password):
        """Test DELETE /api/repos with invalid URL format returns 400."""
        client = TestClient(test_app_with_repos)

        response = client.delete(
            "/api/repos?url=not-a-valid-url",
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "invalid" in data["error"].lower() or "url" in data["error"].lower()
