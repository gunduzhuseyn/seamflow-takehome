import { createBrowserRouter, Navigate, type RouteObject } from "react-router";

import { AppShell } from "./routes/app-shell";
import { ClassifyRoute } from "./routes/classify";
import { DashboardRoute } from "./routes/dashboard";
import { HistoryRoute } from "./routes/history";
import { ProtectedLayout } from "./routes/protected-layout";
import { ReviewRoute } from "./routes/review";

export const routes: RouteObject[] = [
  {
    Component: ProtectedLayout,
    children: [
      {
        Component: AppShell,
        children: [
          { index: true, Component: ClassifyRoute },
          { path: "review", Component: ReviewRoute },
          { path: "history", Component: HistoryRoute },
          { path: "dashboard", Component: DashboardRoute },
        ],
      },
      // Unknown paths go home, behind the same sign-in check.
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
