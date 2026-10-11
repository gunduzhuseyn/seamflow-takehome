import { useQuery } from "@tanstack/react-query";

import { QueryResult } from "@/components/query-result";
import { authMeOptions } from "@/lib/api/@tanstack/react-query.gen";

export function MeProfile() {
  const query = useQuery(authMeOptions());

  return (
    <QueryResult query={query}>
      {(me) => (
        <div className="space-y-4 text-sm">
          <table className="w-full">
            <tbody>
              {[
                { label: "Email", value: me.user.email },
                { label: "Organization", value: me.org.name },
                { label: "Role", value: me.role },
              ].map(({ label, value }) => (
                <tr key={label} className="border-b last:border-0">
                  <th scope="row" className="py-2 text-left font-medium">
                    {label}
                  </th>
                  <td className="py-2 text-right">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <section aria-labelledby="memberships-heading">
            <h3 id="memberships-heading" className="mb-2 font-medium">
              Memberships
            </h3>
            <ul className="space-y-1">
              {me.memberships.map(({ org, role }) => (
                <li key={org.id} className="flex justify-between">
                  <span>{org.name}</span>
                  <span className="text-muted-foreground">{role}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </QueryResult>
  );
}
