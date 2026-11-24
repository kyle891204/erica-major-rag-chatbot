"""Run on EC2 through SSM; uses the instance role, never access keys."""
import json
import time
import boto3

REGION = "ap-northeast-2"
PROJECT = "erica-major-rag-chatbot"
session = boto3.Session(region_name=REGION)
identity = session.client("sts").get_caller_identity()
bucket = f"{PROJECT}-{identity['Account']}-{REGION}"
index = "handbook-titan-v2-1024"
runtime = session.client("bedrock-runtime")
s3 = session.client("s3")
vectors = session.client("s3vectors")
result = {"identity": identity["Arn"], "region": REGION}
body = b"Week 2 EC2 role storage verification. No personal data."
key = "tests/week2/ec2-role-storage.txt"
s3.put_object(Bucket=bucket, Key=key, Body=body)
assert s3.get_object(Bucket=bucket, Key=key)["Body"].read() == body
result["s3_write_read"] = True
response = runtime.invoke_model(modelId="amazon.titan-embed-text-v2:0", contentType="application/json", accept="application/json", body=json.dumps({"inputText": "ERICA infrastructure verification. This is not academic evidence.", "dimensions": 1024, "normalize": True}))
embedding = json.loads(response["body"].read())["embedding"]
assert len(embedding) == 1024
result["titan_dimensions"] = len(embedding)
vector_key = "test-only/week2/ec2-titan-1024"
vectors.put_vectors(vectorBucketName=bucket, indexName=index, vectors=[{"key": vector_key, "data": {"float32": embedding}, "metadata": {"dataset": "week2-ec2-test", "text": "EC2 role infrastructure test, excluded from handbook retrieval.", "item_name": "environment-test", "source_url": "https://github.com/kyle891204/erica-major-rag-chatbot", "revision_date": "2026-11-22"}}])
for attempt in range(12):
    matches = vectors.query_vectors(vectorBucketName=bucket, indexName=index, queryVector={"float32": embedding}, topK=1, filter={"dataset": {"$eq": "week2-ec2-test"}}, returnMetadata=True, returnDistance=True)["vectors"]
    if matches:
        break
    time.sleep(2)
assert matches and matches[0]["key"] == vector_key
result["vector_write_query"] = matches
nova = runtime.converse(modelId="apac.amazon.nova-micro-v1:0", messages=[{"role": "user", "content": [{"text": "Reply with OK only. Infrastructure test."}]}], inferenceConfig={"maxTokens": 8, "temperature": 0})
result["nova_profile"] = "apac.amazon.nova-micro-v1:0"
result["nova_response"] = nova["output"]["message"]["content"]
result["nova_usage"] = nova.get("usage")
print(json.dumps(result, ensure_ascii=False))
