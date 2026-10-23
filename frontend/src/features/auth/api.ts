import { apiGet, apiPost } from "@/lib/api";

/** Auth endpoints (backend app/api/v1/auth.py, me.py; architecture.md §11.1). */

const AUTH = "/api/v1/auth";

export interface User {
  id: string;
  email: string;
  display_name: string;
  email_verified: boolean;
  platform_role: string | null;
}

interface Message {
  message: string;
}

export const fetchMe = (signal?: AbortSignal) => apiGet<{ user: User }>("/api/v1/me", signal);

export const signIn = (body: { email: string; password: string }) =>
  apiPost<{ user: User; csrf_token: string }>(`${AUTH}/login`, body);

export const register = (body: { email: string; password: string; display_name: string }) =>
  apiPost<Message>(`${AUTH}/register`, body);

export const verifyEmail = (token: string) => apiPost<Message>(`${AUTH}/verify-email`, { token });

export const resendVerification = () => apiPost<Message>(`${AUTH}/resend-verification`);

export const requestPasswordReset = (body: { email: string }) => apiPost<Message>(`${AUTH}/password-reset/request`, body);

export const confirmPasswordReset = (body: { token: string; new_password: string }) =>
  apiPost<Message>(`${AUTH}/password-reset/confirm`, body);

export const changePassword = (body: { current_password: string; new_password: string }) =>
  apiPost<{ csrf_token: string }>("/api/v1/me/password", body);

export const signOut = () => apiPost<void>(`${AUTH}/logout`);

export const signOutEverywhere = () => apiPost<void>(`${AUTH}/logout-all`);
