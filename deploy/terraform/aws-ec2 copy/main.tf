terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

# Local values for VPC and subnet selection
locals {
  vpc_id    = var.create_vpc ? aws_vpc.main[0].id : var.vpc_id
  subnet_id = var.create_vpc ? aws_subnet.public[0].id : var.subnet_id
}

# Create VPC (conditional - only when create_vpc is true)
resource "aws_vpc" "main" {
  count = var.create_vpc ? 1 : 0
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.tags, {
    Name = "${var.service_name}-vpc"
  })
}

# Create Internet Gateway (conditional)
resource "aws_internet_gateway" "main" {
  count  = var.create_vpc ? 1 : 0
  vpc_id = aws_vpc.main[0].id

  tags = merge(var.tags, {
    Name = "${var.service_name}-igw"
  })
}

# Create public subnet (conditional)
resource "aws_subnet" "public" {
  count   = var.create_vpc ? 1 : 0
  vpc_id  = aws_vpc.main[0].id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.service_name}-public-subnet"
  })
}

# Create route table (conditional)
resource "aws_route_table" "public" {
  count  = var.create_vpc ? 1 : 0
  vpc_id = aws_vpc.main[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main[0].id
  }

  tags = merge(var.tags, {
    Name = "${var.service_name}-public-rt"
  })
}

# Associate route table with subnet (conditional)
resource "aws_route_table_association" "public" {
  count          = var.create_vpc ? 1 : 0
  subnet_id      = aws_subnet.public[0].id
  route_table_id = aws_route_table.public[0].id
}

# Data source for availability zones
data "aws_availability_zones" "available" {
  state = "available"
}

# Data sources for existing VPC/subnet (when not creating new ones)
data "aws_vpc" "existing" {
  count = var.create_vpc ? 0 : 1
  id    = var.vpc_id
}

data "aws_subnet" "existing" {
  count = var.create_vpc ? 0 : 1
  id    = var.subnet_id
}

# Data source for latest Amazon Linux 2023 AMI
data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Security group for EC2 instance
resource "aws_security_group" "mcp_server" {
  name_prefix = "${var.service_name}-sg-"
  description = "Security group for Code Expert MCP server"
  vpc_id      = local.vpc_id

  # Allow inbound HTTP
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow HTTP"
  }

  # Allow inbound HTTPS
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow HTTPS"
  }

  # Allow inbound on MCP port
  ingress {
    from_port   = 3001
    to_port     = 3001
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow MCP service"
  }

  # Allow SSH (optional, for debugging)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.ssh_allowed_ips
    description = "Allow SSH from specific IPs"
  }

  # Allow all outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }

  tags = merge(var.tags, {
    Name = "${var.service_name}-security-group"
  })
}

# EC2 instance
resource "aws_instance" "mcp_server" {
  ami           = data.aws_ami.amazon_linux_2023.id
  instance_type = var.instance_type

  # Network configuration - ensure same AZ as cache volume
  availability_zone           = data.aws_availability_zones.available.names[0]
  subnet_id                   = local.subnet_id
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.mcp_server.id]

  # Storage for cache
  root_block_device {
    volume_type = "gp3"
    volume_size = var.volume_size
    encrypted   = true
    
    tags = merge(var.tags, {
      Name = "${var.service_name}-root-volume"
    })
  }

  # User data script to install Docker and run container
  user_data = templatefile("${path.module}/user_data.sh", {
    docker_image     = var.docker_image
    max_cached_repos = var.max_cached_repos
    service_name     = var.service_name
    domain_name      = var.domain_name
    github_token     = var.github_token
    azure_devops_pat = var.azure_devops_pat
  })

  # IAM instance profile for SSM access
  iam_instance_profile = aws_iam_instance_profile.mcp_server.name

  tags = merge(var.tags, {
    Name = "${var.service_name}-instance"
  })
}

# Persistent EBS volume for cache storage
resource "aws_ebs_volume" "cache" {
  availability_zone = data.aws_availability_zones.available.names[0]  # Fixed AZ, not dependent on instance
  size              = var.cache_volume_size
  type              = "gp3"
  encrypted         = true

  # Prevent destruction when instance is replaced
  lifecycle {
    prevent_destroy = false  # Allow manual destroy but not automatic
    ignore_changes  = [availability_zone]  # Don't recreate if AZ changes
  }

  tags = merge(var.tags, {
    Name = "${var.service_name}-cache-volume"
  })
}

# Attach the cache volume to the instance
resource "aws_volume_attachment" "cache" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.cache.id
  instance_id = aws_instance.mcp_server.id
  
  # Force detach on destroy to allow instance replacement
  force_detach = true
  
  # Ensure attachment is recreated when instance is replaced
  lifecycle {
    replace_triggered_by = [
      aws_instance.mcp_server
    ]
  }
}

# Elastic IP for consistent addressing
resource "aws_eip" "mcp_server" {
  count    = var.use_elastic_ip ? 1 : 0
  instance = aws_instance.mcp_server.id
  domain   = "vpc"

  tags = merge(var.tags, {
    Name = "${var.service_name}-eip"
  })
}

# CloudWatch log group
resource "aws_cloudwatch_log_group" "mcp_server" {
  name              = "/aws/ec2/${var.service_name}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# IAM role for EC2 instance (for SSM access)
resource "aws_iam_role" "mcp_server" {
  name_prefix = "${var.service_name}-role-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# Attach SSM policy for Session Manager access
resource "aws_iam_role_policy_attachment" "ssm_policy" {
  role       = aws_iam_role.mcp_server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Create instance profile
resource "aws_iam_instance_profile" "mcp_server" {
  name_prefix = "${var.service_name}-profile-"
  role        = aws_iam_role.mcp_server.name

  tags = var.tags
}

# Route 53 DNS record (optional)
resource "aws_route53_record" "mcp_server" {
  count   = var.domain_name != "" && var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"
  ttl     = 60
  records = [var.use_elastic_ip && length(aws_eip.mcp_server) > 0 ? aws_eip.mcp_server[0].public_ip : aws_instance.mcp_server.public_ip]
}