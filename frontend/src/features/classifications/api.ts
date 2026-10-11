import { getToken } from "@clerk/react";
import { mutationOptions, queryOptions } from "@tanstack/react-query";

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

export type ReviewCreate = {
  final_verdict: Verdict;
};

export type MetricsOut = {
  total: number;
  completed: number;
  hot_dog: number;
  not_hot_dog: number;
  pending_review: number;
  reviewed: number;
  overrides: number;
  /** Fraction 0 to 1. */
  override_rate: number;
  avg_latency_ms: number | null;
  total_cost_usd: number;
  deduplicated: number;
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

async function apiRequest(
  path: string,
  init: { method: "GET" | "POST"; body?: unknown; accept?: string },
): Promise<Response> {
  const token = await getToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (init.accept !== undefined) {
    headers.Accept = init.accept;
  }
  const response = await fetch(`${import.meta.env.VITE_API_URL}${path}`, {
    method: init.method,
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  return response;
}

async function apiFetch<T>(
  path: string,
  init: { method: "GET" | "POST"; body?: unknown },
): Promise<T> {
  const response = await apiRequest(path, init);
  return (await response.json()) as T;
}

function toSearch(query: ClassificationListQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) {
      params.set(key, String(value));
    }
  }
  return params.size > 0 ? `?${params.toString()}` : "";
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
  return apiFetch<ClassificationList>(`/classifications${toSearch(query)}`, {
    method: "GET",
  });
}

/** POST /classifications/{id}/review: confirm or override a verdict. */
export function reviewClassification(
  id: string,
  body: ReviewCreate,
): Promise<ClassificationOut> {
  return apiFetch<ClassificationOut>(`/classifications/${id}/review`, {
    method: "POST",
    body,
  });
}

/** GET /classifications/metrics: the dashboard numbers. */
export function getMetrics(): Promise<MetricsOut> {
  return apiFetch<MetricsOut>("/classifications/metrics", { method: "GET" });
}

/** GET /classifications/export.csv with the same filters as the list. */
export async function exportClassificationsCsv(
  query: ClassificationListQuery = {},
): Promise<Blob> {
  const response = await apiRequest(
    `/classifications/export.csv${toSearch(query)}`,
    { method: "GET", accept: "text/csv" },
  );
  return response.blob();
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

export const metricsQueryKey = ["classification-metrics"] as const;

export const metricsOptions = () =>
  queryOptions({
    queryKey: metricsQueryKey,
    queryFn: getMetrics,
  });

export const reviewClassificationMutationOptions = () =>
  mutationOptions({
    mutationKey: ["classifications", "review"],
    mutationFn: ({ id, ...body }: ReviewCreate & { id: string }) =>
      reviewClassification(id, body),
  });
