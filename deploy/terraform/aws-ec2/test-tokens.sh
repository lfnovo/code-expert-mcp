#!/bin/bash
# Test script to verify token configuration

echo "Testing token configuration..."
echo ""

# Check if tokens are set in terraform.tfvars
if [ -f terraform.tfvars ]; then
    echo "Checking terraform.tfvars for tokens..."
    
    if grep -q "github_token" terraform.tfvars; then
        echo "✓ GitHub token is configured"
    else
        echo "✗ GitHub token is NOT configured (optional)"
    fi
    
    if grep -q "azure_devops_pat" terraform.tfvars; then
        echo "✓ Azure DevOps PAT is configured"
    else
        echo "✗ Azure DevOps PAT is NOT configured (optional)"
    fi
else
    echo "terraform.tfvars not found - using defaults (no tokens)"
fi

echo ""
echo "To add tokens, edit terraform.tfvars and add:"
echo '  github_token     = "ghp_your_token_here"'
echo '  azure_devops_pat = "your_azure_pat_here"'
echo ""
echo "Then run: terraform apply"