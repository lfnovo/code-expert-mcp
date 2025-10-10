from starlette.requests import Request
from starlette.responses import JSONResponse

from .parsers import get_repo_url
from .security import is_valid_signature


async def handle_webhook(request: Request) -> JSONResponse:
    """
    Handles incoming webhooks to trigger repository refreshes.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Webhook request received")

    if not await is_valid_signature(request):
        logger.warning("Invalid webhook signature")
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    repo_url = await get_repo_url(request)
    logger.info(f"Parsed repo URL: {repo_url}")
    if not repo_url:
        logger.error("Could not parse repository URL from payload")
        return JSONResponse(
            {"detail": "Could not parse repository URL from payload"}, status_code=400
        )

    repo_manager = getattr(request.app.state, "repo_manager", None)
    logger.info(f"Repo manager: {repo_manager}")
    if not repo_manager:
        logger.error("Repository manager not available in app.state")
        return JSONResponse(
            {"detail": "Repository manager not available"}, status_code=500
        )

    try:
        repo = await repo_manager.get_repository(repo_url)
    except Exception as e:
        logger.error(f"Error accessing repository: {e}")
        return JSONResponse(
            {"detail": f"Error accessing repository: {e}"}, status_code=500
        )

    if not repo:
        logger.info(f"Repository not in cache, attempting to clone: {repo_url}")
        try:
            clone_result = await repo_manager.clone_repository(repo_url)
            if clone_result.get("status") in ["already_cloned", "pending"]:
                logger.info(f"Repository cloned/cloning: {clone_result}")
                # Try to get the repository again
                repo = await repo_manager.get_repository(repo_url)
                if not repo:
                    return JSONResponse(
                        {"detail": "Repository cloned but not available yet", "result": clone_result},
                        status_code=202  # Accepted - processing
                    )
            else:
                logger.error(f"Failed to clone repository: {clone_result}")
                return JSONResponse(
                    {"detail": "Failed to clone repository", "error": clone_result},
                    status_code=500
                )
        except Exception as e:
            logger.error(f"Error cloning repository: {e}")
            return JSONResponse(
                {"detail": f"Error cloning repository: {e}"}, status_code=500
            )

    refresh_result = await repo.refresh()
    if refresh_result.get("status") == "success":
        return JSONResponse(
            {"detail": "Repository refreshed", "commit": refresh_result.get("commit")},
            status_code=200,
        )
    elif refresh_result.get("status") == "not_git_repo":
        return JSONResponse({"detail": "Not a git repository"}, status_code=400)
    else:
        return JSONResponse(
            {"detail": "Refresh failed", "error": refresh_result.get("error")},
            status_code=500,
        )
