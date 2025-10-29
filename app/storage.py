from pathlib import Path
import json
import tempfile
from typing import Optional

from .config import settings

UPLOADS = Path(settings.uploads_dir)
UPLOADS.mkdir(parents=True, exist_ok=True)

AUDIT_DIR = UPLOADS / "audit"
AUDIT_DIR.mkdir(exist_ok=True)

TEXT_DIR = UPLOADS / "ocr"
TEXT_DIR.mkdir(exist_ok=True)

PARSE_DIR = UPLOADS / "parsed"
PARSE_DIR.mkdir(exist_ok=True)


# LEGACY: GCS (Google Cloud Storage) integration removed
# Kept as stubs for backward compatibility
def _make_gcs_client():
	"""DEPRECATED: GCS client creation. Returns None."""
	return None


def gcs_upload_bytes(bucket_name: str, blob_name: str, data: bytes) -> bool:
	"""Upload bytes to GCS. Returns True on success, False otherwise."""
	client = _make_gcs_client()
	if not client:
		return False
	try:
		bucket = client.bucket(bucket_name)
		blob = bucket.blob(blob_name)
		blob.upload_from_string(data)
		return True
	except Exception:
		return False


def gcs_download_bytes(bucket_name: str, blob_name: str) -> Optional[bytes]:
	"""Download bytes from GCS. Returns bytes or None if not available/failed."""
	client = _make_gcs_client()
	if not client:
		return None
	try:
		bucket = client.bucket(bucket_name)
		blob = bucket.blob(blob_name)
		return blob.download_as_bytes()
	except Exception:
		return None

