import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const defaultQueryClient = new QueryClient();

type AppProviderProps = {
  children: ReactNode;
  /** Tests pass a fresh client with retries off. */
  queryClient?: QueryClient;
};

export function AppProvider({
  children,
  queryClient = defaultQueryClient,
}: AppProviderProps) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
