import { useSearchParams } from "react-router";

import { TextLink } from "@/components/TextLink";

import { AuthHeading } from "./AuthHeading";
import { safeNextPath } from "./navigation";

/** After registering. Says the same for new and existing emails (AUTH-002). Resending needs a
 * session, so the way to a new link is signing in (decided 2026-10-23). */
export function CheckEmailPage() {
  const [params] = useSearchParams();
  // Where to go after signing in: back to an invitation, or by default the join flow.
  const next = encodeURIComponent(params.has("next") ? safeNextPath(params.get("next")) : "/join");
  return (
    <div className="space-y-8">
      <AuthHeading title="Check your email">
        <p>Check your email to finish setting up your account. The link works for 24 hours.</p>
      </AuthHeading>
      <div className="space-y-2 text-sm text-muted">
        <p>
          No email? Check your spam folder. You can also <TextLink to={`/sign-in?next=${next}`}>sign in</TextLink> to continue or to send a new link.
        </p>
      </div>
    </div>
  );
}
