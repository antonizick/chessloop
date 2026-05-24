import { api } from "./client";
import type { Line, LineMove } from "@/types";

export const linesApi = {
  listForLibrary: (libId: string) => api<Line[]>(`/libraries/${libId}/lines`),
  create: (libId: string, body: { name?: string; starting_fen?: string }) =>
    api<Line>(`/libraries/${libId}/lines`, { method: "POST", body: JSON.stringify(body) }),
  get: (id: string) => api<Line>(`/lines/${id}`),
  update: (id: string, body: { name?: string }) =>
    api<Line>(`/lines/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  remove: (id: string) => api<void>(`/lines/${id}`, { method: "DELETE" }),
  appendMove: (id: string, move: LineMove) =>
    api<Line>(`/lines/${id}/moves`, { method: "POST", body: JSON.stringify(move) }),
  deleteMove: (id: string, index: number) =>
    api<Line>(`/lines/${id}/moves/${index}`, { method: "DELETE" }),
  updateMoveNote: (id: string, index: number, text: string) =>
    api<Line>(`/lines/${id}/moves/${index}/note`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
};
