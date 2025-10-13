"""
Base classes and utilities for API integration tests.

Provides test client setup, authentication helpers, and common test utilities.
"""

import os
from typing import Dict, Optional

import pytest
from starlette.testclient import TestClient


class APITestBase:
    """Base class for API integration tests."""

    @pytest.fixture(autouse=True)
    def setup_test_env(self, monkeypatch):
        """Setup test environment with API password."""
        # Set test API password
        monkeypatch.setenv("REPO_API_PASSWORD", "test-password-123")

    def get_auth_headers(self, password: Optional[str] = "test-password-123") -> Dict[str, str]:
        """
        Get authentication headers for API requests.

        Args:
            password: API password to use (defaults to test password)

        Returns:
            Dictionary with Authorization header
        """
        if password is None:
            return {}
        return {"Authorization": f"Bearer {password}"}

    def get_invalid_auth_headers(self) -> Dict[str, str]:
        """Get invalid authentication headers for testing auth failure."""
        return {"Authorization": "Bearer wrong-password"}

    def get_malformed_auth_headers(self) -> Dict[str, str]:
        """Get malformed authentication headers for testing."""
        return {"Authorization": "InvalidFormat"}


@pytest.fixture
def api_password():
    """Fixture providing the test API password."""
    return "test-password-123"
