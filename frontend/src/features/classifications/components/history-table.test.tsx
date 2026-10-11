import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  classificationStore,
  completedRow,
  TEST_SESSION_TOKEN,
} from "@/testing/handlers";
import { renderWithProviders } from "@/testing/render";

import { HistoryTable } from "./history-table";

vi.mock("@clerk/react", () => ({
  getToken: vi.fn(() => Promise.resolve(TEST_SESSION_TOKEN)),
}));

// jsdom has no object URLs and does not navigate on download clicks.
const revokeObjectURL = vi.fn();
Object.assign(URL, {
  createObjectURL: vi.fn(() => "blob:test"),
  revokeObjectURL,
});
const anchorClick = vi
  .spyOn(HTMLAnchorElement.prototype, "click")
  .mockImplementation(() => undefined);

const lastListQuery = () =>
  new URL(classificationStore.listRequests.at(-1)!).searchParams;

describe("HistoryTable", () => {
  beforeEach(() => {
    classificationStore.reset();
    anchorClick.mockClear();
    classificationStore.rows.push(
      completedRow({ created_at: "2026-10-11T15:00:00Z" }),
      completedRow({
        filename: "burger.png",
        verdict: "no_match",
        final_verdict: "match",
        confidence: 0.61,
        review_status: "reviewed",
        created_at: "2026-10-11T16:00:00Z",
      }),
    );
  });

  it("renders every column and sends the filters with the list query", async () => {
    renderWithProviders(<HistoryTable />);

    const burgerRow = (await screen.findByText("burger.png")).closest("tr")!;
    expect(burgerRow).toHaveTextContent("Ada Lovelace");
    expect(burgerRow).toHaveTextContent("Not Hot Dog");
    expect(burgerRow).toHaveTextContent("Hot Dog");
    expect(burgerRow).toHaveTextContent("61%");
    expect(burgerRow).toHaveTextContent("Completed");
    expect(burgerRow).toHaveTextContent("2026");
    expect(screen.getByText("hotdog.jpg")).toBeInTheDocument();
    expect(lastListQuery().get("limit")).toBe("50");
    expect(lastListQuery().has("verdict")).toBe(false);

    fireEvent.change(screen.getByLabelText("Verdict"), {
      target: { value: "match" },
    });
    await waitFor(() => {
      expect(lastListQuery().get("verdict")).toBe("match");
    });
    await waitFor(() => {
      expect(screen.queryByText("burger.png")).not.toBeInTheDocument();
    });
    expect(screen.getByText("hotdog.jpg")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Review status"), {
      target: { value: "reviewed" },
    });
    await waitFor(() => {
      expect(lastListQuery().get("review_status")).toBe("reviewed");
    });
    expect(lastListQuery().get("verdict")).toBe("match");
    expect(
      await screen.findByText("No classifications match these filters."),
    ).toBeInTheDocument();
  });

  it("exports a CSV with the current filters and the auth header", async () => {
    renderWithProviders(<HistoryTable />);
    await screen.findByText("burger.png");

    fireEvent.change(screen.getByLabelText("Verdict"), {
      target: { value: "no_match" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    await waitFor(() => {
      expect(anchorClick).toHaveBeenCalledTimes(1);
    });
    expect(classificationStore.exports).toHaveLength(1);
    const [request] = classificationStore.exports;
    const url = new URL(request.url);
    expect(url.pathname).toBe("/classifications/export.csv");
    expect(url.searchParams.get("verdict")).toBe("no_match");
    expect(url.searchParams.has("limit")).toBe(false);
    expect(request.authorization).toBe(`Bearer ${TEST_SESSION_TOKEN}`);
    const link = anchorClick.mock.contexts[0] as HTMLAnchorElement;
    expect(link.download).toBe("classifications.csv");
    expect(link.href).toBe("blob:test");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
