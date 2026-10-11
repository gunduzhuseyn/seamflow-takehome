import { PageHeader } from "@/components/page-header";
import { HistoryTable } from "@/features/classifications/components/history-table";

export function HistoryRoute() {
  return (
    <>
      <PageHeader
        title="History"
        description="Browse every classification your organization ran, newest first, filter it, or export CSV."
      />
      <HistoryTable />
    </>
  );
}
