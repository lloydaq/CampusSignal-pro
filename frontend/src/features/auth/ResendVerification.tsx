import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Callout } from "@/components/Callout";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";

import { resendVerification } from "./api";
import { retryAfterText } from "./navigation";
import { sessionQueryKey } from "./session";

/** Pause between sends so the 3-per-hour limit (AUTH-003) isn't spent by double clicks. */
export const RESEND_COOLDOWN_SECONDS = 60;

/** Seconds left in a cooldown, ticking once a second, and a function to start one. */
function useCooldown(): [number, (seconds: number) => void] {
  const [clock, setClock] = useState<{ until: number; now: number } | null>(null);
  useEffect(() => {
    if (clock === null) return;
    const timer = window.setInterval(() => setClock((c) => (c ? { ...c, now: Date.now() } : c)), 1000);
    return () => window.clearInterval(timer);
  }, [clock?.until]); // eslint-disable-line react-hooks/exhaustive-deps -- restart only for a new cooldown
  const start = (seconds: number) => {
    const now = Date.now();
    setClock({ until: now + seconds * 1000, now });
  };
  const left = clock === null ? 0 : Math.max(0, Math.ceil((clock.until - clock.now) / 1000));
  return [left, start];
}

function waitLabel(seconds: number): string {
  return seconds > 60 ? `${Math.ceil(seconds / 60)} min` : `${seconds} s`;
}

/** "Send a new link" for a signed-in, unverified user, with the cooldown shown on the button. */
export function ResendVerification() {
  const queryClient = useQueryClient();
  const [secondsLeft, startCooldown] = useCooldown();

  const mutation = useMutation({
    mutationFn: resendVerification,
    onSuccess: () => startCooldown(RESEND_COOLDOWN_SECONDS),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 429) {
        startCooldown(error.retryAfterSeconds ?? RESEND_COOLDOWN_SECONDS);
      }
      if (error instanceof ApiError && error.code === "already_verified") {
        void queryClient.invalidateQueries({ queryKey: sessionQueryKey });
      }
    },
  });

  const waiting = secondsLeft > 0;
  const error = mutation.error;
  return (
    <div className="space-y-3">
      <Button variant="secondary" onClick={() => mutation.mutate()} disabled={mutation.isPending || waiting}>
        {mutation.isPending ? "Sending…" : waiting ? `Send again in ${waitLabel(secondsLeft)}` : "Send a new link"}
      </Button>
      {mutation.isSuccess && <Callout tone="success">We've sent a new verification link. It works for 24 hours.</Callout>}
      {error && (
        <Callout tone="danger">
          {error instanceof ApiError && error.status === 429 ? `You've asked for several links recently. ${retryAfterText(error.retryAfterSeconds)}` : error.message}
        </Callout>
      )}
    </div>
  );
}
