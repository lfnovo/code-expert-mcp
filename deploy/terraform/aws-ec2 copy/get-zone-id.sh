#!/bin/bash
# Helper script to find your Route 53 hosted zone ID

echo "Finding your Route 53 hosted zones..."
echo ""

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed."
    echo "Please install it first: https://aws.amazon.com/cli/"
    exit 1
fi

# Get AWS profile from argument or use default
PROFILE="${1:-default}"

echo "Using AWS profile: $PROFILE"
echo ""
echo "Your Route 53 Hosted Zones:"
echo "============================"

aws route53 list-hosted-zones \
    --profile "$PROFILE" \
    --query 'HostedZones[*].[Id,Name]' \
    --output table 2>/dev/null

if [ $? -ne 0 ]; then
    echo ""
    echo "Error: Could not list hosted zones."
    echo "Please check your AWS credentials and profile name."
    echo ""
    echo "Usage: ./get-zone-id.sh [profile-name]"
    echo "Example: ./get-zone-id.sh supernova"
    exit 1
fi

echo ""
echo "To use a zone, copy the ID (without /hostedzone/) to terraform.tfvars"
echo "Example: ZVF6FKEY4KFK0"