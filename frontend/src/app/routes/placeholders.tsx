import { PageHeader } from "@/components/page-header";

/** Placeholder pages. Their content comes in the next unit. */

export function ReviewRoute() {
  return (
    <PageHeader
      title="Review"
      description="Confirm or override verdicts below the confidence threshold."
    />
  );
}

export function HistoryRoute() {
  return (
    <PageHeader
      title="History"
      description="Every classification in your organization, with filters and CSV export."
    />
  );
}

export function DashboardRoute() {
  return (
    <PageHeader
      title="Dashboard"
      description="Totals, hot dog ratio, latency, spend, and override rate."
    />
  );
}
