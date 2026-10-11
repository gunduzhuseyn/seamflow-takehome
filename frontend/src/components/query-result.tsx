import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";

type QueryResultProps<TData, TError> = {
  query: UseQueryResult<TData, TError>;
  /** Marks a successful result as empty. Lists pass `(d) => d.length === 0`. */
  isEmpty?: (data: TData) => boolean;
  emptyMessage?: string;
  children: (data: TData) => ReactNode;
};

/**
 * The one loading, empty, and error pattern. Every screen renders its query
 * through this component so the three states look and behave the same.
 * A failed refetch keeps the last data on screen and adds an inline notice.
 */
export function QueryResult<TData, TError>({
  query,
  isEmpty,
  emptyMessage = "Nothing here yet.",
  children,
}: QueryResultProps<TData, TError>) {
  if (query.isPending) {
    return (
      <p role="status" className="text-muted-foreground">
        Loading…
      </p>
    );
  }

  const retry = (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        void query.refetch();
      }}
    >
      Retry
    </Button>
  );

  const { data } = query;
  if (data === undefined) {
    // Only an error leaves a settled query without data.
    return (
      <div role="alert" className="flex items-center gap-3">
        <span className="text-destructive">Could not load.</span>
        {retry}
      </div>
    );
  }

  return (
    <>
      {query.isError && (
        <div
          role="alert"
          className="mb-3 flex items-center gap-3 text-xs text-destructive"
        >
          <span>Could not refresh.</span>
          {retry}
        </div>
      )}
      {isEmpty?.(data) ? (
        <p className="text-muted-foreground">{emptyMessage}</p>
      ) : (
        children(data)
      )}
    </>
  );
}
