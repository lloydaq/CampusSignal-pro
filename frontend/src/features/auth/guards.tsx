import { RotateCw } from "lucide-react";
import { Navigate, Outlet, useLocation, useSearchParams } from "react-router";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { useDelayedFlag } from "@/lib/useDelayedFlag";

import { AuthHeading } from "./AuthHeading";
import { landingPath } from "./landing";
import { safeNextPath, signInPathFor } from "./navigation";
import { MeContext, useMe, useSession, useSessionEnded } from "./session";
import { SessionEndedDialog } from "./SessionEndedDialog";

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

/**
 * Signed-in routes. A fresh visit while signed out goes to sign-in with a return path. A session
 * that ends while the page is open (any 401) keeps the page mounted with the last known /me and
 * shows the "Your session ended" dialog over it (Design.md §7).
 */
export function RequireAuth() {
  const session = useSession();
  const ended = useSessionEnded();
  const location = useLocation();

  if (session.isPending) return <SessionLoading />;
  if (session.isError) {
    return <SessionError error={session.error} onRetry={() => void session.refetch()} retrying={session.isFetching} />;
  }
  if (session.data === null) {
    if (ended) {
      return (
        <MeContext.Provider value={ended.me}>
          <Outlet />
          <SessionEndedDialog previousUserId={ended.me.user.id} />
        </MeContext.Provider>
      );
    }
    return <Navigate to={signInPathFor(location)} replace />;
  }
  return (
    <MeContext.Provider value={session.data}>
      <Outlet />
    </MeContext.Provider>
  );
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

/** "/" sends each account to its home: campus, the join flow, or (platform admins) the account. */
export function HomeRedirect() {
  const session = useSession();
  if (session.isPending) return <SessionLoading />;
  return <Navigate to={session.data ? landingPath(session.data) : "/sign-in"} replace />;
}

/** Campus pages need an ACTIVE membership in an ACTIVE college; others go where they belong. */
export function RequireCampus() {
  const me = useMe();
  if (!me.capabilities.includes("campus")) return <Navigate to={landingPath(me)} replace />;
  return <Outlet />;
}
