output "instance_id" {
  description = "ID of the EC2 instance"
  value       = aws_instance.mcp_server.id
}

output "public_ip" {
  description = "Public IP address of the instance"
  value       = var.use_elastic_ip && length(aws_eip.mcp_server) > 0 ? aws_eip.mcp_server[0].public_ip : aws_instance.mcp_server.public_ip
}

output "public_dns" {
  description = "Public DNS name of the instance"
  value       = aws_instance.mcp_server.public_dns
}

output "service_url_http" {
  description = "HTTP URL of the MCP service"
  value       = "http://${var.use_elastic_ip && length(aws_eip.mcp_server) > 0 ? aws_eip.mcp_server[0].public_ip : aws_instance.mcp_server.public_ip}"
}

output "service_url_https" {
  description = "HTTPS URL of the MCP service (self-signed cert)"
  value       = "https://${var.use_elastic_ip && length(aws_eip.mcp_server) > 0 ? aws_eip.mcp_server[0].public_ip : aws_instance.mcp_server.public_ip}"
}

output "mcp_direct_url" {
  description = "Direct MCP service URL (port 3001)"
  value       = "http://${var.use_elastic_ip && length(aws_eip.mcp_server) > 0 ? aws_eip.mcp_server[0].public_ip : aws_instance.mcp_server.public_ip}:3001"
}

output "ssh_command" {
  description = "SSH command to connect to the instance (if SSH is enabled)"
  value       = length(var.ssh_allowed_ips) > 0 ? "ssh ec2-user@${var.use_elastic_ip && length(aws_eip.mcp_server) > 0 ? aws_eip.mcp_server[0].public_ip : aws_instance.mcp_server.public_ip}" : "SSH is disabled - set ssh_allowed_ips to enable"
}

output "docker_logs_command" {
  description = "Command to view Docker logs"
  value       = "ssh ec2-user@${var.use_elastic_ip && length(aws_eip.mcp_server) > 0 ? aws_eip.mcp_server[0].public_ip : aws_instance.mcp_server.public_ip} 'sudo docker logs code-expert-mcp'"
}

output "cache_directory" {
  description = "Cache directory path on the instance"
  value       = "/var/cache/code-expert-mcp"
}

output "domain_url" {
  description = "Domain URL if configured"
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "No domain configured"
}