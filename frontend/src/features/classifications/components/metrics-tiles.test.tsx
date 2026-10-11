import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TEST_SESSION_TOKEN } from "@/testing/handlers";
import { renderWithProviders } from "@/testing/render";

import { MetricsTiles } from "./metrics-tiles";

vi.mock("@clerk/react", () => ({
  getToken: vi.fn(() => Promise.resolve(TEST_SESSION_TOKEN)),
}));

describe("MetricsTiles", () => {
  it("renders one tile per metric with formatted values", async () => {
    renderWithProviders(<MetricsTiles />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
    expect(await screen.findByText("Total classified")).toBeInTheDocument();
    const tiles = screen.getAllByRole("listitem");
    expect(tiles.map((tile) => tile.textContent)).toEqual([
      "Total classified42",
      "Match ratio63%",
      "Pending review3",
      "Override rate25%",
      "Average latency1,480 ms",
      "Total spend$0.1312",
      "Deduplicated5",
    ]);
  });
});
