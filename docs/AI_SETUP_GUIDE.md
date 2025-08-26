# AI Assistant Setup Prompt for MCP Code Expert Server

Copy and paste this entire prompt to your AI coding assistant to help you install and configure the MCP Code Expert Server.

---

## Instructions for AI Assistant

You are helping me set up the MCP Code Expert Server. Please follow these steps:

### Step 1: Verify Prerequisites

First, check if the user has `uv` installed:

```bash
which uv
```

If not installed, guide them to install it:

```bash
# macOS/Linux
curl -sSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
ipow https://astral.sh/uv/install.ps1 | iex
```

### Step 2: Install the MCP Server

Use the isolated tool installation method:

```bash
uv tool install code-expert-mcp
```

### Step 3: Verify Installation

Find the installed binary location:

```bash
which code-expert-mcp
```

Expected output example: `/Users/username/.local/bin/code-expert-mcp`

### Step 4: Configure MCP Client

Help the user configure their MCP client with the verified binary path:

```json
{
  "mcpServers": {
    "code-understanding": {
      "command": "/path/to/code-expert-mcp",
      "args": [],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token-here"
      }
    }
  }
}
```

### Important Notes

1. **Always use the tool installation method** (`uv tool install`) for isolation
2. **Avoid uvx for production use** - it may have dependency conflicts
3. **Use absolute paths** in the MCP configuration
4. **Windows is not supported** - inform Windows users that support is planned

### Troubleshooting Common Issues

If the user encounters issues:

1. **Binary not found**: Check `~/.local/bin` is in PATH
2. **Dependency conflicts**: Ensure they used `uv tool install`, not `uvx`
3. **Permission errors**: Verify write access to cache directories

## Example User Interaction

**User**: "Help me set up the MCP Code Expert Server"

**AI Assistant**: "I'll help you set up the MCP Code Expert Server. Let me guide you through the installation process.

First, let's check if you have `uv` installed:

```bash
which uv
```

[Continue with the steps above based on the user's responses]"

## Available MCP Tools

Once configured, the following tools will be available:

- `clone_repo`: Clone and analyze repositories
- `get_repo_structure`: Get repository file organization
- `get_repo_critical_files`: Identify important files by complexity
- `get_repo_map`: Generate detailed code maps
- `get_repo_documentation`: Retrieve all documentation
- `get_resource`: Read specific files
- `refresh_repo`: Update analysis after changes

## Configuration Options

The server supports these command-line options:

- `--cache-dir`: Custom cache directory (default: `~/.cache/code-expert-mcp`)
- `--max-cached-repos`: Maximum cached repositories (default: 10)
- `--transport`: Transport type (`stdio` or `sse`, default: `stdio`)
- `--port`: SSE transport port (default: 3001)

## Environment Variables

- `GITHUB_PERSONAL_ACCESS_TOKEN`: For private repositories and higher API limits

Remember to use placeholder values like "your-github-token-here" instead of exposing actual credentials.