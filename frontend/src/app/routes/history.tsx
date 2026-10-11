import { PageHeader } from "@/components/page-header";
import { HistoryTable } from "@/features/classifications/components/history-table";

export function HistoryRoute() {
  return (
    <>
      <PageHeader
        title="History"
        description="Every classification your organization ran, newest first: filter by status, verdict, review, or question, then export the filtered rows as CSV."
      />
      <HistoryTable />
    </>
  );
}
