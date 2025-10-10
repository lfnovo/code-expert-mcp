import hashlib
import hmac
from unittest.mock import patch

import pytest
from code_expert.webhooks.handler import handle_webhook
from code_expert.webhooks.parsers import get_repo_url
from code_expert.webhooks.security import is_valid_signature
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# --- Test Fixtures ---

SECRET = "test-secret"
VALID_PAYLOAD = {"repository": {"clone_url": "https://github.com/user/repo.git"}}
INVALID_PAYLOAD = {"foo": "bar"}


@pytest.fixture
def test_client_factory():
    def _create_client(app):
        return TestClient(app)

    return _create_client


# --- Tests for security.py ---


@pytest.mark.asyncio
@patch("os.environ.get", return_value=SECRET)
async def test_is_valid_signature_valid(mock_env):
    """Test that a valid signature returns True."""
    body = b'{"key": "value"}'
    signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

    async def app(scope, receive, send):
        request = Request(scope, receive)
        assert await is_valid_signature(request)
        await JSONResponse({"status": "ok"})(scope, receive, send)

    client = TestClient(app)
    response = client.post(
        "/", content=body, headers={"X-Hub-Signature-256": signature}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("os.environ.get", return_value=SECRET)
async def test_is_valid_signature_invalid(mock_env):
    """Test that an invalid signature returns False."""
    body = b'{"key": "value"}'

    async def app(scope, receive, send):
        request = Request(scope, receive)
        assert not await is_valid_signature(request)
        await JSONResponse({"status": "ok"})(scope, receive, send)

    client = TestClient(app)
    response = client.post(
        "/", content=body, headers={"X-Hub-Signature-256": "sha256=invalid"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("os.environ.get", return_value=SECRET)
async def test_is_valid_signature_missing_header(mock_env):
    """Test that a missing signature header returns False."""

    async def app(scope, receive, send):
        request = Request(scope, receive)
        assert not await is_valid_signature(request)
        await JSONResponse({"status": "ok"})(scope, receive, send)

    client = TestClient(app)
    response = client.post("/", content=b"{}")
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("os.environ.get", return_value=None)
async def test_is_valid_signature_missing_secret(mock_env):
    """Test that a missing webhook secret returns False."""

    async def app(scope, receive, send):
        request = Request(scope, receive)
        assert not await is_valid_signature(request)
        await JSONResponse({"status": "ok"})(scope, receive, send)

    client = TestClient(app)
    response = client.post(
        "/", content=b"{}", headers={"X-Hub-Signature-256": "sha256=anything"}
    )
    assert response.status_code == 200


# --- Tests for parsers.py ---


@pytest.mark.asyncio
async def test_get_repo_url_github_push():
    """Test parsing a valid GitHub push event."""

    async def app(scope, receive, send):
        request = Request(scope, receive)
        url = await get_repo_url(request)
        await JSONResponse({"url": url})(scope, receive, send)

    client = TestClient(app)
    response = client.post(
        "/", json=VALID_PAYLOAD, headers={"User-Agent": "GitHub-Hookshot/1.0"}
    )
    assert response.json()["url"] == "https://github.com/user/repo.git"


@pytest.mark.asyncio
async def test_get_repo_url_invalid_payload():
    """Test parsing an invalid payload."""

    async def app(scope, receive, send):
        request = Request(scope, receive)
        url = await get_repo_url(request)
        await JSONResponse({"url": url})(scope, receive, send)

    client = TestClient(app)
    response = client.post(
        "/", json=INVALID_PAYLOAD, headers={"User-Agent": "GitHub-Hookshot/1.0"}
    )
    assert response.json()["url"] is None


@pytest.mark.asyncio
async def test_get_repo_url_unknown_provider():
    """Test that an unknown provider returns None."""

    async def app(scope, receive, send):
        request = Request(scope, receive)
        url = await get_repo_url(request)
        await JSONResponse({"url": url})(scope, receive, send)

    client = TestClient(app)
    response = client.post(
        "/",
        json=VALID_PAYLOAD,
        headers={"User-Agent": "GitLab-Hookshot/1.0"},  # Different user agent
    )
    assert response.json()["url"] is None


# --- Tests for handler.py (Integration) ---


@patch("code_expert.webhooks.handler.is_valid_signature", return_value=True)
@patch(
    "code_expert.webhooks.handler.get_repo_url",
    return_value="https://github.com/user/repo.git",
)
def test_handle_webhook_success(mock_get_url, mock_is_valid):
    """Test the handler with valid signature and payload."""
    app = Starlette(
        routes=[Route("/webhooks/refresh", handle_webhook, methods=["POST"])]
    )

    # Inject a mock repo_manager into app.state
    class DummyRepo:
        async def refresh(self):
            return {"status": "success", "commit": "abc123"}

    class DummyRepoManager:
        async def get_repository(self, url):
            return DummyRepo()

    app.state.repo_manager = DummyRepoManager()
    client = TestClient(app)

    response = client.post("/webhooks/refresh", json={})
    assert response.status_code == 200
    assert response.json()["detail"] == "Repository refreshed"


@patch("code_expert.webhooks.handler.is_valid_signature", return_value=False)
def test_handle_webhook_unauthorized(mock_is_valid):
    """Test the handler with an invalid signature."""
    app = Starlette(
        routes=[Route("/webhooks/refresh", handle_webhook, methods=["POST"])]
    )
    client = TestClient(app)

    response = client.post("/webhooks/refresh", json={})
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


@patch("code_expert.webhooks.handler.is_valid_signature", return_value=True)
@patch("code_expert.webhooks.handler.get_repo_url", return_value=None)
def test_handle_webhook_bad_request(mock_get_url, mock_is_valid):
    """Test the handler with a payload that cannot be parsed."""
    app = Starlette(
        routes=[Route("/webhooks/refresh", handle_webhook, methods=["POST"])]
    )
    client = TestClient(app)

    response = client.post("/webhooks/refresh", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "Could not parse repository URL from payload"
