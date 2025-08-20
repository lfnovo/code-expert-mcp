variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "default"
}

variable "service_name" {
  description = "Name of the service"
  type        = string
  default     = "code-expert-mcp"
}

variable "docker_image" {
  description = "Docker image to deploy"
  type        = string
  default     = "docker.io/lfnovo/code-expert-mcp:latest"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"  # 2 vCPU, 2 GB RAM - good for MCP
}

variable "volume_size" {
  description = "Size of root EBS volume in GB (for git cache)"
  type        = number
  default     = 30  # Enough for many repos
}

variable "max_cached_repos" {
  description = "Maximum number of repositories to cache"
  type        = string
  default     = "100"
}

variable "use_elastic_ip" {
  description = "Use Elastic IP for consistent addressing"
  type        = bool
  default     = true
}

variable "ssh_allowed_ips" {
  description = "CIDR blocks allowed to SSH (set to empty list to disable SSH)"
  type        = list(string)
  default     = []  # No SSH by default, add your IP if needed
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "code-expert-mcp"
    ManagedBy   = "terraform"
    Environment = "production"
  }
}

variable "domain_name" {
  description = "Domain name for the MCP server (e.g., code-expert.supernovalabs.com)"
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone ID for the domain"
  type        = string
  default     = ""
}