import { getToken } from "@clerk/react";

import type { CreateClientConfig } from "./api/client.gen";

/**
 * Runtime config for the generated client. `baseUrl` comes from the
 * environment. `auth` runs on secured operations only and returns the Clerk
 * session token. Signed out, it returns undefined and the API answers 401.
 */
export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: import.meta.env.VITE_API_URL,
  auth: async () => (await getToken()) ?? undefined,
});
