# Deployment Checklist

## DNS Configuration Required

Before deploying, you need to create the MCP subdomain in Route53:

1. Go to Route53 console
2. Select the hosted zone for `supernovalabs.com`
3. Create a new A record:
   - **Name:** `mcp.code-expert-v2.supernovalabs.com`
   - **Type:** A
   - **Value:** (Will be set by Terraform)
   - **TTL:** 60

OR just let Terraform create it during deployment (it's configured to do this automatically).

## Deployment Steps

1. **Build and push Docker image:**
   ```bash
   docker build -t docker.io/lfnovo/code-expert-mcp:latest .
   docker push docker.io/lfnovo/code-expert-mcp:latest
   ```

2. **Deploy with Terraform:**
   ```bash
   cd deploy/terraform/aws-ec2
   terraform init
   terraform taint aws_instance.mcp_server
   terraform apply
   ```

3. **Wait for Let's Encrypt:**
   - The instance will start, install nginx, and request certificates
   - This takes about 2-3 minutes
   - Check logs: `AWS_PROFILE=supernova aws ssm send-command --instance-ids <instance-id> --document-name "AWS-RunShellScript" --parameters 'commands=["tail -100 /var/log/cloud-init-output.log"]' --region us-east-1`

4. **Verify deployment:**
   - Web UI: https://code-expert-v2.supernovalabs.com
   - MCP Server: https://mcp.code-expert-v2.supernovalabs.com
   - Test OAuth discovery: `curl https://mcp.code-expert-v2.supernovalabs.com/.well-known/oauth-authorization-server`

## What Changed

### Architecture
**Before (Main Branch):**
- nginx → port 3001 (MCP only)
- No Web UI

**Now (Current Branch):**
- nginx → port 3000 (Web UI) via `code-expert-v2.supernovalabs.com`
- nginx → port 3001 (MCP) via `mcp.code-expert-v2.supernovalabs.com`
- Both use Let's Encrypt SSL certificates

### Why This Fixes MCP Authentication

The MCP server's OAuth endpoints were unreachable because:
1. Nginx was proxying all traffic to the Web UI (port 3000)
2. Claude clients trying to connect to the MCP server hit the Web UI instead
3. OAuth discovery failed because it returned Web UI responses

Now:
1. MCP server has its own subdomain with nginx SSL termination
2. Claude clients connect to `mcp.code-expert-v2.supernovalabs.com`
3. OAuth discovery works correctly through nginx proxy
4. SSL is handled by nginx (same as main branch)

## Files Modified

- `deploy/terraform/aws-ec2/variables.tf` - Added mcp_domain_name variable
- `deploy/terraform/aws-ec2/terraform.tfvars` - Set mcp.code-expert-v2.supernovalabs.com
- `deploy/terraform/aws-ec2/main.tf` - Added MCP DNS record, passed mcp_domain_name to user_data
- `deploy/terraform/aws-ec2/user_data.sh` - Two nginx server blocks, both domains in certbot
- `deploy/terraform/aws-ec2/outputs.tf` - Show both URLs in outputs
- `src/code_expert/mcp/server/simple_http_app.py` - Reverted to main branch (hardcoded https)
