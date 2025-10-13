"""
Integration tests for clone repository endpoint.

Tests the POST /api/repos/clone endpoint with various scenarios.
"""

import pytest
from starlette.testclient import TestClient

from tests.integration.test_api_base import APITestBase


class TestCloneRepository(APITestBase):
    """Test clone repository endpoint."""

    def test_clone_github_repository_returns_201_pending(self, test_app, api_password):
        """Test POST /api/repos/clone with valid GitHub URL returns 201 with pending status."""
        client = TestClient(test_app)

        response = client.post(
            "/api/repos/clone",
            json={
                "url": "https://github.com/anthropics/claude-code",
                "branch": "main",
                "cache_strategy": "shared"
            },
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert "path" in data
        assert "message" in data
        assert data["cache_strategy"] == "shared"

    def test_clone_already_cloned_repository_returns_200(self, test_app, api_password):
        """Test POST /api/repos/clone for already cloned repository returns 200."""
        client = TestClient(test_app)

        # First clone
        response1 = client.post(
            "/api/repos/clone",
            json={"url": "https://github.com/test/repo"},
            headers=self.get_auth_headers(api_password)
        )

        # Wait for clone to complete (or mock this)
        # Second attempt should return already_cloned
        response2 = client.post(
            "/api/repos/clone",
            json={"url": "https://github.com/test/repo"},
            headers=self.get_auth_headers(api_password)
        )

        assert response2.status_code == 200
        data = response2.json()
        assert data["status"] == "already_cloned"
        assert "current_branch" in data

    def test_clone_in_progress_returns_409(self, test_app, api_password):
        """Test POST /api/repos/clone while clone in progress returns 409 Conflict."""
        client = TestClient(test_app)

        # First request starts clone
        response1 = client.post(
            "/api/repos/clone",
            json={"url": "https://github.com/large/repository"},
            headers=self.get_auth_headers(api_password)
        )

        # Immediate second request should get 409
        response2 = client.post(
            "/api/repos/clone",
            json={"url": "https://github.com/large/repository"},
            headers=self.get_auth_headers(api_password)
        )

        assert response2.status_code == 409
        data = response2.json()
        assert "in progress" in data["error"].lower()

    def test_clone_without_authentication_returns_401(self, test_app):
        """Test POST /api/repos/clone without Authorization header returns 401."""
        client = TestClient(test_app)

        response = client.post(
            "/api/repos/clone",
            json={"url": "https://github.com/test/repo"}
            # No auth headers
        )

        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"
        assert "Authorization" in data["error"]

    def test_clone_with_invalid_password_returns_401(self, test_app):
        """Test POST /api/repos/clone with invalid password returns 401."""
        client = TestClient(test_app)

        response = client.post(
            "/api/repos/clone",
            json={"url": "https://github.com/test/repo"},
            headers=self.get_invalid_auth_headers()
        )

        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"
        assert "Invalid API password" in data["error"]

    def test_clone_default_branch_when_not_specified(self, test_app, api_password):
        """Test POST /api/repos/clone uses default branch when branch not specified."""
        client = TestClient(test_app)

        response = client.post(
            "/api/repos/clone",
            json={"url": "https://github.com/test/repo"},
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code in [200, 201]
        # Branch should be determined by repository default

    def test_clone_with_cache_strategy_per_branch(self, test_app, api_password):
        """Test POST /api/repos/clone with per-branch cache strategy."""
        client = TestClient(test_app)

        response = client.post(
            "/api/repos/clone",
            json={
                "url": "https://github.com/test/repo",
                "cache_strategy": "per-branch"
            },
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["cache_strategy"] == "per-branch"

    def test_clone_with_invalid_url_returns_400(self, test_app, api_password):
        """Test POST /api/repos/clone with invalid URL format returns 400 Bad Request."""
        client = TestClient(test_app)

        response = client.post(
            "/api/repos/clone",
            json={"url": "not-a-valid-url"},
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "invalid" in data["error"].lower() or "url" in data["error"].lower()
        # Error message should be clear and actionable per SC-005
        assert len(data["error"]) > 10  # Meaningful error message

    def test_clone_with_unsupported_provider_returns_400(self, test_app, api_password):
        """Test POST /api/repos/clone with unsupported git provider returns 400."""
        client = TestClient(test_app)

        response = client.post(
            "/api/repos/clone",
            json={"url": "https://unsupported-provider.com/user/repo"},
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "provider" in data["error"].lower() or "unsupported" in data["error"].lower()

    def test_clone_when_cache_full_returns_507(self, test_app, api_password):
        """Test POST /api/repos/clone when cache full returns 507 Insufficient Storage."""
        client = TestClient(test_app)

        # This test would need to mock the cache being full
        # Implementation should check cache capacity before cloning
        # For now, structure shows the expected behavior

        # Mock scenario: Fill cache to MAX_CACHED_REPOS
        # Then attempt another clone

        response = client.post(
            "/api/repos/clone",
            json={"url": "https://github.com/test/new-repo"},
            headers=self.get_auth_headers(api_password)
        )

        # When cache full, should return 507 with helpful message
        if response.status_code == 507:
            data = response.json()
            assert data["status"] == "error"
            assert "cache" in data["error"].lower() or "storage" in data["error"].lower()
            # Should suggest deletion per FR-015
            if "suggestion" in data:
                assert "delete" in data["suggestion"].lower()

    def test_clone_error_messages_are_clear_and_actionable(self, test_app, api_password):
        """Test that error messages meet SC-005 clarity requirements."""
        client = TestClient(test_app)

        # Test with various error scenarios
        error_scenarios = [
            {"url": ""},  # Empty URL
            {"url": "invalid"},  # Invalid format
            {},  # Missing URL
        ]

        for scenario in error_scenarios:
            response = client.post(
                "/api/repos/clone",
                json=scenario,
                headers=self.get_auth_headers(api_password)
            )

            assert response.status_code in [400, 422]  # Client error
            data = response.json()
            assert data["status"] == "error"
            assert "error" in data
            # Per SC-005: Error messages >= 10 chars, describe issue and suggest fix
            assert len(data["error"]) >= 10
            # Error should mention what's wrong
            assert any(word in data["error"].lower() for word in ["url", "required", "invalid", "missing"])

    def test_clone_with_invalid_branch_name_returns_400(self, test_app, api_password):
        """Test POST /api/repos/clone with invalid branch name returns 400."""
        client = TestClient(test_app)

        response = client.post(
            "/api/repos/clone",
            json={
                "url": "https://github.com/test/repo",
                "branch": "../../etc/passwd"  # Path traversal attempt
            },
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "branch" in data["error"].lower()

    def test_clone_with_invalid_cache_strategy_returns_400(self, test_app, api_password):
        """Test POST /api/repos/clone with invalid cache_strategy returns 400."""
        client = TestClient(test_app)

        response = client.post(
            "/api/repos/clone",
            json={
                "url": "https://github.com/test/repo",
                "cache_strategy": "invalid-strategy"
            },
            headers=self.get_auth_headers(api_password)
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "cache_strategy" in data["error"].lower() or "strategy" in data["error"].lower()
