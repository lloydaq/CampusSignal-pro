import { ServiceStatus } from "@/features/system-status/ServiceStatus";

/**
 * Placeholder for the signed-out entry point until sign-in ships (Phase 2). It states what
 * is true today and shows live service status instead of an inert sign-in form
 * (Rules.md R-3.7, Design.md §8).
 */
export function AccountsUnavailablePage() {
  return (
    <div className="space-y-10">
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Accounts aren't open yet</h1>
        <p className="text-base text-muted">
          Signing in and joining your college aren't available in this build. Once they are,
          you'll sign in here.
        </p>
      </div>
      <ServiceStatus />
    </div>
  );
}
