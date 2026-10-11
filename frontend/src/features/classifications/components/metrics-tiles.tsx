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

/** Share of completed verdicts that are hot dogs. Null before the first one. */
function hotDogRatio(m: MetricsOut): number | null {
  const decided = m.hot_dog + m.not_hot_dog;
  return decided === 0 ? null : m.hot_dog / decided;
}

const TILES: { label: string; value: (m: MetricsOut) => string }[] = [
  { label: "Total classified", value: (m) => integer.format(m.total) },
  { label: "Hot dog ratio", value: (m) => percent(hotDogRatio(m)) },
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
