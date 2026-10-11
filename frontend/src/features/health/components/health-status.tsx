import { useQuery } from "@tanstack/react-query";

import { QueryResult } from "@/components/query-result";
import { healthHealthOptions } from "@/lib/api/@tanstack/react-query.gen";

const ROWS = [
  { key: "status", label: "Status" },
  { key: "db", label: "Database" },
  { key: "redis", label: "Redis" },
] as const;

export function HealthStatus() {
  const query = useQuery(healthHealthOptions());

  return (
    <QueryResult query={query}>
      {(health) => (
        <table className="w-full text-sm">
          <tbody>
            {ROWS.map(({ key, label }) => (
              <tr key={key} className="border-b last:border-0">
                <th scope="row" className="py-2 text-left font-medium">
                  {label}
                </th>
                <td className="py-2 text-right">{health[key]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </QueryResult>
  );
}
