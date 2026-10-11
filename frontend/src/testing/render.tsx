import { QueryClient } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";

import { AppProvider } from "@/app/provider";

/** Renders inside the real app provider with a fresh, non-retrying cache. */
export function renderWithProviders(
  ui: ReactNode,
): RenderResult & { queryClient: QueryClient } {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const result = render(
    <AppProvider queryClient={queryClient}>{ui}</AppProvider>,
  );
  return { ...result, queryClient };
}
