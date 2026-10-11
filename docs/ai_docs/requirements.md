# Requirements: SeeFood Enterprise

Written 2026-10-11 16:10, revised 16:28 after the design discussion. Task received 16:00. Deadline 19:00.

## The task in our words

Build and deploy a web app that takes an image and answers "Hot Dog" or "Not Hot Dog".
The app must look and behave like a serious enterprise product.
The reviewer opens a live URL, signs in, uploads an image, and reads the verdict.
Grading: product thinking, technical execution, shipping under constraints, tool use.

## Users

- Operator: a team member who submits images and reads verdicts.
- Reviewer: a team member who confirms or overrides uncertain verdicts.
- Both roles are the same user type. Any member of an organization can review.

## Main flow

1. Visitor opens the root URL and sees the Clerk sign-in page.
2. User signs in with the seed login from the email, or signs up.
3. The app opens on the Classify page: a drop zone and the organization's recent results.
4. User drops one or more images. For each image the browser asks the API for a presigned
   upload URL, uploads the file straight to object storage, then creates a classification.
5. Each result card appears at once in status queued, then processing, then shows the verdict,
   a confidence bar, what the model saw, latency, and cost. The page polls while rows are in flight.
6. A result below the confidence threshold also shows a "Pending review" badge.
7. User opens the Review queue, confirms or overrides each pending verdict.
8. User opens History, filters by verdict or status, exports CSV.
9. User opens Dashboard: totals, hot dog ratio, average latency, spend, override rate.

## Architecture

- Upload: browser to Cloudflare R2 with a presigned PUT. Local dev uses RustFS through the same S3 client.
  The API never carries image bytes. Keys are server generated under `incoming/{org_id}/{uuid}`.
- Processing: the API creates the row in status queued and enqueues an arq job. The worker downloads
  the object, checks size and magic bytes, hashes it, deduplicates, resizes, calls the vision model, and writes the result.
- Delivery: the browser polls the list every 2 seconds while any row is queued or processing.
  Thumbnails are presigned GET URLs with a one hour expiry.
- Fallback: if the presigned upload is not working end to end by 17:30, the API accepts multipart
  and writes to R2 itself. The service layer takes a storage key, so only the ingress changes.

## Data model

Kept from the template: users, organizations, memberships, llm_calls.

Kept from the template: jobs.

New table `classifications`, scoped by organization_id:

| Column | Type | Note |
| --- | --- | --- |
| id | uuid | primary key |
| organization_id | uuid | tenancy scope |
| submitted_by | uuid | user id |
| created_at, updated_at | timestamptz | |
| filename | text | as uploaded, display only |
| original_key | text | object key in storage |
| original_mime | text | set by the worker from magic bytes |
| original_bytes | int | set by the worker from HEAD |
| image_sha256 | text, null | set by the worker |
| thumbnail_key | text, null | 320 px WebP in storage |
| status | enum | queued, processing, completed, failed |
| review_status | enum | not_required, pending, reviewed |
| verdict | enum, null | hot_dog, not_hot_dog |
| confidence | numeric(4,3), null | 0 to 1 |
| observations | text, null | under 300 chars |
| final_verdict | enum, null | set by a reviewer |
| reviewed_by, reviewed_at | null | |
| latency_ms | int, null | worker measured, download to result |
| cost_usd | numeric(10,6) | 0 when deduplicated |
| llm_call_id | uuid, null | |
| job_id | uuid, null | |
| duplicate_of | uuid, null | earlier row with the same hash |
| error_code | text, null | set when status is failed |

Indexes: (organization_id, created_at desc), (organization_id, image_sha256), (organization_id, review_status).

Rules:

- confidence >= 0.85 gives review_status not_required. Below gives pending.
- A review sets final_verdict, reviewed_by, reviewed_at, review_status reviewed.
- Override means final_verdict differs from verdict. The dashboard reports the override rate.
- "Was this correct?" on any card is the same review call.
- Same hash in the same organization copies the earlier verdict with cost 0 and duplicate_of set. No model call.
- The job is idempotent. It re-reads the row and skips the model call when a verdict exists.

## LLM feature

- Provider: Anthropic vision through the template's provider interface. Fake provider in tests.
- Input: one image as a base64 content block plus a prompt file. Image is downscaled before the call.
- Output tool schema:

```json
{
  "verdict": "hot_dog | not_hot_dog",
  "confidence": 0.0,
  "observations": "string, max 300 chars"
}
```

- Output is validated with Pydantic. A schema failure retries once, then fails the request.
- Each call writes an llm_calls row with tokens and cost. Per-user rate limit from the template.

### Failure states

| Case | Where | UI |
| --- | --- | --- |
| Wrong type or over 10 MB, declared | 400 from POST /uploads | Inline error on the drop zone, nothing stored |
| Wrong type or over 10 MB, actual | Worker marks failed with error_code | Card shows "Rejected: not an image" |
| Rate limit hit | 429 from POST /classifications | Toast with the retry time |
| Provider error or timeout | Job retries twice, then failed with error_code | Card shows "Analysis failed" and a retry button |
| Low confidence | 200 | Verdict shown, "Pending review" badge, row in the queue |

## Cut list

| Cut | Reason |
| --- | --- |
| Public landing page | User decision. Root goes straight to sign-in. |
| Classify by URL | SSRF guards cost more than the feature shows. |
| Shareable public result page | Second unauthenticated route, no grading value. |
| API keys and public API | Second auth path, 30+ minutes. Mentioned in README as next step. |
| Client side hash before upload | Would skip the upload for duplicates. Server recomputes anyway. Next step. |
| SSE per job | Polling the list while rows are in flight is simpler and good enough at this scale. |
| HEIC | Browsers convert on upload in most cases. Rejected with a clear message otherwise. |

## Grading map

| Criterion | Visible evidence |
| --- | --- |
| Product thinking | Review queue, confidence, deduplication at zero cost, override rate, batch drop, live status per card, enterprise copy and empty states |
| Technical execution | Direct-to-storage upload, idempotent worker job, tenancy tests, fake provider and fake storage in tests, validated model output, migrations, generated client, structured logs |
| Shipping under constraints | Repo built module by module in the template's order, live by 17:30, one unit per branch, cut list with reasons, README with tradeoffs |
| Tool use | README disclosure, conductor plus parallel sessions, Codex reviews, docs/ai_docs kept in the repo |

## Open questions

- Confidence threshold value. Start at 0.85, tune after the first ten real images.
- Seed images: cut at 18:20. The demo starts with a live batch drop.
- Configurability shipped as a per-request question label (default hot dog), validated and placed in the prompt as data. Org settings page and rerun of past images were cut for time.
- Cut order if behind at 18:00: CSV export, then dashboard trimmed to four tiles, then batch drop. Feature stop 18:35.
