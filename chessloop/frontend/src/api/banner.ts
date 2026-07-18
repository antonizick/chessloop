import { api } from "@/api/client";

export const bannerApi = {
  get: () => api<{ html_content: string; version: number } | null>("/banner"),
  dismiss: () => api<void>("/banner/dismiss", { method: "POST" }),
};
