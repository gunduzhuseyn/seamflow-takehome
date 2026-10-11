import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  classificationStore,
  completedRow,
  TEST_SESSION_TOKEN,
} from "@/testing/handlers";
import { renderWithProviders } from "@/testing/render";

import { ReviewQueue } from "./review-queue";

vi.mock("@clerk/react", () => ({
  getToken: vi.fn(() => Promise.resolve(TEST_SESSION_TOKEN)),
}));

describe("ReviewQueue", () => {
  beforeEach(() => {
    classificationStore.reset();
  });

  it("shows the empty state when nothing is pending", async () => {
    classificationStore.rows.push(completedRow());

    renderWithProviders(<ReviewQueue />);

    expect(
      await screen.findByText("Nothing waiting for review"),
    ).toBeInTheDocument();
    expect(classificationStore.listRequests[0]).toContain(
      "review_status=pending",
    );
  });

  it("confirms or overrides a row and removes it from the table", async () => {
    const burger = completedRow({
      filename: "burger.png",
      verdict: "no_match",
      confidence: 0.61,
      review_status: "pending",
      observations: "A round patty between two buns.",
    });
    const cornDog = completedRow({
      filename: "corndog.jpg",
      verdict: "no_match",
      confidence: 0.55,
      review_status: "pending",
    });
    classificationStore.rows.push(completedRow(), burger, cornDog);

    renderWithProviders(<ReviewQueue />);

    const burgerRow = (await screen.findByText("burger.png")).closest("tr");
    expect(burgerRow).not.toBeNull();
    expect(within(burgerRow!).getByText("Not Hot Dog")).toBeInTheDocument();
    expect(within(burgerRow!).getByText("61%")).toBeInTheDocument();
    expect(within(burgerRow!).getByText("Ada Lovelace")).toBeInTheDocument();
    expect(
      within(burgerRow!).getByText("A round patty between two buns."),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Confirm" })).toHaveLength(2);
    expect(screen.queryByText("hotdog.jpg")).not.toBeInTheDocument();

    fireEvent.click(
      within(burgerRow!).getByRole("button", { name: "Confirm" }),
    );
    await waitFor(() => {
      expect(screen.queryByText("burger.png")).not.toBeInTheDocument();
    });
    expect(classificationStore.reviews).toEqual([
      { id: burger.id, body: { final_verdict: "no_match" } },
    ]);

    const cornDogRow = screen.getByText("corndog.jpg").closest("tr")!;
    fireEvent.click(
      within(cornDogRow).getByRole("button", { name: "Override" }),
    );
    expect(
      await screen.findByText("Nothing waiting for review"),
    ).toBeInTheDocument();
    expect(classificationStore.reviews[1]).toEqual({
      id: cornDog.id,
      body: { final_verdict: "match" },
    });
    // The list refetched after each review.
    expect(classificationStore.listRequests.length).toBeGreaterThanOrEqual(3);
  });
});
