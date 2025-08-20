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

# Create VPC (since no default VPC exists)
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.tags, {
    Name = "${var.service_name}-vpc"
  })
}

# Create Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.tags, {
    Name = "${var.service_name}-igw"
  })
}

# Create public subnet
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.service_name}-public-subnet"
  })
}

# Create route table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(var.tags, {
    Name = "${var.service_name}-public-rt"
  })
}

# Associate route table with subnet
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Data source for availability zones
data "aws_availability_zones" "available" {
  state = "available"
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
  vpc_id      = aws_vpc.main.id

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

  # Network configuration
  subnet_id                   = aws_subnet.public.id
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.mcp_server.id]
  key_name                    = "code-expert-mcp-debug"

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
  user_data = templatefile("${path.module}/user_data_letsencrypt.sh", {
    docker_image     = var.docker_image
    max_cached_repos = var.max_cached_repos
    service_name     = var.service_name
    domain_name      = var.domain_name
  })

  # IAM instance profile (if needed for AWS services)
  # iam_instance_profile = aws_iam_instance_profile.mcp_server.name

  tags = merge(var.tags, {
    Name = "${var.service_name}-instance"
  })
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

# Route 53 DNS record (optional)
resource "aws_route53_record" "mcp_server" {
  count   = var.domain_name != "" && var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"
  ttl     = 60
  records = [var.use_elastic_ip && length(aws_eip.mcp_server) > 0 ? aws_eip.mcp_server[0].public_ip : aws_instance.mcp_server.public_ip]
}