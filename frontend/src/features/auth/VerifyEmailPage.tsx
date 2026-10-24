import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { Callout } from "@/components/Callout";
import { TextLink } from "@/components/TextLink";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";

import { verifyEmail, type Me } from "./api";
import { AuthHeading } from "./AuthHeading";
import { DEFAULT_SIGNED_IN_PATH, retryAfterText } from "./navigation";
import { ResendVerification } from "./ResendVerification";
import { sessionQueryKey, useSession } from "./session";
import { useFragmentToken } from "./useFragmentToken";

const SIGN_IN_FOR_NEW_LINK = "/sign-in?next=%2Fjoin";

function NextStep({ signedIn }: { signedIn: boolean }) {
  return (
    <p>
      {signedIn ? <TextLink to={DEFAULT_SIGNED_IN_PATH}>Continue</TextLink> : <TextLink to="/sign-in">Sign in</TextLink>}
    </p>
  );
}

function NewLink({ signedIn }: { signedIn: boolean }) {
  return signedIn ? (
    <ResendVerification />
  ) : (
    <p>
      <TextLink to={SIGN_IN_FOR_NEW_LINK}>Sign in to get a new link</TextLink>
    </p>
  );
}

/** Opened from the verification email (AUTH-003, US-01). Verifies once, then explains the result. */
export function VerifyEmailPage() {
  const token = useFragmentToken();
  const queryClient = useQueryClient();
  const signedIn = Boolean(useSession().data);
  const started = useRef(false);

  const { mutate, ...verification } = useMutation({
    mutationFn: verifyEmail,
    onSuccess: async () => {
      // A /me request sent alongside this one may predate the verification. Invalidating
      // alone would join that request instead of replacing it, so cancel it first.
      await queryClient.cancelQueries({ queryKey: sessionQueryKey });
      queryClient.setQueryData<Me | null>(sessionQueryKey, (me) =>
        me ? { ...me, user: { ...me.user, email_verified: true } } : me,
      );
      await queryClient.invalidateQueries({ queryKey: sessionQueryKey });
    },
  });

  useEffect(() => {
    if (token && !started.current) {
      started.current = true;
      mutate(token);
    }
  }, [token, mutate]);

  if (!token) {
    return (
      <div className="space-y-6">
        <AuthHeading title="This link isn't valid">
          <p>Open the whole link from your verification email. If it still doesn't work, ask for a new one.</p>
        </AuthHeading>
        <NewLink signedIn={signedIn} />
      </div>
    );
  }

  if (verification.isSuccess) {
    return (
      <div className="space-y-6">
        <AuthHeading title="Your email is verified">
          <p>You can now join your college.</p>
        </AuthHeading>
        <NextStep signedIn={signedIn} />
      </div>
    );
  }

  if (verification.isError) {
    const error = verification.error;
    const code = error instanceof ApiError ? error.code : null;
    if (code === "token_used") {
      return (
        <div className="space-y-6">
          <AuthHeading title="This link was already used">
            <p>Your email may already be verified. Sign in to check.</p>
          </AuthHeading>
          <NextStep signedIn={signedIn} />
        </div>
      );
    }
    if (code === "token_expired") {
      return (
        <div className="space-y-6">
          <AuthHeading title="This link has expired">
            <p>Verification links work for 24 hours. Ask for a new one.</p>
          </AuthHeading>
          <NewLink signedIn={signedIn} />
        </div>
      );
    }
    if (code === "token_invalid") {
      return (
        <div className="space-y-6">
          <AuthHeading title="This link isn't valid">
            <p>Open the whole link from your verification email, or ask for a new one.</p>
          </AuthHeading>
          <NewLink signedIn={signedIn} />
        </div>
      );
    }
    const rateLimited = error instanceof ApiError && error.status === 429;
    return (
      <div className="space-y-6">
        <AuthHeading title="Couldn't verify your email" />
        <Callout tone="danger">{rateLimited ? `Too many attempts. ${retryAfterText(error.retryAfterSeconds)}` : error.message}</Callout>
        {!rateLimited && (
          <Button variant="secondary" onClick={() => mutate(token)}>
            Try again
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AuthHeading title="Verifying your email" />
      <p role="status" className="text-base text-muted">
        Checking your link…
      </p>
    </div>
  );
}
