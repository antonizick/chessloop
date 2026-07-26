export interface User {
  id: string;
  email: string;
  username: string;
  role: "user" | "admin";
  mfa_enabled: boolean;
  theme: string;
  piece_set: string;
  board_theme: string;
  sounds_on: boolean;
  tts_enabled: boolean;
  tts_voice: string;
  boost_visibility: boolean;
  created_at: string;
  last_login: string | null;
}

export interface Library {
  id: string;
  name: string;
  color: "white" | "black" | "both";
  owner_user_id: string;
  is_active: boolean;
  is_public: boolean;
  forked_from_id: string | null;
  published_at: string | null;
  description: string | null;
  eco_code: string | null;
  difficulty: "beginner" | "intermediate" | "advanced" | null;
  created_at: string;
  updated_at: string;
}

export interface LineMove {
  san: string;
  uci: string;
  fen_after: string;
  note?: string;
}

export interface Line {
  id: string;
  library_id: string;
  name: string | null;
  starting_fen: string;
  moves: LineMove[];
  order_index: number;
  is_learned: boolean;
  created_at: string;
  updated_at: string;
}

// ── My Games ───────────────────────────────────────────────────────────────

export type GameColor = "white" | "black";
export type GameResult = "win" | "loss" | "draw";

export interface Game {
  id: string;
  owner_user_id: string;
  name: string;
  played_date: string | null;
  played_color: GameColor;
  opponent_level: number | null;
  result: GameResult;
  what_happened: string | null;
  lesson_learned: string | null;
  repeat_offense: boolean;
  starting_fen: string;
  moves: LineMove[];
  created_at: string;
  updated_at: string;
}

// ── Practice ─────────────────────────────────────────────────────────────────

export type PracticeMode = "weakest" | "leech_drill" | "selected";

export interface SessionStartResponse {
  id: string;
  mode: PracticeMode;
  scope: Record<string, unknown>;
  started_at: string;
  seeded_positions: number;
}

export interface PrecedingMove {
  san: string;
  uci: string;
  fen_after: string;
  note?: string;
}

export interface NextPositionResponse {
  done: false;
  practice_position_id: string;
  line_id: string;
  line_name: string | null;
  library_id: string;
  library_name: string;
  library_color: string;
  move_index: number;
  starting_fen: string;
  fen_before: string;
  turn_color: "white" | "black";
  preceding_moves: PrecedingMove[];
  /** Full mainline from move_index to end. [0] = user's challenge move,
   *  [1] = computer reply, [2] = user's next move, … */
  remaining_moves: PrecedingMove[];
  is_new: boolean;
  is_leech: boolean;
  repetitions: number;
  ease_factor: number;
}

export interface SessionDoneResponse {
  done: true;
  stats: { correct: number; wrong: number; positions_seen: number };
}

export interface SrsState {
  ease_factor: number;
  interval_days: number;
  due_at: string;
  repetitions: number;
  leech_count: number;
  is_leech: boolean;
}

export interface AnswerRequest {
  practice_position_id: string;
  move_uci: string;
  ease?: "easy" | "hard" | null;
  response_ms?: number;
  /** Full-line practice: overrides the server-side UCI check when present. */
  line_correct?: boolean | null;
}

export interface AnswerResponse {
  correct: boolean;
  expected_san: string;
  expected_uci: string;
  fen_after: string;
  note?: string;
  srs: SrsState;
}

export interface SessionStats {
  correct: number;
  wrong: number;
  positions_seen: number;
}

export interface SessionEndResponse {
  id: string;
  ended_at: string;
  stats: SessionStats;
}

export interface DueCountResponse {
  count: number;
  new: number;
  leeches: number;
}

// ── Stats ─────────────────────────────────────────────────────────────────────

export interface HeatmapBucket {
  move_number: number;
  total: number;
  correct: number;
  accuracy: number; // 0.0 – 1.0
}

export interface HeatmapResponse {
  by_move_number: HeatmapBucket[];
}

export type MasteryBadge =
  | "not_started"
  | "learning"
  | "developing"
  | "advanced"
  | "mastered";

export interface MasteryEntry {
  library_id: string;
  library_name: string;
  color: "white" | "black" | "both";
  total_positions: number;
  mastered_positions: number;
  mastery_pct: number;
  badge: MasteryBadge;
}

export interface MasteryResponse {
  libraries: MasteryEntry[];
}

export interface LeechEntry {
  practice_position_id: string;
  line_id: string;
  line_name: string | null;
  library_id: string;
  library_name: string;
  move_index: number;
  leech_count: number;
  ease_factor: number;
}

export interface RecentSession {
  id: string;
  mode: string;
  started_at: string;
  ended_at: string | null;
  correct: number;
  wrong: number;
  positions_seen: number;
}

// ── Accuracy trend ────────────────────────────────────────────────────────────

export interface TrendPoint {
  date: string;
  total: number;
  correct: number;
  accuracy: number;
}

export interface LibraryTrendSeries {
  library_id: string;
  library_name: string;
  points: TrendPoint[];
}

export interface AccuracyTrendResponse {
  series: LibraryTrendSeries[];
  date_labels: string[];
  granularity: "daily" | "weekly";
  days: number;
}

export type TrendGranularity = "daily" | "weekly";
export type TrendRange = 30 | 90 | 0;

// ── Public ────────────────────────────────────────────────────────────────────

export interface PublicLibraryEntry {
  id: string;
  name: string;
  color: "white" | "black" | "both";
  description: string | null;
  eco_code: string | null;
  difficulty: "beginner" | "intermediate" | "advanced" | null;
  owner_username: string;
  published_at: string;
  star_count: number;
  line_count: number;
  forked_from_id: string | null;
  video_links: VideoLink[];
}

export interface CommentEntry {
  id: string;
  username: string;
  content: string;
  created_at: string;
}

export interface VideoLink {
  id: string;
  library_id: string;
  title: string;
  url: string;
  created_at: string;
}

export interface PublicLibraryDetail extends PublicLibraryEntry {
  user_has_starred: boolean;
  comments: CommentEntry[];
  video_links: VideoLink[];
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export interface MfaChallengeResponse {
  mfa_required: true;
  challenge_token: string;
}

export type LoginResponse = TokenResponse | MfaChallengeResponse;
