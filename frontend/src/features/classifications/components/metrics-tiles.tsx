import { useQuery } from "@tanstack/react-query";

import { QueryResult } from "@/components/query-result";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";

import { metricsOptions, type MetricsOut } from "../api";
import { money, percent } from "../format";

const integer = new Intl.NumberFormat("en-US");

/** Share of completed rows the model matched. Null before the first one. */
function matchRatio(m: MetricsOut): number | null {
  return m.completed === 0 ? null : m.match / m.completed;
}

const TILES: { label: string; value: (m: MetricsOut) => string }[] = [
  { label: "Total classified", value: (m) => integer.format(m.total) },
  { label: "Match ratio", value: (m) => percent(matchRatio(m)) },
  { label: "Pending review", value: (m) => integer.format(m.pending_review) },
  { label: "Override rate", value: (m) => percent(m.override_rate) },
  {
    label: "Average latency",
    value: (m) =>
      m.avg_latency_ms === null
        ? "—"
        : `${integer.format(Math.round(m.avg_latency_ms))} ms`,
  },
  { label: "Total spend", value: (m) => money.format(m.total_cost_usd) },
  { label: "Deduplicated", value: (m) => integer.format(m.deduplicated) },
];

/** The dashboard: one card per number, in a two-row grid. */
export function MetricsTiles() {
  const query = useQuery(metricsOptions());

  return (
    <QueryResult query={query}>
      {(metrics) => (
        <ul className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {TILES.map(({ label, value }) => (
            <li key={label}>
              <Card size="sm" className="gap-1">
                <CardHeader>
                  <CardDescription>{label}</CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-semibold tabular-nums">
                    {value(metrics)}
                  </p>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </QueryResult>
  );
}
