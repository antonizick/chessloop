import { api } from "./client";
import type { LoginResponse, TokenResponse, User } from "@/types";

export const authApi = {
  register: (body: { email: string; username: string; password: string }) =>
    api<User>("/auth/register", { method: "POST", body: JSON.stringify(body), auth: false }),

  login: (body: { email: string; password: string }) =>
    api<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify(body), auth: false }),

  loginMfa: (body: { challenge_token: string; totp_code: string }) =>
    api<TokenResponse>("/auth/login/mfa", { method: "POST", body: JSON.stringify(body), auth: false }),

  me: () => api<User>("/auth/me"),

  mfaSetup: () => api<{ secret: string; otpauth_url: string }>("/auth/mfa/setup", { method: "POST" }),

  mfaConfirm: (totp_code: string) =>
    api<void>("/auth/mfa/confirm", { method: "POST", body: JSON.stringify({ totp_code }) }),
};
