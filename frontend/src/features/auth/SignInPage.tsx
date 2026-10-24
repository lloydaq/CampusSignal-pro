import { useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate, useSearchParams } from "react-router";

import { Callout } from "@/components/Callout";
import { TextLink } from "@/components/TextLink";

import { AuthHeading } from "./AuthHeading";
import { safeNextPath } from "./navigation";
import { refreshSession } from "./session";
import { SignInForm } from "./SignInForm";

/** A message handed over by the previous screen, e.g. after a password reset or sign-out. */
export interface SignInNotice {
  notice?: string;
}

export function SignInPage() {
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const notice = (location.state as SignInNotice | null)?.notice;
  const next = params.get("next");

  return (
    <div className="space-y-8">
      <AuthHeading title="Sign in">{next !== null && <p>Sign in to continue.</p>}</AuthHeading>
      {notice && <Callout tone="success">{notice}</Callout>}
      <SignInForm
        onSignedIn={async () => {
          // Sign-in returns only the user; load the membership and capabilities too.
          await refreshSession(queryClient);
          await navigate(safeNextPath(next), { replace: true });
        }}
      />
      <div className="space-y-2 text-sm text-muted">
        <p>
          <TextLink to="/forgot-password">Forgot your password?</TextLink>
        </p>
        <p>
          New to CampusSignal?{" "}
          <TextLink to={next !== null ? `/register?next=${encodeURIComponent(safeNextPath(next))}` : "/register"}>
            Create an account
          </TextLink>
        </p>
      </div>
    </div>
  );
}
