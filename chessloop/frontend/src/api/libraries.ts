import { api } from "./client";
import type { Library } from "@/types";

export interface LibraryCreate {
  name: string;
  color: "white" | "black" | "both";
  description?: string;
  eco_code?: string;
  difficulty?: "beginner" | "intermediate" | "advanced";
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
};
