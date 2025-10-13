#!/bin/sh
# Start both the MCP server and Web UI server

# Start Web UI server in the background
echo "Starting Web UI server on port 3000..."
uv run code-expert-web --host 0.0.0.0 --port 3000 --cache-dir /cache --max-cached-repos ${MAX_CACHED_REPOS} &
WEB_PID=$!

# Start MCP server in the foreground
echo "Starting MCP server on port 3001..."
uv run code-expert-mcp-simple --host 0.0.0.0 --port 3001 --cache-dir /cache --max-cached-repos ${MAX_CACHED_REPOS} &
MCP_PID=$!

# Wait for both processes
wait $WEB_PID $MCP_PID
