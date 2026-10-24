/** Where to go after signing in: "/" picks the right home for the account (HomeRedirect).
 * Only same-site paths are accepted (no open redirects). */
export const DEFAULT_SIGNED_IN_PATH = "/";

export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) {
    return DEFAULT_SIGNED_IN_PATH;
  }
  // Control characters could make browsers parse the value differently.
  for (const char of next) {
    const code = char.charCodeAt(0);
    if (code < 0x20 || code === 0x7f) return DEFAULT_SIGNED_IN_PATH;
  }
  // Belt and braces: whatever URL parsing makes of it must stay on this site.
  const base = "https://campussignal.invalid";
  const url = new URL(next, base);
  return url.origin === base ? url.pathname + url.search + url.hash : DEFAULT_SIGNED_IN_PATH;
}

export function signInPathFor(location: { pathname: string; search: string }): string {
  return `/sign-in?next=${encodeURIComponent(location.pathname + location.search)}`;
}

/** "Try again in 3 minutes." for a 429's Retry-After (Design.md §5, screen 1). */
export function retryAfterText(seconds: number | null): string {
  if (seconds === null || seconds <= 0) return "Try again later.";
  if (seconds < 60) return seconds === 1 ? "Try again in 1 second." : `Try again in ${seconds} seconds.`;
  const minutes = Math.ceil(seconds / 60);
  return minutes === 1 ? "Try again in 1 minute." : `Try again in ${minutes} minutes.`;
}
