"""
Storage Service — Unified file storage provider.
Supports Cloudflare R2 and AWS S3 object storage with automatic fallback to local disk storage.
"""
from __future__ import annotations
import os
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from core.config import settings

logger = logging.getLogger("service.storage")

LOCAL_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def is_s3_configured() -> bool:
    return bool(
        settings.effective_s3_bucket
        and settings.effective_s3_access_key
        and settings.effective_s3_secret_key
    )


def get_s3_client():
    if not is_s3_configured():
        return None
    try:
        import boto3
        from botocore.config import Config

        endpoint = settings.effective_s3_endpoint_url
        is_r2 = endpoint and "r2.cloudflarestorage.com" in endpoint

        session = boto3.session.Session()
        client = session.client(
            service_name="s3",
            aws_access_key_id=settings.effective_s3_access_key,
            aws_secret_access_key=settings.effective_s3_secret_key,
            region_name="auto" if is_r2 else (settings.AWS_REGION or "us-east-1"),
            endpoint_url=endpoint or None,
            config=Config(
                s3={"addressing_style": "path" if is_r2 else "virtual"},
                connect_timeout=10,
                read_timeout=15,
                retries={"max_attempts": 3},
            ),
        )
        return client
    except Exception as e:
        logger.warning(f"[Storage] Failed to initialize S3/R2 client: {e}")
        return None


def upload_bytes(
    data: bytes,
    original_filename: str,
    content_type: Optional[str] = None,
    subfolder: str = "uploads",
) -> Dict[str, Any]:
    """
    Upload file bytes to Cloudflare R2 / AWS S3 if configured.
    Falls back gracefully to local static storage on error or when S3 is unconfigured.
    """
    ext = os.path.splitext(original_filename)[1].lower()
    unique_key = f"{subfolder}/{uuid.uuid4().hex}{ext}"
    bucket = settings.effective_s3_bucket

    # Try Cloudflare R2 / S3 first
    if is_s3_configured() and bucket:
        try:
            s3 = get_s3_client()
            if s3:
                extra_args = {}
                if content_type:
                    extra_args["ContentType"] = content_type

                s3.put_object(
                    Bucket=bucket,
                    Key=unique_key,
                    Body=data,
                    **extra_args,
                )

                if settings.R2_PUBLIC_URL_PREFIX:
                    s3_url = f"{settings.R2_PUBLIC_URL_PREFIX.rstrip('/')}/{unique_key}"
                elif settings.effective_s3_endpoint_url:
                    s3_url = f"{settings.effective_s3_endpoint_url.rstrip('/')}/{bucket}/{unique_key}"
                else:
                    region = settings.AWS_REGION or "us-east-1"
                    s3_url = f"https://{bucket}.s3.{region}.amazonaws.com/{unique_key}"

                logger.info(f"[Storage] Successfully uploaded to R2/S3: {s3_url}")
                return {
                    "url": s3_url,
                    "storage": "r2" if (settings.effective_s3_endpoint_url and "r2.cloudflarestorage.com" in settings.effective_s3_endpoint_url) else "s3",
                    "filename": original_filename,
                    "size": len(data),
                    "content_type": content_type,
                    "key": unique_key,
                }
        except Exception as e:
            logger.error(f"[Storage] R2/S3 upload failed, falling back to local storage: {e}")

    # Fallback to local static storage
    target_dir = LOCAL_STATIC_DIR / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)
    local_filename = f"{uuid.uuid4().hex}{ext}"
    local_path = target_dir / local_filename

    with open(local_path, "wb") as f:
        f.write(data)

    local_url = f"/static/{subfolder}/{local_filename}"
    logger.info(f"[Storage] Saved locally: {local_url}")
    return {
        "url": local_url,
        "storage": "local",
        "filename": original_filename,
        "size": len(data),
        "content_type": content_type,
        "key": f"{subfolder}/{local_filename}",
    }


def test_storage_connection() -> Dict[str, Any]:
    """Test Cloudflare R2 / S3 connectivity and return diagnostic info."""
    configured = is_s3_configured()
    if not configured:
        return {
            "status": "unconfigured",
            "message": "S3/R2 credentials not set in environment",
            "storage": "local",
        }
    try:
        s3 = get_s3_client()
        if not s3:
            return {"status": "error", "message": "Failed to create S3 client"}
        
        bucket = settings.effective_s3_bucket
        s3.head_bucket(Bucket=bucket)
        
        # Test a lightweight write and delete
        probe_key = f"diagnostics/probe_{uuid.uuid4().hex[:8]}.txt"
        s3.put_object(
            Bucket=bucket,
            Key=probe_key,
            Body=b"ok",
            ContentType="text/plain",
        )
        s3.delete_object(Bucket=bucket, Key=probe_key)

        return {
            "status": "connected",
            "storage_type": "cloudflare_r2" if (settings.effective_s3_endpoint_url and "r2.cloudflarestorage.com" in settings.effective_s3_endpoint_url) else "aws_s3",
            "bucket": bucket,
            "endpoint": settings.effective_s3_endpoint_url,
            "public_url_prefix": settings.R2_PUBLIC_URL_PREFIX,
            "read_write_verified": True,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "bucket": settings.effective_s3_bucket,
        }
