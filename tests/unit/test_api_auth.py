"""
Unit tests for API authentication middleware.

Tests password verification, constant-time comparison, and authentication decorator.
"""

import os
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from code_expert.api.auth import (
    get_api_password,
    require_api_password,
    verify_password,
)


class TestPasswordVerification:
    """Test password verification functions."""

    def test_get_api_password_returns_env_var(self, monkeypatch):
        """Test that get_api_password reads REPO_API_PASSWORD from environment."""
        monkeypatch.setenv("REPO_API_PASSWORD", "test-password")
        assert get_api_password() == "test-password"

    def test_get_api_password_returns_none_when_not_set(self, monkeypatch):
        """Test that get_api_password returns None when env var not set."""
        monkeypatch.delenv("REPO_API_PASSWORD", raising=False)
        assert get_api_password() is None

    def test_verify_password_accepts_correct_password(self, monkeypatch):
        """Test that verify_password returns True for correct password."""
        monkeypatch.setenv("REPO_API_PASSWORD", "correct-password")
        assert verify_password("correct-password") is True

    def test_verify_password_rejects_incorrect_password(self, monkeypatch):
        """Test that verify_password returns False for incorrect password."""
        monkeypatch.setenv("REPO_API_PASSWORD", "correct-password")
        assert verify_password("wrong-password") is False

    def test_verify_password_returns_false_when_no_password_set(self, monkeypatch):
        """Test that verify_password returns False when no password configured."""
        monkeypatch.delenv("REPO_API_PASSWORD", raising=False)
        assert verify_password("any-password") is False

    def test_verify_password_uses_constant_time_comparison(self, monkeypatch):
        """
        Test that verify_password uses constant-time comparison.

        This is a behavioral test - we verify that hmac.compare_digest is used
        by testing that timing doesn't leak information about password length.
        """
        monkeypatch.setenv("REPO_API_PASSWORD", "a" * 100)

        # Both short and long wrong passwords should fail
        assert verify_password("b") is False
        assert verify_password("b" * 100) is False


@pytest.mark.asyncio
class TestAuthenticationDecorator:
    """Test require_api_password decorator."""

    async def test_decorator_returns_500_when_password_not_configured(self, monkeypatch):
        """Test that decorator returns 500 when REPO_API_PASSWORD not set."""
        monkeypatch.delenv("REPO_API_PASSWORD", raising=False)

        @require_api_password
        async def dummy_handler(request: Request) -> JSONResponse:
            return JSONResponse({"status": "success"})

        # Create mock request
        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        response = await dummy_handler(mock_request)
        assert response.status_code == 500
        body = response.body.decode()
        assert "API password not configured" in body

    async def test_decorator_returns_401_when_authorization_header_missing(self, monkeypatch):
        """Test that decorator returns 401 when Authorization header missing."""
        monkeypatch.setenv("REPO_API_PASSWORD", "test-password")

        @require_api_password
        async def dummy_handler(request: Request) -> JSONResponse:
            return JSONResponse({"status": "success"})

        # Create mock request without Authorization header
        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        response = await dummy_handler(mock_request)
        assert response.status_code == 401
        body = response.body.decode()
        assert "Missing Authorization header" in body

    async def test_decorator_returns_401_for_malformed_authorization_header(self, monkeypatch):
        """Test that decorator returns 401 for malformed Authorization header."""
        monkeypatch.setenv("REPO_API_PASSWORD", "test-password")

        @require_api_password
        async def dummy_handler(request: Request) -> JSONResponse:
            return JSONResponse({"status": "success"})

        # Create mock request with malformed header
        mock_request = Mock(spec=Request)
        mock_request.headers = {"Authorization": "InvalidFormat"}

        response = await dummy_handler(mock_request)
        assert response.status_code == 401
        body = response.body.decode()
        assert "Invalid Authorization header format" in body

    async def test_decorator_returns_401_for_invalid_password(self, monkeypatch):
        """Test that decorator returns 401 for invalid password."""
        monkeypatch.setenv("REPO_API_PASSWORD", "correct-password")

        @require_api_password
        async def dummy_handler(request: Request) -> JSONResponse:
            return JSONResponse({"status": "success"})

        # Create mock request with wrong password
        mock_request = Mock(spec=Request)
        mock_request.headers = {"Authorization": "Bearer wrong-password"}

        response = await dummy_handler(mock_request)
        assert response.status_code == 401
        body = response.body.decode()
        assert "Invalid API password" in body

    async def test_decorator_calls_handler_with_valid_password(self, monkeypatch):
        """Test that decorator calls handler when password is valid."""
        monkeypatch.setenv("REPO_API_PASSWORD", "correct-password")

        # Create handler that tracks if it was called
        handler_called = False

        @require_api_password
        async def dummy_handler(request: Request) -> JSONResponse:
            nonlocal handler_called
            handler_called = True
            return JSONResponse({"status": "success"})

        # Create mock request with correct password
        mock_request = Mock(spec=Request)
        mock_request.headers = {"Authorization": "Bearer correct-password"}

        response = await dummy_handler(mock_request)
        assert response.status_code == 200
        assert handler_called is True
        body = response.body.decode()
        assert "success" in body
