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
  description = "Size of root EBS volume in GB"
  type        = number
  default     = 30
}

variable "cache_volume_size" {
  description = "Size of persistent cache EBS volume in GB"
  type        = number
  default     = 50  # Separate persistent storage for git repos
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
  description = "Domain name for the Web UI (e.g., code-expert.supernovalabs.com)"
  type        = string
  default     = ""
}

variable "mcp_domain_name" {
  description = "Domain name for the MCP server (e.g., mcp.code-expert.supernovalabs.com)"
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone ID for the domain"
  type        = string
  default     = ""
}

variable "github_token" {
  description = "GitHub Personal Access Token for private repository access"
  type        = string
  default     = ""
  sensitive   = true
}

variable "azure_devops_pat" {
  description = "Azure DevOps Personal Access Token for private repository access"
  type        = string
  default     = ""
  sensitive   = true
}

variable "webhook_secret" {
  description = "Secret for validating incoming webhook signatures (HMAC-SHA256)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "repo_api_password" {
  description = "API password for repository management endpoints"
  type        = string
  default     = ""
  sensitive   = true
}

# VPC Configuration
variable "create_vpc" {
  description = "Whether to create a new VPC or use an existing one"
  type        = bool
  default     = true
}

variable "vpc_id" {
  description = "ID of existing VPC to use (when create_vpc is false)"
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "ID of existing subnet to use (when create_vpc is false)"
  type        = string
  default     = ""
}