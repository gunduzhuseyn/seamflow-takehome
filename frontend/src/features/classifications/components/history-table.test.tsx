import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
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

/** Shows the router's search string, so tests read the URL state. */
function SearchProbe() {
  return <output data-testid="search">{useLocation().search}</output>;
}

const search = () => screen.getByTestId("search").textContent;

function renderHistory(initialSearch = "") {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/history${initialSearch}`]}>
      <HistoryTable />
      <SearchProbe />
    </MemoryRouter>,
  );
}

describe("HistoryTable", () => {
  beforeEach(() => {
    classificationStore.reset();
    anchorClick.mockClear();
    classificationStore.labels = ["hot dog", "pizza"];
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
      completedRow({
        filename: "slice.png",
        question_label: "pizza",
        verdict_labels: { match: "Pizza", no_match: "Not Pizza" },
        status: "failed",
        verdict: null,
        confidence: null,
        created_at: "2026-10-11T14:00:00Z",
      }),
    );
  });

  it("renders every column and puts the filters in the URL and the query", async () => {
    renderHistory();

    const burgerRow = (await screen.findByText("burger.png")).closest("tr")!;
    expect(burgerRow).toHaveTextContent("Ada Lovelace");
    expect(burgerRow).toHaveTextContent("hot dog");
    expect(
      screen.getByRole("columnheader", { name: "Question" }),
    ).toBeInTheDocument();
    expect(burgerRow).toHaveTextContent("Not Hot Dog");
    expect(burgerRow).toHaveTextContent("Hot Dog");
    expect(burgerRow).toHaveTextContent("61%");
    expect(burgerRow).toHaveTextContent("Completed");
    expect(burgerRow).toHaveTextContent("2026");
    expect(screen.getByText("hotdog.jpg")).toBeInTheDocument();
    expect(screen.getByText("Showing 1 to 3 of 3")).toBeInTheDocument();
    expect(lastListQuery().get("limit")).toBe("50");
    expect(lastListQuery().has("offset")).toBe(false);
    expect(lastListQuery().has("verdict")).toBe(false);
    const question = screen.getByLabelText("Question");
    await waitFor(() => {
      expect(within(question).getByText("pizza")).toBeInTheDocument();
    });
    expect(within(question).getByText("All")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Verdict"), {
      target: { value: "match" },
    });
    await waitFor(() => {
      expect(lastListQuery().get("verdict")).toBe("match");
    });
    expect(search()).toBe("?verdict=match");
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

    fireEvent.change(screen.getByLabelText("Verdict"), {
      target: { value: "" },
    });
    await waitFor(() => {
      expect(lastListQuery().has("verdict")).toBe(false);
    });
    fireEvent.change(screen.getByLabelText("Review status"), {
      target: { value: "" },
    });
    await waitFor(() => {
      expect(lastListQuery().has("review_status")).toBe(false);
    });
    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "failed" },
    });
    await waitFor(() => {
      expect(lastListQuery().get("status")).toBe("failed");
    });
    expect(search()).toBe("?status=failed");
    expect(await screen.findByText("slice.png")).toBeInTheDocument();
    expect(screen.queryByText("burger.png")).not.toBeInTheDocument();

    fireEvent.change(question, { target: { value: "pizza" } });
    await waitFor(() => {
      expect(lastListQuery().get("question_label")).toBe("pizza");
    });
    expect(search()).toBe("?status=failed&question_label=pizza");
    expect(screen.getByText("slice.png")).toBeInTheDocument();
  });

  it("restores the filters and the page from the URL", async () => {
    for (let i = 0; i < 60; i += 1) {
      classificationStore.rows.push(
        completedRow({
          filename: `extra-${i}.jpg`,
          question_label: "pizza",
          created_at: `2026-10-10T${String(i % 24).padStart(2, "0")}:${String(
            Math.floor(i / 24),
          ).padStart(2, "0")}:00Z`,
        }),
      );
    }

    renderHistory("?question_label=pizza&status=completed&offset=50");

    expect(
      await screen.findByText("Showing 51 to 60 of 60"),
    ).toBeInTheDocument();
    expect(lastListQuery().get("offset")).toBe("50");
    expect(lastListQuery().get("question_label")).toBe("pizza");
    expect(lastListQuery().get("status")).toBe("completed");
    expect(screen.getByLabelText("Status")).toHaveValue("completed");
    expect(screen.getByLabelText("Question")).toHaveValue("pizza");
  });

  it("pages with Next and Prev and resets the page when a filter changes", async () => {
    for (let i = 0; i < 60; i += 1) {
      classificationStore.rows.push(
        completedRow({
          filename: `extra-${i}.jpg`,
          created_at: `2026-10-10T${String(i % 24).padStart(2, "0")}:${String(
            Math.floor(i / 24),
          ).padStart(2, "0")}:00Z`,
        }),
      );
    }

    renderHistory();

    expect(
      await screen.findByText("Showing 1 to 50 of 63"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prev" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(lastListQuery().get("offset")).toBe("50");
    });
    expect(search()).toBe("?offset=50");
    expect(
      await screen.findByText("Showing 51 to 63 of 63"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(screen.queryByText("burger.png")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Verdict"), {
      target: { value: "no_match" },
    });

    await waitFor(() => {
      expect(lastListQuery().get("verdict")).toBe("no_match");
    });
    expect(lastListQuery().has("offset")).toBe(false);
    expect(search()).toBe("?verdict=no_match");
    expect(await screen.findByText("Showing 1 to 1 of 1")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Verdict"), {
      target: { value: "" },
    });
    await screen.findByText("Showing 1 to 50 of 63");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("Showing 51 to 63 of 63");
    fireEvent.click(screen.getByRole("button", { name: "Prev" }));

    await waitFor(() => {
      expect(lastListQuery().has("offset")).toBe(false);
    });
    expect(
      await screen.findByText("Showing 1 to 50 of 63"),
    ).toBeInTheDocument();
  });

  it("exports a CSV with every active filter, the auth header, and the server filename", async () => {
    renderHistory();
    await screen.findByText("burger.png");

    fireEvent.change(screen.getByLabelText("Verdict"), {
      target: { value: "no_match" },
    });
    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "completed" },
    });
    fireEvent.change(screen.getByLabelText("Question"), {
      target: { value: "hot dog" },
    });
    await screen.findByText("Showing 1 to 1 of 1");
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    await waitFor(() => {
      expect(anchorClick).toHaveBeenCalledTimes(1);
    });
    expect(classificationStore.exports).toHaveLength(1);
    const [request] = classificationStore.exports;
    const url = new URL(request.url);
    expect(url.pathname).toBe("/classifications/export.csv");
    expect(url.searchParams.get("verdict")).toBe("no_match");
    expect(url.searchParams.get("status")).toBe("completed");
    expect(url.searchParams.get("question_label")).toBe("hot dog");
    expect(url.searchParams.has("limit")).toBe(false);
    expect(url.searchParams.has("offset")).toBe(false);
    expect(request.authorization).toBe(`Bearer ${TEST_SESSION_TOKEN}`);
    const link = anchorClick.mock.contexts[0] as HTMLAnchorElement;
    expect(link.download).toBe("history-export.csv");
    expect(link.href).toBe("blob:test");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
