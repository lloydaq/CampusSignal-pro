import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { Callout } from "@/components/Callout";
import { SubmitButton } from "@/components/SubmitButton";
import { TextLink } from "@/components/TextLink";
import { Button } from "@/components/ui/button";
import { acceptInvite, signOut } from "@/features/auth/api";
import { AuthHeading } from "@/features/auth/AuthHeading";
import { refreshSession, sessionQueryKey, useSession } from "@/features/auth/session";
import { useFragmentToken } from "@/features/auth/useFragmentToken";
import { ApiError } from "@/lib/api";

/**
 * The invite token from the emailed link (#token=…). If the person has to sign in or register
 * first, it waits in sessionStorage: per tab, never sent anywhere, removed once used or refused.
 * Carrying it through the sign-in URL instead would put it in the address bar, and a reload
 * would send it to the server's access log.
 */
const STORAGE_KEY = "campussignal.invite-token";

function rememberToken(fresh: string | null): string | null {
  try {
    if (fresh) window.sessionStorage.setItem(STORAGE_KEY, fresh);
    return fresh ?? window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return fresh; // storage blocked: the token still works in this page view
  }
}

function forgetToken(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // nothing stored
  }
}

const LINK_PROBLEMS: Record<string, { title: string; body: string }> = {
  token_used: { title: "This invitation was already used", body: "Each invitation works once. If you've already joined, sign in to continue." },
  token_expired: { title: "This invitation has expired", body: "Invitations work for 7 days. Ask your college for a new one." },
  token_invalid: { title: "This invitation isn't valid", body: "Open the whole link from your invitation email, or ask your college for a new one." },
};

const REFUSALS: Record<string, string> = {
  platform_admin_cannot_join: "Platform admin accounts can't join a college. Sign in with a different account to accept.",
  already_member: "You're already a member of another college, so you can't accept this invitation.",
  membership_open: "You already have a request or a suspended membership at this college. Contact your college office.",
  college_inactive: "This college isn't available right now. Try again later or contact your college office.",
};

const HERE = "/invites/accept";

export function InviteAcceptPage() {
  const fresh = useFragmentToken();
  const [stored] = useState(() => rememberToken(null));
  const effective = fresh ?? stored;
  useEffect(() => {
    if (fresh) rememberToken(fresh); // once, so forgetting it later sticks
  }, [fresh]);
  const session = useSession();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const accept = useMutation({
    mutationFn: acceptInvite,
    onSuccess: async () => {
      forgetToken();
      await refreshSession(queryClient);
      await navigate("/home", { replace: true });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code in LINK_PROBLEMS) forgetToken();
    },
  });
  const leave = useMutation({
    mutationFn: signOut,
    onSettled: () => {
      queryClient.removeQueries();
      queryClient.setQueryData(sessionQueryKey, null);
    },
  });

  const code = accept.error instanceof ApiError ? accept.error.code : null;
  const problem = (code && LINK_PROBLEMS[code]) || (!effective ? LINK_PROBLEMS.token_invalid : undefined);
  if (problem) {
    return (
      <div className="space-y-6">
        <AuthHeading title={problem.title}>
          <p>{problem.body}</p>
        </AuthHeading>
        <p>
          <TextLink to="/">Go to CampusSignal</TextLink>
        </p>
      </div>
    );
  }

  if (session.isPending) {
    return (
      <p role="status" className="text-base text-muted">
        Loading…
      </p>
    );
  }

  const me = session.data;
  if (!me) {
    const next = encodeURIComponent(HERE);
    return (
      <div className="space-y-8">
        <AuthHeading title="You're invited to join your college">
          <p>Sign in, or create an account, with the email address the invitation was sent to. You'll come back here to accept it.</p>
        </AuthHeading>
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => void navigate(`/sign-in?next=${next}`)}>Sign in</Button>
          <Button variant="secondary" onClick={() => void navigate(`/register?next=${next}`)}>
            Create an account
          </Button>
        </div>
      </div>
    );
  }

  const mismatch = code === "invite_email_mismatch";
  const refusal = code ? REFUSALS[code] : undefined;
  const otherError = accept.isError && !mismatch && !refusal ? accept.error.message : null;
  return (
    <div className="space-y-8">
      <AuthHeading title="Accept your invitation">
        <p>
          You're signed in as <span className="font-medium text-fg">{me.user.email}</span>. Accepting adds you to the college that invited you.
        </p>
      </AuthHeading>
      {mismatch && (
        <Callout tone="danger" title="This invitation is for a different email address">
          <p>Sign out, then sign in or create an account with the address the invitation was sent to.</p>
        </Callout>
      )}
      {refusal && <Callout tone="danger">{refusal}</Callout>}
      {otherError && <Callout tone="danger">{otherError}</Callout>}
      <div className="flex flex-wrap gap-3">
        {!mismatch && !refusal && (
          <SubmitButton type="button" pending={accept.isPending} pendingLabel="Accepting…" onClick={() => effective && accept.mutate(effective)}>
            Accept invitation
          </SubmitButton>
        )}
        {(mismatch || code === "platform_admin_cannot_join") && (
          <Button variant="secondary" onClick={() => leave.mutate()} disabled={leave.isPending}>
            {leave.isPending ? "Signing out…" : "Sign out"}
          </Button>
        )}
      </div>
    </div>
  );
}
