import { api } from "@/api/client";

export interface OpeningSearchResult {
  eco: string;
  name: string;
  color: string;
  difficulty: string;
  description: string;
  moves: string[];
  available_variations: number;
}

export interface SeedOpeningsResponse {
  seeded: number;
  skipped: number;
  errors: string[];
}

export interface ImportOpeningRequest {
  eco: string;
  name: string;
  color: string;
  difficulty: string;
  description: string;
  moves: string[];
  publish?: boolean;
  variations_to_import?: number;
}

export interface ImportOpeningResponse {
  id: string;
  name: string;
  status: "created" | "exists";
}

export interface PullVariationsResponse {
  opening_name: string;
  added: number;
  message: string;
}

export interface DeleteOpeningResponse {
  deleted: boolean;
  message: string;
}

export interface LichessImportResponse {
  library_name: string;
  eco_code: string;
  imported: number;
  skipped: number;
  errors: string[];
}

export interface ActivityLogEntry {
  id: string;
  user_id: string | null;
  username: string;
  action: string;
  target: string | null;
  detail: string | null;
  timestamp: string;
}

export interface LogLines {
  lines: string[];
}

export interface NewUserPopupContent {
  html_content: string;
  is_enabled: boolean;
}

export interface BannerContent {
  html_content: string;
  is_enabled: boolean;
}

export interface SystemSettingsContent {
  enforce_email_verification: boolean;
}

export const adminApi = {
  searchOpenings: (q: string) =>
    api<OpeningSearchResult[]>(`/admin/openings/search?q=${encodeURIComponent(q)}`),

  seedOpenings: () =>
    api<SeedOpeningsResponse>("/admin/openings/seed", { method: "POST" }),

  importOpening: (body: ImportOpeningRequest) =>
    api<ImportOpeningResponse>("/admin/openings/import", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  pullVariations: (library_id: string, count = 5) =>
    api<PullVariationsResponse>("/admin/openings/pull-variations", {
      method: "POST",
      body: JSON.stringify({ library_id, count }),
    }),

  deleteOpening: (name: string) =>
    api<DeleteOpeningResponse>(`/admin/openings/delete?name=${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  importLichessLines: (library_id: string) =>
    api<LichessImportResponse>("/admin/openings/import-lichess-lines", {
      method: "POST",
      body: JSON.stringify({ library_id }),
    }),

  getActivityLogs: (limit = 200) =>
    api<ActivityLogEntry[]>(`/admin/logs/activity?limit=${limit}`),

  getBackendLogs: (lines = 300) =>
    api<LogLines>(`/admin/logs/backend?lines=${lines}`),

  getFrontendLogs: (lines = 300) =>
    api<LogLines>(`/admin/logs/frontend?lines=${lines}`),

  getNewUserPopup: () => api<NewUserPopupContent>("/admin/new-user-popup"),
  updateNewUserPopup: (body: NewUserPopupContent) =>
    api<NewUserPopupContent>("/admin/new-user-popup", { method: "PUT", body: JSON.stringify(body) }),

  getBanner: () => api<BannerContent>("/admin/banner"),
  updateBanner: (body: BannerContent) =>
    api<BannerContent>("/admin/banner", { method: "PUT", body: JSON.stringify(body) }),

  getSystemSettings: () => api<SystemSettingsContent>("/admin/system-settings"),
  updateSystemSettings: (body: SystemSettingsContent) =>
    api<SystemSettingsContent>("/admin/system-settings", { method: "PUT", body: JSON.stringify(body) }),
};
