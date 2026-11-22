"""Collect actual AWS responses for the report; contains no credential output."""
import datetime
import json
from pathlib import Path
import zipfile
import boto3

state = json.loads((Path.home() / "erica-week2-state.json").read_text())
session = boto3.Session(region_name=state["region"])
ec2, s3, iam, vectors, logs, ssm = [session.client(x) for x in ["ec2", "s3", "iam", "s3vectors", "logs", "ssm"]]
evidence = {"collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "state": state}
instance = ec2.describe_instances(InstanceIds=[state["instance_id"]])["Reservations"][0]["Instances"][0]
evidence["ec2"] = instance
evidence["volumes"] = ec2.describe_volumes(VolumeIds=[x["Ebs"]["VolumeId"] for x in instance["BlockDeviceMappings"]])["Volumes"]
evidence["security_group"] = ec2.describe_security_groups(GroupIds=[state["security_group_id"]])["SecurityGroups"][0]
evidence["route_table"] = ec2.describe_route_tables(RouteTableIds=[state["route_table_id"]])["RouteTables"][0]
evidence["s3_public_access"] = s3.get_public_access_block(Bucket=state["bucket"])["PublicAccessBlockConfiguration"]
evidence["s3_encryption"] = s3.get_bucket_encryption(Bucket=state["bucket"])["ServerSideEncryptionConfiguration"]
evidence["s3_test_objects"] = s3.list_objects_v2(Bucket=state["bucket"], Prefix="tests/week2/").get("Contents", [])
evidence["vector_index"] = vectors.get_index(vectorBucketName=state["bucket"], indexName=state["index"])["index"]
evidence["test_vector_keys"] = vectors.list_vectors(vectorBucketName=state["bucket"], indexName=state["index"], returnData=False, returnMetadata=True)["vectors"]
evidence["runtime_role"] = iam.get_role(RoleName=state["ec2_role"])["Role"]
evidence["runtime_policy"] = iam.get_role_policy(RoleName=state["ec2_role"], PolicyName="ProjectRuntime")["PolicyDocument"]
evidence["managed_policies"] = iam.list_attached_role_policies(RoleName=state["ec2_role"])["AttachedPolicies"]
evidence["cloudwatch_groups"] = logs.describe_log_groups(logGroupNamePrefix=state["log_group"])["logGroups"]
evidence["cloudwatch_events"] = [e for page in logs.get_paginator("filter_log_events").paginate(logGroupName=state["log_group"], PaginationConfig={"MaxItems": 50}) for e in page.get("events", [])]
evidence["ssm_checks"] = ssm.list_command_invocations(InstanceId=state["instance_id"], Details=True, MaxResults=20)["CommandInvocations"]
for filename in ["erica-arm-price.json", "erica-ebs-price.json"]:
    p = Path("/tmp") / filename
    if p.exists():
        evidence[filename] = json.loads(p.read_text())
out = Path.home() / "erica-week2-evidence.zip"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("aws-evidence.json", json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
print(json.dumps({"saved": str(out), "instance": state["instance_id"], "api_log_events": len(evidence["cloudwatch_events"]), "test_vectors": len(evidence["test_vector_keys"])}))
