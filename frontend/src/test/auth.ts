import type { Me, Membership, User } from "@/features/auth/api";

import { envelope, json } from "./http";

export const USER: User = {
  id: "8d6c1c55-6a66-4bd7-9b1b-6b8e1d1d0001",
  email: "aarav@northfield.example",
  display_name: "Aarav Nair",
  email_verified: true,
  platform_role: null,
};

export const NORTHFIELD_MEMBERSHIP: Membership = {
  id: "5b1c0d5e-0000-4000-8000-000000000001",
  kind: "STUDENT",
  status: "ACTIVE",
  college: {
    id: "c0000000-0000-4000-8000-000000000001",
    name: "Northfield Institute",
    slug: "northfield",
    timezone: "Asia/Kolkata",
    status: "ACTIVE",
    is_demo: true,
  },
  department: { id: "d0000000-0000-4000-8000-000000000001", code: "CSE", name: "Computer Science" },
};

/** /me for a signed-in account; by default a verified user with no college yet. */
export function meFor(user: Partial<User> = {}, extra: Partial<Me> = {}): Me {
  return { user: { ...USER, ...user }, membership: null, roles: [], capabilities: [], ...extra };
}

export const MEMBER: Partial<Me> = { membership: NORTHFIELD_MEMBERSHIP, capabilities: ["campus"] };

export const signedOut = () => envelope(401, "not_authenticated", "Sign in to continue.");
export const signedIn =
  (user: Partial<User> = {}, extra: Partial<Me> = {}) =>
  () =>
    json(meFor(user, extra));
