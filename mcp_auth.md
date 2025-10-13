# MCP Server Authentication Architecture

## Overview

The Code Expert MCP server has **NO REAL AUTHENTICATION** for MCP protocol connections. It uses a "fake OAuth" system that automatically approves all connections to satisfy Claude's requirement for OAuth discovery endpoints.

## Two Separate Authentication Systems

### 1. MCP Protocol (Port 3001) - NO Authentication

**Location**: `/Users/luisnovo/dev/projetos/code-expert-mcp/src/code_expert/mcp/server/simple_http_app.py`

The MCP server implements fake OAuth endpoints that immediately approve all connections:

```python
# Lines 50-54: Session Manager - NO authentication
session_manager = StreamableHTTPSessionManager(
    app=mcp_server,
    json_response=False,  # Use SSE for streaming
)
```

#### Fake OAuth Endpoints

**Discovery Endpoints** (Lines 74-82):
- `/.well-known/oauth-authorization-server`
- `/.well-known/oauth-protected-resource`

Returns metadata pointing to fake OAuth endpoints:
```python
async def fake_oauth_metadata(request):
    """Return OAuth metadata to satisfy Claude's discovery."""
    return JSONResponse({
        "issuer": f"https://{request.headers.get('host', 'localhost:3001')}",
        "authorization_endpoint": f"https://{request.headers.get('host', 'localhost:3001')}/authorize",
        "token_endpoint": f"https://{request.headers.get('host', 'localhost:3001')}/token",
    })
```

**Authorization Endpoint** (Lines 84-91):
```python
async def fake_authorize(request):
    """Fake authorization that immediately approves."""
    redirect_uri = request.query_params.get(
        "redirect_uri", "https://claude.ai/api/mcp/auth_callback"
    )
    state = request.query_params.get("state", "")
    # Just redirect back with a fake code
    return RedirectResponse(f"{redirect_uri}?code=fake_code&state={state}")
```

**Token Endpoint** (Lines 93-101):
```python
async def fake_token(request):
    """Return a fake token."""
    return JSONResponse({
        "access_token": "fake_token_no_auth_needed",
        "token_type": "Bearer",
        "expires_in": 86400,
    })
```

#### MCP Request Handling

All MCP protocol requests go through the `handle_mcp` function (Lines 57-60):
```python
async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
    """Handle MCP requests."""
    logger.info(f"MCP Request: {scope.get('method')} {scope.get('path')}")
    await session_manager.handle_request(scope, receive, send)
```

**No authentication check** - requests go directly to the StreamableHTTPSessionManager.

### 2. Repository Management API (Port 3000) - Password Authentication

**Location**: `/Users/luisnovo/dev/projetos/code-expert-mcp/src/code_expert/api/auth.py`

The Web UI API uses `REPO_API_PASSWORD` environment variable for authentication.

#### Password Verification

```python
def get_api_password() -> str | None:
    """Get the API password from environment variable."""
    return os.getenv("REPO_API_PASSWORD")

def verify_password(provided_password: str) -> bool:
    """
    Verify the provided password against REPO_API_PASSWORD using constant-time comparison.
    """
    expected_password = get_api_password()
    if not expected_password:
        return False

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(provided_password, expected_password)
```

#### Authentication Decorator

```python
def require_api_password(handler):
    """
    Decorator to require API password authentication for a handler.
    Validates Authorization: Bearer <password> header format.
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
                {"status": "error", "error": "Invalid Authorization header format. Expected: Bearer <password>"},
                status_code=401,
            )

        provided_password = parts[1]

        # Verify password
        if not verify_password(provided_password):
            return JSONResponse(
                {"status": "error", "error": "Invalid API password"},
                status_code=401
            )

        # Authentication successful, call the handler
        return await handler(request)

    return wrapper
```

## Current Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Nginx (Port 80/443)                       │
│                  code-expert-v2.supernovalabs.com            │
└────────────────────┬───────────────────────────────────────┘
                     │
                     │ Proxies to Port 3000
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Web UI Server (Port 3000)                       │
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │ Frontend (React)                                   │     │
│  │  - Login page (localStorage session)               │     │
│  │  - Repository management UI                        │     │
│  └───────────────────────────────────────────────────┘     │
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │ API Endpoints (/api/*)                            │     │
│  │  - Decorated with @require_api_password           │     │
│  │  - Requires: Authorization: Bearer <password>     │     │
│  │  - Validates against REPO_API_PASSWORD env var    │     │
│  └───────────────────────────────────────────────────┘     │
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │ Webhook Endpoint (/webhook)                       │     │
│  │  - NO authentication (relies on WEBHOOK_SECRET)   │     │
│  └───────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              MCP Server (Port 3001)                          │
│              Direct access for Claude clients                │
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │ OAuth Discovery Endpoints                         │     │
│  │  - /.well-known/oauth-authorization-server        │     │
│  │  - /.well-known/oauth-protected-resource          │     │
│  │  - /authorize (fake - immediate approval)         │     │
│  │  - /token (fake - returns dummy token)            │     │
│  └───────────────────────────────────────────────────┘     │
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │ MCP Protocol Handler (/)                          │     │
│  │  - NO authentication required                      │     │
│  │  - StreamableHTTPSessionManager                    │     │
│  │  - Direct access to all MCP tools                  │     │
│  └───────────────────────────────────────────────────┘     │
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │ Webhook Endpoint (/webhook)                       │     │
│  │  - NO authentication (relies on WEBHOOK_SECRET)   │     │
│  └───────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Key Findings

### Why MCP Authentication "Doesn't Work"

1. **MCP server (3001) has NO real authentication** - it's designed to work with fake OAuth that immediately approves everything
2. **The fake OAuth system is for Claude client compatibility only** - to satisfy OAuth discovery requirements
3. **Claude clients connect directly to port 3001** - bypassing nginx proxy
4. **The REPO_API_PASSWORD is ONLY for the Web UI API (port 3000)** - not for MCP protocol

### Current State

- **Port 3001 (MCP)**: Accessible without any authentication - anyone can connect
- **Port 3000 (Web UI API)**: Protected by REPO_API_PASSWORD
- **Nginx**: Currently only proxies port 3000, not configured for MCP

## Security Implications

1. **MCP Server is Wide Open**: Anyone who can reach port 3001 can access all repository tools
2. **No Token Validation**: The fake OAuth tokens are never validated
3. **Public Exposure**: Port 3001 is exposed to 0.0.0.0/0 in security groups
4. **Webhook Protection**: Webhooks rely on WEBHOOK_SECRET for signature validation (separate mechanism)

## Recommendations

If authentication is needed for MCP access:

1. **Option A**: Implement real OAuth with token validation in StreamableHTTPSessionManager
2. **Option B**: Add nginx authentication proxy in front of port 3001
3. **Option C**: Use firewall rules to restrict access to port 3001 by IP
4. **Option D**: Keep current design if MCP access should be public within network

## Environment Variables

- `REPO_API_PASSWORD`: Password for Web UI API endpoints (port 3000)
- `WEBHOOK_SECRET`: HMAC secret for webhook signature validation
- `GITHUB_PERSONAL_ACCESS_TOKEN`: For accessing private GitHub repos
- `AZURE_DEVOPS_PAT`: For accessing private Azure DevOps repos

Note: There is NO environment variable for MCP authentication because it doesn't exist.
