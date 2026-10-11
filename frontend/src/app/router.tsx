import { createBrowserRouter, Navigate, type RouteObject } from "react-router";

import { HomeRoute } from "./routes/home";
import { ProtectedLayout } from "./routes/protected-layout";

export const routes: RouteObject[] = [
  {
    Component: ProtectedLayout,
    children: [
      { path: "/", Component: HomeRoute },
      // Unknown paths go home, behind the same sign-in check.
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
