import { Navigate, Outlet } from "react-router";

import { landingPath } from "@/features/auth/landing";
import { useMe } from "@/features/auth/session";

/**
 * Section pages are for faculty (Teaching) and for the department and college admins who read
 * them (ACADEMIC-010); the backend decides per section. Everyone else goes to their home.
 */
export function TeachingGuard() {
  const me = useMe();
  if (!me.capabilities.includes("teaching") && !me.capabilities.includes("review_memberships")) return <Navigate to={landingPath(me)} replace />;
  return <Outlet />;
}
