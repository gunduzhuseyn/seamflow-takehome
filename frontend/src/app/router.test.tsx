import { act, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ME, TEST_SESSION_TOKEN } from "@/testing/handlers";
import { renderWithProviders } from "@/testing/render";

import { routes } from "./router";

// A tiny external store, so a sign-in change re-renders the mocked hooks.
const auth = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  return {
    signedIn: false,
    set(signedIn: boolean) {
      this.signedIn = signedIn;
      listeners.forEach((listener) => listener());
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
});

vi.mock("@clerk/react", async () => {
  const { useSyncExternalStore } = await import("react");
  const useSignedIn = () =>
    useSyncExternalStore(
      (listener) => auth.subscribe(listener),
      () => auth.signedIn,
    );
  return {
    ClerkLoading: () => null,
    useAuth: () => ({ userId: useSignedIn() ? "user_1" : null }),
    useUser: () => ({
      user: useSignedIn()
        ? {
            fullName: "Ada Lovelace",
            primaryEmailAddress: { emailAddress: ME.user.email },
          }
        : null,
    }),
    Show: function Show({
      when,
      children,
    }: {
      when: string;
      children: ReactNode;
    }) {
      return (when === "signed-in") === useSignedIn() ? children : null;
    },
    SignIn: ({ withSignUp }: { withSignUp?: boolean }) => (
      <form aria-label={withSignUp ? "Sign in or sign up" : "Sign in"} />
    ),
    UserButton: () => <button type="button">Open user menu</button>,
    getToken: vi.fn(() =>
      Promise.resolve(auth.signedIn ? TEST_SESSION_TOKEN : null),
    ),
  };
});

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { queryClient } = renderWithProviders(
    <RouterProvider router={router} />,
  );
  return { router, queryClient };
}

describe("routes", () => {
  beforeEach(() => {
    auth.signedIn = false;
  });

  it.each(["/", "/unknown/page"])(
    "shows only sign-in with sign-up when signed out at %s",
    (path) => {
      renderAt(path);

      expect(
        screen.getByRole("form", { name: "Sign in or sign up" }),
      ).toBeInTheDocument();
      expect(screen.queryByText("SeeFood Enterprise")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Open user menu" }),
      ).not.toBeInTheDocument();
    },
  );

  it("shows the shell and the Classify page on / when signed in", async () => {
    auth.signedIn = true;

    renderAt("/");

    expect(
      await screen.findByRole("heading", { name: "Classify" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Current check: is this a hot dog?"),
    ).toBeInTheDocument();
    expect(screen.getByText("SeeFood Enterprise")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Classify", "Review", "History", "Dashboard"]);
    // The org name comes from /me with the session token.
    expect(await screen.findByText(ME.org.name)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Open user menu" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("form", { name: /^Sign in/ }),
    ).not.toBeInTheDocument();
  });

  it.each([
    ["/review", "Review"],
    ["/history", "History"],
    ["/dashboard", "Dashboard"],
  ])("renders the %s placeholder with its header", async (path, title) => {
    auth.signedIn = true;

    renderAt(path);

    expect(
      await screen.findByRole("heading", { name: title }),
    ).toBeInTheDocument();
  });

  it("sends a signed-in user on an unknown path to /", async () => {
    auth.signedIn = true;

    const { router } = renderAt("/unknown/page");

    expect(
      await screen.findByRole("heading", { name: "Classify" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });

  it("empties the query cache on sign-out", async () => {
    auth.signedIn = true;
    const { queryClient } = renderAt("/");
    expect(await screen.findByText(ME.org.name)).toBeInTheDocument();
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThan(0);

    act(() => {
      auth.set(false);
    });

    expect(
      await screen.findByRole("form", { name: "Sign in or sign up" }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    });
  });
});
