import { UserButton } from "@clerk/react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router";

import { cn } from "@/lib/utils";
import { authMeOptions } from "@/lib/api/@tanstack/react-query.gen";

/** Account management happens in this app, not in Clerk's modal. */
const USER_BUTTON_APPEARANCE = {
  elements: {
    userButtonPopoverActionButton__manageAccount: { display: "none" },
  },
};

const NAV = [
  { to: "/", label: "Classify", hint: "Drop images and read verdicts" },
  {
    to: "/review",
    label: "Review",
    hint: "Confirm or override uncertain verdicts",
  },
  {
    to: "/history",
    label: "History",
    hint: "Every classification, with filters and CSV export",
  },
  {
    to: "/dashboard",
    label: "Dashboard",
    hint: "Totals and rates for the organization",
  },
];

/** Signed-in frame: left sidebar with navigation, top bar with org and account. */
export function AppShell() {
  const me = useQuery(authMeOptions());

  return (
    <div className="flex min-h-svh">
      <aside className="flex w-52 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
        <div className="px-4 py-4 text-sm font-semibold tracking-tight">
          SeeFood Enterprise
        </div>
        <nav aria-label="Main" className="px-2">
          <ul className="space-y-0.5">
            {NAV.map(({ to, label, hint }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={to === "/"}
                  title={hint}
                  className={({ isActive }) =>
                    cn(
                      "block rounded-md px-2 py-1.5 text-sm text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                      isActive &&
                        "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
                    )
                  }
                >
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center justify-between border-b bg-card px-6">
          <span className="text-sm font-medium">{me.data?.org.name ?? ""}</span>
          <UserButton appearance={USER_BUTTON_APPEARANCE} />
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
