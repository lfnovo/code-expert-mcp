FROM python:3.12

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install git, ca-certificates, and openssl
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        openssl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . .

# Create cache and certs directories
RUN mkdir -p /cache /app/certs

# Generate self-signed certificate for HTTPS
RUN openssl req -x509 -newkey rsa:4096 -nodes \
    -keyout /app/certs/server.key \
    -out /app/certs/server.crt \
    -days 365 \
    -subj "/C=US/ST=State/L=City/O=MCP/CN=localhost" \
    -addext "subjectAltName = DNS:localhost,DNS:*.localhost,IP:127.0.0.1,IP:0.0.0.0"

# Install dependencies
RUN uv sync --locked

# Set default max cached repos (can be overridden at runtime)
ENV MAX_CACHED_REPOS=50

# Set container environment variable for detection
ENV CONTAINER=docker

# Enable HTTPS by default for Claude compatibility
ENV MCP_USE_HTTPS=true
ENV MCP_CERT_PATH=/app/certs/server.crt
ENV MCP_KEY_PATH=/app/certs/server.key

EXPOSE 3001

# Use the simple HTTP entrypoint (no OAuth) for Claude compatibility
CMD ["sh", "-c", "uv run code-understanding-mcp-server-simple --host 0.0.0.0 --port 3001 --cache-dir /cache --max-cached-repos ${MAX_CACHED_REPOS}"]