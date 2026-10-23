import { usePageTitle } from "@/lib/usePageTitle";

import { ServiceStatus } from "./ServiceStatus";

/** Public service status (formerly the Phase 1 start page), linked from the signed-out footer. */
export function StatusPage() {
  usePageTitle("Service status");
  return (
    <div className="space-y-10">
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Service status</h1>
        <p className="text-base text-muted">Whether the CampusSignal API and database are reachable right now.</p>
      </div>
      <ServiceStatus />
    </div>
  );
}
