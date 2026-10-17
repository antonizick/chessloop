import { api } from "./client";
import type { LoginResponse, TokenResponse, User } from "@/types";

/** Public, secret-free server facts for the sign-in and registration pages. */
export interface AuthConfig {
  registration_open: boolean;
  email_verification: boolean;
  smtp_configured: boolean;
  password_min_length: number;
}

export interface RegisterResult {
  email: string;
  message: string;
  next_step: "check_email" | "ask_admin" | "login";
}

export const authApi = {
  config: () => api<AuthConfig>("/auth/config", { auth: false }),

  register: (body: { email: string; username: string; password: string }) =>
    api<RegisterResult>("/auth/register", { method: "POST", body: JSON.stringify(body), auth: false }),

  changePassword: (body: { current_password: string; new_password: string }) =>
    api<TokenResponse>("/auth/change-password", { method: "POST", body: JSON.stringify(body) }),

  verifyEmail: (token: string) =>
    api<TokenResponse>("/auth/verify-email", { method: "POST", body: JSON.stringify({ token }), auth: false }),

  resendVerification: (email: string) =>
    api<void>("/auth/resend-verification", { method: "POST", body: JSON.stringify({ email }), auth: false }),

  forgotPassword: (email: string) =>
    api<void>("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }), auth: false }),

  resetPassword: (body: { token: string; new_password: string; disable_mfa?: boolean }) =>
    api<TokenResponse>("/auth/reset-password", { method: "POST", body: JSON.stringify(body), auth: false }),

  validateResetToken: (token: string) =>
    api<void>(`/auth/reset-password/validate?token=${encodeURIComponent(token)}`, { auth: false }),

  login: (body: { email: string; password: string }) =>
    api<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify(body), auth: false }),

  loginMfa: (body: { challenge_token: string; totp_code: string }) =>
    api<TokenResponse>("/auth/login/mfa", { method: "POST", body: JSON.stringify(body), auth: false }),

  me: () => api<User>("/auth/me"),

  mfaSetup: () => api<{ secret: string; otpauth_url: string; qr_code_b64: string }>("/auth/mfa/setup", { method: "POST" }),

  mfaConfirm: (totp_code: string) =>
    api<void>("/auth/mfa/confirm", { method: "POST", body: JSON.stringify({ totp_code }) }),

  mfaDisable: (totp_code: string) =>
    api<void>("/auth/mfa", { method: "DELETE", body: JSON.stringify({ totp_code }) }),

  updatePreferences: (body: { theme?: string; piece_set?: string; board_theme?: string; sounds_on?: boolean; tts_enabled?: boolean; tts_voice?: string; boost_visibility?: boolean; show_new_user_popup?: boolean }) =>
    api<User>("/auth/preferences", { method: "PATCH", body: JSON.stringify(body) }),

  getNewUserPopup: () =>
    api<{ html_content: string } | null>("/new-user-popup"),
};
