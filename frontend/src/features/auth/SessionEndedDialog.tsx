import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router";

import { TextLink } from "@/components/TextLink";

import { refreshSession, useMe } from "./session";
import { SignInForm } from "./SignInForm";

/**
 * "Your session ended. Sign in again" over the current page (Design.md §7). The page stays
 * mounted underneath, so unsaved input is kept. Signing in as the same account just closes the
 * dialog; a different account starts over from its own home, so nobody acts on another
 * person's half-finished screen. Escape doesn't dismiss it: there's nothing to go back to.
 */
export function SessionEndedDialog({ previousUserId }: { previousUserId: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const me = useMe();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (typeof dialog.showModal === "function" && !dialog.open) dialog.showModal();
    else dialog.setAttribute("open", "");
    const keepOpen = (event: Event) => event.preventDefault();
    dialog.addEventListener("cancel", keepOpen);
    return () => dialog.removeEventListener("cancel", keepOpen);
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby="session-ended-title"
      aria-describedby="session-ended-text"
      className="fixed inset-0 m-0 h-dvh max-h-none w-full max-w-none items-center justify-center bg-transparent p-4 backdrop:bg-fg/40 open:flex"
    >
      <div className="w-full max-w-auth space-y-6 rounded-md border border-border bg-surface p-6 text-fg shadow-overlay">
        <div className="space-y-2">
          <h2 id="session-ended-title" className="text-xl font-semibold">
            Your session ended
          </h2>
          <p id="session-ended-text" className="text-sm text-muted">
            Sign in again to continue. What you were doing is still on the page.
          </p>
        </div>
        <SignInForm
          idPrefix="session-ended-"
          defaultEmail={me.user.email}
          onSignedIn={async (user) => {
            if (user.id !== previousUserId) {
              queryClient.removeQueries();
              await refreshSession(queryClient);
              await navigate("/", { replace: true });
              return;
            }
            await refreshSession(queryClient);
          }}
        />
        <p className="text-sm text-muted">
          <TextLink to="/forgot-password">
            Forgot your password?
          </TextLink>
        </p>
      </div>
    </dialog>
  );
}
