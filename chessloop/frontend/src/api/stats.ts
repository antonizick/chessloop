import { api } from "./client";
import type {
  HeatmapResponse,
  MasteryResponse,
  LeechEntry,
  RecentSession,
} from "@/types";

export const statsApi = {
  heatmap: () => api<HeatmapResponse>("/stats/heatmap"),
  mastery: () => api<MasteryResponse>("/stats/mastery"),
  leeches: () => api<LeechEntry[]>("/stats/leeches"),
  recentSessions: () => api<RecentSession[]>("/stats/recent-sessions"),
};
