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
			return None
	if settings.google_creds:
		try:
			creds = service_account.Credentials.from_service_account_file(settings.google_creds)
			client = storage.Client(project=settings.google_creds.split("/")[-1] if settings.google_creds else None, credentials=creds)
			return client
		except Exception:
			return None
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

