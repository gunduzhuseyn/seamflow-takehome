import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { describe, expect, it } from "vitest";

import type { HealthHealthError } from "@/lib/api";
import { apiUrl } from "@/testing/handlers";
import { renderWithProviders } from "@/testing/render";
import { server } from "@/testing/server";

import { HealthStatus } from "./health-status";

describe("HealthStatus", () => {
  it("renders status, db and redis when the API answers ok", async () => {
    renderWithProviders(<HealthStatus />);

    expect(
      await screen.findByRole("row", { name: "Status ok" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("row", { name: "Database ok" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("row", { name: "Redis ok" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders the error state on 503", async () => {
    server.use(
      http.get<never, never, HealthHealthError>(apiUrl("/health"), () =>
        HttpResponse.json(
          { status: "error", db: "error", redis: "ok" },
          { status: 503 },
        ),
      ),
    );

    renderWithProviders(<HealthStatus />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not load");
    expect(
      within(alert).getByRole("button", { name: "Retry" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("row")).not.toBeInTheDocument();
  });
});
