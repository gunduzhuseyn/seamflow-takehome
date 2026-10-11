import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

import type { ClassificationOut, ClassificationStatus } from "../api";
import { money, oppositeVerdict, VERDICT_LABEL } from "../format";
import { useReviewClassification } from "../use-review";

const STATUS_LABEL: Record<ClassificationStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};

const STATUS_VARIANT: Record<
  ClassificationStatus,
  "outline" | "secondary" | "destructive"
> = {
  queued: "outline",
  processing: "secondary",
  completed: "secondary",
  failed: "destructive",
};

type ClassificationCardProps = {
  item: ClassificationOut;
  /** Object URL of the local file, shown until the server thumbnail exists. */
  localPreviewUrl?: string;
};

export function ClassificationCard({
  item,
  localPreviewUrl,
}: ClassificationCardProps) {
  const review = useReviewClassification();
  const src = item.thumbnail_url ?? localPreviewUrl;
  const verdict = item.final_verdict ?? item.verdict;
  const modelVerdict = item.verdict;
  // Pending rows go through the Review queue instead.
  const canGiveFeedback =
    item.status === "completed" && item.review_status === "not_required";
  const percent =
    item.confidence === null ? null : Math.round(item.confidence * 100);

  return (
    <Card size="sm" className="gap-3">
      {src ? (
        <img
          src={src}
          alt={`Preview of ${item.filename}`}
          className="aspect-video w-full object-cover rounded-t-xl"
        />
      ) : (
        <div className="aspect-video w-full rounded-t-xl bg-muted" />
      )}
      <CardContent className="space-y-2">
        <div className="flex items-start justify-between gap-2">
          <span className="truncate font-medium" title={item.filename}>
            {item.filename}
          </span>
          <Badge variant={STATUS_VARIANT[item.status]}>
            {STATUS_LABEL[item.status]}
          </Badge>
        </div>

        {item.status === "failed" && (
          <p className="text-destructive">
            Analysis failed
            {item.error_code ? ` (${item.error_code})` : ""}
          </p>
        )}

        {verdict !== null && (
          <div className="flex items-center gap-2">
            <span className="text-xl font-semibold">
              {VERDICT_LABEL[verdict]}
            </span>
            <Badge variant={verdict === "hot_dog" ? "success" : "slate"}>
              {verdict === "hot_dog" ? "Hot dog" : "Not hot dog"}
            </Badge>
          </div>
        )}

        {percent !== null && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Confidence</span>
              <span>{percent}%</span>
            </div>
            <Progress value={percent} aria-label="Confidence" />
          </div>
        )}

        {item.observations && (
          <p className="text-xs text-muted-foreground">{item.observations}</p>
        )}

        {(item.review_status === "pending" || item.duplicate_of !== null) && (
          <div className="flex flex-wrap gap-1">
            {item.review_status === "pending" && (
              <Badge variant="warning">Pending review</Badge>
            )}
            {item.duplicate_of !== null && (
              <Badge variant="outline">Duplicate, $0.00</Badge>
            )}
          </div>
        )}

        {item.status === "completed" && (
          <p className="text-xs text-muted-foreground">
            {item.latency_ms === null ? "" : `${item.latency_ms} ms, `}
            {money.format(item.cost_usd)}
          </p>
        )}

        {canGiveFeedback && modelVerdict !== null && (
          <div className="flex items-center justify-between gap-2 border-t pt-2 text-xs">
            <span className="text-muted-foreground">Was this correct?</span>
            <div className="flex gap-1">
              <Button
                size="xs"
                variant="outline"
                disabled={review.isPending}
                onClick={() =>
                  review.mutate({ id: item.id, final_verdict: modelVerdict })
                }
              >
                Yes
              </Button>
              <Button
                size="xs"
                variant="outline"
                disabled={review.isPending}
                onClick={() =>
                  review.mutate({
                    id: item.id,
                    final_verdict: oppositeVerdict(modelVerdict),
                  })
                }
              >
                No
              </Button>
            </div>
          </div>
        )}
        {review.isError && (
          <p role="alert" className="text-xs text-destructive">
            Feedback failed: {review.error.message}
          </p>
        )}
        {item.review_status === "reviewed" && item.final_verdict !== null && (
          <p className="text-xs text-muted-foreground">
            Final verdict: {VERDICT_LABEL[item.final_verdict]}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
