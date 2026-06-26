#!/usr/bin/env python3
"""Block until the validation pod's MinIO and OpenSearch sidecars are ready.

The sidecars start in parallel with the validation container, so the backend
test suite -- which runs first -- can race ahead of them and trip the backend's
storage preflight. We also create the S3 bucket here: a fresh MinIO starts
empty, whereas the Ceph backend it replaced had the bucket pre-provisioned.

Connection settings are read from the same environment the backend uses, so
this stays in lockstep with the Jenkins job's container env.
"""

import json
import os
import sys
import time
import urllib.request

import boto3
from botocore.config import Config

# Overall budget for both services to come up. OpenSearch's JVM warm-up on a
# memory-capped container is the slow part; MinIO is ready in a second or two.
DEADLINE = time.time() + 180


def wait_for_minio() -> None:
    """Poll MinIO until it answers, then ensure the test bucket exists."""
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 1}),
    )

    while True:
        try:
            s3.list_buckets()
            break
        except Exception as exc:  # any connection error just means "not up yet"
            if time.time() > DEADLINE:
                sys.exit(f"MinIO not reachable at {os.environ['S3_ENDPOINT_URL']}: {exc}")
            time.sleep(2)

    bucket = os.environ["S3_BUCKET_NAME"]
    try:
        s3.create_bucket(Bucket=bucket)
        print(f"Created S3 bucket '{bucket}'")
    except (s3.exceptions.BucketAlreadyOwnedByYou, s3.exceptions.BucketAlreadyExists):
        print(f"S3 bucket '{bucket}' already exists")


def wait_for_opensearch() -> None:
    """Poll OpenSearch until the cluster reports yellow/green status.

    A plain 200 from _cluster/health can still report "red" during start-up, so
    gate on status the way DesignAssistant's suite runner does. The server-side
    wait_for_status holds each request until the status is met (or 5s elapses).
    """
    url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200").rstrip("/")
    health = f"{url}/_cluster/health?wait_for_status=yellow&timeout=5s"

    while True:
        try:
            with urllib.request.urlopen(health, timeout=10) as resp:
                if resp.status == 200 and json.loads(resp.read()).get("status") in ("yellow", "green"):
                    print(f"OpenSearch ready at {url}")
                    return
        except Exception as exc:
            if time.time() > DEADLINE:
                sys.exit(f"OpenSearch not reachable at {url}: {exc}")
        if time.time() > DEADLINE:
            sys.exit(f"OpenSearch did not reach yellow status at {url}")
        time.sleep(2)


if __name__ == "__main__":
    wait_for_minio()
    wait_for_opensearch()
    print("All sidecar services are ready")
