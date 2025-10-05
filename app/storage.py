from pathlib import Path
import json
import tempfile
from typing import Optional
import logging

from .config import settings

logger = logging.getLogger(__name__)

UPLOADS = Path(settings.uploads_dir)
UPLOADS.mkdir(parents=True, exist_ok=True)

AUDIT_DIR = UPLOADS / "audit"
AUDIT_DIR.mkdir(exist_ok=True)

TEXT_DIR = UPLOADS / "ocr"
TEXT_DIR.mkdir(exist_ok=True)

PARSE_DIR = UPLOADS / "parsed"
PARSE_DIR.mkdir(exist_ok=True)


# GCS integration helpers. We lazily import google-cloud-storage to avoid hard dependency when not configured.
def _make_gcs_client():
    """Return a google.cloud.storage.Client or None if not configured/available."""
    try:
        from google.cloud import storage
        from google.oauth2 import service_account
    except Exception:
        return None

    # Prefer JSON string first, then file path
    if settings.google_creds_json:
        try:
            info = json.loads(settings.google_creds_json)
            creds = service_account.Credentials.from_service_account_info(info)
            client = storage.Client(project=info.get("project_id"), credentials=creds)
            return client
        except Exception:
            logger.exception("failed to create GCS client from google_creds_json")
            return None
    if settings.google_creds:
        try:
            creds = service_account.Credentials.from_service_account_file(settings.google_creds)
            client = storage.Client(project=settings.google_creds.split("/")[-1] if settings.google_creds else None, credentials=creds)
            return client
        except Exception:
            logger.exception("failed to create GCS client from google_creds file")
            return None
    return None


def gcs_upload_bytes(bucket_name: str, blob_name: str, data: bytes) -> bool:
    """Upload bytes to GCS. Returns True on success, False otherwise.
       Logs the uploaded gs:// path on success and exception details on failure.
    """
    client = _make_gcs_client()
    if not client:
        logger.info("gcs client not available; skipping upload to %s/%s", bucket_name, blob_name)
        return False
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(data)
        uploaded = f"gs://{bucket_name}/{blob_name}"
        logger.info("uploaded layout blob: %s", uploaded)
        return True
    except Exception:
        logger.exception("failed uploading layout blob to gs://%s/%s", bucket_name, blob_name)
        return False


def gcs_download_bytes(bucket_name: str, blob_name: str) -> Optional[bytes]:
    """Download bytes from GCS. Returns bytes or None if not available/failed."""
    client = _make_gcs_client()
    if not client:
        logger.info("gcs client not available; skipping download from %s/%s", bucket_name, blob_name)
        return None
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        data = blob.download_as_bytes()
        logger.info("downloaded layout blob: gs://%s/%s (bytes=%d)", bucket_name, blob_name, len(data) if data else 0)
        return data
    except Exception:
        logger.exception("failed downloading layout blob from gs://%s/%s", bucket_name, blob_name)
        return None


# new helper for quick debugging of whether GCS client creation succeeds
def gcs_available() -> bool:
    """Return True if a google cloud storage client can be created (credentials present/valid)."""
    client = _make_gcs_client()
    available = client is not None
    logger.info("gcs_available=%s", available)
    return available

# new helper: expose whether paid/premium requests are enabled in configuration
def premium_requests_enabled() -> bool:
    """Return True if paid/premium requests are enabled in settings (safe default False)."""
    enabled = getattr(settings, "premium_requests_enabled", False)
    logger.info("premium_requests_enabled=%s", enabled)
    return bool(enabled)

# new helper: return basic workspace/debug info to confirm context and environment
def workspace_debug_info() -> dict:
    """
    Return a small dict useful for debugging workspace context:
      - uploads_dir path
      - top-level files in uploads dir
      - gcs_available flag
      - premium_requests_enabled flag
    """
    try:
        files = [p.name for p in UPLOADS.iterdir() if p.exists()]
    except Exception:
        files = []
    info = {
        "uploads_dir": str(UPLOADS),
        "uploads_files": files,
        "gcs_available": gcs_available(),
        "premium_requests_enabled": premium_requests_enabled(),
    }
    logger.info("workspace_debug_info: %s", info)
    return info

# ...staged changes present; storage.workspace_debug_info() can help verify paths