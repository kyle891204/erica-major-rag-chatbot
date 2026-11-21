"""Create only this project's week-2 resources, using a temporary deployer session.

Run from AWS CloudShell after bootstrap_role.py. State stays outside the repository.
"""
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

import boto3
from botocore.exceptions import ClientError

REGION = "ap-northeast-2"
PROJECT = "erica-major-rag-chatbot"
TITAN = "amazon.titan-embed-text-v2:0"
NOVA = "apac.amazon.nova-micro-v1:0"
INDEX = "handbook-titan-v2-1024"
state_path = Path.home() / "erica-week2-state.json"
state = json.loads(state_path.read_text()) if state_path.exists() else {}
account = boto3.client("sts").get_caller_identity()["Account"]
credentials = boto3.client("sts").assume_role(
    RoleArn=f"arn:aws:iam::{account}:role/{PROJECT}-deployer",
    RoleSessionName="week2-environment", DurationSeconds=3600,
)["Credentials"]
session = boto3.Session(aws_access_key_id=credentials["AccessKeyId"], aws_secret_access_key=credentials["SecretAccessKey"], aws_session_token=credentials["SessionToken"], region_name=REGION)
del credentials
identity = session.client("sts").get_caller_identity()["Arn"]
bucket = f"{PROJECT}-{account}-{REGION}"
state.update(region=REGION, bucket=bucket, vector_bucket=bucket, index=INDEX, deploy_identity=identity)

def save(**values):
    state.update(values)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str))
    os.chmod(state_path, 0o600)
    print(json.dumps(values, ensure_ascii=False, default=str), flush=True)

def tags(name):
    return [{"Key": "Project", "Value": PROJECT}, {"Key": "Name", "Value": name}, {"Key": "Week", "Value": "2"}]

def tag_spec(kind, name):
    return [{"ResourceType": kind, "Tags": tags(name)}]

save(deploy_identity=identity)
bedrock = session.client("bedrock")
runtime = session.client("bedrock-runtime")
profile = bedrock.get_inference_profile(inferenceProfileIdentifier=NOVA)
assert profile["status"] == "ACTIVE"
model_arns = [m["modelArn"] for m in profile["models"]]
save(nova_profile=NOVA, nova_profile_arn=profile["inferenceProfileArn"], nova_destinations=model_arns)
if not state.get("deployer_titan_success"):
    result = runtime.invoke_model(modelId=TITAN, contentType="application/json", accept="application/json", body=json.dumps({"inputText": "ERICA environment verification only.", "dimensions": 1024, "normalize": True}))
    embedding = json.loads(result["body"].read())["embedding"]
    assert len(embedding) == 1024 and all(isinstance(v, (int, float)) for v in embedding)
    save(deployer_titan_success=True, titan_dimensions=len(embedding), titan_model=TITAN, titan_normalize=True)
if not state.get("deployer_nova_success"):
    result = runtime.converse(modelId=NOVA, messages=[{"role": "user", "content": [{"text": "Reply with OK only. Environment test."}]}], inferenceConfig={"maxTokens": 8, "temperature": 0})
    save(deployer_nova_success=True, deployer_nova_response=result["output"]["message"]["content"], nova_usage=result.get("usage"))

s3 = session.client("s3")
if not state.get("s3_created"):
    existing = {b["Name"] for b in s3.list_buckets()["Buckets"]}
    if bucket not in existing:
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": tags(PROJECT + "-documents")})
    save(s3_created=True, s3_public_access_block=s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"])
test_body = b"ERICA Week 2 storage test. No academic handbook content.\n"
s3.put_object(Bucket=bucket, Key="tests/week2/storage-check.txt", Body=test_body, ContentType="text/plain")
assert s3.get_object(Bucket=bucket, Key="tests/week2/storage-check.txt")["Body"].read() == test_body
save(s3_write_read_success=True, s3_test_key="tests/week2/storage-check.txt")

vectors = session.client("s3vectors")
if not state.get("vector_bucket_created"):
    existing = {b["vectorBucketName"] for b in vectors.list_vector_buckets()["vectorBuckets"]}
    if bucket not in existing:
        vectors.create_vector_bucket(vectorBucketName=bucket)
    save(vector_bucket_created=True)
if not state.get("vector_index_created"):
    indexes = {i["indexName"] for i in vectors.list_indexes(vectorBucketName=bucket)["indexes"]}
    if INDEX not in indexes:
        vectors.create_index(vectorBucketName=bucket, indexName=INDEX, dataType="float32", dimension=1024, distanceMetric="cosine", metadataConfiguration={"nonFilterableMetadataKeys": ["text"]})
    config = vectors.get_index(vectorBucketName=bucket, indexName=INDEX)["index"]
    assert config["dimension"] == 1024 and config["dataType"] == "float32" and config["distanceMetric"] == "cosine"
    save(vector_index_created=True, vector_index_config=config)
test_vector = [1.0] + [0.0] * 1023
vectors.put_vectors(vectorBucketName=bucket, indexName=INDEX, vectors=[{"key": "test-only/week2/synthetic-1024", "data": {"float32": test_vector}, "metadata": {"dataset": "week2-test", "text": "Synthetic infrastructure test; not handbook evidence.", "item_name": "environment-test", "source_url": "https://github.com/kyle891204/erica-major-rag-chatbot", "revision_date": "2026-11-22"}}])
for attempt in range(12):
    matches = vectors.query_vectors(vectorBucketName=bucket, indexName=INDEX, queryVector={"float32": test_vector}, topK=1, filter={"dataset": {"$eq": "week2-test"}}, returnDistance=True, returnMetadata=True)["vectors"]
    if matches:
        break
    time.sleep(2)
assert matches and matches[0]["key"] == "test-only/week2/synthetic-1024"
save(vector_write_query_success=True, vector_test_matches=matches)

logs = session.client("logs")
group = f"/{PROJECT}/api"
try:
    logs.create_log_group(logGroupName=group)
except logs.exceptions.ResourceAlreadyExistsException:
    pass
logs.put_retention_policy(logGroupName=group, retentionInDays=7)
save(log_group=group, log_retention_days=7)

iam = session.client("iam")
role = f"{PROJECT}-ec2"
trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
try:
    iam.get_role(RoleName=role)
except iam.exceptions.NoSuchEntityException:
    iam.create_role(RoleName=role, AssumeRolePolicyDocument=json.dumps(trust), Tags=tags(role))
def statement(actions, resources, condition=None):
    value = {"Effect": "Allow", "Action": actions, "Resource": resources}
    if condition:
        value["Condition"] = condition
    return value
runtime_policy = {"Version": "2012-10-17", "Statement": [
    statement(["s3:ListBucket", "s3:GetBucketLocation"], f"arn:aws:s3:::{bucket}"),
    statement(["s3:GetObject", "s3:PutObject"], f"arn:aws:s3:::{bucket}/*"),
    statement(["s3vectors:GetIndex", "s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:QueryVectors", "s3vectors:ListVectors"], f"arn:aws:s3vectors:{REGION}:{account}:bucket/{bucket}/index/{INDEX}"),
    statement(["bedrock:GetInferenceProfile", "bedrock:InvokeModel"], [profile["inferenceProfileArn"], f"arn:aws:bedrock:{REGION}::foundation-model/{TITAN}"]),
    statement(["bedrock:InvokeModel"], model_arns, {"ArnEquals": {"bedrock:InferenceProfileArn": profile["inferenceProfileArn"]}}),
    statement(["logs:DescribeLogStreams", "logs:CreateLogStream", "logs:PutLogEvents"], f"arn:aws:logs:{REGION}:{account}:log-group:{group}:*"),
]}
iam.put_role_policy(RoleName=role, PolicyName="ProjectRuntime", PolicyDocument=json.dumps(runtime_policy))
iam.attach_role_policy(RoleName=role, PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore")
try:
    iam.get_instance_profile(InstanceProfileName=role)
except iam.exceptions.NoSuchEntityException:
    iam.create_instance_profile(InstanceProfileName=role, Tags=tags(role))
    iam.add_role_to_instance_profile(InstanceProfileName=role, RoleName=role)
save(ec2_role=role, runtime_policy=runtime_policy)

ec2 = session.client("ec2")
if not state.get("vpc_id"):
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "tag:Project", "Values": [PROJECT]}])["Vpcs"]
    assert len(vpcs) <= 1, "Multiple project VPCs; inspect before continuing."
    vpc = vpcs[0] if vpcs else ec2.create_vpc(CidrBlock="10.42.0.0/16", TagSpecifications=tag_spec("vpc", PROJECT + "-vpc"))["Vpc"]
    save(vpc_id=vpc["VpcId"])
vpc_id = state["vpc_id"]
ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})
ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
if not state.get("subnet_id"):
    subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.42.1.0/24", AvailabilityZone="ap-northeast-2a", TagSpecifications=tag_spec("subnet", PROJECT + "-public"))["Subnet"]
    save(subnet_id=subnet["SubnetId"])
if not state.get("igw_id"):
    igw = ec2.create_internet_gateway(TagSpecifications=tag_spec("internet-gateway", PROJECT + "-igw"))["InternetGateway"]
    save(igw_id=igw["InternetGatewayId"])
    ec2.attach_internet_gateway(InternetGatewayId=state["igw_id"], VpcId=vpc_id)
if not state.get("route_table_id"):
    route = ec2.create_route_table(VpcId=vpc_id, TagSpecifications=tag_spec("route-table", PROJECT + "-public"))["RouteTable"]
    save(route_table_id=route["RouteTableId"])
    ec2.create_route(RouteTableId=state["route_table_id"], DestinationCidrBlock="0.0.0.0/0", GatewayId=state["igw_id"])
    ec2.associate_route_table(RouteTableId=state["route_table_id"], SubnetId=state["subnet_id"])
if not state.get("security_group_id"):
    sg = ec2.create_security_group(GroupName=PROJECT + "-api", Description="Week2 health API only; management via SSM; no SSH", VpcId=vpc_id, TagSpecifications=tag_spec("security-group", PROJECT + "-api"))
    save(security_group_id=sg["GroupId"])
    ec2.authorize_security_group_ingress(GroupId=state["security_group_id"], IpPermissions=[{"IpProtocol": "tcp", "FromPort": 8000, "ToPort": 8000, "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Public health API only"}]}])

if not state.get("instance_id"):
    existing = ec2.describe_instances(Filters=[{"Name": "tag:Project", "Values": [PROJECT]}, {"Name": "instance-state-name", "Values": ["pending", "running", "stopped", "stopping"]}])["Reservations"]
    instances = [i for r in existing for i in r["Instances"]]
    assert not instances, "An existing project instance was found; inspect before launching."
    ami = session.client("ssm").get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")["Parameter"]["Value"]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    user_data = "\n".join(["#!/bin/bash", "set -euxo pipefail", "dnf install -y git", f"git clone https://github.com/kyle891204/{PROJECT}.git /opt/{PROJECT}", f"cd /opt/{PROJECT}", f"git checkout {commit}", "bash deploy/install.sh"])
    for attempt in range(8):
        try:
            instance = ec2.run_instances(ImageId=ami, InstanceType="t3.micro", MinCount=1, MaxCount=1, ClientToken=PROJECT + "-week2-20261122", IamInstanceProfile={"Name": role}, NetworkInterfaces=[{"DeviceIndex": 0, "SubnetId": state["subnet_id"], "Groups": [state["security_group_id"]], "AssociatePublicIpAddress": True}], BlockDeviceMappings=[{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 8, "VolumeType": "gp3", "Encrypted": True, "DeleteOnTermination": True}}], MetadataOptions={"HttpTokens": "required", "HttpEndpoint": "enabled", "HttpPutResponseHopLimit": 1}, CreditSpecification={"CpuCredits": "standard"}, UserData=user_data, TagSpecifications=tag_spec("instance", PROJECT + "-api") + tag_spec("volume", PROJECT + "-root"))["Instances"][0]
            break
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "InvalidParameterValue" and "instance profile" in str(exc).lower():
                time.sleep(5)
                continue
            raise
    else:
        raise RuntimeError("Instance profile did not become ready.")
    save(instance_id=instance["InstanceId"], ami=ami, instance_type="t3.micro", volume_gib=8, volume_type="gp3", deployed_commit=commit)
save(provisioning_complete=True, checked_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat())
