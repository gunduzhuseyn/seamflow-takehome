import { http, HttpResponse } from "msw/http";

import type {
  ClassificationCreate,
  ClassificationOut,
  MetricsOut,
  ReviewCreate,
  UploadCreate,
  UploadOut,
} from "@/features/classifications/api";
import type { AuthMeResponse, HealthHealthResponse } from "@/lib/api";

export const apiUrl = (path: string): string =>
  `${import.meta.env.VITE_API_URL}${path}`;

/** The token the mocked Clerk `getToken` returns in tests. */
export const TEST_SESSION_TOKEN = "test-session-token";

export const ME: AuthMeResponse = {
  user: {
    id: "00000000-0000-4000-8000-000000000001",
    email: "ada@example.com",
  },
  org: {
    id: "00000000-0000-4000-8000-000000000002",
    name: "Demo",
    slug: "demo",
  },
  role: "admin",
  memberships: [
    {
      org: {
        id: "00000000-0000-4000-8000-000000000002",
        name: "Demo",
        slug: "demo",
      },
      role: "admin",
    },
    {
      org: {
        id: "00000000-0000-4000-8000-000000000003",
        name: "ada",
        slug: "ada-1a2b3c4d",
      },
      role: "member",
    },
  ],
};

/** Presigned URLs point here. Tests never reach a real bucket. */
export const STORAGE_URL = "http://storage.test/seamflow-takehome";

/** The dashboard numbers the metrics handler returns. */
export const METRICS: MetricsOut = {
  total: 42,
  completed: 40,
  hot_dog: 25,
  not_hot_dog: 15,
  pending_review: 3,
  reviewed: 8,
  overrides: 2,
  override_rate: 0.25,
  avg_latency_ms: 1480,
  total_cost_usd: 0.1312,
  deduplicated: 5,
};

/** A completed row for tests that seed the store. */
export function completedRow(
  overrides: Partial<ClassificationOut> = {},
): ClassificationOut {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    created_at: now,
    updated_at: now,
    filename: "hotdog.jpg",
    submitted_by_name: "Ada Lovelace",
    status: "completed",
    review_status: "not_required",
    verdict: "hot_dog",
    confidence: 0.93,
    observations: "A sausage in a split bun with mustard.",
    final_verdict: null,
    reviewed_at: null,
    latency_ms: 1234,
    cost_usd: 0.0031,
    duplicate_of: null,
    thumbnail_url: `${STORAGE_URL}/thumbs/test.webp?sig=test`,
    error_code: null,
    ...overrides,
  };
}

/** In-memory state behind the classification handlers. Reset per test. */
export const classificationStore = {
  uploads: [] as UploadOut[],
  puts: [] as { key: string; contentType: string | null; bytes: number }[],
  rows: [] as ClassificationOut[],
  /** How many list responses have included each queued row. */
  listPolls: new Map<string, number>(),
  /** Every list request URL, in order. */
  listRequests: [] as string[],
  /** Every review call: row id and body. */
  reviews: [] as { id: string; body: ReviewCreate }[],
  /** Every CSV export request: URL and the Authorization header. */
  exports: [] as { url: string; authorization: string | null }[],
  reset() {
    this.uploads = [];
    this.puts = [];
    this.rows = [];
    this.listPolls.clear();
    this.listRequests = [];
    this.reviews = [];
    this.exports = [];
  },
};

type ListFilter = Pick<
  ClassificationOut,
  "status" | "review_status" | "verdict"
>;
const LIST_FILTERS: (keyof ListFilter)[] = [
  "status",
  "review_status",
  "verdict",
];

/** Applies the contract's list filters from the query string. */
function filterRows(url: URL): ClassificationOut[] {
  return classificationStore.rows.filter((row) =>
    LIST_FILTERS.every((name) => {
      const wanted = url.searchParams.get(name);
      return wanted === null || row[name] === wanted;
    }),
  );
}

function authorized(request: Request): boolean {
  return (
    request.headers.get("Authorization") === `Bearer ${TEST_SESSION_TOKEN}`
  );
}

const unauthorized = () =>
  HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });

/** Flips a row to completed. Verdict follows the filename. */
function complete(row: ClassificationOut): void {
  const hotDog = /hot.?dog/i.test(row.filename);
  row.status = "completed";
  row.verdict = hotDog ? "hot_dog" : "not_hot_dog";
  row.confidence = hotDog ? 0.93 : 0.61;
  row.review_status = hotDog ? "not_required" : "pending";
  row.observations = hotDog
    ? "A sausage in a split bun with mustard."
    : "A round patty between two buns.";
  row.latency_ms = 1234;
  row.cost_usd = 0.0031;
  row.thumbnail_url = `${STORAGE_URL}/thumbs/${row.id}.webp?sig=test`;
  row.updated_at = new Date().toISOString();
}

const classificationHandlers = [
  http.post(apiUrl("/uploads"), async ({ request }) => {
    if (!authorized(request)) {
      return unauthorized();
    }
    const body = (await request.json()) as UploadCreate;
    const key = `incoming/org/${crypto.randomUUID()}`;
    const upload: UploadOut = {
      key,
      upload_url: `${STORAGE_URL}/${key}?sig=test&type=${body.content_type}`,
      expires_in: 600,
    };
    classificationStore.uploads.push(upload);
    return HttpResponse.json(upload, { status: 201 });
  }),

  http.put(`${STORAGE_URL}/incoming/*`, async ({ request }) => {
    const url = new URL(request.url);
    const key = url.pathname.replace("/seamflow-takehome/", "");
    const bytes = (await request.arrayBuffer()).byteLength;
    classificationStore.puts.push({
      key,
      contentType: request.headers.get("Content-Type"),
      bytes,
    });
    return new HttpResponse(null, { status: 200 });
  }),

  http.post(apiUrl("/classifications"), async ({ request }) => {
    if (!authorized(request)) {
      return unauthorized();
    }
    const body = (await request.json()) as ClassificationCreate;
    const now = new Date().toISOString();
    const row: ClassificationOut = {
      id: crypto.randomUUID(),
      created_at: now,
      updated_at: now,
      filename: body.filename,
      submitted_by_name: "Ada Lovelace",
      status: "queued",
      review_status: "not_required",
      verdict: null,
      confidence: null,
      observations: null,
      final_verdict: null,
      reviewed_at: null,
      latency_ms: null,
      cost_usd: 0,
      duplicate_of: null,
      thumbnail_url: null,
      error_code: null,
    };
    classificationStore.rows.push(row);
    return HttpResponse.json(row, { status: 202 });
  }),

  http.get(apiUrl("/classifications"), ({ request }) => {
    if (!authorized(request)) {
      return unauthorized();
    }
    classificationStore.listRequests.push(request.url);
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? 50);
    // A queued row completes on the second list poll that includes it.
    const { listPolls } = classificationStore;
    for (const row of classificationStore.rows) {
      if (row.status !== "queued") {
        continue;
      }
      const polls = (listPolls.get(row.id) ?? 0) + 1;
      listPolls.set(row.id, polls);
      if (polls >= 2) {
        complete(row);
      }
    }
    const matching = filterRows(url);
    const items = [...matching]
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, limit);
    return HttpResponse.json({ items, total: matching.length });
  }),

  http.post(
    apiUrl("/classifications/:id/review"),
    async ({ request, params }) => {
      if (!authorized(request)) {
        return unauthorized();
      }
      const body = (await request.json()) as ReviewCreate;
      const id = String(params.id);
      classificationStore.reviews.push({ id, body });
      const row = classificationStore.rows.find((r) => r.id === id);
      if (!row) {
        return HttpResponse.json({ detail: "Not found" }, { status: 404 });
      }
      if (row.status !== "completed") {
        return HttpResponse.json({ detail: "Not completed" }, { status: 409 });
      }
      row.final_verdict = body.final_verdict;
      row.review_status = "reviewed";
      row.reviewed_at = new Date().toISOString();
      row.updated_at = row.reviewed_at;
      return HttpResponse.json(row);
    },
  ),

  http.get(apiUrl("/classifications/metrics"), ({ request }) => {
    if (!authorized(request)) {
      return unauthorized();
    }
    return HttpResponse.json(METRICS);
  }),

  http.get(apiUrl("/classifications/export.csv"), ({ request }) => {
    if (!authorized(request)) {
      return unauthorized();
    }
    classificationStore.exports.push({
      url: request.url,
      authorization: request.headers.get("Authorization"),
    });
    const lines = filterRows(new URL(request.url)).map((row) =>
      [row.id, row.created_at, row.filename, row.verdict ?? ""].join(","),
    );
    return new HttpResponse(
      ["id,created_at,filename,verdict", ...lines].join("\n"),
      { headers: { "Content-Type": "text/csv" } },
    );
  }),
];

/** Default handlers: every dependency is healthy; /me needs the test token. */
export const handlers = [
  ...classificationHandlers,
  http.get<never, never, HealthHealthResponse>(apiUrl("/health"), () =>
    HttpResponse.json({ status: "ok", db: "ok", redis: "ok" }),
  ),
  http.get(apiUrl("/me"), ({ request }) => {
    if (
      request.headers.get("Authorization") !== `Bearer ${TEST_SESSION_TOKEN}`
    ) {
      return HttpResponse.json(
        { detail: "Not authenticated" },
        { status: 401 },
      );
    }
    return HttpResponse.json(ME);
  }),
];
