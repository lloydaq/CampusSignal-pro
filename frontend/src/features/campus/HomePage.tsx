import { Navigate } from "react-router";

import { AuthHeading } from "@/features/auth/AuthHeading";
import { landingPath } from "@/features/auth/landing";
import { useMe } from "@/features/auth/session";

import { KIND_LABEL, roleLabel } from "./labels";

/**
 * The college home. Its blocks (notices, classes, attendance, issues; Design.md §5 screen 3)
 * arrive with their phases; until then it states the member's place in the college, and
 * shows nothing that can't be used yet (Design.md §8).
 */
export function HomePage() {
  const me = useMe();
  const membership = me.membership;
  if (!membership || !me.capabilities.includes("campus")) return <Navigate to={landingPath(me)} replace />;
  const { college } = membership;
  return (
    <div className="space-y-8">
      <AuthHeading title={college.name} />
      {college.is_demo && (
        <p className="inline-flex rounded-sm border border-warning bg-warning-subtle px-2 py-1 text-sm font-medium text-warning-fg">
          Demo data: this college and everything in it is fictional.
        </p>
      )}
      <section aria-labelledby="membership-heading" className="space-y-4 border-t border-border pt-6">
        <h2 id="membership-heading" className="text-lg font-semibold">
          Your membership
        </h2>
        <dl className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted">Role</dt>
            <dd className="font-medium">{KIND_LABEL[membership.kind]}</dd>
          </div>
          <div>
            <dt className="text-muted">Department</dt>
            <dd className="font-medium">{membership.department ? `${membership.department.name} (${membership.department.code})` : "Not set"}</dd>
          </div>
          {me.roles.length > 0 && (
            <div className="sm:col-span-2">
              <dt className="text-muted">Responsibilities</dt>
              <dd className="font-medium">{me.roles.map(roleLabel).join(", ")}</dd>
            </div>
          )}
        </dl>
      </section>
    </div>
  );
}
