import { api } from "./client";
import type { Game, GameColor, GameResult, LineMove } from "@/types";

export interface GameCreate {
  name: string;
  played_date?: string | null;
  played_color: GameColor;
  opponent_level?: number | null;
  result: GameResult;
  what_happened?: string | null;
  lesson_learned?: string | null;
  repeat_offense: boolean;
  starting_fen?: string;
  moves: string[]; // ordered SANs parsed from the PGN
}

export type GameUpdate = Partial<Omit<GameCreate, "moves" | "starting_fen">>;

export const gamesApi = {
  list: () => api<Game[]>("/games"),
  get: (id: string) => api<Game>(`/games/${id}`),
  create: (body: GameCreate) =>
    api<Game>("/games", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: GameUpdate) =>
    api<Game>(`/games/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  remove: (id: string) => api<void>(`/games/${id}`, { method: "DELETE" }),
  replaceMoves: (id: string, body: { moves: string[]; starting_fen?: string }) =>
    api<Game>(`/games/${id}/moves`, { method: "PUT", body: JSON.stringify(body) }),
  appendMove: (id: string, move: LineMove) =>
    api<Game>(`/games/${id}/moves`, { method: "POST", body: JSON.stringify(move) }),
  deleteMove: (id: string, index: number) =>
    api<Game>(`/games/${id}/moves/${index}`, { method: "DELETE" }),
  updateMoveNote: (id: string, index: number, text: string) =>
    api<Game>(`/games/${id}/moves/${index}/note`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
};
