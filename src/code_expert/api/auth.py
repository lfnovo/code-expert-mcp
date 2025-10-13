"""
Authentication middleware for Repository Management API.

Provides password-based authentication using REPO_API_PASSWORD environment variable.
"""

import hmac
import os
from functools import wraps
from typing import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse


def get_api_password() -> str | None:
    """Get the API password from environment variable."""
    return os.getenv("REPO_API_PASSWORD")


def verify_password(provided_password: str) -> bool:
    """
    Verify the provided password against REPO_API_PASSWORD using constant-time comparison.

    Args:
        provided_password: The password to verify

    Returns:
        True if password matches, False otherwise
    """
    expected_password = get_api_password()
    if not expected_password:
        return False

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(provided_password, expected_password)


def require_api_password(
    handler: Callable[[Request], Awaitable[JSONResponse]],
) -> Callable[[Request], Awaitable[JSONResponse]]:
    """
    Decorator to require API password authentication for a handler.

    Validates Authorization: Bearer <password> header format.
    Returns 401 Unauthorized if authentication fails.

    Args:
        handler: The async handler function to protect

    Returns:
        Wrapped handler that checks authentication first
    """

    @wraps(handler)
    async def wrapper(request: Request) -> JSONResponse:
        # Check if REPO_API_PASSWORD is configured
        if not get_api_password():
            return JSONResponse(
                {"status": "error", "error": "API password not configured on server"},
                status_code=500,
            )

        # Check for Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                {"status": "error", "error": "Missing Authorization header"},
                status_code=401,
            )

        # Validate Bearer token format
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0] != "Bearer":
            return JSONResponse(
                {
                    "status": "error",
                    "error": "Invalid Authorization header format. Expected: Bearer <password>",
                },
                status_code=401,
            )

        provided_password = parts[1]

        # Verify password
        if not verify_password(provided_password):
            return JSONResponse(
                {"status": "error", "error": "Invalid API password"}, status_code=401
            )

        # Authentication successful, call the handler
        return await handler(request)

    return wrapper
