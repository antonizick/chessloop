import { api } from "./client";
import { useAuthStore } from "@/stores/auth";
import type { Library } from "@/types";

export interface LibraryCreate {
  name: string;
  color: "white" | "black" | "both";
  description?: string;
  eco_code?: string;
  difficulty?: "beginner" | "intermediate" | "advanced";
}

export interface LichessImportResult {
  library_name: string;
  eco_code: string;
  imported: number;
  skipped: number;
  errors: string[];
}

export interface ConflictResponse {
  line_a_name: string;
  line_b_name: string;
  move_number: number;
  next_move_a: string;
  next_move_b: string;
  position_fen: string;
}

export interface EvaluateConflictsResult {
  total_positions: number;
  conflicts_found: number;
  conflicts: ConflictResponse[];
}

export const librariesApi = {
  list: () => api<Library[]>("/libraries"),
  get: (id: string) => api<Library>(`/libraries/${id}`),
  create: (body: LibraryCreate) =>
    api<Library>("/libraries", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<LibraryCreate>) =>
    api<Library>(`/libraries/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  remove: (id: string) => api<void>(`/libraries/${id}`, { method: "DELETE" }),
  setActive: (id: string, is_active: boolean) =>
    api<Library>(`/libraries/${id}/active`, {
      method: "PATCH",
      body: JSON.stringify({ is_active }),
    }),
  publish: (id: string) => api<Library>(`/libraries/${id}/publish`, { method: "POST" }),
  fork: (id: string) => api<Library>(`/libraries/${id}/fork`, { method: "POST" }),
  exportPgn: async (id: string) => {
    const token = useAuthStore.getState().accessToken;
    const headers = new Headers();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    const response = await fetch(`/api/libraries/${id}/export/pgn`, {
      method: "GET",
      headers,
    });
    if (!response.ok) throw new Error(`Failed to export library`);
    return response.blob();
  },

  importFromLichess: (id: string) =>
    api<LichessImportResult>(`/libraries/${id}/import-from-lichess`, { method: "POST" }),

  evaluateConflicts: (id: string) =>
    api<EvaluateConflictsResult>(`/libraries/${id}/conflicts`, { method: "GET" }),
};
