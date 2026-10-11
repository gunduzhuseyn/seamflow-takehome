import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TEST_SESSION_TOKEN } from "@/testing/handlers";
import { renderWithProviders } from "@/testing/render";

import { MeProfile } from "./me-profile";

vi.mock("@clerk/react", () => ({
  getToken: vi.fn(() => Promise.resolve(TEST_SESSION_TOKEN)),
}));

describe("MeProfile", () => {
  it("sends the session token and renders user, org, role, memberships", async () => {
    renderWithProviders(<MeProfile />);

    expect(
      await screen.findByRole("row", { name: "Email ada@example.com" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("row", { name: "Organization Demo" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("row", { name: "Role admin" })).toBeInTheDocument();

    const memberships = within(
      screen.getByRole("region", { name: "Memberships" }),
    ).getAllByRole("listitem");
    expect(memberships.map((item) => item.textContent)).toEqual([
      "Demoadmin",
      "adamember",
    ]);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
