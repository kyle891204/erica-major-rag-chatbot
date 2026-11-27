"""Build a local handbook corpus and optionally publish a version to existing AWS resources."""

import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from app.handbook import DATASET, HANDBOOK, build_corpus
from app.rag import INDEX, aws_client, embed, embedding_text


def create_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def read_handbook(path):
    if path:
        return path.read_text(encoding="utf-8")
    with urlopen(HANDBOOK, timeout=45) as response:
        return response.read().decode("utf-8")


def upload(bucket, corpus, originals):
    version = corpus["version"]
    prefix = f"handbook/{version}"
    s3 = aws_client("s3")
    vectors = aws_client("s3vectors")
    bedrock = aws_client("bedrock-runtime")
    s3.put_object(Bucket=bucket, Key=f"{prefix}/source.json", Body=create_json(originals), ContentType="application/json")
    s3.put_object(Bucket=bucket, Key=f"{prefix}/chunks.json", Body=create_json(corpus), ContentType="application/json")

    pending = []
    for chunk in corpus["chunks"]:
        metadata = {key: value for key, value in chunk.items() if key != "key"}
        metadata.update(dataset=DATASET, version=version)
        pending.append({
            "key": f"{prefix}/{chunk['key']}",
            "data": {"float32": embed(bedrock, embedding_text(chunk))},
            "metadata": metadata,
        })
        if len(pending) == 50:
            vectors.put_vectors(vectorBucketName=bucket, indexName=INDEX, vectors=pending)
            pending.clear()
    if pending:
        vectors.put_vectors(vectorBucketName=bucket, indexName=INDEX, vectors=pending)
    s3.put_object(
        Bucket=bucket, Key=f"{prefix}/ready.json",
        Body=create_json({"version": version, "count": len(corpus["chunks"]), "revision_date": corpus["revision_date"]}),
        ContentType="application/json",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, help="편람 HTML 파일 경로. 생략하면 최신 공개 페이지를 다운로드합니다.")
    parser.add_argument("--output", type=Path, default=Path("reports/private/handbook.json"))
    parser.add_argument("--bucket", help="지정하면 이 S3 버킷 및 같은 이름의 S3 Vectors 버킷에 적재합니다.")
    args = parser.parse_args()
    corpus, originals = build_corpus(read_handbook(args.html))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(create_json(corpus))
    if args.bucket:
        upload(args.bucket, corpus, originals)
    print(json.dumps({"version": corpus["version"], "revision_date": corpus["revision_date"], "chunks": len(corpus["chunks"]), "uploaded": bool(args.bucket)}))


if __name__ == "__main__":
    main()
