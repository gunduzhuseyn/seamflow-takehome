import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  metricsQueryKey,
  reviewClassificationMutationOptions,
  type ClassificationList,
  type ClassificationOut,
} from "./api";

/**
 * The one review mutation. On success the returned row replaces its copy in
 * every cached list, then lists and metrics refetch.
 */
export function useReviewClassification() {
  const queryClient = useQueryClient();
  return useMutation({
    ...reviewClassificationMutationOptions(),
    onSuccess: (row: ClassificationOut) => {
      queryClient.setQueriesData<ClassificationList>(
        { queryKey: ["classifications"] },
        (old) =>
          old && {
            ...old,
            items: old.items.map((item) => (item.id === row.id ? row : item)),
          },
      );
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: ["classifications"] }),
        queryClient.invalidateQueries({ queryKey: metricsQueryKey }),
      ]);
    },
  });
}
