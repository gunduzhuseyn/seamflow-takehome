import { useQuery } from "@tanstack/react-query";

import { QueryResult } from "@/components/query-result";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import {
  listClassificationsOptions,
  type ClassificationList,
  type ClassificationOut,
} from "../api";
import { oppositeVerdict, percent, verdictLabel } from "../format";
import { useReviewClassification } from "../use-review";
import { Thumbnail } from "./thumbnail";

const PENDING_QUERY = { limit: 50, review_status: "pending" } as const;

function pendingItems(data: ClassificationList): ClassificationOut[] {
  // A reviewed row leaves at once, before the list refetches.
  return data.items.filter((item) => item.review_status === "pending");
}

/** Every verdict below the confidence threshold, with Confirm and Override. */
export function ReviewQueue() {
  const query = useQuery(listClassificationsOptions(PENDING_QUERY));
  const review = useReviewClassification();

  return (
    <div className="space-y-3">
      {review.isError && (
        <p role="alert" className="text-xs text-destructive">
          Review failed: {review.error.message}
        </p>
      )}
      <QueryResult
        query={query}
        isEmpty={(data) => pendingItems(data).length === 0}
        emptyMessage="Results under the confidence threshold wait here. Nothing is pending."
      >
        {(data) => (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>
                  <span className="sr-only">Thumbnail</span>
                </TableHead>
                <TableHead>Filename</TableHead>
                <TableHead>Submitted by</TableHead>
                <TableHead>Model verdict</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Observations</TableHead>
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pendingItems(data).map((item) => {
                const busy =
                  review.isPending && review.variables.id === item.id;
                const modelVerdict = item.verdict;
                return (
                  <TableRow key={item.id}>
                    <TableCell>
                      <Thumbnail
                        src={item.thumbnail_url}
                        filename={item.filename}
                      />
                    </TableCell>
                    <TableCell className="max-w-48 truncate font-medium">
                      {item.filename}
                    </TableCell>
                    <TableCell>{item.submitted_by_name}</TableCell>
                    <TableCell>
                      {verdictLabel(item.verdict, item.verdict_labels)}
                    </TableCell>
                    <TableCell>{percent(item.confidence)}</TableCell>
                    <TableCell className="max-w-72 text-xs text-muted-foreground">
                      {item.observations}
                    </TableCell>
                    <TableCell>
                      {modelVerdict !== null && (
                        <div className="flex justify-end gap-1.5">
                          <Button
                            size="sm"
                            disabled={busy}
                            onClick={() =>
                              review.mutate({
                                id: item.id,
                                final_verdict: modelVerdict,
                              })
                            }
                          >
                            Confirm
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={busy}
                            onClick={() =>
                              review.mutate({
                                id: item.id,
                                final_verdict: oppositeVerdict(modelVerdict),
                              })
                            }
                          >
                            Override
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </QueryResult>
    </div>
  );
}
