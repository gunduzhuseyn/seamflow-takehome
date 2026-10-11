import { ClerkLoading, Show, SignIn, useAuth } from "@clerk/react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Outlet } from "react-router";

/**
 * Empties the query cache when the signed-in user changes or signs out.
 * Query keys carry no user id, so a cached answer would leak to the next user.
 */
function useClearQueriesOnUserChange() {
  const { userId } = useAuth();
  const queryClient = useQueryClient();
  const previousUserId = useRef(userId);

  useEffect(() => {
    if (previousUserId.current && previousUserId.current !== userId) {
      queryClient.clear();
    }
    previousUserId.current = userId;
  }, [userId, queryClient]);
}

/**
 * Parent of every route. Signed out, it shows only the Clerk sign-in form.
 * Signed in, it renders the matched child route.
 */
export function ProtectedLayout() {
  useClearQueriesOnUserChange();

  return (
    <>
      <ClerkLoading>
        <p role="status" className="p-4 text-center text-muted-foreground">
          Loading…
        </p>
      </ClerkLoading>
      <Show when="signed-out">
        <main className="mx-auto flex min-h-svh max-w-md flex-col justify-center p-4">
          {/* withSignUp keeps sign-up in this app, not on Clerk's hosted page. */}
          <div className="flex justify-center">
            <SignIn routing="hash" withSignUp />
          </div>
        </main>
      </Show>
      <Show when="signed-in">
        <Outlet />
      </Show>
    </>
  );
}
