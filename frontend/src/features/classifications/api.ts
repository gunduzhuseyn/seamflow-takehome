import { getToken } from "@clerk/react";
import { queryOptions } from "@tanstack/react-query";

/**
 * Hand-written client for the classifications contract in docs/ai_docs/plan.md.
 * Same base URL and auth as src/lib/api-config.ts. Nothing outside this module
 * calls fetch. The next unit replaces it with the generated client.
 */

export type ClassificationStatus =
  "queued" | "processing" | "completed" | "failed";
export type ReviewStatus = "not_required" | "pending" | "reviewed";
export type Verdict = "hot_dog" | "not_hot_dog";

export type ClassificationOut = {
  id: string;
  created_at: string;
  updated_at: string;
  filename: string;
  submitted_by_name: string;
  status: ClassificationStatus;
  review_status: ReviewStatus;
  verdict: Verdict | null;
  confidence: number | null;
  observations: string | null;
  final_verdict: Verdict | null;
  reviewed_at: string | null;
  latency_ms: number | null;
  cost_usd: number;
  duplicate_of: string | null;
  thumbnail_url: string | null;
  error_code: string | null;
};

export type UploadCreate = {
  filename: string;
  content_type: string;
  size_bytes: number;
};

export type UploadOut = {
  key: string;
  upload_url: string;
  expires_in: number;
};

export type ClassificationCreate = {
  key: string;
  filename: string;
};

export type ClassificationList = {
  items: ClassificationOut[];
  total: number;
};

export type ClassificationListQuery = {
  limit?: number;
  status?: ClassificationStatus;
  review_status?: ReviewStatus;
  verdict?: Verdict;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readDetail(response: Response): Promise<string> {
  const fallback = `Request failed with status ${response.status}`;
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
    ) {
      return body.detail;
    }
  } catch {
    // Not JSON.
  }
  return fallback;
}

async function apiFetch<T>(
  path: string,
  init: { method: "GET" | "POST"; body?: unknown },
): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${import.meta.env.VITE_API_URL}${path}`, {
    method: init.method,
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  return (await response.json()) as T;
}

/** POST /uploads: ask for a presigned PUT URL. */
export function createUpload(body: UploadCreate): Promise<UploadOut> {
  return apiFetch<UploadOut>("/uploads", { method: "POST", body });
}

/** PUT the file bytes straight to object storage. No auth header. */
export async function putToUploadUrl(
  uploadUrl: string,
  file: File,
): Promise<void> {
  const response = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
  if (!response.ok) {
    throw new ApiError(response.status, "Upload to storage failed");
  }
}

/** POST /classifications: create the row and enqueue the job. */
export function createClassification(
  body: ClassificationCreate,
): Promise<ClassificationOut> {
  return apiFetch<ClassificationOut>("/classifications", {
    method: "POST",
    body,
  });
}

/** GET /classifications with optional filters. */
export function listClassifications(
  query: ClassificationListQuery = {},
): Promise<ClassificationList> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) {
      params.set(key, String(value));
    }
  }
  const search = params.size > 0 ? `?${params.toString()}` : "";
  return apiFetch<ClassificationList>(`/classifications${search}`, {
    method: "GET",
  });
}

export const classificationsQueryKey = (query: ClassificationListQuery = {}) =>
  ["classifications", query] as const;

export const listClassificationsOptions = (
  query: ClassificationListQuery = {},
) =>
  queryOptions({
    queryKey: classificationsQueryKey(query),
    queryFn: () => listClassifications(query),
  });
