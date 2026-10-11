import { http, HttpResponse } from "msw/http";

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

/** Default handlers: every dependency is healthy; /me needs the test token. */
export const handlers = [
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
