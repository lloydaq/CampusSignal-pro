import type { RouteObject } from "react-router";

import { AccountsUnavailablePage } from "@/features/auth/AccountsUnavailablePage";
import { NotFoundPage } from "@/features/auth/NotFoundPage";

import { AuthShell } from "./shells/AuthShell";

/** Phase 1: only the signed-out shell exists (Phases.md, Phase 1 Frontend row). */
export const routes: RouteObject[] = [
  {
    element: <AuthShell />,
    children: [
      { index: true, element: <AccountsUnavailablePage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
