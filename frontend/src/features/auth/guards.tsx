import { RotateCw } from "lucide-react";
import { Navigate, Outlet, useLocation, useSearchParams } from "react-router";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { useDelayedFlag } from "@/lib/useDelayedFlag";

import { AuthHeading } from "./AuthHeading";
import { DEFAULT_SIGNED_IN_PATH, safeNextPath, signInPathFor } from "./navigation";
import { useSession } from "./session";

function SessionLoading() {
  const visible = useDelayedFlag(true);
  return (
    <p role="status" className={visible ? "text-base text-muted" : "sr-only"}>
      Loading…
    </p>
  );
}

function SessionError({ error, onRetry, retrying }: { error: Error; onRetry: () => void; retrying: boolean }) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div className="space-y-6">
      <AuthHeading title="Couldn't load your account">
        <p>{error instanceof ApiError ? error.message : "Something went wrong."}</p>
      </AuthHeading>
      {requestId && <p className="font-mono text-xs text-subtle">Request ID {requestId}</p>}
      <Button variant="secondary" onClick={onRetry} disabled={retrying}>
        <RotateCw aria-hidden="true" strokeWidth={1.5} />
        {retrying ? "Trying again…" : "Try again"}
      </Button>
    </div>
  );
}

/** Signed-in routes. Signed out → sign-in with a return path (Phases.md 2d, decided 2026-10-23). */
export function RequireAuth() {
  const session = useSession();
  const location = useLocation();
  if (session.isPending) return <SessionLoading />;
  if (session.isError) {
    return <SessionError error={session.error} onRetry={() => void session.refetch()} retrying={session.isFetching} />;
  }
  if (session.data === null) return <Navigate to={signInPathFor(location)} replace />;
  return <Outlet />;
}

/** Sign-in and registration: a signed-in visitor goes where they were headed instead. */
export function GuestOnly() {
  const session = useSession();
  const [params] = useSearchParams();
  if (session.isPending) return <SessionLoading />;
  // If the session check itself fails, still show the form: signing in reports its own errors.
  if (session.data) return <Navigate to={safeNextPath(params.get("next"))} replace />;
  return <Outlet />;
}

/** "/" has no page of its own until the campus home exists (Phase 3). */
export function HomeRedirect() {
  const session = useSession();
  if (session.isPending) return <SessionLoading />;
  return <Navigate to={session.data ? DEFAULT_SIGNED_IN_PATH : "/sign-in"} replace />;
}
