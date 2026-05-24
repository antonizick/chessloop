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
  created_at: string;
  updated_at: string;
}

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
