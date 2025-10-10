#!/bin/bash
# User data script to set up Code Expert MCP on EC2 with Let's Encrypt

# Update system
dnf update -y

# Install SSM Agent (for AWS Session Manager)
dnf install -y amazon-ssm-agent
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# Install Docker
dnf install -y docker
systemctl start docker
systemctl enable docker

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Wait for the EBS volume to be attached with retry logic
DEVICE="/dev/nvme1n1"  # This is the consistent device name for attached EBS volumes
MAX_RETRIES=30
RETRY_COUNT=0

echo "Waiting for cache volume to be attached..." | logger -t user-data
while [ ! -b $DEVICE ] && [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "Waiting for device $DEVICE (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)..." | logger -t user-data
    sleep 10
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ ! -b $DEVICE ]; then
    echo "ERROR: Cache volume $DEVICE not found after $MAX_RETRIES attempts" | logger -t user-data
    echo "Continuing without cache volume..." | logger -t user-data
else
    echo "Cache volume $DEVICE found, proceeding with mount..." | logger -t user-data
    
    # Check if the volume is already formatted with a filesystem
    if ! blkid $DEVICE > /dev/null 2>&1; then
        echo "Formatting new cache volume..." | logger -t user-data
        mkfs -t ext4 $DEVICE
    else
        echo "Volume already formatted, skipping..." | logger -t user-data
    fi

    # Create mount point
    mkdir -p /var/cache/code-expert-mcp

    # Mount the volume
    if mount $DEVICE /var/cache/code-expert-mcp; then
        echo "Cache volume mounted successfully" | logger -t user-data
        
        # Add to fstab for persistence across reboots (remove any existing entries first)
        sed -i '/\/var\/cache\/code-expert-mcp/d' /etc/fstab
        UUID=$(blkid -s UUID -o value $DEVICE)
        echo "UUID=$UUID /var/cache/code-expert-mcp ext4 defaults,nofail 0 2" >> /etc/fstab
    else
        echo "ERROR: Failed to mount cache volume" | logger -t user-data
    fi
fi

# Set proper permissions
chmod 755 /var/cache/code-expert-mcp

# Create systemd service for MCP
cat > /etc/systemd/system/code-expert-mcp.service <<EOF
[Unit]
Description=Code Expert MCP Server
After=docker.service
Requires=docker.service

[Service]
Type=simple
Restart=always
RestartSec=10
ExecStartPre=-/usr/bin/docker stop ${service_name}
ExecStartPre=-/usr/bin/docker rm ${service_name}
ExecStartPre=/usr/bin/docker pull ${docker_image}
ExecStart=/usr/bin/docker run \
  --name ${service_name} \
  --rm \
  -p 3001:3001 \
  -v /var/cache/code-expert-mcp:/cache \
  -e PYTHONPATH=/app \
  -e MAX_CACHED_REPOS=${max_cached_repos} \
  -e MCP_USE_HTTPS=false \
  -e CONTAINER=docker \
%{ if github_token != "" }  -e GITHUB_PERSONAL_ACCESS_TOKEN="${github_token}" \
%{ endif }%{ if azure_devops_pat != "" }  -e AZURE_DEVOPS_PAT="${azure_devops_pat}" \
%{ endif }%{ if webhook_secret != "" }  -e WEBHOOK_SECRET="${webhook_secret}" \
%{ endif }  ${docker_image}
ExecStop=/usr/bin/docker stop ${service_name}

[Install]
WantedBy=multi-user.target
EOF

# Start the service
systemctl daemon-reload
systemctl enable code-expert-mcp.service
systemctl start code-expert-mcp.service

# Install nginx and certbot
dnf install -y nginx python3 python3-pip
pip3 install certbot certbot-nginx

# Check if domain is provided
if [ -n "${domain_name}" ]; then
    echo "Setting up Let's Encrypt for ${domain_name}" | logger -t user-data
    
    # Configure nginx first with HTTP only for certbot
    cat > /etc/nginx/conf.d/mcp.conf <<'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name ${domain_name};

    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Add CORS headers
        add_header Access-Control-Allow-Origin * always;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Content-Type, Accept, Authorization, X-Session-Id" always;
        add_header Access-Control-Max-Age 86400 always;
        
        # Handle preflight requests
        if ($request_method = OPTIONS) {
            add_header Access-Control-Allow-Origin * always;
            add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
            add_header Access-Control-Allow-Headers "Content-Type, Accept, Authorization, X-Session-Id" always;
            add_header Access-Control-Max-Age 86400 always;
            add_header Content-Length 0;
            add_header Content-Type text/plain;
            return 204;
        }
    }
}
NGINX

    # Start nginx
    systemctl enable nginx
    systemctl start nginx
    
    # Wait for DNS to propagate (give it a moment)
    sleep 30
    
    # Get Let's Encrypt certificate
    certbot --nginx -d ${domain_name} --non-interactive --agree-tos --email admin@${domain_name} --redirect
    
    # Set up auto-renewal
    echo "0 0,12 * * * root python3 -c 'import random; import time; time.sleep(random.random() * 3600)' && certbot renew -q" | tee -a /etc/crontab > /dev/null
    
else
    echo "No domain provided, using self-signed certificate" | logger -t user-data
    
    # Generate self-signed certificate as fallback
    mkdir -p /etc/nginx/ssl
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout /etc/nginx/ssl/server.key \
      -out /etc/nginx/ssl/server.crt \
      -subj "/C=US/ST=State/L=City/O=MCP/CN=${service_name}.local"
    
    # Configure nginx with self-signed cert
    cat > /etc/nginx/conf.d/mcp.conf <<'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name _;

    ssl_certificate /etc/nginx/ssl/server.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Add CORS headers
        add_header Access-Control-Allow-Origin * always;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Content-Type, Accept, Authorization, X-Session-Id" always;
        add_header Access-Control-Max-Age 86400 always;
        
        # Handle preflight requests
        if ($request_method = OPTIONS) {
            add_header Access-Control-Allow-Origin * always;
            add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
            add_header Access-Control-Allow-Headers "Content-Type, Accept, Authorization, X-Session-Id" always;
            add_header Access-Control-Max-Age 86400 always;
            add_header Content-Length 0;
            add_header Content-Type text/plain;
            return 204;
        }
    }
}
NGINX

    # Start nginx
    systemctl enable nginx
    systemctl start nginx
fi

# Set up daily auto-update check (optional)
cat > /usr/local/bin/update-mcp.sh <<'SCRIPT'
#!/bin/bash
# Check for Docker image updates

echo "Starting MCP image update check..." | logger -t mcp-update

# Get current running image hash
CURRENT_IMAGE=$(docker inspect --format='{{.Image}}' code-expert-mcp 2>/dev/null)
if [ -z "$CURRENT_IMAGE" ]; then
    echo "ERROR: Could not get current image hash. Container may not be running." | logger -t mcp-update
    exit 1
fi

echo "Current image hash: $CURRENT_IMAGE" | logger -t mcp-update

# Pull latest image
echo "Pulling latest image: ${docker_image}" | logger -t mcp-update
if ! docker pull ${docker_image} > /dev/null 2>&1; then
    echo "ERROR: Failed to pull image ${docker_image}" | logger -t mcp-update
    exit 1
fi

# Get new image hash
NEW_IMAGE=$(docker inspect --format='{{.Id}}' ${docker_image} 2>/dev/null)
if [ -z "$NEW_IMAGE" ]; then
    echo "ERROR: Could not get new image hash after pull" | logger -t mcp-update
    exit 1
fi

echo "New image hash: $NEW_IMAGE" | logger -t mcp-update

# Compare and update if needed
if [ "$CURRENT_IMAGE" != "$NEW_IMAGE" ]; then
    echo "New image found! Updating service..." | logger -t mcp-update
    systemctl restart code-expert-mcp
    echo "Service successfully updated to new image" | logger -t mcp-update
else
    echo "No new image found - service is up to date" | logger -t mcp-update
fi
SCRIPT

chmod +x /usr/local/bin/update-mcp.sh

# Add cron job to check for updates daily at 3 AM
echo "0 3 * * * root /usr/local/bin/update-mcp.sh" >> /etc/crontab

# Log the instance is ready
echo "Code Expert MCP server is ready!" | logger -t user-data