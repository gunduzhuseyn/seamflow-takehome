import { PageHeader } from "@/components/page-header";
import { ReviewQueue } from "@/features/classifications/components/review-queue";

export function ReviewRoute() {
  return (
    <>
      <PageHeader
        title="Review"
        description="Confirm or override each verdict that scored below the confidence threshold."
      />
      <ReviewQueue />
    </>
  );
}
