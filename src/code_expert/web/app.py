"""
Web UI server with API endpoints.
Separate from MCP server to avoid routing conflicts.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import click
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

# Configure logging
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("code_expert.web")


async def run_web_server(
    host: str = "0.0.0.0",
    port: int = 3000,
    config_overrides: Optional[dict] = None,
):
    """Run the web UI server with API endpoints."""
    from code_expert.config import load_config
    from code_expert.mcp.server.app import create_mcp_server
    from code_expert.api.handlers import (
        handle_clone_repository,
        handle_list_repositories,
        handle_delete_repository,
    )
    from code_expert.webhooks.handler import handle_webhook

    # Create MCP server to get access to repo_manager
    config = load_config(overrides=config_overrides or {})
    fast_mcp_server = create_mcp_server(config)
    mcp_server = fast_mcp_server._mcp_server

    logger.info(f"Starting Web UI server on {host}:{port}")

    # Webhook endpoint
    async def webhook_endpoint(request):
        request.app.state.repo_manager = app.state.repo_manager
        return await handle_webhook(request)

    # API routes
    api_routes = [
        Route("/api/repos/clone", handle_clone_repository, methods=["POST"]),
        Route("/api/repos", handle_list_repositories, methods=["GET"]),
        Route("/api/repos", handle_delete_repository, methods=["DELETE"]),
    ]

    # Prepare frontend static files path
    frontend_dist = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
    logger.info(f"Looking for frontend at: {frontend_dist}")

    routes = [
        Route("/webhook", webhook_endpoint, methods=["POST"]),
        *api_routes,
    ]

    # Add frontend static files if they exist
    if frontend_dist.exists() and frontend_dist.is_dir():
        logger.info(f"Serving frontend from {frontend_dist}")
        routes.append(Mount("/", app=StaticFiles(directory=str(frontend_dist), html=True), name="frontend"))
    else:
        logger.warning(f"Frontend not found at {frontend_dist}")

    # Create Starlette app
    app = Starlette(
        debug=True,
        routes=routes,
    )

    # Attach repo_manager to app state
    app.state.repo_manager = (
        mcp_server.repo_manager
        if hasattr(mcp_server, "repo_manager")
        else None
    )

    logger.info(f"Web UI available at: http://{host}:{port}/")
    logger.info(f"API available at: http://{host}:{port}/api/*")

    # Configure and run uvicorn
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )

    server = uvicorn.Server(config)
    await server.serve()


@click.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=3000, help="Port to listen on")
@click.option("--cache-dir", help="Directory to store repository cache")
@click.option(
    "--max-cached-repos", type=int, help="Maximum number of cached repositories"
)
def main(
    host: str,
    port: int,
    cache_dir: Optional[str] = None,
    max_cached_repos: Optional[int] = None,
) -> int:
    """Run the web UI server."""
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
        asyncio.run(run_web_server(host, port, overrides))
        return 0
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
