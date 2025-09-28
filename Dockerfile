FROM python:3.12

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install git and ca-certificates
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . .

# Create cache directory
RUN mkdir -p /cache

# Install dependencies
RUN uv sync --locked

# Set default max cached repos (can be overridden at runtime)
ENV MAX_CACHED_REPOS=50

# Set container environment variable for detection
ENV CONTAINER=docker

# HTTP only - HTTPS handled by load balancers/proxies
ENV MCP_USE_HTTPS=false

EXPOSE 3001

# Use the simple HTTP entrypoint
CMD ["sh", "-c", "uv run code-expert-mcp-simple --host 0.0.0.0 --port 3001 --cache-dir /cache --max-cached-repos ${MAX_CACHED_REPOS}"]