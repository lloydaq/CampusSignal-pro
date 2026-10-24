import type { Me } from "./api";

/** Where "/" leads a signed-in account (Design.md §4: navigation follows /me capabilities). */
export function landingPath(me: Me): string {
  if (me.capabilities.includes("campus")) return "/home";
  if (me.capabilities.includes("platform")) return "/account";
  return "/join";
}
