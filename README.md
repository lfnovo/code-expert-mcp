
# Code Expert MCP Server

An MCP (Model Context Protocol) server designed to understand codebases and provide intelligent context to AI coding assistants. This server handles local directories, GitHub repositories, and Azure DevOps repositories, supporting standard MCP-compliant operations.

## Features

- Clone and analyze GitHub repositories, Azure DevOps repositories, or local codebases
- Get repository structure and file organization
- Identify critical files based on complexity metrics and code structure
- Generate detailed repository maps showing:
  - Function signatures and relationships
  - Class definitions and hierarchies
  - Code structure and dependencies
- Retrieve and analyze repository documentation
- Target analysis to specific files or directories
- Keep analysis up-to-date with repository changes via refresh
- **Auto-refresh system**: Intelligent repository synchronization that:
  - Automatically refreshes active repositories every 24 hours
  - Refreshes inactive repositories every 7 days
  - Adapts to repository activity patterns
  - Provides error handling and recovery mechanisms
  - Offers configurable scheduling and resource management

## Quick Start: MCP Client Configuration

### Prerequisites

**Required: `uv` Installation**

This server requires `uv`, a modern Python package manager. If you don't already have `uv` installed:

```bash
# Install UV (macOS/Linux)
curl -sSf https://astral.sh/uv/install.sh | sh

# Install UV (Windows PowerShell)
ipow https://astral.sh/uv/install.ps1 | iex
```

For more installation options, visit the official `uv` installation guide at [astral.sh/uv](https://astral.sh/uv).

### Installation Methods

#### Method 1: Tool Installation (Recommended)

For the most reliable isolated installation:

```bash
# Install the MCP server as a tool
uv tool install code-expert-mcp
```

#### Method 2: Direct Execution with uvx (Fallback)

⚠️ **Warning**: This method may encounter dependency conflicts with other Python packages on your system. Use Method 1 if you experience any issues.

```bash
# Run directly without installation
uvx code-expert-mcp
```

### Verify Installation

After installation, verify the binary location:

```bash
# For Method 1 (tool installation)
which code-expert-mcp
# Expected output example: /Users/username/.local/bin/code-expert-mcp

# For Method 2 (uvx) - no persistent binary
# The tool runs directly through uvx
```

### Configure Your MCP Client

Use the verified binary path in your MCP client configuration:

```json
{
  "mcpServers": {
    "code-expert": {
      "command": "/path/to/code-expert-mcp",
      "args": []
    }
  }
}
```

Replace `/path/to/code-expert-mcp` with the actual path from the verification step above.

For uvx method (less reliable):

```json
{
  "mcpServers": {
    "code-expert": {
      "command": "uvx",
      "args": [
        "code-expert-mcp-server"
      ]
    }
  }
}
```

## Common Use Cases

### Reference Repository Analysis
- Examine external repositories (libraries, dependencies, etc.) to inform current development
- Find implementation patterns and examples in open-source projects
- Understand how specific libraries work internally when documentation is insufficient
- Compare implementation approaches across similar projects
- Identify best practices from high-quality codebases

### Knowledge Extraction and Documentation
- Generate comprehensive documentation for poorly documented codebases
- Create architectural overviews and component relationship diagrams
- Develop progressive learning paths for developer onboarding
- Extract business logic and domain knowledge embedded in code
- Identify and document system integration points and dependencies

### Legacy System Understanding
- Recover knowledge from systems with minimal documentation
- Support migration planning by understanding system boundaries
- Analyze complex dependencies before making changes
- Trace feature implementations across multiple components
- Understand historical design decisions and their rationales

### Cross-Project Knowledge Transfer
- Apply patterns from one project to another
- Bridge knowledge gaps between teams working on related systems
- Identify reusable components across multiple projects
- Understand differences in implementation approaches between teams
- Facilitate knowledge sharing in distributed development environments

## How It Works

The MCP Code Expert Server processes repositories through a series of analysis steps:

1. **Repository Cloning**: The server clones the target repository into its cache
2. **Structure Analysis**: Analysis of directories, files, and their organization
3. **Critical File Identification**: Determination of structurally significant components
4. **Documentation Retrieval**: Collection of all documentation files
5. **Semantic Mapping**: Creation of a detailed map showing relationships between components
6. **Content Analysis**: Examination of specific files as needed for deeper understanding

AI assistants integrate with the server by making targeted requests for each analytical stage, building a comprehensive understanding of the codebase that can be used to address specific user questions and needs.

## MCP Tools Available

The server provides the following MCP tools for AI assistants to interact with repositories:

### Repository Management
- **`clone_repo`** - Initialize a repository for analysis by copying it to MCP's cache
- **`list_repos`** - List all repositories currently in the MCP server's cache with metadata
- **`list_repository_branches`** - List all cached versions of a repository across different branches
- **`delete_repo`** - ⚠️ Remove cached repositories from the MCP server to free disk space
- **`refresh_repo`** - Update a repository with latest changes (manual sync only)
- **`get_repo_status`** - Check if a repository is cloned and ready for analysis

### Repository Analysis
- **`get_repo_structure`** - Retrieve directory structure and analyzable file counts
- **`get_repo_critical_files`** - Identify and analyze the most structurally significant files
- **`get_source_repo_map`** - Retrieve a semantic analysis map of the repository's source code structure
- **`get_repo_documentation`** - Retrieve and analyze documentation files from a repository

### File Operations
- **`get_repo_file_content`** - Retrieve file contents or directory listings from a repository

> **Note**: The `delete_repo` tool is destructive and permanently removes cached repositories. Use with caution as deleted repositories will need to be re-cloned for further analysis.

## Design Considerations for Large Codebases

The server employs several strategies to maintain performance and usability even with enterprise-scale repositories:

- **Asynchronous Processing**: Repository cloning and analysis occur in background threads, providing immediate feedback while deeper analysis continues
- **Progressive Analysis**: Initial quick analysis enables immediate interaction, with more detailed understanding building over time
- **Scope Control**: Parameters for `max_tokens`, `files`, and `directories` enable targeted analysis of specific areas of interest
- **Threshold Management**: Automatic detection of repository size with appropriate guidance for analysis strategies
- **Hierarchical Understanding**: Repository structure is analyzed first, enabling intelligent prioritization of critical components for deeper semantic analysis

These design choices ensure that developers can start working immediately with large codebases while the system builds a progressively deeper understanding in the background, striking an optimal balance between analysis depth and responsiveness.

### Git Repository Authentication (Optional)

#### GitHub
If you need to access private GitHub repositories or want to avoid API rate limits, add your GitHub token to the configuration:

```json
{
  "mcpServers": {
    "code-expert": {
      "command": "/path/to/code-expert-mcp",
      "args": [],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token-here"
      }
    }
  }
}
```

#### Azure DevOps
For private Azure DevOps repositories, add your Personal Access Token (PAT) to the configuration:

```json
{
  "mcpServers": {
    "code-expert": {
      "command": "/path/to/code-expert-mcp",
      "args": [],
      "env": {
        "AZURE_DEVOPS_PAT": "your-azure-devops-pat-here"
      }
    }
  }
}
```

#### Using Both GitHub and Azure DevOps
You can configure both tokens if you work with repositories from both platforms:

```json
{
  "mcpServers": {
    "code-expert": {
      "command": "/path/to/code-expert-mcp",
      "args": [],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token-here",
        "AZURE_DEVOPS_PAT": "your-azure-devops-pat-here"
      }
    }
  }
}
```

### Advanced Configuration Options

For advanced users, the server supports several configuration options:

```json
{
  "mcpServers": {
    "code-expert": {
      "command": "/path/to/code-expert-mcp",
      "args": [
        "--cache-dir", "~/custom-cache-dir",     // Override repository cache location
        "--max-cached-repos", "20",              // Override maximum number of cached repos
        "--transport", "stdio",                  // Transport type (stdio or sse)
        "--port", "3001"                         // Port for SSE transport (only used with sse)
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token-here",
        "AZURE_DEVOPS_PAT": "your-azure-devops-pat-here"
      }
    }
  }
}
```

Available options:
- `--cache-dir`: Override the repository cache directory location (default: ~/.cache/code-expert-mcp)
- `--max-cached-repos`: Set maximum number of cached repositories (default: 10)
- `--transport`: Choose transport type (stdio or sse, default: stdio)
- `--port`: Set port for SSE transport (default: 3001, only used with sse transport)

## Docker Support with Streamable HTTP

The MCP server can be run in a Docker container with Streamable HTTP transport, enabling integration with Claude and other MCP clients that require HTTP-based communication.

### Building the Docker Image

```bash
# Clone the repository
git clone https://github.com/yourusername/code-expert-mcp.git
cd code-expert-mcp

# Build the Docker image
docker build -t mcp-server .
```

### Running the Docker Container

```bash
# Run with default settings (HTTPS on port 3001)
docker run -p 3001:3001 mcp-server

# Run with custom cache directory and max repos
docker run -p 3001:3001 \
  -e MAX_CACHED_REPOS=50 \
  -v /path/to/cache:/cache \
  mcp-server

# Run with authentication tokens for private repos
docker run -p 3001:3001 \
  -e GITHUB_PERSONAL_ACCESS_TOKEN="your-github-token" \
  -e AZURE_DEVOPS_PAT="your-azure-pat" \
  mcp-server
```

### HTTPS and SSL Certificates

The Docker container automatically generates self-signed SSL certificates for HTTPS support, which is required by Claude. The certificates are created at container startup and stored in `/app/certs/`.

**Note**: Self-signed certificates will trigger browser security warnings. This is normal for development use.

### Connecting Claude to Docker Container

Since Claude's backend servers cannot directly access `localhost`, you'll need to expose your Docker container through a tunnel service:

#### Using Cloudflare Tunnel (Recommended)

1. Install cloudflared:
```bash
# macOS
brew install cloudflared

# Linux
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb
```

2. Start the tunnel:
```bash
cloudflared tunnel --url https://localhost:3001
```

3. You'll receive a public URL like `https://example.trycloudflare.com`. Use this URL when adding the MCP server to Claude.

#### Using ngrok (Alternative)

1. Install ngrok and authenticate:
```bash
# Install ngrok (see ngrok.com for instructions)
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

2. Start the tunnel:
```bash
ngrok http https://localhost:3001
```

3. Use the provided HTTPS URL when configuring Claude.

### Docker Environment Variables

The Docker container supports the following environment variables:

- `MAX_CACHED_REPOS`: Maximum number of repositories to cache (default: 50)
- `GITHUB_PERSONAL_ACCESS_TOKEN`: GitHub PAT for private repositories
- `AZURE_DEVOPS_PAT`: Azure DevOps PAT for private repositories
- `MCP_USE_HTTPS`: Enable HTTPS (default: true, required for Claude)

### Docker Compose Example

For production deployments, you can use Docker Compose:

```yaml
version: '3.8'
services:
  mcp-server:
    build: .
    ports:
      - "3001:3001"
    environment:
      - MAX_CACHED_REPOS=100
      - GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_TOKEN}
      - AZURE_DEVOPS_PAT=${AZURE_PAT}
    volumes:
      - ./cache:/cache
    restart: unless-stopped
```

## Supported Repository Formats

The server supports the following repository URL formats:

### GitHub
- HTTPS: `https://github.com/owner/repo`
- SSH: `git@github.com:owner/repo.git`

### Azure DevOps
- HTTPS: `https://dev.azure.com/organization/project/_git/repository`
- HTTPS with org: `https://organization@dev.azure.com/organization/project/_git/repository`
- SSH: `git@ssh.dev.azure.com:v3/organization/project/repository`

### Local Directories
- Absolute paths: `/home/user/projects/my-repo`
- Relative paths: `./my-repo` or `../other-repo`

### Platform-Specific Notes

#### macOS
- Binary typically installs to: `~/.local/bin/code-expert-mcp`
- Ensure `~/.local/bin` is in your PATH

#### Linux
- Binary typically installs to: `~/.local/bin/code-expert-mcp`
- May require: `export PATH="$HOME/.local/bin:$PATH"` in your shell profile

#### Windows
- **Not currently supported** - Windows support is planned for a future release
- Development work is ongoing to enable Windows compatibility

### Troubleshooting

#### Dependency Conflicts

If you encounter dependency conflicts when using `uvx`:

1. Switch to the tool installation method:
   ```bash
   uv tool install code-expert-mcp
   ```

2. If conflicts persist, create an isolated environment:
   ```bash
   # Create a dedicated virtual environment
   uv venv ~/.venvs/code-expert-mcp
   # Activate it (macOS/Linux)
   source ~/.venvs/code-expert-mcp/bin/activate
   # Install the package
   uv pip install code-expert-mcp
   ```

#### Binary Not Found

If the installed binary is not found:

1. Check installation location:
   ```bash
   # macOS/Linux
   find ~/.local -name "code-expert-mcp" 2>/dev/null
   ```

2. Add to PATH if needed:
   ```bash
   # Add to ~/.bashrc, ~/.zshrc, or appropriate shell config
   export PATH="$HOME/.local/bin:$PATH"
   ```

3. Use absolute path in MCP configuration

## Server Configuration

The server uses a `config.yaml` file for base configuration. This file is automatically created in the standard configuration directory (`~/.config/code-expert-mcp/config.yaml`) when the server first runs. You can also place a `config.yaml` file in your current directory to override the default configuration.

Here's the default configuration structure:

```yaml
name: "Code Expert Server"
log_level: "debug"

repository:
  cache_dir: "~/.cache/code-expert-mcp"
  max_cached_repos: 10

# Auto-refresh system configuration
auto_refresh:
  enabled: true                       # Enable/disable auto-refresh
  active_repo_interval_hours: 24      # Refresh interval for active repos (hours)
  inactive_repo_interval_hours: 168   # Refresh interval for inactive repos (hours, 7 days)
  startup_delay_seconds: 30           # Delay before first refresh on startup
  max_concurrent_refreshes: 2         # Maximum concurrent refresh operations
  activity_threshold_days: 7          # Days to consider repo active (based on commits)

documentation:
  include_tags:
    - markdown
    - rst
    - adoc
  include_extensions:
    - .md
    - .markdown
    - .rst
    - .txt
    - .adoc
    - .ipynb
  format_mapping:
    tag:markdown: markdown
    tag:rst: restructuredtext
    tag:adoc: asciidoc
    ext:.md: markdown
    ext:.markdown: markdown
    ext:.rst: restructuredtext
    ext:.txt: plaintext
    ext:.adoc: asciidoc
    ext:.ipynb: jupyter
  category_patterns:
    readme: 
      - readme
    api: 
      - api
    documentation:
      - docs
      - documentation
    examples:
      - examples
      - sample
```

### Auto-Refresh System

The auto-refresh system keeps your repository caches current by automatically refreshing them based on activity patterns:

- **Active repositories** (with commits in the last 7 days): Refreshed every 24 hours by default
- **Inactive repositories**: Refreshed every 7 days by default
- **Smart scheduling**: Repositories are scheduled based on their last commit activity
- **Error handling**: Failed refreshes use exponential backoff and temporary disabling
- **Resource management**: Configurable concurrent refresh limits prevent system overload

#### Configuration Options

- `enabled`: Enable or disable the auto-refresh system (default: true)
- `active_repo_interval_hours`: How often to refresh active repositories in hours (default: 24)
- `inactive_repo_interval_hours`: How often to refresh inactive repositories in hours (default: 168)
- `startup_delay_seconds`: Delay before starting refreshes on server startup (default: 30)
- `max_concurrent_refreshes`: Maximum number of concurrent refresh operations (default: 2)
- `activity_threshold_days`: Days to consider a repository active based on commit history (default: 7)

#### Auto-Refresh Management Tools

The server provides MCP tools to monitor and manage the auto-refresh system:

- `get_auto_refresh_status`: Get detailed status including scheduled repositories, error statistics, and performance metrics
- `start_auto_refresh`: Manually start the auto-refresh system (typically automatic)
- `stop_auto_refresh`: Manually stop the auto-refresh system

## For Developers

### Prerequisites

- **Python 3.11 or 3.12**: Required for both development and usage
  ```bash
  # Verify your Python version
  python --version
  # or
  python3 --version
  ```
- **UV Package Manager**: The modern Python package installer
  ```bash
  # Install UV
  curl -sSf https://astral.sh/uv/install.sh | sh
  ```

### Development Setup

To contribute or run this project locally:

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/code-expert-mcp.git
cd code-expert-mcp

# 2. Create virtual environment
uv venv

# 3. Activate the virtual environment
#    Choose the command appropriate for your operating system and shell:

#    Linux/macOS (bash/zsh):
source .venv/bin/activate

#    Windows (Command Prompt - cmd.exe):
.venv\\Scripts\\activate.bat

#    Windows (PowerShell):
#    Note: You might need to adjust your execution policy first.
#    Run: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.venv\\Scripts\\Activate.ps1

# 4. Install dependencies (editable mode with dev extras)
#    (Ensure your virtual environment is activated first!)
uv pip install -e ".[dev]"

# 5. Set up pre-commit hooks
pre-commit install

# 6. Run tests
uv run pytest

# 7. Test the server using MCP inspector
# Without authentication:
uv run mcp dev src/code_understanding/mcp/server/app.py

# With GitHub authentication (for testing private repos):
GITHUB_PERSONAL_ACCESS_TOKEN=your_token_here uv run mcp dev src/code_understanding/mcp/server/app.py

# With Azure DevOps authentication:
AZURE_DEVOPS_PAT=your_token_here uv run mcp dev src/code_understanding/mcp/server/app.py

# With both GitHub and Azure DevOps authentication:
GITHUB_PERSONAL_ACCESS_TOKEN=github_token AZURE_DEVOPS_PAT=azure_token uv run mcp dev src/code_understanding/mcp/server/app.py
```

This will launch an interactive console where you can test all MCP server endpoints directly.

### Development Tools

The following development tools are available after installing with dev extras (`.[dev]`):

Run tests with coverage:
```bash
uv run pytest
```

Format code (using black and isort):
```bash
# Format with black
uv run black .

# Sort imports
uv run isort .
```

Type checking with mypy:
```bash
uv run mypy .
```

All tools are configured via pyproject.toml with settings optimized for this project.

### Publishing to PyPI

When you're ready to publish a new version to PyPI, follow these steps:

1. Update the version number in `pyproject.toml`:
   ```bash
   # Edit pyproject.toml and change the version field
   # For example: version = "0.1.1"
   ```

2. Clean previous build artifacts:
   ```bash
   # Remove previous distribution packages and build directories
   rm -rf dist/ 2>/dev/null || true
   rm -rf build/ 2>/dev/null || true
   rm -rf src/*.egg-info/ 2>/dev/null || true
   ```

3. Build the distribution packages:
   ```bash
   uv run python -m build
   ```

4. Verify the built packages:
   ```bash
   ls dist/
   ```

5. Upload to PyPI (use TestPyPI first if unsure):
   ```bash
   # Install twine if you haven't already
   uv pip install twine
   
   # For PyPI release:
   uv run python -m twine upload dist/*
   ```

You'll need PyPI credentials configured or you'll be prompted to enter them during upload.

## Version History

### v0.1.6 (Latest)
- **Dependency Fix**: Explicitly pinned `configargparse==1.7` to resolve installation issues caused by the yanked version in PyPI
- This ensures clean installation with `uvx` and other package managers by preventing dependency resolution failures
- No functional changes to the server capabilities

## License

MIT

## Acknowledgments

This project was originally inspired by [mcp-code-understanding](https://github.com/codingthefuturewithai/mcp-code-understanding).

<!-- Trigger GitHub metadata refresh -->

## Webhook Integration

The MCP server supports webhook-triggered repository refreshes via a secure HTTP endpoint. This allows external systems (e.g., GitHub) to notify the server of repository changes and trigger an immediate refresh.


### Webhook Endpoint

- **URL:** `/webhook` (POST)
- **Purpose:** Trigger a refresh of the repository specified in the webhook payload.
- **Supported Providers:** GitHub (push events)

> **Common issues? Check the [Troubleshooting](#troubleshooting) section below for quick tips.**

#### Example: GitHub Webhook Setup

1. Go to your repository's **Settings > Webhooks** in GitHub.
2. Add a new webhook with the following settings:
  - **Payload URL:** `https://your-server-domain/webhook`
  - **Content type:** `application/json`
  - **Secret:** Set to a strong random value (see below)
  - **Events:** Choose "Just the push event" or as needed

### Security: HMAC Signature Validation

The server validates incoming webhook requests using HMAC-SHA256 signatures. You must set the `WEBHOOK_SECRET` environment variable to match the secret configured in your webhook provider (e.g., GitHub).

**Environment Variable:**

```bash
export WEBHOOK_SECRET="your-strong-secret"
```

**Validation:**
- The server checks the `X-Hub-Signature-256` header against the request body using the shared secret.
- Requests with missing or invalid signatures are rejected with HTTP 401 Unauthorized.

### Payload Parsing

- The server extracts the repository clone URL from the webhook payload (currently supports GitHub push events).
- If the repository cannot be parsed, the server returns HTTP 400 Bad Request.

### Refresh Logic

- If the repository is found in the cache, the server triggers a refresh (git pull).
- If not found, the server attempts to clone it.
- Success returns HTTP 200 with commit info; errors return appropriate status codes.

### Example Request

```bash
curl -X POST https://your-server-domain/webhook \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=..." \
  -d '{ "repository": { "clone_url": "https://github.com/user/repo.git" }, ... }'
```

### Configuration Reference

- Set `WEBHOOK_SECRET` in your environment for production use.
- The endpoint is enabled by default when running the server.

### Troubleshooting

- **401 Unauthorized:** Check that your webhook secret matches `WEBHOOK_SECRET` and the signature is correct.
- **400 Bad Request:** Ensure the payload includes a valid `repository.clone_url` field.
- **500 Internal Server Error:** Indicates a problem with repository access or refresh logic.

---# Testing webhook
