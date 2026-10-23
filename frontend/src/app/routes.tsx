import type { RouteObject } from "react-router";

import { AccountPage } from "@/features/auth/AccountPage";
import { CheckEmailPage } from "@/features/auth/CheckEmailPage";
import { ForgotPasswordPage } from "@/features/auth/ForgotPasswordPage";
import { GuestOnly, HomeRedirect, RequireAuth } from "@/features/auth/guards";
import { NotFoundPage } from "@/features/auth/NotFoundPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { ResetPasswordPage } from "@/features/auth/ResetPasswordPage";
import { SignInPage } from "@/features/auth/SignInPage";
import { VerifyEmailPage } from "@/features/auth/VerifyEmailPage";
import { StatusPage } from "@/features/system-status/StatusPage";

import { AuthShell } from "./shells/AuthShell";

/**
 * Phase 2: account screens. Paths for emailed links (/verify-email, /reset-password,
 * /sign-in, /forgot-password) are fixed by the backend's email templates.
 */
export const routes: RouteObject[] = [
  {
    element: <AuthShell />,
    children: [
      { index: true, element: <HomeRedirect /> },
      {
        element: <GuestOnly />,
        children: [
          { path: "sign-in", element: <SignInPage /> },
          { path: "register", element: <RegisterPage /> },
        ],
      },
      { path: "forgot-password", element: <ForgotPasswordPage /> },
      { path: "check-email", element: <CheckEmailPage /> },
      { path: "verify-email", element: <VerifyEmailPage /> },
      { path: "reset-password", element: <ResetPasswordPage /> },
      { path: "status", element: <StatusPage /> },
      { element: <RequireAuth />, children: [{ path: "account", element: <AccountPage /> }] },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
