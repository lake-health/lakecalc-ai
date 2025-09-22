#!/usr/bin/env bash
# Quick smoke tests for GCS bucket: lakecalc-ocr-prod-layoutcache-jnl-2025
# Usage: ./scripts/gcs_smoke.sh [path-to-service-account-key]
set -euo pipefail
KEY_FILE=${1:-}
BUCKET=lakecalc-ocr-prod-layoutcache-jnl-2025
if [[ -n "$KEY_FILE" ]]; then
  echo "Activating service account: $KEY_FILE"
  gcloud auth activate-service-account --key-file="$KEY_FILE"
fi

echo "Listing bucket"
gsutil ls "gs://$BUCKET"

echo "Uploading test object"
echo '{"test":"ok"}' > /tmp/gcs_smoke_test.json
gsutil cp /tmp/gcs_smoke_test.json "gs://$BUCKET/ocr_texts/gcs_smoke_test.json"

echo "Reading back"
gsutil cat "gs://$BUCKET/ocr_texts/gcs_smoke_test.json"

echo "Cleaning up"
gsutil rm "gs://$BUCKET/ocr_texts/gcs_smoke_test.json"

echo "Done"
