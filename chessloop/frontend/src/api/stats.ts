import { api } from "./client";
import type {
  HeatmapResponse,
  MasteryResponse,
  LeechEntry,
  RecentSession,
  AccuracyTrendResponse,
  TrendGranularity,
  TrendRange,
} from "@/types";

export const statsApi = {
  heatmap: () => api<HeatmapResponse>("/stats/heatmap"),
  mastery: () => api<MasteryResponse>("/stats/mastery"),
  leeches: () => api<LeechEntry[]>("/stats/leeches"),
  recentSessions: () => api<RecentSession[]>("/stats/recent-sessions"),
  accuracyTrend: (days: TrendRange, granularity: TrendGranularity) =>
    api<AccuracyTrendResponse>(
      `/stats/accuracy-trend?days=${days}&granularity=${granularity}`
    ),
};
