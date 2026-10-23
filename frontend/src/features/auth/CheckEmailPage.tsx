import { TextLink } from "@/components/TextLink";

import { AuthHeading } from "./AuthHeading";

/** After registering. Says the same for new and existing emails (AUTH-002). Resending needs a
 * session, so the way to a new link is signing in (decided 2026-10-23). */
export function CheckEmailPage() {
  return (
    <div className="space-y-8">
      <AuthHeading title="Check your email">
        <p>Check your email to finish setting up your account. The link works for 24 hours.</p>
      </AuthHeading>
      <div className="space-y-2 text-sm text-muted">
        <p>
          No email? Check your spam folder, or <TextLink to="/sign-in?next=%2Faccount">sign in to send a new link</TextLink>.
        </p>
      </div>
    </div>
  );
}
