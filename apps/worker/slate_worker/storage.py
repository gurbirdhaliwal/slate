"""MinIO payload access (standard S3 client — boto3, §7)."""

from __future__ import annotations

import json
from typing import Any

import boto3

from .config import Config


def make_s3_client(cfg: Config):
    return boto3.client(
        "s3",
        endpoint_url=cfg.minio_endpoint,
        aws_access_key_id=cfg.minio_access_key,
        aws_secret_access_key=cfg.minio_secret_key,
        region_name="us-east-1",  # ignored by MinIO
    )


def get_step_payload(s3, bucket: str, storage_key: str) -> dict[str, Any]:
    """Full step input/output payload: {org_id}/runs/{run_id}/{step_id}.json"""
    obj = s3.get_object(Bucket=bucket, Key=storage_key)
    return json.loads(obj["Body"].read())
