GCS Cheat Sheet for lakecalc-ocr-prod-layoutcache-jnl-2025
=====================================================

Replace PROJECT and BUCKET where noted. Your bucket: `lakecalc-ocr-prod-layoutcache-jnl-2025`

Authenticate (local test with service account key):

```bash
gcloud auth activate-service-account --key-file=lakecalc-sa-key.json
```

Basic bucket/object inspection

```bash
# List the bucket itself
gsutil ls gs://lakecalc-ocr-prod-layoutcache-jnl-2025

# List top-level objects (or folders)
gsutil ls gs://lakecalc-ocr-prod-layoutcache-jnl-2025/**

# List objects under the OCR layout cache folder
gsutil ls gs://lakecalc-ocr-prod-layoutcache-jnl-2025/ocr_layouts/

# List objects under the OCR text cache folder
gsutil ls gs://lakecalc-ocr-prod-layoutcache-jnl-2025/ocr_texts/
```

Upload / download / view a quick test object

```bash
# create a small test file and upload it to the ocr_texts folder
echo '{"test":"ok"}' > /tmp/test.json
gsutil cp /tmp/test.json gs://lakecalc-ocr-prod-layoutcache-jnl-2025/ocr_texts/test.json

# view the uploaded file
gsutil cat gs://lakecalc-ocr-prod-layoutcache-jnl-2025/ocr_texts/test.json

# download it back
gsutil cp gs://lakecalc-ocr-prod-layoutcache-jnl-2025/ocr_texts/test.json /tmp/test_from_gcs.json

# remove the test object when done
gsutil rm gs://lakecalc-ocr-prod-layoutcache-jnl-2025/ocr_texts/test.json
```

Inspect bucket IAM and metadata

```bash
# show bucket IAM policy
gsutil iam get gs://lakecalc-ocr-prod-layoutcache-jnl-2025

# show bucket metadata
gsutil ls -L -b gs://lakecalc-ocr-prod-layoutcache-jnl-2025
```

Project-level helpful commands

```bash
# list all buckets in your GCP project
gcloud storage buckets list --project=turnkey-energy-472923-c2

# confirm bucket exists (exit 0 if found)
gsutil ls gs://lakecalc-ocr-prod-layoutcache-jnl-2025 || echo "bucket not found or no access"
```

Tips

- The Railway env var `GCS_BUCKET_NAME` should be the plain bucket name (no `gs://`).
- If you run into permission errors, ensure the service account has `roles/storage.objectAdmin` on the bucket.
