"""
Simple HTTP transport for MCP server using Streamable HTTP protocol.
No OAuth, just direct MCP access like the official examples.
"""

import asyncio
import contextlib
import logging
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Optional

import click
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from code_expert.config import load_config
from code_expert.mcp.server.app import create_mcp_server

# Configure logging
logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("code_expert.mcp.simple_http")


async def run_simple_http_server(
    host: str = "0.0.0.0",
    port: int = 3001,
    config_overrides: dict = None,
    use_https: bool = True,
):
    """Run the MCP server with simple HTTP transport."""
    # Create MCP server with configuration
    config = load_config(overrides=config_overrides or {})
    fast_mcp_server = create_mcp_server(config)

    logger.info(f"Starting Simple MCP HTTP server on {host}:{port}")

    # Access the internal lowlevel MCP server from FastMCP
    # FastMCP stores it as _mcp_server
    mcp_server = fast_mcp_server._mcp_server

    # Create the session manager - NO authentication
    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        json_response=False,  # Use SSE for streaming
    )

    # ASGI handler for streamable HTTP connections
    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        """Handle MCP requests."""
        logger.info(f"MCP Request: {scope.get('method')} {scope.get('path')}")
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        """Manage session manager lifecycle."""
        async with session_manager.run():
            logger.info("MCP StreamableHTTP session manager started!")
            yield
            logger.info("MCP StreamableHTTP session manager shutting down...")

    # Create fake OAuth endpoints that just redirect to allow access
    from starlette.responses import JSONResponse, RedirectResponse
    from starlette.routing import Route

    async def fake_oauth_metadata(request):
        """Return OAuth metadata to satisfy Claude's discovery."""
        return JSONResponse(
            {
                "issuer": f"https://{request.headers.get('host', 'localhost:3001')}",
                "authorization_endpoint": f"https://{request.headers.get('host', 'localhost:3001')}/authorize",
                "token_endpoint": f"https://{request.headers.get('host', 'localhost:3001')}/token",
            }
        )

    async def fake_authorize(request):
        """Fake authorization that immediately approves."""
        redirect_uri = request.query_params.get(
            "redirect_uri", "https://claude.ai/api/mcp/auth_callback"
        )
        state = request.query_params.get("state", "")
        # Just redirect back with a fake code
        return RedirectResponse(f"{redirect_uri}?code=fake_code&state={state}")

    async def fake_token(request):
        """Return a fake token."""
        return JSONResponse(
            {
                "access_token": "fake_token_no_auth_needed",
                "token_type": "Bearer",
                "expires_in": 86400,
            }
        )

    # Import webhook handler at the top of the function
    from code_expert.webhooks.handler import handle_webhook

    async def webhook_endpoint(request):
        # Attach repo_manager from app state to request
        request.app.state.repo_manager = app.state.repo_manager
        return await handle_webhook(request)

    # Create Starlette app with MCP endpoint and fake OAuth
    app = Starlette(
        debug=True,
        routes=[
            Route("/.well-known/oauth-authorization-server", fake_oauth_metadata),
            Route("/.well-known/oauth-protected-resource", fake_oauth_metadata),
            Route("/authorize", fake_authorize),
            Route("/token", fake_token, methods=["POST"]),
            Route("/webhook", webhook_endpoint, methods=["POST"]),  # Must come before Mount
            Mount("/", app=handle_mcp),  # Mount MCP at root since Claude posts there
        ],
        lifespan=lifespan,
    )

    # Attach repo_manager to app state for webhook handler
    app.state.repo_manager = (
        fast_mcp_server._mcp_server.repo_manager
        if hasattr(fast_mcp_server._mcp_server, "repo_manager")
        else None
    )

    # Import uvicorn
    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn is required. Install with: uv pip install uvicorn")
        sys.exit(1)

    # Prepare SSL if needed
    ssl_keyfile = None
    ssl_certfile = None

    if use_https:
        cert_dir = Path("/app/certs")
        if not cert_dir.exists():
            cert_dir = Path.cwd() / "certs"

        cert_file = cert_dir / "server.crt"
        key_file = cert_dir / "server.key"

        if cert_file.exists() and key_file.exists():
            ssl_certfile = str(cert_file)
            ssl_keyfile = str(key_file)
            logger.info(f"Using SSL certificate from {cert_file}")
        else:
            logger.warning("No SSL certificate found. Running HTTP only.")
            use_https = False

    # Configure and run uvicorn
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
    )

    server = uvicorn.Server(config)
    await server.serve()


@click.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=3001, help="Port to listen on")
@click.option("--cache-dir", help="Directory to store repository cache")
@click.option(
    "--max-cached-repos", type=int, help="Maximum number of cached repositories"
)
@click.option(
    "--https/--no-https", default=True, help="Enable HTTPS (default: enabled)"
)
def main(
    host: str,
    port: int,
    cache_dir: Optional[str] = None,
    max_cached_repos: Optional[int] = None,
    https: bool = True,
) -> int:
    """Run the simple MCP server without OAuth."""
    try:
        # Use environment variables as defaults
        if max_cached_repos is None and os.environ.get("MAX_CACHED_REPOS"):
            max_cached_repos = int(os.environ.get("MAX_CACHED_REPOS"))
        if cache_dir is None and os.environ.get("CACHE_DIR"):
            cache_dir = os.environ.get("CACHE_DIR")

        # Create config overrides
        overrides = {}
        if cache_dir or max_cached_repos:
            overrides["repository"] = {}
            if cache_dir:
                overrides["repository"]["cache_dir"] = cache_dir
            if max_cached_repos:
                overrides["repository"]["max_cached_repos"] = max_cached_repos

        # Run the server
        asyncio.run(run_simple_http_server(host, port, overrides, https))
        return 0
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
