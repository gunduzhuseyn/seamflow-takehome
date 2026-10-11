import { PageHeader } from "@/components/page-header";
import { MetricsTiles } from "@/features/classifications/components/metrics-tiles";

export function DashboardRoute() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Totals, match ratio, latency, spend, and override rate."
      />
      <MetricsTiles />
    </>
  );
}
