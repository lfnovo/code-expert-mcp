import hashlib
import hmac
import os

from starlette.requests import Request


async def is_valid_signature(request: Request) -> bool:
    """
    Validates the GitHub webhook signature.
    """
    webhook_secret = os.environ.get("WEBHOOK_SECRET")
    if not webhook_secret:
        # If the secret is not configured, we cannot validate the signature.
        # For security, we should treat this as an invalid request.
        return False

    signature_header = request.headers.get("X-Hub-Signature-256")
    if not signature_header:
        return False

    body = await request.body()
    expected_signature = (
        "sha256=" + hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    )

    return hmac.compare_digest(expected_signature, signature_header)
