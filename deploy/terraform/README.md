# Terraform Deployment for Code Expert MCP

Deploy Code Expert MCP server to cloud providers using Terraform.

## 🚀 AWS EC2 Deployment (Available Now)

Deploy to AWS EC2 with automatic HTTPS using Let's Encrypt.

### Features

- ✅ **Automatic HTTPS** with Let's Encrypt (requires domain)
- ✅ **Docker containerized** deployment
- ✅ **Persistent cache** for git repositories (30GB EBS)
- ✅ **Elastic IP** for consistent addressing
- ✅ **CloudWatch logging**
- ✅ **Route 53 DNS** integration (optional)
- ✅ **Auto-renewing SSL certificates**

### Prerequisites

1. **AWS CLI configured**
   ```bash
   aws configure --profile your-profile
   ```

2. **Terraform installed**
   ```bash
   brew install terraform
   # Or download from https://terraform.io
   ```

3. **(Optional but recommended) Domain in Route 53**
   - For automatic HTTPS with Let's Encrypt
   - Without a domain, uses self-signed certificate (may cause issues with Claude Desktop)

### Quick Start

1. **Navigate to the AWS EC2 deployment directory**
   ```bash
   cd deploy/terraform/aws-ec2
   ```

2. **Copy and configure the variables file**
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```
   
   Edit `terraform.tfvars` with your settings:
   - `aws_profile`: Your AWS CLI profile name
   - `domain_name`: Your domain (e.g., `mcp.yourdomain.com`) - optional but recommended
   - `route53_zone_id`: Your Route 53 hosted zone ID - optional
   - `ssh_allowed_ips`: Your IP for SSH access, or leave empty

3. **Initialize Terraform**
   ```bash
   terraform init
   ```

4. **Review the deployment plan**
   ```bash
   terraform plan
   ```

5. **Deploy the infrastructure**
   ```bash
   terraform apply
   ```
   
   Type `yes` when prompted. Deployment takes about 3-5 minutes.

6. **Get your server URL**
   ```bash
   terraform output domain_url
   # Or if no domain configured:
   terraform output service_url_https
   ```

### Adding to Claude Desktop

Once deployed:

1. Open Claude Desktop
2. Go to **Settings > Connectors > Add custom connector**
3. Enter your server URL:
   - With domain: `https://your-domain.com`
   - Without domain: `https://<elastic-ip>` (will show certificate warning)
4. Complete the OAuth flow (automatically approves)
5. Start using Code Expert MCP!

### Outputs

After deployment, Terraform provides these outputs:

- `domain_url` - Your HTTPS URL with domain (if configured)
- `service_url_https` - HTTPS URL with IP address
- `public_ip` - The Elastic IP address
- `ssh_command` - SSH command to access the instance
- `docker_logs_command` - Command to view Docker logs

### Managing the Deployment

**View current state:**
```bash
terraform show
```

**Update configuration:**
```bash
# Edit terraform.tfvars
terraform apply
```

**View logs:**
```bash
# Get the SSH command
terraform output ssh_command

# SSH and view logs
ssh ec2-user@<ip> 'sudo docker logs code-expert-mcp'
```

**Destroy infrastructure:**
```bash
terraform destroy
```

### Architecture

```
Internet → Route 53 (optional) → EC2 Instance
                                       ↓
                                 nginx (HTTPS)
                                       ↓
                                 Docker Container
                                   Port 3001
                                       ↓
                                 /var/cache (30GB)
```

### Cost Estimation

AWS costs (approximate):
- **EC2 t3.small**: ~$15/month
- **EBS 30GB**: ~$2.40/month
- **Elastic IP**: Free when attached
- **Data transfer**: Variable, typically <$1/month
- **Total**: ~$18-20/month

### Troubleshooting

**Certificate issues with Claude Desktop:**
- Ensure your domain DNS has propagated (can take up to 30 minutes)
- Check nginx logs: `sudo tail -f /var/log/nginx/error.log`
- Verify Let's Encrypt certificate: `sudo certbot certificates`

**Container not starting:**
- Check Docker logs: `sudo docker logs code-expert-mcp`
- Verify Docker is running: `sudo systemctl status docker`
- Check systemd service: `sudo systemctl status code-expert-mcp`

**Can't connect from Claude Desktop:**
- Verify security groups allow ports 80 and 443
- Check nginx is running: `sudo systemctl status nginx`
- Test the endpoint: `curl https://your-domain/`

### Security Considerations

- The server uses OAuth with automatic approval (no authentication required)
- Restrict SSH access using `ssh_allowed_ips` in terraform.tfvars
- Consider using AWS Systems Manager Session Manager instead of SSH
- Regularly update the Docker image for security patches

## 🔜 Coming Soon

### Google Cloud Run
- Serverless container platform
- Automatic HTTPS with Google domains
- Pay-per-request pricing

### Azure Container Instances
- Simple container hosting
- Application Gateway for HTTPS
- Azure Files for persistent storage

## Support

For issues or questions:
- Check the [main README](../../../README.md)
- Open an issue on GitHub
- Review CloudWatch logs in AWS Console