import { api } from "./client";
import type { PublicLibraryEntry, PublicLibraryDetail, CommentEntry } from "@/types";

export interface BrowseParams {
  q?: string;
  eco?: string;
  color?: string;
  difficulty?: string;
  sort?: "stars" | "newest" | "name" | "lines";
}

function buildQuery(params: BrowseParams): string {
  const p = new URLSearchParams();
  if (params.q) p.set("q", params.q);
  if (params.eco) p.set("eco", params.eco);
  if (params.color) p.set("color", params.color);
  if (params.difficulty) p.set("difficulty", params.difficulty);
  if (params.sort) p.set("sort", params.sort);
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const publicApi = {
  browse: (params: BrowseParams = {}) =>
    api<PublicLibraryEntry[]>(`/public/libraries${buildQuery(params)}`),

  getLibrary: (id: string) =>
    api<PublicLibraryDetail>(`/public/libraries/${id}`),

  toggleStar: (id: string) =>
    api<void>(`/public/libraries/${id}/star`, { method: "POST" }),

  getComments: (id: string) =>
    api<CommentEntry[]>(`/public/libraries/${id}/comments`),

  addComment: (id: string, content: string) =>
    api<CommentEntry>(`/public/libraries/${id}/comments`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
};
