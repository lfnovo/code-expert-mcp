from starlette.requests import Request


async def get_repo_url(request: Request) -> str | None:
    """
    Parses the webhook payload to extract the repository clone URL.
    """
    # For now, we only support GitHub. We can add logic to detect other
    # providers based on headers like 'User-Agent'.
    if "GitHub-Hookshot" in request.headers.get("User-Agent", ""):
        return await _parse_github_push(request)
    return None


async def _parse_github_push(request: Request) -> str | None:
    """
    Parses a GitHub push event payload.
    """
    try:
        payload = await request.json()
        repo = payload.get("repository")
        if repo and isinstance(repo, dict):
            clone_url = repo.get("clone_url")
            if isinstance(clone_url, str):
                return clone_url
        return None
    except Exception:
        return None
