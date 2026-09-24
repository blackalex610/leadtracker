import { lazy } from "react";
import { Outlet, type RouteObject } from "react-router";

import { AppShell } from "@/components/app/app-shell";
import { RequireAuth } from "@/lib/auth";
import { DashboardPage } from "@/pages/dashboard";
import { FindLeadsPage } from "@/pages/find-leads";
import { LeadDetailPage } from "@/pages/lead-detail";
import { LeadsPage } from "@/pages/leads";
import { LoginPage } from "@/pages/login";
import { NotFoundPage } from "@/pages/not-found";

const CallingSessionPage = lazy(() => import("@/pages/calling-session"));
const CampaignsPage = lazy(() => import("@/pages/campaigns"));
const SettingsPage = lazy(() => import("@/pages/settings"));
const ImportPage = lazy(() => import("@/pages/import"));

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: (
      <RequireAuth>
        <Outlet />
      </RequireAuth>
    ),
    children: [
      { path: "/calling/:id", element: <CallingSessionPage /> },
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "search", element: <FindLeadsPage /> },
          { path: "leads", element: <LeadsPage /> },
          { path: "leads/import", element: <ImportPage /> },
          { path: "leads/:id", element: <LeadDetailPage /> },
          { path: "campaigns", element: <CampaignsPage /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];
