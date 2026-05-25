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
};
