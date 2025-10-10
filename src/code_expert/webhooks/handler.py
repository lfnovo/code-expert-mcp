from starlette.requests import Request
from starlette.responses import JSONResponse

from .parsers import get_repo_url
from .security import is_valid_signature


async def handle_webhook(request: Request) -> JSONResponse:
    """
    Handles incoming webhooks to trigger repository refreshes.
    """
    if not await is_valid_signature(request):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    repo_url = await get_repo_url(request)
    if not repo_url:
        return JSONResponse(
            {"detail": "Could not parse repository URL from payload"}, status_code=400
        )

    repo_manager = getattr(request.app.state, "repo_manager", None)
    if not repo_manager:
        return JSONResponse(
            {"detail": "Repository manager not available"}, status_code=500
        )

    try:
        repo = await repo_manager.get_repository(repo_url)
    except Exception as e:
        return JSONResponse(
            {"detail": f"Error accessing repository: {e}"}, status_code=500
        )

    if not repo:
        return JSONResponse(
            {"detail": "Repository not found in cache"}, status_code=404
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
