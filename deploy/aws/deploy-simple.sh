#!/bin/bash

# Simplified AWS deployment with HTTPS using AWS-provided domain
# This uses ALB with AWS-generated SSL certificate (no custom domain needed)

set -e

AWS_REGION="us-east-1"
STACK_NAME="code-understanding-stack"

echo "🚀 Deploying with CloudFormation (includes HTTPS)..."

# Create CloudFormation template
cat > deploy/aws/cloudformation.yaml << 'EOF'
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Code Understanding MCP Service with HTTPS'

Resources:
  # ECS Cluster
  Cluster:
    Type: AWS::ECS::Cluster
    Properties:
      ClusterName: code-understanding-cluster

  # EFS File System for cache
  FileSystem:
    Type: AWS::EFS::FileSystem
    Properties:
      Encrypted: true
      PerformanceMode: generalPurpose
      ThroughputMode: bursting
      Tags:
        - Key: Name
          Value: code-understanding-cache

  # EFS Mount Targets (one per subnet)
  MountTarget1:
    Type: AWS::EFS::MountTarget
    Properties:
      FileSystemId: !Ref FileSystem
      SubnetId: !Ref PublicSubnet1
      SecurityGroups:
        - !Ref EFSSecurityGroup

  MountTarget2:
    Type: AWS::EFS::MountTarget
    Properties:
      FileSystemId: !Ref FileSystem
      SubnetId: !Ref PublicSubnet2
      SecurityGroups:
        - !Ref EFSSecurityGroup

  # EFS Access Point
  AccessPoint:
    Type: AWS::EFS::AccessPoint
    Properties:
      FileSystemId: !Ref FileSystem
      PosixUser:
        Uid: 1000
        Gid: 1000
      RootDirectory:
        Path: /cache
        CreationInfo:
          OwnerUid: 1000
          OwnerGid: 1000
          Permissions: '755'

  # VPC Configuration
  VPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.0.0.0/16
      EnableDnsHostnames: true
      EnableDnsSupport: true

  PublicSubnet1:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.0.1.0/24
      AvailabilityZone: !Select [0, !GetAZs '']
      MapPublicIpOnLaunch: true

  PublicSubnet2:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.0.2.0/24
      AvailabilityZone: !Select [1, !GetAZs '']
      MapPublicIpOnLaunch: true

  InternetGateway:
    Type: AWS::EC2::InternetGateway

  AttachGateway:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref VPC
      InternetGatewayId: !Ref InternetGateway

  PublicRouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref VPC

  PublicRoute:
    Type: AWS::EC2::Route
    DependsOn: AttachGateway
    Properties:
      RouteTableId: !Ref PublicRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway

  SubnetRouteTableAssociation1:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PublicSubnet1
      RouteTableId: !Ref PublicRouteTable

  SubnetRouteTableAssociation2:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PublicSubnet2
      RouteTableId: !Ref PublicRouteTable

  # Security Groups
  ALBSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Security group for ALB
      VpcId: !Ref VPC
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: 0.0.0.0/0
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0

  ECSSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Security group for ECS tasks
      VpcId: !Ref VPC
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 3001
          ToPort: 3001
          SourceSecurityGroupId: !Ref ALBSecurityGroup

  EFSSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Security group for EFS
      VpcId: !Ref VPC
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 2049
          ToPort: 2049
          SourceSecurityGroupId: !Ref ECSSecurityGroup

  # Application Load Balancer
  LoadBalancer:
    Type: AWS::ElasticLoadBalancingV2::LoadBalancer
    Properties:
      Name: code-understanding-alb
      Subnets:
        - !Ref PublicSubnet1
        - !Ref PublicSubnet2
      SecurityGroups:
        - !Ref ALBSecurityGroup

  TargetGroup:
    Type: AWS::ElasticLoadBalancingV2::TargetGroup
    Properties:
      Name: code-understanding-tg
      Port: 3001
      Protocol: HTTP
      VpcId: !Ref VPC
      TargetType: ip
      HealthCheckPath: /
      HealthCheckIntervalSeconds: 30
      HealthCheckTimeoutSeconds: 5
      HealthyThresholdCount: 2
      UnhealthyThresholdCount: 3

  # HTTP Listener (redirects to HTTPS)
  HTTPListener:
    Type: AWS::ElasticLoadBalancingV2::Listener
    Properties:
      LoadBalancerArn: !Ref LoadBalancer
      Port: 80
      Protocol: HTTP
      DefaultActions:
        - Type: redirect
          RedirectConfig:
            Protocol: HTTPS
            Port: '443'
            StatusCode: HTTP_301

  # HTTPS Listener with AWS-managed certificate
  HTTPSListener:
    Type: AWS::ElasticLoadBalancingV2::Listener
    Properties:
      LoadBalancerArn: !Ref LoadBalancer
      Port: 443
      Protocol: HTTPS
      Certificates:
        - CertificateArn: !Ref Certificate
      DefaultActions:
        - Type: forward
          TargetGroupArn: !Ref TargetGroup

  # Self-signed certificate for ALB (AWS-managed)
  Certificate:
    Type: AWS::CertificateManager::Certificate
    Properties:
      DomainName: !GetAtt LoadBalancer.DNSName
      ValidationMethod: DNS
      DomainValidationOptions:
        - DomainName: !GetAtt LoadBalancer.DNSName
          HostedZoneId: !Ref 'AWS::NoValue'

  # ECR Repository
  ECRRepository:
    Type: AWS::ECR::Repository
    Properties:
      RepositoryName: code-understanding-mcp

  # Task Execution Role
  TaskExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: ecs-tasks.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

  # Task Role
  TaskRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: ecs-tasks.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: EFSAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - elasticfilesystem:ClientMount
                  - elasticfilesystem:ClientWrite
                Resource: !GetAtt FileSystem.Arn

  # CloudWatch Log Group
  LogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /ecs/code-understanding-mcp
      RetentionInDays: 7

  # Task Definition
  TaskDefinition:
    Type: AWS::ECS::TaskDefinition
    Properties:
      Family: code-understanding-mcp
      NetworkMode: awsvpc
      RequiresCompatibilities:
        - FARGATE
      Cpu: '1024'
      Memory: '2048'
      ExecutionRoleArn: !Ref TaskExecutionRole
      TaskRoleArn: !Ref TaskRole
      Volumes:
        - Name: cache-volume
          EFSVolumeConfiguration:
            FilesystemId: !Ref FileSystem
            TransitEncryption: ENABLED
            AuthorizationConfig:
              AccessPointId: !Ref AccessPoint
              IAM: ENABLED
      ContainerDefinitions:
        - Name: code-understanding-mcp
          Image: !Sub '${AWS::AccountId}.dkr.ecr.${AWS::Region}.amazonaws.com/code-understanding-mcp:latest'
          Essential: true
          PortMappings:
            - ContainerPort: 3001
              Protocol: tcp
          Environment:
            - Name: PYTHONPATH
              Value: /app
            - Name: MAX_CACHED_REPOS
              Value: '50'
          MountPoints:
            - SourceVolume: cache-volume
              ContainerPath: /cache
          LogConfiguration:
            LogDriver: awslogs
            Options:
              awslogs-group: !Ref LogGroup
              awslogs-region: !Ref 'AWS::Region'
              awslogs-stream-prefix: ecs

  # ECS Service
  Service:
    Type: AWS::ECS::Service
    DependsOn:
      - HTTPSListener
      - HTTPListener
    Properties:
      Cluster: !Ref Cluster
      ServiceName: code-understanding-service
      TaskDefinition: !Ref TaskDefinition
      DesiredCount: 1
      LaunchType: FARGATE
      NetworkConfiguration:
        AwsvpcConfiguration:
          Subnets:
            - !Ref PublicSubnet1
            - !Ref PublicSubnet2
          SecurityGroups:
            - !Ref ECSSecurityGroup
          AssignPublicIp: ENABLED
      LoadBalancers:
        - TargetGroupArn: !Ref TargetGroup
          ContainerName: code-understanding-mcp
          ContainerPort: 3001

Outputs:
  ServiceURL:
    Description: URL of the service
    Value: !Sub 'https://${LoadBalancer.DNSName}'
  ECRRepository:
    Description: ECR Repository URI
    Value: !Sub '${AWS::AccountId}.dkr.ecr.${AWS::Region}.amazonaws.com/code-understanding-mcp'
EOF

# Deploy stack
aws cloudformation deploy \
    --template-file deploy/aws/cloudformation.yaml \
    --stack-name $STACK_NAME \
    --capabilities CAPABILITY_IAM \
    --region $AWS_REGION

# Get outputs
ECR_URI=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query 'Stacks[0].Outputs[?OutputKey==`ECRRepository`].OutputValue' --output text)
SERVICE_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query 'Stacks[0].Outputs[?OutputKey==`ServiceURL`].OutputValue' --output text)

# Build and push Docker image
echo "🐳 Building and pushing Docker image..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI
docker build -t code-understanding-mcp .
docker tag code-understanding-mcp:latest $ECR_URI:latest
docker push $ECR_URI:latest

# Update service to use new image
aws ecs update-service --cluster code-understanding-cluster --service code-understanding-service --force-new-deployment --region $AWS_REGION

echo "✅ Deployment complete!"
echo "🌐 Your service is available at: $SERVICE_URL"
echo "Note: The HTTPS certificate is self-signed. You'll see a security warning in your browser."