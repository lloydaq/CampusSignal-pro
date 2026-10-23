import type { User } from "@/features/auth/api";

import { envelope, json } from "./http";

export const USER: User = {
  id: "8d6c1c55-6a66-4bd7-9b1b-6b8e1d1d0001",
  email: "aarav@northfield.example",
  display_name: "Aarav Nair",
  email_verified: true,
  platform_role: null,
};

export const signedOut = () => envelope(401, "not_authenticated", "Sign in to continue.");
export const signedIn = (user: Partial<User> = {}) => () => json({ user: { ...USER, ...user } });
