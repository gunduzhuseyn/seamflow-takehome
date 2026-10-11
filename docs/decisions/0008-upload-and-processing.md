# 0008: Upload and processing

Date: 2026-10-11. Status: accepted.

## Context

Users upload images and read a verdict. The whole product ships in a 3 hour window.
Image bytes must not slow the API. The vision model call takes seconds and can fail.
The result must appear in the browser without a manual refresh.

## Decision

- The browser asks the API for a presigned PUT URL and uploads straight to Cloudflare R2.
  Local development uses RustFS through the same S3 client.
- The API creates the classification row in status queued and enqueues an arq job.
  The worker downloads the object, validates it, calls the vision model, and writes the result.
- The browser polls the list every 2 seconds while any row is queued or processing.

## Consequences

- The API never carries image bytes. Upload size does not affect API latency.
- The job is idempotent. It re-reads the row and skips the model call when a verdict exists.
- Polling replaces server-sent events. It is simpler and good enough at this scale.
- Fallback: if presigning fails end to end, the API accepts multipart and writes to R2 itself.
  The service layer takes a storage key, so only the ingress changes.
