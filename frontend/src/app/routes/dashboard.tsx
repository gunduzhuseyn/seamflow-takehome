import { PageHeader } from "@/components/page-header";
import { MetricsTiles } from "@/features/classifications/components/metrics-tiles";

export function DashboardRoute() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Organization-wide totals: volume, match ratio, pending review, override rate, latency, and spend."
      />
      <MetricsTiles />
    </>
  );
}
