#!/bin/bash
# User data script to set up Code Expert MCP on EC2

# Update system
dnf update -y

# Install Docker
dnf install -y docker
systemctl start docker
systemctl enable docker

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Create cache directory with proper permissions
mkdir -p /var/cache/code-expert-mcp
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
  -p 80:3001 \
  -p 443:3001 \
  -p 3001:3001 \
  -v /var/cache/code-expert-mcp:/cache \
  -e PYTHONPATH=/app \
  -e MAX_CACHED_REPOS=${max_cached_repos} \
  -e MCP_USE_HTTPS=false \
  -e CONTAINER=docker \
  ${docker_image}
ExecStop=/usr/bin/docker stop ${service_name}

[Install]
WantedBy=multi-user.target
EOF

# Start the service
systemctl daemon-reload
systemctl enable code-expert-mcp.service
systemctl start code-expert-mcp.service

# Set up nginx as reverse proxy with self-signed cert (optional)
dnf install -y nginx openssl

# Generate self-signed certificate
mkdir -p /etc/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/server.key \
  -out /etc/nginx/ssl/server.crt \
  -subj "/C=US/ST=State/L=City/O=MCP/CN=${service_name}.local"

# Configure nginx
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
    }
}
NGINX

# Start nginx
systemctl enable nginx
systemctl start nginx

# Log the instance is ready
echo "Code Expert MCP server is ready!" | logger -t user-data