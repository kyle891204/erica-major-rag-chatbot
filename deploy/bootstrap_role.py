"""One-time role bootstrap. No long-lived access keys are created."""
import json
import boto3

REGION = "ap-northeast-2"
PROJECT = "erica-major-rag-chatbot"
session = boto3.Session(region_name=REGION)
identity = session.client("sts").get_caller_identity()
account = identity["Account"]
iam = session.client("iam")
role_name = f"{PROJECT}-deployer"
runtime_arn = f"arn:aws:iam::{account}:role/{PROJECT}-ec2"

def statement(actions, resources, condition=None):
    s = {"Effect": "Allow", "Action": actions, "Resource": resources}
    if condition:
        s["Condition"] = condition
    return s

regional = {"StringEquals": {"aws:RequestedRegion": REGION}}
tagged = {"StringEquals": {"aws:RequestedRegion": REGION, "ec2:ResourceTag/Project": PROJECT}}
bucket = f"{PROJECT}-{account}-{REGION}"
policy = {"Version": "2012-10-17", "Statement": [
    statement(["ec2:Describe*"], "*", regional),
    statement(["ec2:CreateVpc", "ec2:CreateSubnet", "ec2:CreateInternetGateway", "ec2:CreateRouteTable", "ec2:CreateSecurityGroup", "ec2:RunInstances"], "*",
              {"StringEquals": {"aws:RequestedRegion": REGION, "aws:RequestTag/Project": PROJECT}}),
    statement(["ec2:CreateTags"], "*", {"StringEquals": {"aws:RequestedRegion": REGION, "ec2:CreateAction": ["CreateVpc", "CreateSubnet", "CreateInternetGateway", "CreateRouteTable", "CreateSecurityGroup", "RunInstances"]}, "ForAllValues:StringEquals": {"aws:TagKeys": ["Project", "Name", "Week"]}}),
    statement(["ec2:ModifyVpcAttribute", "ec2:ModifySubnetAttribute", "ec2:AttachInternetGateway", "ec2:CreateRoute", "ec2:AssociateRouteTable", "ec2:AuthorizeSecurityGroupIngress", "ec2:ModifyInstanceAttribute", "ec2:StartInstances", "ec2:StopInstances"], "*", tagged),
    statement(["iam:CreateRole", "iam:GetRole", "iam:TagRole", "iam:PutRolePolicy"], runtime_arn),
    statement(["iam:AttachRolePolicy"], runtime_arn, {"ArnEquals": {"iam:PolicyARN": "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"}}),
    statement(["iam:CreateInstanceProfile", "iam:GetInstanceProfile", "iam:AddRoleToInstanceProfile", "iam:TagInstanceProfile"], f"arn:aws:iam::{account}:instance-profile/{PROJECT}-ec2"),
    statement(["iam:PassRole"], runtime_arn, {"StringEquals": {"iam:PassedToService": "ec2.amazonaws.com"}}),
    statement(["s3:ListAllMyBuckets"], "*"),
    statement(["s3:CreateBucket", "s3:GetBucketLocation", "s3:PutBucketPublicAccessBlock", "s3:GetBucketPublicAccessBlock", "s3:PutBucketTagging", "s3:PutEncryptionConfiguration", "s3:GetEncryptionConfiguration", "s3:ListBucket"], f"arn:aws:s3:::{bucket}"),
    statement(["s3:PutObject", "s3:GetObject"], f"arn:aws:s3:::{bucket}/*"),
    statement(["s3vectors:ListVectorBuckets"], "*", regional),
    statement(["s3vectors:CreateVectorBucket", "s3vectors:GetVectorBucket", "s3vectors:ListIndexes", "s3vectors:CreateIndex", "s3vectors:GetIndex", "s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:QueryVectors", "s3vectors:ListVectors", "s3vectors:TagResource"], f"arn:aws:s3vectors:{REGION}:{account}:bucket/{bucket}*", regional),
    statement(["bedrock:ListInferenceProfiles", "bedrock:ListFoundationModels"], "*", regional),
    statement(["bedrock:GetInferenceProfile", "bedrock:InvokeModel"], [f"arn:aws:bedrock:{REGION}:{account}:inference-profile/apac.amazon.nova-micro-v1:0", f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"]),
    statement(["bedrock:InvokeModel"], [f"arn:aws:bedrock:{r}::foundation-model/amazon.nova-micro-v1:0" for r in ["ap-southeast-2", "ap-northeast-1", "ap-south-1", REGION, "ap-southeast-1", "ap-northeast-3"]], {"ArnEquals": {"bedrock:InferenceProfileArn": f"arn:aws:bedrock:{REGION}:{account}:inference-profile/apac.amazon.nova-micro-v1:0"}}),
    statement(["logs:CreateLogGroup", "logs:PutRetentionPolicy", "logs:TagResource", "logs:DescribeLogStreams", "logs:GetLogEvents", "logs:FilterLogEvents", "logs:CreateLogStream", "logs:PutLogEvents"], f"arn:aws:logs:{REGION}:{account}:log-group:/{PROJECT}/*", regional),
    statement(["ssm:GetParameter"], f"arn:aws:ssm:{REGION}::parameter/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"),
    statement(["ssm:DescribeInstanceInformation", "ssm:GetCommandInvocation", "ssm:ListCommandInvocations"], "*", regional),
    statement(["ssm:SendCommand"], f"arn:aws:ec2:{REGION}:{account}:instance/*", {"StringEquals": {"ssm:resourceTag/Project": PROJECT, "aws:RequestedRegion": REGION}}),
    statement(["ssm:SendCommand"], f"arn:aws:ssm:{REGION}::document/AWS-RunShellScript"),
]}
trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"AWS": f"arn:aws:iam::{account}:root"}, "Action": "sts:AssumeRole"}]}
try:
    iam.get_role(RoleName=role_name)
except iam.exceptions.NoSuchEntityException:
    iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust), MaxSessionDuration=3600, Tags=[{"Key": "Project", "Value": PROJECT}])
else:
    raise SystemExit("Deployer role already exists: inspect before changing its policy.")
iam.put_role_policy(RoleName=role_name, PolicyName="ProjectEnvironmentSetup", PolicyDocument=json.dumps(policy))
print(json.dumps({"bootstrap_identity": identity["Arn"], "created_role": f"arn:aws:iam::{account}:role/{role_name}", "access_keys_created": False}))
