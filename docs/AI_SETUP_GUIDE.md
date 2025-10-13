# MCP Code Expert Server - Complete Setup Guide

This guide covers all deployment options for the MCP Code Expert Server: local Docker development, package installation, and production AWS deployment.

---

## Table of Contents

1. [Local Development (Docker)](#local-development-docker)
2. [Package Installation](#package-installation)
3. [Production Deployment (AWS)](#production-deployment-aws)
4. [Configuration Reference](#configuration-reference)
5. [Troubleshooting](#troubleshooting)

---

## Local Development (Docker)

Perfect for testing and development. Runs both the Web UI (port 3000) and MCP Server (port 3001) in a single container.

### Prerequisites

- Docker and Docker Compose installed
- Git (for cloning the repository)

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-org/code-expert-mcp.git
cd code-expert-mcp
```

### Step 2: Generate Local HTTPS Certificates

Claude Desktop requires HTTPS even for localhost. Use mkcert for trusted certificates:

```bash
# Install mkcert (one-time setup)
brew install mkcert  # macOS
# OR
apt install mkcert   # Linux

# Generate trusted certificates
./generate-local-certs-mkcert.sh

# Install the local CA (you'll be prompted for your password)
mkcert -install
```

**Alternative:** If you don't have mkcert, use the OpenSSL script (creates self-signed certs that need manual trust):

```bash
./generate-local-certs.sh
```

### Step 3: Start the Docker Container

```bash
# Set your API password
export REPO_API_PASSWORD="your-secure-password"

# Start the services
docker compose up -d

# Check logs
docker compose logs -f
```

### Step 4: Configure Claude Desktop

Add to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "code-expert-local": {
      "url": "https://localhost:3001"
    }
  }
}
```

### Access Points

- **MCP Server**: https://localhost:3001
- **Web UI**: http://localhost:3000
- **API**: http://localhost:3000/api/*

### Environment Variables (Optional)

Create a `.env` file in the project root:

```env
# Repository Management API password
REPO_API_PASSWORD=changeme-secure-password

# GitHub token for private repos (optional)
GITHUB_TOKEN=ghp_your_token_here

# Azure DevOps token (optional)
AZURE_DEVOPS_TOKEN=your_token_here

# Webhook secret for GitHub/Azure webhooks (optional)
WEBHOOK_SECRET=your_webhook_secret

# Maximum cached repositories
MAX_CACHED_REPOS=50
```

---

## Package Installation

Install the MCP server as a standalone Python package using `uv` (recommended) or `pip`.

### Prerequisites

- Python 3.11 or 3.12
- `uv` (recommended) or `pip`

### Step 1: Install uv (if not already installed)

```bash
# macOS/Linux
curl -sSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Step 2: Install the MCP Server

**Option A: Using uv (Recommended - Isolated Installation)**

```bash
# Install as an isolated tool
uv tool install code-expert-mcp

# Verify installation
which code-expert-mcp
# Output example: /Users/username/.local/bin/code-expert-mcp
```

**Option B: Using pip**

```bash
pip install code-expert-mcp
```

### Step 3: Run the Server

**STDIO Transport (for Claude Desktop):**

```bash
code-expert-mcp
```

**HTTP Transport (for web clients):**

```bash
code-expert-mcp-simple --host 0.0.0.0 --port 3001
```

### Step 4: Configure Claude Desktop

Add to your MCP configuration file:

**Location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

**Configuration:**

```json
{
  "mcpServers": {
    "code-expert": {
      "command": "/Users/username/.local/bin/code-expert-mcp",
      "args": [
        "--cache-dir", "/path/to/cache",
        "--max-cached-repos", "50"
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

**Important:** Use the absolute path returned by `which code-expert-mcp`.

### Command Line Options

```bash
code-expert-mcp --help

Options:
  --cache-dir TEXT              Cache directory path (default: ~/.cache/code-expert-mcp)
  --max-cached-repos INTEGER    Maximum cached repositories (default: 10)
  --transport [stdio|sse]       Transport type (default: stdio)
  --port INTEGER                SSE transport port (default: 3001)
  --help                        Show this message and exit
```

---

## Production Deployment (AWS)

Deploy to AWS EC2 with Terraform for a production-ready setup with SSL certificates, automatic updates, and monitoring.

### Architecture

The production deployment includes:
- EC2 instance (t3.small) running Docker
- Separate EBS volume for persistent repository cache
- Nginx reverse proxy with Let's Encrypt SSL
- Two domains:
  - Web UI: `code-expert-v2.supernovalabs.com` → port 3000
  - MCP Server: `mcp.code-expert-v2.supernovalabs.com` → port 3001
- Automatic Docker image updates (daily check)
- CloudWatch logging
- SSM for secure remote access

### Prerequisites

1. AWS account with appropriate permissions
2. Terraform installed (v1.0+)
3. AWS CLI configured with credentials
4. Route53 hosted zone for your domain
5. Docker Hub account (for pushing images)

### Step 1: Configure Terraform Variables

Edit `deploy/terraform/aws-ec2/terraform.tfvars`:

```hcl
# AWS Configuration
aws_region  = "us-east-1"
aws_profile = "your-profile"

# Service Configuration
service_name = "code-expert-mcp"
docker_image = "docker.io/your-org/code-expert-mcp:latest"

# Instance Configuration
instance_type = "t3.small"  # 2 vCPU, 2 GB RAM
volume_size   = 30          # Root volume in GB
cache_volume_size = 50      # Persistent cache volume in GB

# Domain Configuration
domain_name     = "code-expert.yourdomain.com"      # Web UI
mcp_domain_name = "mcp.code-expert.yourdomain.com"  # MCP Server
route53_zone_id = "YOUR_ZONE_ID"

# Security
repo_api_password = "your-secure-password"  # Change this!
webhook_secret    = "your-webhook-secret"   # For GitHub/Azure webhooks

# Optional: Tokens for private repos
github_token     = "ghp_your_token"
azure_devops_pat = "your_pat"

# Network
ssh_allowed_ips = []  # Empty for no SSH, or ["1.2.3.4/32"] for specific IP

# Service Settings
max_cached_repos = "100"
use_elastic_ip   = true  # Consistent IP address

# Tags
tags = {
  Project     = "code-expert-mcp"
  Environment = "production"
  ManagedBy   = "terraform"
}
```

### Step 2: Build and Push Docker Image

```bash
# Build the image
docker build -t docker.io/your-org/code-expert-mcp:latest .

# Login to Docker Hub
docker login

# Push the image
docker push docker.io/your-org/code-expert-mcp:latest
```

### Step 3: Create DNS Records (Optional)

If Terraform will create the DNS records automatically, skip this. Otherwise, create A records in Route53:

1. `code-expert.yourdomain.com` → (Terraform will set the IP)
2. `mcp.code-expert.yourdomain.com` → (Terraform will set the IP)

### Step 4: Deploy with Terraform

```bash
cd deploy/terraform/aws-ec2

# Initialize Terraform
terraform init

# Review the deployment plan
terraform plan

# Deploy
terraform apply

# Note the outputs
terraform output
```

### Step 5: Wait for SSL Certificates

The instance will automatically:
1. Install Docker and Nginx
2. Pull your Docker image
3. Request Let's Encrypt SSL certificates (takes 2-3 minutes)
4. Start both services

Monitor the process:

```bash
# Get instance ID from terraform output
INSTANCE_ID=$(terraform output -raw instance_id)

# Check cloud-init logs
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["tail -100 /var/log/cloud-init-output.log"]' \
  --region us-east-1
```

### Step 6: Verify Deployment

```bash
# Test Web UI
curl https://code-expert.yourdomain.com

# Test MCP OAuth discovery
curl https://mcp.code-expert.yourdomain.com/.well-known/oauth-authorization-server
```

Expected response:
```json
{
  "issuer": "https://mcp.code-expert.yourdomain.com",
  "authorization_endpoint": "https://mcp.code-expert.yourdomain.com/authorize",
  "token_endpoint": "https://mcp.code-expert.yourdomain.com/token"
}
```

### Step 7: Configure Claude Desktop for Production

```json
{
  "mcpServers": {
    "code-expert-prod": {
      "url": "https://mcp.code-expert.yourdomain.com"
    }
  }
}
```

### Terraform Resources Created

- **EC2 Instance**: Running Docker with both services
- **EBS Volume**: Persistent 50GB storage for repository cache
- **Elastic IP**: Consistent IP address
- **Security Group**: Ports 22 (SSH), 80 (HTTP), 443 (HTTPS), 3000, 3001
- **IAM Role**: For SSM access (secure remote access without SSH)
- **Route53 Records**: DNS for both domains
- **CloudWatch Log Group**: Centralized logging

### Updating the Deployment

**To update the Docker image:**

```bash
# Build and push new image
docker build -t docker.io/your-org/code-expert-mcp:latest .
docker push docker.io/your-org/code-expert-mcp:latest

# Restart the service (automatically pulls latest)
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["systemctl restart code-expert-mcp"]' \
  --region us-east-1
```

**To update infrastructure:**

```bash
# Make changes to terraform.tfvars
terraform plan
terraform apply
```

### Monitoring and Maintenance

**View Docker logs:**

```bash
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker logs code-expert-mcp --tail 100"]' \
  --region us-east-1
```

**Check service status:**

```bash
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["systemctl status code-expert-mcp nginx"]' \
  --region us-east-1
```

**Auto-update is enabled by default** - the server checks for new Docker images daily at 3 AM.

---

## Configuration Reference

### Available MCP Tools

Once configured, these tools are available:

- `clone_repo`: Clone and analyze repositories
- `get_repo_structure`: Get repository file organization
- `get_repo_critical_files`: Identify important files by complexity metrics
- `get_source_repo_map`: Generate detailed semantic code maps
- `get_repo_documentation`: Retrieve all documentation files
- `get_repo_file_content`: Read specific files or directories
- `refresh_repo`: Update repository analysis after changes
- `list_repos`: List all cached repositories
- `delete_repo`: Remove repository from cache

### Environment Variables

**Repository Access:**
- `GITHUB_PERSONAL_ACCESS_TOKEN`: GitHub token for private repos and higher API limits
- `AZURE_DEVOPS_PAT`: Azure DevOps PAT for private repos

**Service Configuration:**
- `MAX_CACHED_REPOS`: Maximum repositories to cache (default: 50)
- `CACHE_DIR`: Repository cache directory (default: ~/.cache/code-expert-mcp)
- `MCP_USE_HTTPS`: Enable HTTPS for MCP server (default: false, nginx handles SSL in prod)

**Web UI Authentication:**
- `REPO_API_PASSWORD`: Password for Web UI API endpoints (port 3000)

**Webhooks:**
- `WEBHOOK_SECRET`: HMAC secret for validating webhook signatures

### Docker Compose Volumes

- `./.cache:/cache` - Repository cache (persistent across restarts)
- `./certs:/app/certs:ro` - SSL certificates for local HTTPS

### Docker Compose Environment

Configured via environment variables or `.env` file:
- `REPO_API_PASSWORD`: Web UI API password
- `GITHUB_TOKEN`: GitHub access token
- `AZURE_DEVOPS_TOKEN`: Azure DevOps token
- `MAX_CACHED_REPOS`: Cache limit
- `PYTHONPATH=/app`: Python module path (required)

---

## Troubleshooting

### Local Development Issues

**Problem: "Certificate not trusted" error**

Solution:
```bash
# Install mkcert CA
mkcert -install

# Regenerate certificates
./generate-local-certs-mkcert.sh

# Restart Docker
docker compose restart
```

**Problem: Port already in use**

Solution:
```bash
# Check what's using the ports
lsof -i :3000
lsof -i :3001

# Stop conflicting services or change ports in docker-compose.yml
```

**Problem: Container fails to start**

Solution:
```bash
# Check logs
docker compose logs

# Common issues:
# - Missing .env variables
# - Invalid certificate files
# - Insufficient disk space
```

### Package Installation Issues

**Problem: `code-expert-mcp: command not found`**

Solution:
```bash
# Add ~/.local/bin to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Or use full path
~/.local/bin/code-expert-mcp
```

**Problem: Dependency conflicts**

Solution:
```bash
# Use uv tool install (isolated environment)
uv tool uninstall code-expert-mcp
uv tool install code-expert-mcp

# Avoid using uvx for production - it may cause conflicts
```

**Problem: Permission errors with cache**

Solution:
```bash
# Create cache directory with correct permissions
mkdir -p ~/.cache/code-expert-mcp
chmod 755 ~/.cache/code-expert-mcp
```

### Production Deployment Issues

**Problem: Let's Encrypt certificate fails**

Solution:
```bash
# Check DNS propagation
dig code-expert.yourdomain.com
dig mcp.code-expert.yourdomain.com

# Both should point to your EC2 instance IP

# Check certbot logs
aws ssm send-command --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["tail -100 /var/log/letsencrypt/letsencrypt.log"]'
```

**Problem: Can't connect to MCP server**

Solution:
```bash
# Test OAuth discovery endpoint
curl https://mcp.code-expert.yourdomain.com/.well-known/oauth-authorization-server

# Check nginx configuration
aws ssm send-command --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["nginx -t"]'

# Verify both services are running
aws ssm send-command --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker ps"]'
```

**Problem: High memory usage**

Solution:
```bash
# Reduce max cached repos in terraform.tfvars
max_cached_repos = "50"  # Default is 100

# Or upgrade instance type
instance_type = "t3.medium"  # 4GB RAM instead of 2GB

# Apply changes
terraform apply
```

### Claude Desktop Connection Issues

**Problem: Claude Desktop can't connect**

Checklist:
1. ✅ Is the server running? (`docker ps` or check systemd service)
2. ✅ Is HTTPS enabled? (Check logs for "Uvicorn running on https://")
3. ✅ Is certificate trusted? (Run `mkcert -install` for local)
4. ✅ Is the URL correct in Claude config?
5. ✅ Can you access `/.well-known/oauth-authorization-server`?

**Problem: Authentication fails silently**

Solution:
```bash
# Check MCP logs for OAuth requests
docker logs code-expert-mcp | grep -i oauth

# Verify OAuth endpoints respond
curl -k https://localhost:3001/.well-known/oauth-authorization-server
curl -k https://localhost:3001/authorize?redirect_uri=test&state=test
curl -k -X POST https://localhost:3001/token
```

### Getting Help

**Check service health:**

```bash
# Local
docker compose ps
docker compose logs

# Production
terraform output
aws ssm send-command --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["systemctl status code-expert-mcp nginx"]'
```

**Enable debug logging:**

Add to environment variables:
```bash
LOG_LEVEL=debug
```

**Report issues:**

Include:
- Deployment type (local/package/AWS)
- Error messages from logs
- Configuration (redact secrets!)
- Steps to reproduce

---

## Security Best Practices

### Local Development
- Use mkcert for certificates (automatically trusted)
- Set strong `REPO_API_PASSWORD`
- Don't commit `.env` files with secrets
- Use `.gitignore` for `certs/` directory

### Production Deployment
- Change default `REPO_API_PASSWORD` in terraform.tfvars
- Use AWS Secrets Manager for sensitive values (future enhancement)
- Restrict SSH access (`ssh_allowed_ips = []`)
- Enable CloudWatch logging
- Regular security updates (auto-update enabled by default)
- Use strong webhook secrets

### Token Management
- Use fine-grained GitHub tokens with minimal permissions
- Rotate tokens regularly
- Don't commit tokens to version control
- Use environment variables or secure parameter stores

---

## Additional Resources

- **GitHub Repository**: [code-expert-mcp](https://github.com/your-org/code-expert-mcp)
- **MCP Documentation**: [Model Context Protocol](https://modelcontextprotocol.io)
- **Docker Hub**: [code-expert-mcp](https://hub.docker.com/r/your-org/code-expert-mcp)
- **Issues & Support**: GitHub Issues

---

## Quick Reference

### Local Development
```bash
# Start
./generate-local-certs-mkcert.sh && mkcert -install
docker compose up -d

# Connect
https://localhost:3001
```

### Production
```bash
# Deploy
cd deploy/terraform/aws-ec2
terraform apply

# Update
docker push docker.io/your-org/code-expert-mcp:latest
aws ssm send-command --instance-ids $ID --parameters 'commands=["systemctl restart code-expert-mcp"]'
```

### Package
```bash
# Install
uv tool install code-expert-mcp

# Run
code-expert-mcp  # stdio
code-expert-mcp-simple --host 0.0.0.0 --port 3001  # http
```
