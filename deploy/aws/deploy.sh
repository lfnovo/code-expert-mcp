#!/bin/bash

# AWS ECS Fargate Deployment Script with EFS and HTTPS/ALB
# Prerequisites: AWS CLI, Docker, and proper AWS credentials configured

set -e

# Configuration
AWS_REGION="us-east-1"
CLUSTER_NAME="code-understanding-cluster"
SERVICE_NAME="code-understanding-service"
ECR_REPO_NAME="code-understanding-mcp"
EFS_NAME="code-understanding-cache"
ALB_NAME="code-understanding-alb"
TARGET_GROUP_NAME="code-understanding-tg"
DOMAIN_NAME=""  # Set your domain name here (e.g., "mcp.example.com")
VPC_ID=""  # Will be auto-detected or use existing
SUBNET_IDS=""  # Will be auto-detected or use existing
PUBLIC_SUBNET_IDS=""  # For ALB (will be auto-detected)

echo "🚀 Starting deployment to AWS ECS Fargate with EFS..."

# Step 1: Create ECR repository if it doesn't exist
echo "📦 Setting up ECR repository..."
aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $AWS_REGION 2>/dev/null || \
aws ecr create-repository --repository-name $ECR_REPO_NAME --region $AWS_REGION

# Get ECR repository URI
ECR_URI=$(aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $AWS_REGION --query 'repositories[0].repositoryUri' --output text)
echo "ECR URI: $ECR_URI"

# Step 2: Build and push Docker image
echo "🐳 Building and pushing Docker image..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI
docker build -t $ECR_REPO_NAME .
docker tag $ECR_REPO_NAME:latest $ECR_URI:latest
docker push $ECR_URI:latest

# Step 3: Create EFS file system if it doesn't exist
echo "💾 Setting up EFS for persistent cache..."
EFS_ID=$(aws efs describe-file-systems --region $AWS_REGION --query "FileSystems[?Name=='$EFS_NAME'].FileSystemId" --output text)

if [ -z "$EFS_ID" ]; then
    EFS_ID=$(aws efs create-file-system \
        --creation-token $EFS_NAME \
        --performance-mode generalPurpose \
        --throughput-mode bursting \
        --encrypted \
        --tags "Key=Name,Value=$EFS_NAME" \
        --region $AWS_REGION \
        --query 'FileSystemId' \
        --output text)
    echo "Created EFS: $EFS_ID"
    
    # Wait for EFS to be available
    aws efs wait file-system-available --file-system-id $EFS_ID --region $AWS_REGION
else
    echo "Using existing EFS: $EFS_ID"
fi

# Step 4: Get or create VPC and subnets
if [ -z "$VPC_ID" ]; then
    VPC_ID=$(aws ec2 describe-vpcs --region $AWS_REGION --query 'Vpcs[?IsDefault==`true`].VpcId' --output text)
    echo "Using default VPC: $VPC_ID"
fi

if [ -z "$SUBNET_IDS" ]; then
    SUBNET_IDS=$(aws ec2 describe-subnets --region $AWS_REGION --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[*].SubnetId' --output text | tr '\t' ',')
    echo "Using subnets: $SUBNET_IDS"
fi

if [ -z "$PUBLIC_SUBNET_IDS" ]; then
    PUBLIC_SUBNET_IDS=$(aws ec2 describe-subnets --region $AWS_REGION --filters "Name=vpc-id,Values=$VPC_ID" "Name=map-public-ip-on-launch,Values=true" --query 'Subnets[*].SubnetId' --output text | tr '\t' ',')
    echo "Using public subnets for ALB: $PUBLIC_SUBNET_IDS"
fi

# Step 5: Create EFS mount targets for each subnet
echo "🔗 Creating EFS mount targets..."
IFS=',' read -ra SUBNET_ARRAY <<< "$SUBNET_IDS"
for SUBNET in "${SUBNET_ARRAY[@]}"; do
    aws efs describe-mount-targets --file-system-id $EFS_ID --region $AWS_REGION --query "MountTargets[?SubnetId=='$SUBNET'].MountTargetId" --output text || \
    aws efs create-mount-target \
        --file-system-id $EFS_ID \
        --subnet-id $SUBNET \
        --region $AWS_REGION 2>/dev/null || true
done

# Step 6: Create EFS access point
echo "🔐 Creating EFS access point..."
ACCESS_POINT_ID=$(aws efs describe-access-points --file-system-id $EFS_ID --region $AWS_REGION --query 'AccessPoints[0].AccessPointId' --output text)

if [ -z "$ACCESS_POINT_ID" ] || [ "$ACCESS_POINT_ID" == "None" ]; then
    ACCESS_POINT_ID=$(aws efs create-access-point \
        --file-system-id $EFS_ID \
        --posix-user "Uid=1000,Gid=1000" \
        --root-directory "Path=/cache,CreationInfo={OwnerUid=1000,OwnerGid=1000,Permissions=755}" \
        --tags "Key=Name,Value=code-understanding-cache-ap" \
        --region $AWS_REGION \
        --query 'AccessPointId' \
        --output text)
    echo "Created access point: $ACCESS_POINT_ID"
else
    echo "Using existing access point: $ACCESS_POINT_ID"
fi

# Step 7: Update task definition with actual EFS details
echo "📝 Updating task definition..."
sed -i.bak "s/fs-xxxxxx/$EFS_ID/g" deploy/aws/ecs-task-definition.json
sed -i.bak "s/fsap-xxxxxx/$ACCESS_POINT_ID/g" deploy/aws/ecs-task-definition.json
sed -i.bak "s|YOUR_ECR_REPO_URI|$ECR_URI|g" deploy/aws/ecs-task-definition.json

# Step 8: Register task definition
echo "📋 Registering task definition..."
aws ecs register-task-definition \
    --cli-input-json file://deploy/aws/ecs-task-definition.json \
    --region $AWS_REGION

# Step 9: Create Security Groups
echo "🔒 Setting up security groups..."
# Security group for ALB
ALB_SG_ID=$(aws ec2 describe-security-groups --region $AWS_REGION --filters "Name=group-name,Values=code-understanding-alb-sg" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)
if [ -z "$ALB_SG_ID" ] || [ "$ALB_SG_ID" == "None" ]; then
    ALB_SG_ID=$(aws ec2 create-security-group \
        --group-name code-understanding-alb-sg \
        --description "Security group for Code Understanding ALB" \
        --vpc-id $VPC_ID \
        --region $AWS_REGION \
        --query 'GroupId' \
        --output text)
    
    # Allow HTTPS traffic
    aws ec2 authorize-security-group-ingress \
        --group-id $ALB_SG_ID \
        --protocol tcp \
        --port 443 \
        --cidr 0.0.0.0/0 \
        --region $AWS_REGION
    
    # Allow HTTP traffic (for redirect to HTTPS)
    aws ec2 authorize-security-group-ingress \
        --group-id $ALB_SG_ID \
        --protocol tcp \
        --port 80 \
        --cidr 0.0.0.0/0 \
        --region $AWS_REGION
    
    echo "Created ALB security group: $ALB_SG_ID"
else
    echo "Using existing ALB security group: $ALB_SG_ID"
fi

# Security group for ECS tasks
ECS_SG_ID=$(aws ec2 describe-security-groups --region $AWS_REGION --filters "Name=group-name,Values=code-understanding-ecs-sg" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)
if [ -z "$ECS_SG_ID" ] || [ "$ECS_SG_ID" == "None" ]; then
    ECS_SG_ID=$(aws ec2 create-security-group \
        --group-name code-understanding-ecs-sg \
        --description "Security group for Code Understanding ECS tasks" \
        --vpc-id $VPC_ID \
        --region $AWS_REGION \
        --query 'GroupId' \
        --output text)
    
    # Allow traffic from ALB
    aws ec2 authorize-security-group-ingress \
        --group-id $ECS_SG_ID \
        --protocol tcp \
        --port 3001 \
        --source-group $ALB_SG_ID \
        --region $AWS_REGION
    
    echo "Created ECS security group: $ECS_SG_ID"
else
    echo "Using existing ECS security group: $ECS_SG_ID"
fi

# Step 10: Request or import SSL certificate
echo "🔐 Setting up SSL certificate..."
if [ -n "$DOMAIN_NAME" ]; then
    # Check if certificate already exists
    CERT_ARN=$(aws acm list-certificates --region $AWS_REGION --query "CertificateSummaryList[?DomainName=='$DOMAIN_NAME'].CertificateArn" --output text)
    
    if [ -z "$CERT_ARN" ] || [ "$CERT_ARN" == "None" ]; then
        # Request new certificate
        CERT_ARN=$(aws acm request-certificate \
            --domain-name $DOMAIN_NAME \
            --validation-method DNS \
            --region $AWS_REGION \
            --query 'CertificateArn' \
            --output text)
        echo "Requested certificate: $CERT_ARN"
        echo "⚠️  IMPORTANT: You must validate the certificate via DNS before the ALB can use it!"
        echo "Check your email or AWS Console for validation instructions."
    else
        echo "Using existing certificate: $CERT_ARN"
    fi
else
    echo "⚠️  No domain name specified. ALB will be created without HTTPS listener."
    echo "Set DOMAIN_NAME in the script to enable HTTPS."
fi

# Step 11: Create Target Group
echo "🎯 Creating target group..."
TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups --names $TARGET_GROUP_NAME --region $AWS_REGION --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null)

if [ -z "$TARGET_GROUP_ARN" ] || [ "$TARGET_GROUP_ARN" == "None" ]; then
    TARGET_GROUP_ARN=$(aws elbv2 create-target-group \
        --name $TARGET_GROUP_NAME \
        --protocol HTTP \
        --port 3001 \
        --vpc-id $VPC_ID \
        --target-type ip \
        --health-check-protocol HTTP \
        --health-check-path / \
        --health-check-interval-seconds 30 \
        --health-check-timeout-seconds 5 \
        --healthy-threshold-count 2 \
        --unhealthy-threshold-count 3 \
        --region $AWS_REGION \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text)
    echo "Created target group: $TARGET_GROUP_ARN"
else
    echo "Using existing target group: $TARGET_GROUP_ARN"
fi

# Step 12: Create Application Load Balancer
echo "⚖️ Creating Application Load Balancer..."
ALB_ARN=$(aws elbv2 describe-load-balancers --names $ALB_NAME --region $AWS_REGION --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null)

if [ -z "$ALB_ARN" ] || [ "$ALB_ARN" == "None" ]; then
    ALB_OUTPUT=$(aws elbv2 create-load-balancer \
        --name $ALB_NAME \
        --subnets $PUBLIC_SUBNET_IDS \
        --security-groups $ALB_SG_ID \
        --region $AWS_REGION)
    
    ALB_ARN=$(echo $ALB_OUTPUT | jq -r '.LoadBalancers[0].LoadBalancerArn')
    ALB_DNS=$(echo $ALB_OUTPUT | jq -r '.LoadBalancers[0].DNSName')
    echo "Created ALB: $ALB_ARN"
    echo "ALB DNS: $ALB_DNS"
else
    echo "Using existing ALB: $ALB_ARN"
    ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN --region $AWS_REGION --query 'LoadBalancers[0].DNSName' --output text)
fi

# Step 13: Create ALB Listeners
echo "👂 Setting up ALB listeners..."

# HTTP listener (redirects to HTTPS if certificate exists)
HTTP_LISTENER_ARN=$(aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --region $AWS_REGION --query "Listeners[?Port==\`80\`].ListenerArn" --output text)

if [ -z "$HTTP_LISTENER_ARN" ] || [ "$HTTP_LISTENER_ARN" == "None" ]; then
    if [ -n "$CERT_ARN" ] && [ "$CERT_ARN" != "None" ]; then
        # Redirect to HTTPS
        aws elbv2 create-listener \
            --load-balancer-arn $ALB_ARN \
            --protocol HTTP \
            --port 80 \
            --default-actions "Type=redirect,RedirectConfig={Protocol=HTTPS,Port=443,StatusCode=HTTP_301}" \
            --region $AWS_REGION
    else
        # Forward to target group
        aws elbv2 create-listener \
            --load-balancer-arn $ALB_ARN \
            --protocol HTTP \
            --port 80 \
            --default-actions Type=forward,TargetGroupArn=$TARGET_GROUP_ARN \
            --region $AWS_REGION
    fi
    echo "Created HTTP listener"
fi

# HTTPS listener (if certificate exists)
if [ -n "$CERT_ARN" ] && [ "$CERT_ARN" != "None" ]; then
    HTTPS_LISTENER_ARN=$(aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --region $AWS_REGION --query "Listeners[?Port==\`443\`].ListenerArn" --output text)
    
    if [ -z "$HTTPS_LISTENER_ARN" ] || [ "$HTTPS_LISTENER_ARN" == "None" ]; then
        aws elbv2 create-listener \
            --load-balancer-arn $ALB_ARN \
            --protocol HTTPS \
            --port 443 \
            --certificates CertificateArn=$CERT_ARN \
            --default-actions Type=forward,TargetGroupArn=$TARGET_GROUP_ARN \
            --region $AWS_REGION
        echo "Created HTTPS listener"
    fi
fi

# Step 14: Create ECS cluster if it doesn't exist
echo "🏗️ Setting up ECS cluster..."
aws ecs describe-clusters --clusters $CLUSTER_NAME --region $AWS_REGION 2>/dev/null || \
aws ecs create-cluster --cluster-name $CLUSTER_NAME --region $AWS_REGION

# Step 15: Create or update service with ALB
echo "🚀 Creating/updating ECS service with ALB..."

# Check if service exists
SERVICE_EXISTS=$(aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $AWS_REGION --query 'services[0].serviceName' --output text 2>/dev/null)

if [ "$SERVICE_EXISTS" == "$SERVICE_NAME" ]; then
    # Update existing service
    aws ecs update-service \
        --cluster $CLUSTER_NAME \
        --service $SERVICE_NAME \
        --task-definition code-understanding-mcp \
        --desired-count 1 \
        --region $AWS_REGION
else
    # Create new service with ALB
    aws ecs create-service \
        --cluster $CLUSTER_NAME \
        --service-name $SERVICE_NAME \
        --task-definition code-understanding-mcp \
        --desired-count 1 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_IDS],securityGroups=[$ECS_SG_ID],assignPublicIp=ENABLED}" \
        --load-balancers targetGroupArn=$TARGET_GROUP_ARN,containerName=code-understanding-mcp,containerPort=3001 \
        --region $AWS_REGION
fi

echo "✅ Deployment complete!"
echo ""
echo "📊 Service Dashboard: https://console.aws.amazon.com/ecs/home?region=$AWS_REGION#/clusters/$CLUSTER_NAME/services/$SERVICE_NAME/tasks"
echo ""
if [ -n "$DOMAIN_NAME" ]; then
    echo "🌐 Your service will be available at: https://$DOMAIN_NAME"
    echo "   (after DNS configuration and certificate validation)"
    echo ""
    echo "📝 Next steps:"
    echo "   1. Validate the ACM certificate (check AWS Console or email)"
    echo "   2. Point your domain's DNS to: $ALB_DNS"
else
    echo "🌐 Your service is available at: http://$ALB_DNS"
    echo ""
    echo "📝 To enable HTTPS:"
    echo "   1. Set DOMAIN_NAME in this script"
    echo "   2. Re-run the deployment"
fi