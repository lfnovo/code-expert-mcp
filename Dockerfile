# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci

# Copy frontend source
COPY frontend/ ./

# Build argument for API URL (empty for production = same origin)
ARG VITE_API_URL=
ENV VITE_API_URL=${VITE_API_URL}

# Build frontend
RUN npm run build

# Stage 2: Python backend with frontend
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

# Copy frontend build artifacts from stage 1
COPY --from=frontend-builder /frontend/dist ./frontend/dist

# Copy and make entrypoint script executable
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Create cache and certs directories
RUN mkdir -p /cache /app/certs

# Install dependencies
RUN uv sync --locked

# Set default max cached repos (can be overridden at runtime)
ENV MAX_CACHED_REPOS=50

# Set container environment variable for detection
ENV CONTAINER=docker

# HTTP only - HTTPS handled by load balancers/proxies
ENV MCP_USE_HTTPS=false

# Expose both API and frontend ports
EXPOSE 3000 3001

# Use the entrypoint script to start both servers
CMD ["/app/docker-entrypoint.sh"]