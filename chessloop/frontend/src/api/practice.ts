import { api } from "./client";
import type {
  PracticeMode,
  SessionStartResponse,
  NextPositionResponse,
  SessionDoneResponse,
  AnswerRequest,
  AnswerResponse,
  SessionEndResponse,
  DueCountResponse,
} from "@/types";

export const practiceApi = {
  start: (mode: PracticeMode, scope: Record<string, unknown> = {}, is_rated: boolean = true) =>
    api<SessionStartResponse>("/practice/session/start", {
      method: "POST",
      body: JSON.stringify({ mode, scope, is_rated }),
    }),

  next: (sid: string) =>
    api<NextPositionResponse | SessionDoneResponse>(`/practice/session/${sid}/next`),

  answer: (sid: string, body: AnswerRequest) =>
    api<AnswerResponse>(`/practice/session/${sid}/answer`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  end: (sid: string) =>
    api<SessionEndResponse>(`/practice/session/${sid}/end`, { method: "POST" }),

  dueCount: () => api<DueCountResponse>("/practice/due-count"),
};
