import { PageHeader } from "@/components/page-header";
import { HistoryTable } from "@/features/classifications/components/history-table";

export function HistoryRoute() {
  return (
    <>
      <PageHeader
        title="History"
        description="Every classification in your organization, with filters and CSV export."
      />
      <HistoryTable />
    </>
  );
}
